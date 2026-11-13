import html as _html
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_DIR.parent
# Los flujos viven en modulos/ y se invocan desde la raíz del proyecto.
ENV_FILE = PROJECT_ROOT / ".env"

sys.path.insert(0, str(PROJECT_ROOT))
from modulos import semestre as _semestre  # noqa: E402

# La app conserva estos nombres; la logica vive en modulos/semestre.
semestre_activo = _semestre.activo
listar_semestres = _semestre.listar
set_semestre_activo = _semestre.activar
crear_semestre = _semestre.crear

SEMESTRES_DIR = PROJECT_ROOT / "semestres"
_TEMPLATE_DIR = SEMESTRES_DIR / "_template"
ACTIVO_FILE = SEMESTRES_DIR / "activo.txt"
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


# Las rutas las resuelve modulos/semestre: acá solo se les pone el nombre que
# usa la app. Antes estaban calculadas a mano y había que cambiarlas en dos
# lugares cada vez.
def tests_data_dir(semestre: str | None = None) -> Path:
    return _semestre.datos("tests_semanales", semestre)


def tests_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre.prompts("tests_semanales", semestre)


def tareas_data_dir(semestre: str | None = None) -> Path:
    return _semestre.datos("tareas", semestre)


def tareas_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre.prompts("tareas", semestre)


def tareas_entregas_dir(semestre: str | None = None, tarea: str | None = None) -> Path:
    base = tareas_data_dir(semestre) / "entregas"
    return base / tarea if tarea else base


def tareas_clases_dir(semestre: str | None = None) -> Path:
    return tareas_data_dir(semestre) / "clases"


def tareas_salidas_dir(semestre: str | None = None) -> Path:
    return tareas_data_dir(semestre) / "salidas"


def tareas_conocidas(semestre: str | None = None) -> list[str]:
    """Nombres de tarea (T1, T2, ...) con feedback ya generado o con entregas subidas."""
    conocidas: set[str] = set()

    salidas_dir = tareas_salidas_dir(semestre)
    if salidas_dir.exists():
        conocidas |= {
            p.stem.replace("feedback_", "").upper()
            for p in salidas_dir.glob("feedback_*.csv")
        }

    entregas_base = tareas_entregas_dir(semestre)
    if entregas_base.exists():
        conocidas |= {p.name.upper() for p in entregas_base.iterdir() if p.is_dir()}

    return sorted(conocidas)


def tarea_selector(key: str, semestre: str | None = None) -> str:
    """Selector de tarea (T1, T2, ...) compartido entre Entregas y el flujo de Tareas."""
    import streamlit as st

    opciones = tareas_conocidas(semestre)
    if not opciones:
        return st.text_input("Tarea (ej. T1)", value="T1", key=key + "_text")

    seleccion = st.selectbox("Tarea", opciones + ["Nueva..."], key=key + "_sel")
    if seleccion == "Nueva...":
        return st.text_input("Nombre de tarea (ej. T2)", value="T2", key=key + "_new")
    return seleccion


