"""
Ejecuta un trabajo pedido desde la página: evaluar, enviar, tutoría...

Cada trabajo corre en una carpeta propia y desechable, que tiene una copia de
`modulos/` y del semestre bajado desde R2. El código del curso no sabe que está
en la nube: lee y escribe sus CSV y prompts en las mismas rutas de siempre. Al
terminar se suben a R2 los archivos que cambiaron y la carpeta se borra.

Esa carpeta propia no es un detalle. En desarrollo el motor corre en el PC del
curso, y si trabajara sobre semestres/ real, una prueba podría pisar los datos.

Lo que hay que ejecutar lo arma este archivo, no la página: la página solo
elige un flujo de una lista cerrada, y los argumentos se validan acá.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import sitio

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- qué se ejecuta


def _semana(a: dict) -> str:
    s = int(a.get("semana", 0))
    if not 1 <= s <= 52:
        raise ValueError(f"Semana fuera de rango: {s}")
    return str(s)


def _prueba(a: dict) -> list[str]:
    # Todo trabajo es de prueba salvo que se haya pedido explícitamente lo
    # contrario. Así, un error en la página no puede mandar correos.
    return [] if a.get("prueba") is False else ["--dry-run"]


def _solo(a: dict) -> list[str]:
    """Los correos elegidos en la página: solo a esos se evalúa o corrige.

    Sin "solo" se procesa todo lo pendiente, como siempre. Una lista vacía no
    se acepta: significaría "no procesar a nadie", y eso se hace no corriendo.
    """
    if "solo" not in a:
        return []
    correos = a["solo"]
    if not isinstance(correos, list) or not correos or len(correos) > 300:
        raise ValueError("'solo' tiene que ser una lista de correos, no vacía.")
    for c in correos:
        if not (isinstance(c, str) and re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", c)):
            raise ValueError(f"Correo inválido en 'solo': {c!r}")
    return ["--solo", ",".join(c.lower() for c in correos)]


def _paso_segunda(a: dict) -> list[str]:
    paso = a.get("paso")
    if paso == "preparar":
        return ["preparar", _tarea(a)]
    if paso == "enviar":
        # Como en el resto: sin "prueba": false, no sale nada; se arman los borradores.
        return ["enviar", _tarea(a), "--confirmar"] if a.get("prueba") is False else ["borradores", _tarea(a)]
    raise ValueError(f"Paso inválido: {paso!r}")


def _ajuste(a: dict) -> list[str]:
    """Ajuste manual de nota. Quién lo hace lo pone el sitio (pedido_por), no la página."""
    flujo = a.get("flujo")
    if flujo not in ("test", "tarea"):
        raise ValueError(f"Flujo inválido: {flujo!r}")
    item = str(a.get("item", ""))
    if not re.fullmatch(r"\d{1,2}" if flujo == "test" else r"T\d{1,2}", item):
        raise ValueError(f"Ítem inválido: {item!r}")
    correo = str(a.get("correo", ""))
    if not re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", correo):
        raise ValueError(f"Correo inválido: {correo!r}")
    nota = str(a.get("nota", ""))
    if not re.fullmatch(r"\d{1,2}([.,]\d)?", nota):
        raise ValueError(f"Nota inválida: {nota!r}")
    # El motivo es opcional; si viene, a lo más 500 caracteres.
    motivo = " ".join(str(a.get("motivo", "")).split())
    if len(motivo) > 500:
        raise ValueError("El motivo es muy largo (más de 500 caracteres).")
    return ["-m", "modulos.datos.ajustar", "--flujo", flujo, "--item", item, "--correo", correo,
            "--nota", nota, "--motivo", motivo, "--por", a.get("_pedido_por") or "desconocido"]


def _tarea(a: dict) -> str:
    t = str(a.get("tarea", ""))
    if not re.fullmatch(r"T\d{1,2}", t):
        raise ValueError(f"Tarea inválida: {t!r}")
    return t


def _minutos(a: dict) -> list[str]:
    """El plazo para responder la pregunta de una tarea. Sin él, el del script (20)."""
    if a.get("minutos") is None:
        return []
    m = int(a["minutos"])
    if not 1 <= m <= 24 * 60:
        raise ValueError(f"Minutos fuera de rango: {m}")
    return ["--minutos", str(m)]


def _desde(a: dict) -> list[str]:
    """Un envío programado cuenta el plazo desde la hora programada (la valida el sitio)."""
    if not a.get("a_las"):
        return []
    cuando = str(a["a_las"])
    datetime.fromisoformat(cuando.replace("Z", "+00:00"))  # ValueError si no es una fecha
    return ["--desde", cuando]


def _entregas(a: dict) -> list[str]:
    """Los HTML elegidos en la página, como rutas dentro de la carpeta de trabajo."""
    nombres = a.get("archivos") or []
    if not isinstance(nombres, list):
        raise ValueError("archivos tiene que ser una lista")
    for n in nombres:
        if not (isinstance(n, str) and re.fullmatch(r"[^/\\]{1,200}\.html", n) and ".." not in n):
            raise ValueError(f"Entrega inválida: {n!r}")
    carpeta = f"semestres/{a['_semestre']}/tareas/data/entregas/{_tarea(a)}"
    return [f"{carpeta}/{n}" for n in nombres]


# El chequeo de Streamlit se dibuja con los datos, no con el texto. Acá se
# imprime como en la terminal y además se guarda en JSON para la página.
_CHEQUEO = (
    "import json, sys\n"
    "from modulos import semestre\n"
    "from modulos.tareas import chequeo\n"
    "tarea = sys.argv[1]\n"
    "informe = chequeo.revisar(tarea)\n"
    "chequeo.imprimir(informe)\n"
    "destino = semestre.raiz() / 'tareas' / 'cache' / f'chequeo_{tarea}.json'\n"
    "destino.parent.mkdir(parents=True, exist_ok=True)\n"
    "destino.write_text(json.dumps(informe, ensure_ascii=False, default=str), encoding='utf-8')\n"
)


# "Probar un prompt": como en Streamlit, el candidato se guarda como
# prompt_candidato.md y se corre el experimento con él. El archivo vigente del
# semestre no se toca.
_EXPERIMENTO = (
    "import runpy, sys\n"
    "from modulos import semestre\n"
    "destino = semestre.raiz() / 'tests_semanales' / 'data' / 'prompt_candidato.md'\n"
    "destino.parent.mkdir(parents=True, exist_ok=True)\n"
    "destino.write_text(sys.argv[1], encoding='utf-8')\n"
    "sys.argv = ['experimento', '--prompt', str(destino), *sys.argv[2:]]\n"
    "runpy.run_module('modulos.tests.experimento', run_name='__main__')\n"
)


def _experimento(a: dict) -> list[str]:
    prompt = a.get("prompt")
    # 30.000 caracteres: holgado para un prompt, y cabe en la línea de comandos de Windows.
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 30000:
        raise ValueError("Falta el prompt candidato, o es demasiado largo.")
    n, semilla = int(a.get("n", 20)), int(a.get("semilla", 19))
    if not (1 <= n <= 300 and 0 <= semilla <= 99999):
        raise ValueError("Cantidad o semilla fuera de rango.")
    cmd = ["-c", _EXPERIMENTO, prompt, "-n", str(n), "--semilla", str(semilla)]
    # Sin semana son todas; una semana 0 o vacía es un error, no "todas".
    if a.get("semana") is not None:
        cmd += ["--semana", _semana(a)]
    # Aquí "prueba" es "solo mostrar la muestra": no llama al modelo.
    return cmd + _prueba(a)


# flujo -> (perfil de archivos que necesita, cómo se arma el comando)
FLUJOS = {
    "tests.enviar": ("tests", lambda a: ["-m", "modulos.tests.enviar", _semana(a), *_prueba(a)]),
    "tests.evaluar": ("tests", lambda a: ["-m", "modulos.tests.evaluar", _semana(a), *_prueba(a), *_solo(a)]),
    "tests.tutoria": ("tests", lambda a: ["-m", "modulos.tests.tutoria",
                                          *([_semana(a)] if a.get("semana") else []), *_prueba(a)]),
    # No manda correos ni modifica el curso: solo lee y cuenta.
    "tests.chequeo": ("tests", lambda a: ["-m", "modulos.tests.chequeo", _semana(a)]),
    # No manda correos, pero sí llama al modelo: gasta API aunque sea "prueba".
    "tests.resumen": ("tests", lambda a: ["-m", "modulos.tests.resumen", _semana(a)]),
    # No manda correos ni cambia notas; sin modo prueba, gasta una llamada por respuesta.
    "tests.experimento": ("tests", _experimento),
    # Solo recalcula la reportería, después de editar alumnos o notas a mano.
    "datos.panel": ("tests", lambda a: ["-c", "print('Recalculando la reportería…')"]),
    # La sábana de datos del semestre, en exportes/sabana.csv. Solo lee.
    "datos.sabana": ("sabana", lambda a: ["-m", "modulos.sabana"]),
    # Cambiar una nota a mano, con motivo. No manda correos.
    "datos.ajustar": ("tests", _ajuste),

    # No llama al modelo: lee las entregas y deja el resultado para la página.
    "tareas.chequeo": ("tareas", lambda a: ["-c", _CHEQUEO, _tarea(a)]),
    # Llama al modelo pero no manda correos, igual que en Streamlit.
    "tareas.generar": ("tareas", lambda a: ["-m", "modulos.tareas.generar", _tarea(a), "--no-interactivo",
                                            *_entregas(a)]),
    "tareas.enviar": ("tareas", lambda a: ["-m", "modulos.tareas.enviar", _tarea(a), *_prueba(a), *_minutos(a),
                                           *_desde(a)]),
    # Solo lee el buzón y actualiza el CSV. Con "solo", busca solo a esos correos
    # (el envío programado a un grupo chico).
    "tareas.recolectar": ("tareas", lambda a: ["-m", "modulos.tareas.recolectar", _tarea(a), *_solo(a)]),
    # Segunda oportunidad: "preparar" genera las preguntas nuevas (llama al
    # modelo, no manda correos); "enviar" en modo prueba solo escribe los
    # borradores, y en real los manda.
    "tareas.segunda": ("tareas", lambda a: ["-m", "modulos.tareas.segunda_oportunidad", *_paso_segunda(a)]),
    # "sin_tarde" deja fuera las respuestas fuera de plazo aunque vengan en "solo".
    "tareas.corregir": ("tareas", lambda a: ["-m", "modulos.tareas.corregir", _tarea(a), *_prueba(a), *_solo(a),
                                             *(["--sin-tarde"] if a.get("sin_tarde") is True else []),
                                             *(["--no-enviar"] if a.get("no_enviar") is True
                                               and a.get("prueba") is False else [])]),
    # Manda las correcciones que se guardaron para revisarlas (corregir sin enviar).
    "tareas.feedback": ("tareas", lambda a: ["-m", "modulos.tareas.feedback", _tarea(a), *_prueba(a), *_solo(a)]),
}

# Los parámetros de la página que el motor le pasa al script. config.py los toma
# de las variables de entorno antes que del .env. Solo estos: si la tabla de
# parámetros trajera otra cosa, no llega al script.
PARAMETROS = ("MODELO", "TEMPERATURA", "MAX_TOKENS", "NOTA_MIN", "NOTA_MAX",
              "TAREA_DEFAULT", "GRUPO_CONTROL_TRATAMIENTO", "GRUPO_SEED", "PRECIOS_API")

# ---------------------------------------------------------------- qué archivos baja

# Extensiones de la raíz del semestre que usan los flujos: las tablas y alguna
# configuración. Lo demás de la raíz (planillas de análisis, informes en R) no lo
# necesita ningún trabajo y no se baja.
_RAIZ = (".csv", ".json", ".md", ".txt")


def _en_perfil(perfil: str, ruta: str) -> bool:
    """Si un archivo del semestre hace falta para un trabajo de ese perfil.

    Un trabajo de tests baja unos 3 MB; uno de tareas, las entregas en HTML,
    que en un semestre completo pasan de 100 MB. Bajar todo siempre haría lento
    cada trabajo sin ganar nada.
    """
    if "/" not in ruta:
        return ruta.lower().endswith(_RAIZ)
    if perfil == "sabana":
        # La sábana cruza tests y tareas, pero de tareas solo necesita las
        # salidas (preguntas y pautas por alumno), no las entregas.
        return ruta.startswith(("tests_semanales/", "tareas/data/salidas/", "exportes/"))
    carpeta = {"tests": "tests_semanales/", "tareas": "tareas/"}[perfil]
    return ruta.startswith(carpeta)


def _huella(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _preparar(semestre: str, perfil: str, base: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Arma la carpeta de trabajo.

    Devuelve la huella de cada archivo bajado (para saber qué cambió) y su etag
    en R2 (para no pisar, al subir, una versión que alguien cambió mientras
    tanto).
    """
    shutil.copytree(REPO / "modulos", base / "modulos",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    carpeta = base / "semestres" / semestre
    carpeta.mkdir(parents=True)
    # El semestre del trabajo es el activo de esta carpeta. IN5162_SEMESTRE ya
    # lo fija, pero algunos módulos listan semestres y leen activo.txt.
    (base / "semestres" / "activo.txt").write_text(semestre, encoding="utf-8")

    def bajar(ruta: str) -> tuple[str, str]:
        destino = carpeta / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(sitio.bajar_archivo(semestre, ruta))
        return ruta, _huella(destino)

    # De a varios a la vez: de a uno, cada archivo espera la ida y vuelta al
    # sitio, y un semestre con entregas son cientos de archivos.
    lista = [a for a in sitio.listar_archivos(semestre) if _en_perfil(perfil, a["ruta"])]
    with ThreadPoolExecutor(max_workers=8) as grupo:
        huellas = dict(grupo.map(bajar, [a["ruta"] for a in lista]))
    return huellas, {a["ruta"]: a.get("etag", "") for a in lista}


def _cambiados(carpeta: Path, perfil: str, huellas: dict[str, str]) -> list[str]:
    """Archivos del perfil que el trabajo creó o modificó."""
    salida = []
    for p in sorted(carpeta.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        ruta = p.relative_to(carpeta).as_posix()
        if _en_perfil(perfil, ruta) and huellas.get(ruta) != _huella(p):
            salida.append(ruta)
    return salida


# ---------------------------------------------------------------- ejecución


class _Salida:
    """Junta lo que imprime el script y lo manda al sitio cada poco rato.

    Mandar línea por línea serían cientos de pedidos por trabajo; juntarlas
    cada segundo y medio basta para que en la página se vea avanzar.
    """

    INTERVALO = 1.5

    def __init__(self, id_trabajo: str):
        self.id = id_trabajo
        self._pendiente: list[str] = []
        self._candado = threading.Lock()
        self._ultimo = 0.0
        # Se prende si alguien pidió detener el trabajo desde la página.
        self.cancelado = threading.Event()

    def agregar(self, texto: str) -> None:
        with self._candado:
            self._pendiente.append(texto)
        if time.monotonic() - self._ultimo >= self.INTERVALO:
            self.vaciar()

    def vaciar(self, **extra) -> bool:
        """Manda lo juntado. Devuelve False si el sitio no respondió.

        Si falla, el texto se guarda para el próximo intento. Un aviso perdido
        no puede cortar un trabajo que ya está mandando correos: antes, una
        caída del sitio a mitad de corrida dejaba los envíos sin registrar.
        """
        with self._candado:
            texto = "".join(self._pendiente)
            self._pendiente.clear()
        self._ultimo = time.monotonic()
        if not (texto or extra):
            return True
        try:
            sitio.informar(self.id, salida=texto, **extra)
            return True
        except Exception:  # noqa: BLE001
            with self._candado:
                self._pendiente.insert(0, texto)
            return False

    def cerrar(self, **extra) -> None:
        """El aviso final (terminado o fallido): se insiste un rato antes de rendirse."""
        for espera in (0, 5, 15, 30):
            time.sleep(espera)
            if self.vaciar(**extra):
                return


# Cloud Tasks espera hasta 30 minutos; pasado eso suelta el cupo y despacha el
# trabajo siguiente, que correría a la vez que este y pisaría sus archivos. Se
# corta antes, para alcanzar a guardar lo hecho y responder a tiempo.
LIMITE_SEGUNDOS = 25 * 60

# Cada cuánto se mira si alguien pidió detener el trabajo desde la página.
VIGILANCIA_SEGUNDOS = 5
# Los que no mandan correos se pueden cortar en seco. Los demás paran solos
# entre un alumno y otro (modulos/progreso.py), para que ningún correo quede
# enviado sin registrar.
CORTABLES = {"tests.chequeo", "tests.experimento", "tareas.chequeo", "tareas.generar",
             "datos.panel", "datos.sabana"}


def _correr(cmd: list[str], base: Path, semestre: str, salida: _Salida,
            parametros: dict[str, str], id_trabajo: str = "", cortable: bool = False) -> int:
    aviso_cancelar = base / ".cancelar"
    entorno = {
        **os.environ,
        **{k: v for k, v in parametros.items() if k in PARAMETROS},
        "IN5162_SEMESTRE": semestre,
        # Para nombrar lo que el trabajo deja a la página (candidatos_<item>_<id>.json).
        "IN5162_TRABAJO": id_trabajo,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        # Si este archivo aparece, el script para antes del alumno siguiente.
        "IN5162_CANCELAR": str(aviso_cancelar),
    }
    proc = subprocess.Popen(
        [sys.executable, *cmd], cwd=base, env=entorno,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    vencido = threading.Event()
    termino = threading.Event()

    def cortar() -> None:
        vencido.set()
        proc.kill()

    def vigilar() -> None:
        """Mira cada tanto si en la página pidieron detenerlo ("cancelando")."""
        while not termino.wait(VIGILANCIA_SEGUNDOS):
            try:
                pedido = sitio.ver_trabajo(id_trabajo).get("estado") == "cancelando"
            except Exception:  # noqa: BLE001  (un aviso perdido no corta nada)
                continue
            if pedido:
                salida.cancelado.set()
                aviso_cancelar.write_text("", encoding="utf-8")
                if cortable:
                    proc.kill()
                return

    reloj = threading.Timer(LIMITE_SEGUNDOS, cortar)
    reloj.start()
    if id_trabajo:
        threading.Thread(target=vigilar, daemon=True).start()
    try:
        assert proc.stdout is not None
        for linea in proc.stdout:
            salida.agregar(linea)
    finally:
        termino.set()
        reloj.cancel()
        if proc.poll() is None:
            proc.kill()
        codigo = proc.wait()
    if vencido.is_set():
        salida.agregar(f"\n✗ El trabajo pasó de {LIMITE_SEGUNDOS // 60} minutos y se detuvo. "
                       "Lo que alcanzó a hacer se guarda igual.\n")
        return -9
    if salida.cancelado.is_set():
        salida.agregar("\n⊘ Se detuvo a pedido. Lo que alcanzó a hacer se guarda.\n")
    return codigo


def _panel(base: Path, semestre: str) -> list[dict]:
    """La tabla de la reportería, calculada sobre los archivos ya actualizados."""
    codigo = ("import json, sys; from modulos.datos import reportes; "
              f"sys.stdout.write(json.dumps(reportes.panel({semestre!r}), ensure_ascii=False))")
    r = subprocess.run([sys.executable, "-c", codigo], cwd=base, capture_output=True,
                       text=True, encoding="utf-8",
                       env={**os.environ, "IN5162_SEMESTRE": semestre, "PYTHONUTF8": "1"})
    if r.returncode != 0:
        raise RuntimeError(f"no pude recalcular la reportería: {r.stderr[-400:]}")
    return json.loads(r.stdout)


def _como_se_ve(cmd: list[str]) -> str:
    """El comando para mostrar en la página, sin el código de los -c ni argumentos
    largos como un prompt entero, que taparían la salida."""
    partes = []
    for i, x in enumerate(cmd):
        if i and cmd[i - 1] == "-c":
            partes.append("<script del motor>")
        elif len(x) > 80 or "\n" in x:
            partes.append(f"<{len(x):,} caracteres>".replace(",", "."))
        else:
            partes.append(f'"{x}"' if " " in x else x)
    return " ".join(partes)


class _YaTomado(Exception):
    """Otro intento ya tomó este trabajo (la cola lo entregó dos veces)."""


def _guardar(base: Path, semestre: str, perfil: str, huellas: dict[str, str],
             etags: dict[str, str], id_trabajo: str, salida: _Salida) -> tuple[list[str], list[str]]:
    """Sube lo que el script cambió. Devuelve (guardados, los que no se pudieron guardar).

    Cada archivo va por separado: si uno falla, los demás igual se guardan. Se
    sube con el etag con que se bajó; si en la nube cambió mientras tanto, el
    sitio lo rechaza en vez de pisar esa versión.
    """
    carpeta = base / "semestres" / semestre
    guardados, fallidos = [], []
    for ruta in _cambiados(carpeta, perfil, huellas):
        try:
            sitio.subir_archivo(semestre, ruta, (carpeta / ruta).read_bytes(),
                                origen=f"trabajo {id_trabajo}", etag=etags.get(ruta))
            guardados.append(ruta)
        except Exception as e:  # noqa: BLE001
            fallidos.append(f"{ruta} ({e})")
    if guardados:
        salida.agregar(f"\n(guardados {len(guardados)} archivos: {', '.join(guardados)})\n")
    for f in fallidos:
        salida.agregar(f"✗ No pude guardar {f}\n")
    return guardados, fallidos


def ejecutar(id_trabajo: str) -> None:
    """Corre un trabajo de punta a punta. Nunca levanta excepción: la informa.

    Lo que el script alcanzó a cambiar se guarda SIEMPRE, también si falló o se
    cortó a medio camino: si ya mandó correos, tienen que quedar registrados, o
    la corrida siguiente los volvería a mandar.
    """
    salida = _Salida(id_trabajo)
    base = None  # la carpeta de trabajo se crea recién al bajar el semestre
    preparado = None  # (semestre, perfil, huellas, etags) una vez bajado el semestre
    codigo, flujo = -1, ""
    try:
        t = sitio.ver_trabajo(id_trabajo)
        if t.get("estado") != "pendiente":
            # Cloud Tasks puede entregar dos veces el mismo pedido. Un trabajo
            # que ya empezó no se repite: podría mandar correos dos veces.
            return
        # Un trabajo programado que llega antes de su hora (al encolarlo no se
        # pudo leer la hora) vuelve a la cola, ahora con ella. Si corriera, las
        # preguntas saldrían antes de tiempo.
        from . import cola
        cuando = cola.hora_programada(t)
        if cuando and cuando > datetime.now(timezone.utc) + timedelta(seconds=60):
            cola.encolar(id_trabajo)
            return
        semestre, flujo, args = t["semestre"], t["flujo"], t.get("argumentos") or {}
        if flujo not in FLUJOS:
            raise ValueError(f"Flujo desconocido: {flujo}")
        perfil, armar = FLUJOS[flujo]
        # El semestre lo pone el motor, no la página: pisa cualquier "_semestre" que venga.
        cmd = armar({**args, "_semestre": semestre, "_pedido_por": t.get("pedido_por", "")})

        # El sitio solo lo pasa a "corriendo" si seguía "pendiente": si dos
        # intentos llegan a la vez, uno solo lo ejecuta. La marca de esta
        # ejecución distingue el otro caso que da 409: el aviso sí llegó, se
        # cortó la respuesta y el reintento chocó con su propio cambio.
        inicio = f"$ python {_como_se_ve(cmd)}   [{semestre}] · ejecución {uuid.uuid4().hex[:8]}\n"
        try:
            sitio.informar(id_trabajo, estado="corriendo", salida=inicio)
        except RuntimeError as e:
            if " 409 " not in f" {e} ":
                raise
            if inicio not in (sitio.ver_trabajo(id_trabajo).get("salida") or ""):
                raise _YaTomado() from e
        base = Path(tempfile.mkdtemp(prefix="in5162-trabajo-"))
        huellas, etags = _preparar(semestre, perfil, base)
        preparado = (semestre, perfil, huellas, etags)
        parametros = sitio.leer_parametros()
        modelo = f"; modelo {parametros['MODELO']}" if parametros.get("MODELO") else ""
        salida.agregar(f"(bajados {len(huellas)} archivos del semestre{modelo})\n\n")

        codigo = _correr(cmd, base, semestre, salida, parametros, id_trabajo, cortable=flujo in CORTABLES)
    except _YaTomado:
        return
    except Exception as e:  # noqa: BLE001
        salida.agregar(f"\n✗ El trabajo falló: {type(e).__name__}: {e}\n")
        salida.agregar("".join(traceback.format_exc(limit=4)))
        codigo = -1
    try:
        fallidos = []
        if preparado:
            semestre, perfil, huellas, etags = preparado
            guardados, fallidos = _guardar(base, semestre, perfil, huellas, etags, id_trabajo, salida)
            # La reportería sale de los CSV de la raíz del semestre y de los tests.
            # Un trabajo de tareas que solo guardó sus archivos no la cambia.
            afecta = [r for r in guardados if "/" not in r or r.startswith("tests_semanales/")]
            if (afecta or flujo == "datos.panel") and not fallidos:
                filas = _panel(base, semestre)
                sitio.subir_panel(semestre, filas)
                if flujo == "datos.panel":
                    salida.agregar(f"✓ reportería al día: {len(filas)} casillas\n")
        ok = codigo == 0 and not fallidos
        # Detenido a pedido queda "cancelado", salvo que no haya podido guardar lo hecho.
        estado = "cancelado" if salida.cancelado.is_set() and not fallidos else "terminado" if ok else "fallido"
        salida.cerrar(estado=estado, codigo=codigo if codigo else (0 if ok else -1))
    except Exception as e:  # noqa: BLE001
        salida.agregar(f"\n✗ Falló al guardar: {type(e).__name__}: {e}\n")
        salida.cerrar(estado="fallido", codigo=-1)
    finally:
        if base:
            shutil.rmtree(base, ignore_errors=True)
