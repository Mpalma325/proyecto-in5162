"""
Ninguna simulación escribe notas.csv ni el log.

El motor sube lo que un trabajo cambió también cuando es una simulación, y las
simulaciones corren a la vez que los trabajos reales. Si una escribiera esas
tablas, chocaría por etag con el trabajo real (motor/trabajo.py, _guardar) y uno
de los dos perdería lo guardado. Las columnas nuevas del esquema lo hacen más
probable: una escritura cualquiera las agrega.

Corre cada flujo que la página trata como simulación (SIMULABLES de
web/public/comun.js, y tareas.segunda con paso "enviar") en modo prueba, con el
mismo comando que arma el motor, sobre una copia del semestre, y compara la
huella de notas.csv y del log antes y después. Un flujo nuevo en SIMULABLES sin
caso acá hace fallar la prueba.

No compara alumnos.csv: tests.enviar asigna los grupos que falten antes de
mirar si es simulación, y eso ya se sabe (diseño, sección 3).
"""

import hashlib
import io
import os
import re
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import (check, correo_entrante, enviados, resultado, respuestas_falsas,  # noqa: E402
                   semestre_desechable, sin_red, titulo)

RAIZ = Path(__file__).resolve().parent.parent
COMUN_JS = RAIZ / "web" / "public" / "comun.js"

PROMPT = "Evalúa.\nPreguntas: {{PREGUNTAS}}\nPautas: {{PAUTAS}}\nTermina con NOTA FINAL: y ORIGINALIDAD:\n"


def simulables() -> list[str]:
    """Los flujos cuyo modo prueba la página muestra como simulación."""
    m = re.search(r"const SIMULABLES = new Set\(\[(.*?)\]\)", COMUN_JS.read_text(encoding="utf-8"), re.S)
    nombres = re.findall(r'"([a-z]+\.[a-z]+)"', m.group(1)) if m else []
    # simula(): tareas.segunda cuenta como simulación solo en el paso "enviar".
    return nombres + ["tareas.segunda"]