def run_command(
    cmd: list[str],
    cwd: Path,
    output_callback: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    lines: list[str] = []
    for line in process.stdout:
        lines.append(line)
        if output_callback:
            output_callback("".join(lines))

    process.wait()
    return process.returncode, "".join(lines)


def python() -> str:
    return sys.executable


from modulos.tareas.desempacar import (  # noqa: E402,F401  (la extracción vive allá)
    _es_basura_mac, _es_enunciado, _extraer_rar, _extraer_zip, _guardar_html,
    _hay_lector_rar, _miembro_valido, _recoger_de_directorio, _rmd_de, extraer_entregas,
)


def render_output(output: str) -> str:
    """Convert script output to a styled HTML log for Streamlit (unsafe_allow_html=True)."""
    parts: list[str] = []
    for line in output.split("\n"):
        text = line.rstrip()
        if not text:
            parts.append("")
            continue
        stripped = text.lstrip()
        if stripped.startswith("✓"):
            style = "color:#2e7d32;font-weight:bold"
        elif stripped.startswith("✗"):
            style = "color:#c62828;font-weight:bold"
        elif stripped.startswith("⚠"):
            style = "color:#e65100;font-weight:bold"
        elif stripped.startswith("⊘"):
            style = "color:#616161"
        elif stripped.startswith("⋯"):
            style = "color:#616161"
        elif stripped.startswith("→"):
            style = "color:#1565c0"
        elif any(stripped.startswith(w) for w in ("Evaluados:", "enviado", "Módulo", "Nada")):
            style = "font-weight:bold;color:#212121"
        else:
            style = "color:#37474f"
        escaped = _html.escape(text)
        parts.append(
            f'<span style="font-family:monospace;font-size:13px;line-height:1.7;{style}">'
            f"{escaped}</span>"
        )
    body = "<br>".join(parts)
    return (
        '<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;'
        'padding:14px 16px;max-height:440px;overflow-y:auto">'
        f"{body}</div>"
    )


# --- Chequeo previo de las entregas -----------------------------------------
# El cálculo vive en modulos/tareas/chequeo.py; acá solo se dibuja, igual que
# con la reportería.

def chequeo_tareas(tarea: str) -> dict:
    """El estado de las entregas de una tarea. No llama al modelo."""
    from modulos.tareas import chequeo
    return chequeo.revisar(tarea)


def _pintar_grupo(st, grupo: dict, tarea: str, elegido: dict) -> None:
    """Un grupo dentro del chequeo. Deja en `elegido` lo que se elija a mano."""
    archivo = grupo["archivo"]

    if grupo["bloqueo"]:
        icono, resumen = "❌", "se va a saltar"
    elif grupo["sin_roles"] or any(not i["correo"] for i in grupo["integrantes"]):
        icono, resumen = "⚠️", "pide revisión"
    else:
        icono, resumen = "✅", f"{len(grupo['integrantes'])} integrantes"

    with st.expander(f"{icono} {archivo} — {resumen}",
                     expanded=bool(grupo["bloqueo"]) or grupo["sin_roles"]):
        if grupo["fuente"] != archivo:
            st.info(f"El HTML viene sin código: se lee `{grupo['fuente']}`.")

        cortes = " · ".join(f"P{n}: {c:,} car." for n, c in grupo["secciones"].items())
        st.caption(cortes.replace(",", "."))

        if grupo["bloqueo"]:
            st.error("No se llama al modelo por esto:\n\n"
                     + "\n".join(f"- {m}" for m in grupo["bloqueo"]))
            return

        st.caption(f"Integrantes según: {grupo['origen_integrantes']}")

        if grupo["sin_roles"]:
            st.warning(
                "Este grupo no declaró quién hizo qué. Cada integrante trae una "
                "pregunta repartida al azar (con semilla fija, así que no cambia "
                "sola entre corridas). Cámbiala acá si sabes cuál le corresponde."
            )

        for integrante in grupo["integrantes"]:
            nombre = integrante["nombre"]
            col_nombre, col_correo, col_pregunta = st.columns([3, 4, 2])

            with col_nombre:
                st.markdown(f"**{nombre}**")

            with col_correo:
                if integrante["correo"]:
                    st.markdown(f"`{integrante['correo']}`")
                else:
                    st.markdown(":red[Sin correo — elígelo en Datos → Feedback Tareas]")
                    for cand_nombre, cand_correo, sim in integrante["candidatos"]:
                        st.caption(f"¿{cand_nombre}? `{cand_correo}` (parecido {sim})")
                    if not integrante["candidatos"]:
                        st.caption("Ningún candidato razonable en el roster.")

            with col_pregunta:
                asignada = grupo["asignacion"].get(nombre)
                if asignada:
                    opciones = ["P1", "P2", "P3", "P4"]
                    elegida = st.selectbox(
                        "Pregunta", opciones, index=opciones.index(asignada),
                        key=f"asig_{tarea}_{archivo}_{nombre}",
                        label_visibility="collapsed",
                    )
                    elegido[(archivo, nombre)] = elegida


def pintar_chequeo(st, informe: dict, tarea: str) -> None:
    """Dibuja el chequeo previo y deja guardar la asignación que se elija."""
    from modulos.tareas import asignacion as _asignacion

    grupos = informe["grupos"]
    if not grupos:
        st.warning("No hay entregas que revisar.")
        return

    a_generar = sum(1 for g in grupos if not g["bloqueo"]
                    for i in g["integrantes"] if i["correo"])
    saltados = sum(1 for g in grupos if g["bloqueo"])
    sin_correo = sum(1 for g in grupos if not g["bloqueo"]
                     for i in g["integrantes"] if not i["correo"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Preguntas que se generarían", a_generar)
    col2.metric("Sin correo, a resolver", sin_correo)
    col3.metric("Grupos que se saltarían", saltados)

    elegido = dict(_asignacion.leer(tarea))
    for grupo in grupos:
        _pintar_grupo(st, grupo, tarea, elegido)

    hay_reparto = any(g["asignacion"] for g in grupos)
    if hay_reparto and st.button("Guardar asignación", key=f"guardar_asig_{tarea}"):
        path = _asignacion.escribir(tarea, elegido)
        st.success(f"Guardado en `{path.name}`. Generar va a usar esto.")

    if informe["sin_entrega"]:
        with st.expander(
            f"Del roster ({informe['total_roster']}), quedan sin pregunta "
            f"{len(informe['sin_entrega'])}"
        ):
            st.caption(
                "Revisa la lista antes de sacar conclusiones: acá también cae el "
                "equipo docente, si está en el roster."
            )
            for nombre in informe["sin_entrega"]:
                st.markdown(f"- {nombre}")
