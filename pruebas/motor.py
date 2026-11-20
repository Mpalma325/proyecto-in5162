"""
El motor que ejecuta los trabajos en la nube, sin red.

El sitio web (Cloudflare) se reemplaza por un diccionario en memoria: los
archivos que estarían en R2 y los trabajos que estarían en D1. Así se prueba el
ciclo completo —bajar el semestre, correr el script, informar la salida, subir
lo que cambió— sin levantar nada.

Lo que más importa verificar es lo que protege al curso:
- todo trabajo es de prueba salvo que se pida lo contrario de forma explícita;
- el motor nunca toca la carpeta semestres/ real;
- un trabajo que ya empezó no se vuelve a ejecutar si la cola lo entrega dos
  veces, porque podría mandar correos repetidos.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo

from motor import trabajo


class SitioFalso:
    """Lo que el motor ve del Worker: archivos del semestre y trabajos."""

    def __init__(self, archivos: dict[str, bytes], trabajos: dict[str, dict]):
        self.archivos = archivos
        self.trabajos = trabajos
        self.subidos: dict[str, bytes] = {}
        self.origenes: dict[str, str] = {}
        self.paneles: list = []
        self.parametros: dict[str, str] = {}

    # Como R2: el etag cambia con el contenido.
    @staticmethod
    def _etag(datos):
        import hashlib
        return hashlib.md5(datos).hexdigest()

    def listar_archivos(self, semestre):
        return [{"ruta": r, "bytes": len(d), "etag": self._etag(d)} for r, d in self.archivos.items()]

    def bajar_archivo(self, semestre, ruta):
        return self.archivos[ruta]

    def subir_archivo(self, semestre, ruta, datos, origen="motor", etag=None):
        # Igual que el Worker: con etag, solo si nadie lo cambió; sin etag, solo si es nuevo.
        actual = self.archivos.get(ruta)
        if (etag and (actual is None or self._etag(actual) != etag)) or (not etag and actual is not None):
            raise RuntimeError(f"PUT {ruta}: 409 b'cambió en la nube'")
        self.origenes[ruta] = origen
        self.subidos[ruta] = datos
        self.archivos[ruta] = datos

    def ver_trabajo(self, id_trabajo):
        return dict(self.trabajos[id_trabajo])

    caido = False  # simula que el sitio no responde a los avisos de avance

    def informar(self, id_trabajo, salida="", estado=None, codigo=None):
        t = self.trabajos[id_trabajo]
        if self.caido and not estado:
            raise RuntimeError("POST motor/trabajos: sin respuesta del sitio")
        # Igual que el Worker: solo pasa a "corriendo" desde "pendiente".
        if estado == "corriendo" and t.get("estado") != "pendiente":
            raise RuntimeError(f"POST motor/trabajos/{id_trabajo}: 409 b'ya lo tomo otro'")
        t["salida"] = t.get("salida", "") + salida
        if estado:
            t["estado"] = estado
        if codigo is not None:
            t["codigo"] = codigo

    def subir_panel(self, semestre, filas):
        self.paneles.append(filas)

    def leer_parametros(self):
        return dict(self.parametros)


def usar(sitio_falso):
    for nombre in ("listar_archivos", "bajar_archivo", "subir_archivo", "ver_trabajo",
                   "informar", "subir_panel", "leer_parametros"):
        setattr(trabajo.sitio, nombre, getattr(sitio_falso, nombre))


# Un semestre mínimo: lo justo para que el panel se pueda calcular.
SEMESTRE = {
    "alumnos.csv": "Nombre,Correo,Grupo\nAna Pérez,ana@x.cl,control\n".encode(),
    "notas.csv": b"Correo,Flujo,Item,Enviado,Respondio,Nota,Originalidad\n"
                 b"ana@x.cl,test,1,SI,SI,\"6,0\",Media\n",
    "log_envios.csv": b"",
    "tests_semanales/data/preguntas.csv": b"Semana,Tema\n1,Prueba\n",
    "tareas/data/entregas/T1/grupo.html": b"<html>pesado</html>",
    "analisis.xlsx": b"no lo necesita ningun trabajo",
}

titulo("1. los comandos se arman acá, no en la página")
_, armar = trabajo.FLUJOS["tests.evaluar"]
check("sin decir nada, es modo prueba", armar({"semana": 4})[-1] == "--dry-run", armar({"semana": 4}))
check("prueba=True también", "--dry-run" in armar({"semana": 4, "prueba": True}))
check("solo prueba=False lo quita", "--dry-run" not in armar({"semana": 4, "prueba": False}))
check("un 'false' en texto NO cuenta como envío real",
      "--dry-run" in armar({"semana": 4, "prueba": "false"}))
# El id de una instancia va de 1 a 999 (semestres nuevos: `instancia`; los de
# antes: `semana`, que es el mismo id). Ya no hay tope de 52 semanas.
for malo in (0, 1000, -1, True, "04"):
    try:
        armar({"semana": malo})
        check(f"semana {malo!r} se rechaza", False)
    except ValueError:
        check(f"semana {malo!r} se rechaza", True)
try:
    armar({"semana": "4; rm -rf /"})
    check("una semana con comandos se rechaza", False)
except ValueError:
    check("una semana con comandos se rechaza", True)
check("instancia 53 y 999 se aceptan (no son semanas)",
      armar({"semana": 53})[-2] == "53" and armar({"instancia": 999})[-2] == "999", armar({"instancia": 999}))
check("instancia y semana dan el mismo comando", armar({"instancia": 4}) == armar({"semana": 4}))
try:
    armar({"instancia": "4; rm -rf /"})
    check("una instancia con comandos se rechaza", False)
except ValueError:
    check("una instancia con comandos se rechaza", True)
check("los demás flujos de tests también leen instancia",
      all("12" in trabajo.FLUJOS[f][1]({"instancia": 12}) for f in ("tests.enviar", "tests.resumen", "tests.chequeo")))
check("el chequeo nunca envía: no tiene modo real", "--dry-run" not in " ".join(
    trabajo.FLUJOS["tests.chequeo"][1]({"semana": 4, "prueba": False})) and
    "enviar" not in trabajo.FLUJOS["tests.chequeo"][1]({"semana": 4})[1])

titulo("1b. los flujos de tareas")
_, corregir = trabajo.FLUJOS["tareas.corregir"]
check("corregir: sin decir nada, es modo prueba", corregir({"tarea": "T1"})[-1] == "--dry-run")
check("corregir: 'no enviar' solo cuenta en modo real",
      "--no-enviar" not in corregir({"tarea": "T1", "no_enviar": True}) and
      "--no-enviar" in corregir({"tarea": "T1", "no_enviar": True, "prueba": False}))
check("enviar tareas: modo prueba por defecto",
      "--dry-run" in trabajo.FLUJOS["tareas.enviar"][1]({"tarea": "T2"}))
_, enviar_t = trabajo.FLUJOS["tareas.enviar"]
cmd = enviar_t({"tarea": "T2", "prueba": False, "minutos": 25, "a_las": "2026-11-13T13:00:00.000Z"})
check("enviar tareas: los minutos y la hora programada llegan al script",
      cmd[-4:] == ["--minutos", "25", "--desde", "2026-11-13T13:00:00.000Z"] and "--dry-run" not in cmd, cmd)
check("enviar tareas: sin minutos ni hora, el script usa los suyos",
      "--minutos" not in enviar_t({"tarea": "T2"}) and "--desde" not in enviar_t({"tarea": "T2"}))
for malo in ({"minutos": 0}, {"minutos": 5000}, {"minutos": "20; rm"}, {"a_las": "mañana"}):
    try:
        enviar_t({"tarea": "T2", **malo})
        check(f"enviar tareas: {malo} se rechaza", False)
    except ValueError:
        check(f"enviar tareas: {malo} se rechaza", True)
_, mandar = trabajo.FLUJOS["tareas.feedback"]
check("mandar correcciones: modo prueba por defecto, y solo a los elegidos",
      mandar({"tarea": "T2"})[-1] == "--dry-run"
      and "--dry-run" not in mandar({"tarea": "T2", "prueba": False, "solo": ["a@x.cl"]})
      and "--solo" in mandar({"tarea": "T2", "prueba": False, "solo": ["a@x.cl"]}))
for malo in ("T", "t1", "T123", "T1; rm", ""):
    try:
        corregir({"tarea": malo})
        check(f"tarea {malo!r} se rechaza", False)
    except ValueError:
        check(f"tarea {malo!r} se rechaza", True)
_, generar = trabajo.FLUJOS["tareas.generar"]
cmd = generar({"tarea": "T1", "archivos": ["Grupo 1.html"], "_semestre": "2026-2"})
check("generar recibe las rutas dentro de la carpeta de trabajo",
      cmd[-1] == "semestres/2026-2/tareas/data/entregas/T1/Grupo 1.html" and "--no-interactivo" in cmd, cmd)
for malo in (["../../alumnos.csv"], ["a/b.html"], ["x.csv"], "Grupo.html"):
    try:
        generar({"tarea": "T1", "archivos": malo, "_semestre": "2026-2"})
        check(f"entrega {malo!r} se rechaza", False)
    except ValueError:
        check(f"entrega {malo!r} se rechaza", True)

titulo("1e. ajuste manual de nota")
_, ajuste = trabajo.FLUJOS["datos.ajustar"]
cmd = ajuste({"flujo": "test", "item": "3", "correo": "ana@x.cl", "nota": "6,5",
              "motivo": "castigó la firma", "_pedido_por": "profe@x.cl", "por": "otro@x.cl"})
check("quién ajusta lo pone el sitio, no la página", cmd[-1] == "profe@x.cl", cmd)
check("el motivo va como un solo argumento", "castigó la firma" in cmd)
check("el motivo es opcional", ajuste({"flujo": "test", "item": "3", "correo": "ana@x.cl", "nota": "6,5",
                                     "_pedido_por": "profe@x.cl"})[-3] == "")
for malo in ({"flujo": "test", "item": "3", "correo": "ana@x.cl", "nota": "6,5", "motivo": "x" * 501},
             {"flujo": "test", "item": "T1", "correo": "ana@x.cl", "nota": "6,5", "motivo": "motivo ok"},
             {"flujo": "test", "item": "3", "correo": "no-es-correo", "nota": "6,5", "motivo": "motivo ok"},
             {"flujo": "test", "item": "3", "correo": "ana@x.cl", "nota": "6,5; rm", "motivo": "motivo ok"}):
    try:
        ajuste(malo)
        check(f"ajuste rechaza {str(malo)[:50]}", False)
    except ValueError:
        check(f"ajuste rechaza {str(malo)[:50]}", True)

titulo("1d. segunda oportunidad")
_, segunda = trabajo.FLUJOS["tareas.segunda"]
check("preparar genera preguntas (no manda correos)",
      segunda({"tarea": "T2", "paso": "preparar"})[-2:] == ["preparar", "T2"])
check("enviar sin decir nada solo arma los borradores",
      segunda({"tarea": "T2", "paso": "enviar"})[-2:] == ["borradores", "T2"])
check("enviar con prueba=False manda, con --confirmar",
      segunda({"tarea": "T2", "paso": "enviar", "prueba": False})[-3:] == ["enviar", "T2", "--confirmar"])
check("un 'false' en texto NO manda",
      "--confirmar" not in segunda({"tarea": "T2", "paso": "enviar", "prueba": "false"}))
for malo in ({"tarea": "T2"}, {"tarea": "T2", "paso": "borrar"}, {"tarea": "x", "paso": "preparar"}):
    try:
        segunda(malo)
        check(f"segunda rechaza {malo}", False)
    except ValueError:
        check(f"segunda rechaza {malo}", True)

titulo("1c. evaluar o corregir solo a los elegidos")
_, evaluar_ = trabajo.FLUJOS["tests.evaluar"]
cmd = evaluar_({"semana": 7, "prueba": False, "solo": ["Ana.Mora@x.cl"]})
check("pasa la lista en minúscula", cmd[-2:] == ["--solo", "ana.mora@x.cl"], cmd)
check("sin 'solo' se procesa todo, como siempre", "--solo" not in evaluar_({"semana": 7}))
check("corregir tareas también acepta 'solo'",
      "--solo" in trabajo.FLUJOS["tareas.corregir"][1]({"tarea": "T1", "solo": ["a@b.cl"]}))
cmd = trabajo.FLUJOS["tareas.recolectar"][1]({"tarea": "T1", "prueba": False, "solo": ["Hugo.Vera@x.cl"]})
check("recolectar también acepta 'solo' (envío programado a un grupo)",
      cmd[-2:] == ["--solo", "hugo.vera@x.cl"], cmd)
check("recolectar sin 'solo' busca a todos, como siempre",
      "--solo" not in trabajo.FLUJOS["tareas.recolectar"][1]({"tarea": "T1"}))
cmd = trabajo.FLUJOS["tareas.corregir"][1]({"tarea": "T1", "prueba": False, "solo": ["a@b.cl"], "sin_tarde": True})
check("corregir con 'sin_tarde' sigue dejando fuera lo que llegó tarde", "--sin-tarde" in cmd, cmd)
check("sin 'sin_tarde' no se agrega",
      "--sin-tarde" not in trabajo.FLUJOS["tareas.corregir"][1]({"tarea": "T1", "solo": ["a@b.cl"]}))
for malo in ([], "a@b.cl", ["no-es-correo"], ["a@b.cl,c@d.cl"], ["a@b.cl --dry-run"]):
    try:
        evaluar_({"semana": 7, "solo": malo})
        check(f"'solo' = {malo!r} se rechaza", False)
    except ValueError:
        check(f"'solo' = {malo!r} se rechaza", True)

_, experimento = trabajo.FLUJOS["tests.experimento"]
cmd = experimento({"prompt": "Evalúa {{PREGUNTAS}}", "n": 5})
check("experimento: por defecto solo muestra la muestra (no llama al modelo)", cmd[-1] == "--dry-run", cmd[3:])
check("experimento: el prompt va como argumento, no como código", cmd[2] == "Evalúa {{PREGUNTAS}}")
for malo in ({"prompt": ""}, {"prompt": "x" * 30001}, {"prompt": "x", "n": 301}, {"prompt": "x", "semana": 1000}):
    try:
        experimento(malo)
        check(f"experimento rechaza {str(malo)[:40]}", False)
    except ValueError:
        check(f"experimento rechaza {str(malo)[:40]}", True)

titulo("2. cada trabajo baja solo lo que necesita")
check("tests baja las tablas", trabajo._en_perfil("tests", "notas.csv"))
check("tests baja sus prompts", trabajo._en_perfil("tests", "tests_semanales/prompts/x.md"))
check("tests NO baja las entregas de tareas",
      not trabajo._en_perfil("tests", "tareas/data/entregas/T1/grupo.html"))
check("tareas baja sus entregas", trabajo._en_perfil("tareas", "tareas/data/entregas/T1/grupo.html"))
check("nadie baja planillas de análisis", not trabajo._en_perfil("tests", "analisis.xlsx"))

titulo("3. un trabajo de punta a punta, con un script de mentira")
# Se registra un flujo de prueba que imprime y escribe un archivo nuevo, para no
# depender del buzón ni de OpenAI.
trabajo.FLUJOS["prueba.eco"] = ("tests", lambda a: [
    "-c",
    "import os, pathlib; print('✓ hola desde el motor'); "
    "d = pathlib.Path('semestres', os.environ['IN5162_SEMESTRE'], 'tests_semanales', 'data'); "
    "(d / 'resumen_semana_1.txt').write_text('resumen', encoding='utf-8'); "
    "print('semestre', os.environ['IN5162_SEMESTRE'])",
])
real = Path("semestres")
antes = {p: p.stat().st_mtime for p in real.rglob("*") if p.is_file()} if real.exists() else {}

sitio = SitioFalso(dict(SEMESTRE), {"t1": {"estado": "pendiente", "semestre": "zz-prueba",
                                           "flujo": "prueba.eco", "argumentos": {}}})
usar(sitio)
trabajo.ejecutar("t1")
t = sitio.trabajos["t1"]
check("terminó bien", t["estado"] == "terminado" and t["codigo"] == 0, t)
check("la salida llegó al sitio", "hola desde el motor" in t["salida"], t["salida"][:200])
check("corrió con el semestre del trabajo", "semestre zz-prueba" in t["salida"])
check("bajó solo lo del perfil (4 de 6 archivos)", "bajados 4 archivos" in t["salida"], t["salida"][:200])
check("subió el archivo nuevo", "tests_semanales/data/resumen_semana_1.txt" in sitio.subidos,
      list(sitio.subidos))
check("no volvió a subir lo que no cambió", "notas.csv" not in sitio.subidos)
check("cada archivo subido dice qué trabajo lo escribió (para el historial)",
      sitio.origenes.get("tests_semanales/data/resumen_semana_1.txt") == "trabajo t1", sitio.origenes)
check("recalculó la reportería", len(sitio.paneles) == 1 and sitio.paneles[0][0]["Correo"] == "ana@x.cl",
      sitio.paneles[:1])

titulo("4. no toca los datos reales ni deja basura")
despues = {p: p.stat().st_mtime for p in real.rglob("*") if p.is_file()} if real.exists() else {}
check("semestres/ real quedó igual", antes == despues)
import tempfile
restos = list(Path(tempfile.gettempdir()).glob("in5162-t1*"))
check("la carpeta de trabajo se borró", not restos, restos[:2])

titulo("5. un trabajo ya empezado no se repite")
sitio.trabajos["t1"]["salida"] = ""
trabajo.ejecutar("t1")
check("si la cola lo entrega dos veces, la segunda no hace nada",
      sitio.trabajos["t1"]["salida"] == "")

titulo("5b. un trabajo programado que llega antes de su hora vuelve a la cola")
from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: E402
from unittest import mock as _mk  # noqa: E402
from motor import cola as _cola  # noqa: E402
_hora = (_dt.now(_tz.utc) + _td(hours=1)).isoformat()
sitio.trabajos["t_prog"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "tests.resumen",
                            "argumentos": {"semana": 1, "a_las": _hora}}
with _mk.patch.object(_cola, "encolar") as _reencolar:
    trabajo.ejecutar("t_prog")
check("no corre antes de tiempo y se vuelve a encolar con su hora",
      sitio.trabajos["t_prog"]["estado"] == "pendiente" and not sitio.trabajos["t_prog"].get("salida")
      and _reencolar.call_args == _mk.call("t_prog"), (sitio.trabajos["t_prog"], _reencolar.call_args))

titulo("6. un error se informa, no se pierde")
trabajo.FLUJOS["prueba.falla"] = ("tests", lambda a: ["-c", "import sys; print('✗ algo salió mal'); sys.exit(3)"])
sitio.trabajos["t2"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "prueba.falla",
                        "argumentos": {}}
trabajo.ejecutar("t2")
check("queda fallido con el código del script",
      sitio.trabajos["t2"]["estado"] == "fallido" and sitio.trabajos["t2"]["codigo"] == 3,
      sitio.trabajos["t2"])
sitio.trabajos["t3"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "no.existe",
                        "argumentos": {}}
trabajo.ejecutar("t3")
check("un flujo desconocido queda fallido, sin ejecutar nada",
      sitio.trabajos["t3"]["estado"] == "fallido" and "desconocido" in sitio.trabajos["t3"]["salida"])

titulo("7. los parámetros de la página llegan al script, y solo esos")
trabajo.FLUJOS["prueba.entorno"] = ("tests", lambda a: [
    "-c", "import os; print('MODELO=' + os.environ.get('MODELO', '-')); "
          "print('OPENAI=' + os.environ.get('OPENAI_API_KEY', '-'))"])
sitio.parametros = {"MODELO": "gpt-prueba", "OPENAI_API_KEY": "robada"}
sitio.trabajos["t4"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "prueba.entorno",
                        "argumentos": {}}
os.environ.pop("OPENAI_API_KEY", None)
trabajo.ejecutar("t4")
salida = sitio.trabajos["t4"]["salida"]
check("el modelo elegido en la página llega", "MODELO=gpt-prueba" in salida, salida[-200:])
check("una clave colada en los parámetros no llega", "OPENAI=-" in salida, salida[-200:])
sitio.parametros = {}

titulo("7b. un trabajo de tareas que solo guarda lo suyo no recalcula la reportería")
trabajo.FLUJOS["prueba.tareas"] = ("tareas", lambda a: [
    "-c", "import os, pathlib; d = pathlib.Path('semestres', os.environ['IN5162_SEMESTRE'], 'tareas', 'cache');"
          "d.mkdir(parents=True, exist_ok=True); (d / 'x.json').write_text('{}')"])
sitio.paneles.clear()
sitio.trabajos["t6"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "prueba.tareas", "argumentos": {}}
trabajo.ejecutar("t6")
check("guarda su archivo", "tareas/cache/x.json" in sitio.subidos and sitio.trabajos["t6"]["estado"] == "terminado")
check("y no toca la reportería", sitio.paneles == [])

titulo("8. recalcular la reportería sin cambiar archivos")
sitio.paneles.clear()
sitio.trabajos["t5"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "datos.panel",
                        "argumentos": {}}
trabajo.ejecutar("t5")
check("datos.panel termina bien", sitio.trabajos["t5"]["estado"] == "terminado", sitio.trabajos["t5"])
check("y sube el panel aunque nada haya cambiado", len(sitio.paneles) == 1)

from unittest import mock  # noqa: E402

ESCRIBE = ("import os, pathlib, sys, time; "
           "d = pathlib.Path('semestres', os.environ['IN5162_SEMESTRE'], 'tests_semanales', 'data'); "
           "(d / 'hecho.txt').write_text('ya se mandaron los correos', encoding='utf-8'); "
           "print('✓ correos enviados'); ")


def correr(id_, flujo, codigo_extra="", **estado):
    trabajo.FLUJOS[flujo] = ("tests", lambda a: ["-c", ESCRIBE + codigo_extra])
    sitio.trabajos[id_] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": flujo,
                           "argumentos": {}, **estado}
    sitio.archivos.pop("tests_semanales/data/hecho.txt", None)
    sitio.subidos.clear()
    with mock.patch.object(trabajo.time, "sleep", lambda s: None):
        trabajo.ejecutar(id_)
    return sitio.trabajos[id_]


titulo("9. si el sitio no responde a los avisos, lo hecho igual se guarda")
sitio.caido = True
t = correr("t7", "prueba.caido")
sitio.caido = False
check("el archivo que dejó el script llegó a la nube", "tests_semanales/data/hecho.txt" in sitio.subidos)
check("y el trabajo cerró como terminado", t["estado"] == "terminado", t.get("estado"))

titulo("10. si el script falla después de mandar correos, lo que hizo se guarda")
t = correr("t8", "prueba.falla_tarde", "sys.exit(3)")
check("el archivo se guardó igual", "tests_semanales/data/hecho.txt" in sitio.subidos)
check("y el trabajo queda fallido con su código", t["estado"] == "fallido" and t["codigo"] == 3, t)

titulo("11. no se pisa una versión que cambió en la nube mientras corría")
original = sitio.listar_archivos
sitio.listar_archivos = lambda sem: [dict(a, etag="version-vieja") if a["ruta"] == "notas.csv" else a
                                     for a in original(sem)]
usar(sitio)
t = correr("t9", "prueba.conflicto",
           "(d.parent.parent / 'notas.csv').write_text('Correo\\n', encoding='utf-8')")
sitio.listar_archivos = original
usar(sitio)
check("notas.csv no se sube (la nube tiene otra versión)", "notas.csv" not in sitio.subidos)
check("lo demás sí se guarda", "tests_semanales/data/hecho.txt" in sitio.subidos)
check("y el trabajo queda fallido, diciendo qué no guardó",
      t["estado"] == "fallido" and "No pude guardar notas.csv" in t["salida"], t["salida"][-300:])

titulo("12. si la cola lo entrega dos veces a la vez, corre una sola")
real_ver = sitio.ver_trabajo
sitio.ver_trabajo = lambda i: dict(real_ver(i), estado="pendiente")  # los dos lo ven pendiente
usar(sitio)
t = correr("t10", "prueba.doble", estado="corriendo")
sitio.ver_trabajo = real_ver
usar(sitio)
check("el segundo no ejecuta nada", "tests_semanales/data/hecho.txt" not in sitio.subidos and not t.get("salida"),
      t)

titulo("13. un trabajo que pasa del límite se corta, y lo hecho se guarda")
limite = trabajo.LIMITE_SEGUNDOS
trabajo.LIMITE_SEGUNDOS = 2
t = correr("t11", "prueba.eterno", "time.sleep(60)")
trabajo.LIMITE_SEGUNDOS = limite
check("se cortó y quedó fallido", t["estado"] == "fallido" and "pasó de" in t["salida"], t["salida"][-200:])
check("lo que alcanzó a escribir se guardó", "tests_semanales/data/hecho.txt" in sitio.subidos)

titulo("13b. detener a pedido: para entre un alumno y otro, y lo hecho se guarda")
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

vigilancia = trabajo.VIGILANCIA_SEGUNDOS
trabajo.VIGILANCIA_SEGUNDOS = 0.2
# Diez "alumnos" de medio segundo: cada uno se registra apenas sale su correo.
DIEZ = ("\nfrom modulos.progreso import avanzar\n"
        "for i in avanzar(range(10), 'correos'):\n"
        "    time.sleep(0.5); print(f'✓ correo {i}', flush=True)\n"
        "    with (d / 'registro.txt').open('a', encoding='utf-8') as f: f.write(f'{i}\\n')\n")
threading.Timer(1.2, lambda: sitio.trabajos["t11b"].update(estado="cancelando")).start()
t = correr("t11b", "prueba.detener", DIEZ)
registro = sitio.subidos.get("tests_semanales/data/registro.txt", b"").decode()
check("quedó cancelado", t["estado"] == "cancelado", t.get("estado"))
check("paró antes de terminar", 0 < registro.count("\n") < 10, registro)
check("cada correo que salió quedó registrado (cortó entre uno y otro)",
      len(re.findall(r"✓ correo \d", t["salida"])) == registro.count("\n"), (t["salida"][-400:], registro))
check("dice cuántos quedaron sin procesar", "Detenido a pedido: quedaron" in t["salida"], t["salida"][-300:])

trabajo.FLUJOS["tests.chequeo_lento"] = ("tests", lambda a: ["-c", "import time; print('leyendo', flush=True); time.sleep(60)"])
trabajo.CORTABLES.add("tests.chequeo_lento")
sitio.trabajos["t11c"] = {"estado": "pendiente", "semestre": "zz-prueba", "flujo": "tests.chequeo_lento",
                          "argumentos": {}}
threading.Timer(1.0, lambda: sitio.trabajos["t11c"].update(estado="cancelando")).start()
inicio = time.monotonic()
trabajo.ejecutar("t11c")
check("un flujo sin correos se corta en seco", time.monotonic() - inicio < 20
      and sitio.trabajos["t11c"]["estado"] == "cancelado", sitio.trabajos["t11c"].get("estado"))
trabajo.VIGILANCIA_SEGUNDOS = vigilancia

titulo("13c. cerca del límite: para entre alumnos antes del corte, guarda y queda fallido")
limite, aviso = trabajo.LIMITE_SEGUNDOS, trabajo.AVISO_ANTES_SEGUNDOS
# El aviso llega a los 2 s; el corte en seco sería a los 8 y los diez alumnos tardan 5.
trabajo.LIMITE_SEGUNDOS, trabajo.AVISO_ANTES_SEGUNDOS = 8, 6
sitio.archivos.pop("tests_semanales/data/registro.txt", None)  # el que dejó 13b
t = correr("t11d", "prueba.limite", DIEZ)
trabajo.LIMITE_SEGUNDOS, trabajo.AVISO_ANTES_SEGUNDOS = limite, aviso
registro = sitio.subidos.get("tests_semanales/data/registro.txt", b"").decode()
check("queda fallido, para que Inicio lo muestre", t["estado"] == "fallido", t.get("estado"))
check("avisa que se acerca el límite", "Se acerca el límite de 0 minutos" in t["salida"], t["salida"][-500:])
check("y dice que hay que volver a correrlo", "vuelve a correrlo para seguir con lo que falta" in t["salida"],
      t["salida"][-300:])
check("no llegó al corte en seco", "pasó de" not in t["salida"], t["salida"][-300:])
check("paró antes de terminar", 0 < registro.count("\n") < 10, registro)
check("cada correo que salió quedó registrado y subido",
      len(re.findall(r"✓ correo \d", t["salida"])) == registro.count("\n"), (t["salida"][-400:], registro))

sitio.archivos.pop("tests_semanales/data/registro.txt", None)
t = correr("t11e", "prueba.limite_holgado", DIEZ)
check("con tiempo de sobra, el mismo recorrido termina bien",
      t["estado"] == "terminado" and "Se acerca el límite" not in t["salida"], t.get("estado"))

titulo("14. si el aviso de inicio llegó pero se cortó la respuesta, el trabajo corre igual")
real_informar = sitio.informar


def informar_cortado(id_trabajo, salida="", estado=None, codigo=None):
    real_informar(id_trabajo, salida, estado, codigo)
    if estado == "corriendo":
        # el reintento choca con su propio cambio
        raise RuntimeError(f"POST motor/trabajos/{id_trabajo}: 409 b'El trabajo ya está corriendo.'")


sitio.informar = informar_cortado
usar(sitio)
t = correr("t12", "prueba.cortado")
sitio.informar = real_informar
usar(sitio)
check("no lo confunde con otro intento: corre y termina", t["estado"] == "terminado", t.get("estado"))
check("y guarda lo que hizo", "tests_semanales/data/hecho.txt" in sitio.subidos)

# Desde acá, las funciones de verdad de motor/sitio.py, con la red simulada.
import hashlib  # noqa: E402
import http.client  # noqa: E402
import importlib  # noqa: E402

sitio_real = importlib.reload(trabajo.sitio)
os.environ.setdefault("TOKEN_MOTOR", "prueba")


class _Respuesta:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.cuerpo


titulo("15. la conexión cortada sin respuesta se reintenta")
llamadas = []


def urlopen_que_corta(req, timeout=None):
    llamadas.append(req.get_method())
    if len(llamadas) == 1:
        raise http.client.RemoteDisconnected("Remote end closed connection without response")
    return _Respuesta(b'{"ok": true}')


with mock.patch.object(sitio_real.urllib.request, "urlopen", urlopen_que_corta), \
        mock.patch.object(sitio_real.time, "sleep", lambda s: None):
    sitio_real.informar("t13", salida="x")
check("reintentó y el aviso llegó", llamadas == ["POST", "POST"], llamadas)

titulo("16. una subida que llegó pero perdió la respuesta no se da por fallida")
guardado = b"Correo\nana@x.cl\n"


def pedir_409(*_, **__):
    raise RuntimeError("PUT motor/archivo/zz/notas.csv: 409 b'El archivo cambió en la nube'")


with mock.patch.object(sitio_real, "_pedir", pedir_409), \
        mock.patch.object(sitio_real, "listar_archivos",
                          lambda sem: [{"ruta": "notas.csv", "etag": f'"{hashlib.md5(guardado).hexdigest()}"'}]):
    try:
        sitio_real.subir_archivo("zz", "notas.csv", guardado, etag="vieja")
        check("si en la nube está justo lo que se subía, cuenta como guardado", True)
    except RuntimeError as e:
        check("si en la nube está justo lo que se subía, cuenta como guardado", False, e)
    try:
        sitio_real.subir_archivo("zz", "notas.csv", b"otra cosa", etag="vieja")
        check("si en la nube hay otra cosa, sigue siendo un conflicto", False)
    except RuntimeError:
        check("si en la nube hay otra cosa, sigue siendo un conflicto", True)

titulo("17. un trabajo programado espera en la cola hasta su hora")
import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from unittest import mock as _mock  # noqa: E402

from motor import cola  # noqa: E402

futuro = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
check("la hora programada se lee de los argumentos, en UTC",
      cola.hora_programada({"argumentos": {"a_las": futuro.isoformat().replace("+00:00", "Z")}}) == futuro)
check("sin hora, o con una que no se entiende, no se programa",
      cola.hora_programada({"argumentos": {}}) is None
      and cola.hora_programada({"argumentos": {"a_las": "mañana"}}) is None
      and cola.hora_programada({"argumentos": {"a_las": "2026-11-13T10:00"}}) is None)

pedidos_tareas = []


class _Respuesta:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


def _urlopen_tareas(req, timeout=None):
    pedidos_tareas.append(json.loads(req.data))
    return _Respuesta()


entorno = {"GCP_PROYECTO": "p", "GCP_REGION": "r", "GCP_COLA": "reales", "GCP_COLA_SIMULACIONES": "sims",
           "MOTOR_URL_PUBLICA": "https://motor", "TOKEN_WEB": "t"}
with _mock.patch.dict(os.environ, entorno), \
        _mock.patch.object(cola, "_token_google", return_value="tok"), \
        _mock.patch.object(cola.urllib.request, "urlopen", _urlopen_tareas):
    cola._cloudtasks("id1", {"prueba": 0, "argumentos": {"a_las": futuro.isoformat()}})
    cola._cloudtasks("id2", {"prueba": 1, "argumentos": {}})
    cola._cloudtasks("id3", {"prueba": 0, "argumentos": {"a_las": "2020-01-01T00:00:00Z"}})
check("Cloud Tasks lo despacha recién a esa hora",
      pedidos_tareas[0]["task"].get("scheduleTime") == futuro.strftime("%Y-%m-%dT%H:%M:%SZ"), pedidos_tareas[0])
check("sin hora, o con una que ya pasó, sale de inmediato",
      "scheduleTime" not in pedidos_tareas[1]["task"] and "scheduleTime" not in pedidos_tareas[2]["task"])

encolados = []
with _mock.patch.object(cola, "_pendientes") as _cola_local, \
        _mock.patch.object(cola.threading, "Timer") as _timer:
    _cola_local.put.side_effect = encolados.append
    cola._local("ya", None)
    cola._local("despues", futuro)
check("en el PC, uno sin hora entra a la cola al tiro", encolados == ["ya"], encolados)
check("y uno programado espera con un temporizador",
      _timer.call_count == 1 and 7000 < _timer.call_args[0][0] <= 7200, _timer.call_args)

sys.exit(resultado())