def huella(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def correr(cmd: list[str]) -> str:
    """Corre en este proceso lo que el motor correría como `python <cmd>`."""
    salida = io.StringIO()
    argv = sys.argv
    try:
        with redirect_stdout(salida):
            if cmd[0] == "-m":
                sys.argv = [cmd[1], *cmd[2:]]
                runpy.run_module(cmd[1], run_name="__main__", alter_sys=True)
            elif cmd[0] == "-c":
                sys.argv = ["-c", *cmd[2:]]
                exec(compile(cmd[1], "<motor>", "exec"), {"__name__": "__main__"})
            else:
                raise ValueError(f"comando inesperado: {cmd[:2]}")
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError(f"salió con código {e.code}:\n{salida.getvalue()[-600:]}") from e
    finally:
        sys.argv = argv
    return salida.getvalue()


def _sin_modelo(*_a, **_k):
    raise AssertionError("una simulación no llama al modelo")


with semestre_desechable(sid="_tmp_simulaciones") as (sid, tmp), sin_red():
    from motor import trabajo
    from modulos import datos

    os.environ["IN5162_TRABAJO"] = "simulacion"

    # Un test con alumnos sin corregir y otro ya corregido, y la tarea que tenga notas.
    notas = datos.notas.leer(sid)
    tests = sorted({int(f["Item"]) for f in notas if f["Flujo"] == datos.TESTS})
    semana = tests[-1]
    del_test = [f for f in notas if f["Flujo"] == datos.TESTS and f["Item"] == str(semana)]
    sin_nota = [f["Correo"] for f in del_test if not f["Nota"].strip()][:2]
    con_nota = [f["Correo"] for f in del_test if f["Nota"].strip()][:2]
    tarea = sorted({f["Item"] for f in notas if f["Flujo"] == datos.TAREAS})[0]

    # Lo que el buzón traería: respuestas nuevas, un segundo envío de quien ya
    # tiene nota, un correo ya procesado y una duda sobre un feedback. Lo que
    # haga falta en el log se agrega antes de tomar las huellas.
    datos.log.registrar("respuesta", datos.TESTS, semana, con_nota[1], sid,
                        MessageId="<ya-procesado@correo.test>", Respuesta="ya procesada")
    datos.log.registrar("evaluacion", datos.TESTS, semana, con_nota[0], sid,
                        MessageId="<feedback-sim@correo.test>", Nota="6,0",
                        EvaluacionIA="<p>NOTA FINAL: 6,0</p>")
    # Para tests.feedback: una corrección automática cuyo feedback no salió. El
    # semestre no tiene configuracion.json (automático), así que la mandaría.
    pendiente = ([f["Correo"] for f in del_test if not f["Nota"].strip()][2:3] or sin_nota[:1])[0]
    datos.log.registrar("correccion", datos.TESTS, semana, pendiente, sid, Modelo="modelo-prueba", Nota="5,0",
                        EvaluacionIA="<p>Bien.</p><p>NOTA FINAL: 5,0</p>", Detalle="modo=auto")
    buzon_tests = (respuestas_falsas(sin_nota + con_nota[:1], semana, message_ids=True)
                   + [correo_entrante(con_nota[1], semana, "otra vez", uid="801",
                                      message_id="<ya-procesado@correo.test>")])
    buzon = buzon_tests + [correo_entrante(con_nota[0], semana, "¿Por qué un 6?", uid="802",
                                           in_reply_to="<feedback-sim@correo.test>")]

    # Por flujo: los argumentos de cada corrida y, si se sabe, algo que la
    # salida tiene que decir (para no dar por buena una simulación que no hizo nada).
    CASOS = {
        "tests.enviar": [({"semana": semana}, None), ({"semana": semana + 1}, "Se enviaría a")],
        "tests.evaluar": [({"semana": semana}, "Duplicados: 1"), ({"semana": semana}, "Ya procesados antes: 1")],
        "tests.feedback": [({"semana": semana}, "Feedback se enviarían: 1")],
        "tests.tutoria": [({"semana": semana}, "respondería"), ({}, "respondería")],
        "tests.experimento": [({"prompt": PROMPT, "n": 3, "semana": semana}, "MODO PRUEBA")],
        "tareas.enviar": [({"tarea": tarea}, None)],
        "tareas.corregir": [({"tarea": tarea}, None)],
        "tareas.feedback": [({"tarea": tarea}, None)],
        "tareas.segunda": [({"tarea": tarea, "paso": "enviar"}, None)],
    }

    titulo("1. cada flujo simulable tiene su caso")
    faltan = [f for f in simulables() if f not in CASOS]
    check("ninguno sin caso en esta prueba", not faltan, faltan)
    check("la lista de la página se leyó", len(simulables()) >= 8, simulables())

    titulo("2. en modo prueba, ninguno toca notas.csv ni el log")
    tablas = [tmp / "notas.csv", tmp / "log_envios.csv"]
    with patch("modulos.mail.buscar_respuestas_semana", return_value=buzon_tests), \
         patch("modulos.mail.buscar_no_leidos", return_value=buzon), \
         patch("modulos.mail.buscar_respuestas", return_value={}), \
         patch("modulos.ia.cliente._cliente", side_effect=_sin_modelo):
        for flujo in simulables():
            for args, espera in CASOS.get(flujo, []):
                antes = [huella(p) for p in tablas]
                enviados.clear()
                perfil, armar = trabajo.FLUJOS[flujo]
                cmd = armar({**args, "_semestre": sid, "_pedido_por": "prueba@correo.test"})
                nombre = f"{flujo} {args.get('semana', args.get('tarea', 'todas'))}"
                try:
                    texto = correr(cmd)
                    check(f"{nombre}: corre", True)
                    if espera:
                        check(f"{nombre}: dice «{espera}»", espera in texto, texto[-400:])
                except Exception as e:  # noqa: BLE001
                    check(f"{nombre}: corre", False, f"{type(e).__name__}: {e}")
                cambiadas = [p.name for p, h in zip(tablas, antes) if huella(p) != h]
                check(f"{nombre}: no escribe notas.csv ni el log", not cambiadas, cambiadas)
                check(f"{nombre}: no manda correos", enviados == [], enviados)
                check(f"{nombre}: sin temporales de escritura",
                      not [p for p in tablas if p.with_suffix(p.suffix + ".tmp").exists()])

    os.environ.pop("IN5162_TRABAJO", None)

sys.exit(resultado())
