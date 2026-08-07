import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import runner
from utils.runner import TAREAS_DIR, python, run_command, render_output

st.title("Tareas")

for key in ["tar_p1_out", "tar_p1_rc",
            "tar_p2_out", "tar_p2_rc",
            "tar_p3_out", "tar_p3_rc",
            "tar_p4_out", "tar_p4_rc"]:
    if key not in st.session_state:
        st.session_state[key] = None


def _run_section(cmd: list[str], out_key: str, rc_key: str) -> None:
    st.session_state[out_key] = None
    st.session_state[rc_key] = None
    area = st.empty()
    with st.spinner("Ejecutando..."):
        rc, output = run_command(
            cmd, TAREAS_DIR,
            lambda o: area.markdown(render_output(o), unsafe_allow_html=True),
        )
    st.session_state[out_key] = output
    st.session_state[rc_key] = rc


def _show_result(out_key: str, rc_key: str) -> None:
    if st.session_state[out_key]:
        st.markdown(render_output(st.session_state[out_key]), unsafe_allow_html=True)
    if st.session_state[rc_key] is not None:
        rc = st.session_state[rc_key]
        if rc == 0:
            st.success("Completado sin errores")
        else:
            st.error(f"El proceso terminó con código {rc}")


tab1, tab2, tab3, tab4 = st.tabs([
    "1 · Generar preguntas",
    "2 · Enviar preguntas",
    "3 · Recolectar respuestas",
    "4 · Corregir",
])

with tab1:
    st.markdown(
        "Procesa los HTMLs de U-Cursos, genera una pregunta de comprensión por alumno "
        "y resuelve correos contra el CSV."
    )

    tarea_p1 = runner.tarea_selector("p1")

    entregas_dir = runner.tareas_entregas_dir(tarea=tarea_p1)
    htmls = sorted(entregas_dir.glob("*.html")) if entregas_dir.exists() else []

    if not htmls:
        st.warning(
            f"No hay archivos HTML para **{tarea_p1}** en `entregas/{tarea_p1}/`. "
            "Súbelos desde la página **Datos y Configuración → Datos del curso → "
            "Entregas (Tareas)**, eligiendo esta misma tarea."
        )
        archivos_sel = []
    else:
        nombres = [h.name for h in htmls]
        sel = st.multiselect(
            f"HTMLs a procesar ({len(htmls)} disponibles para {tarea_p1})",
            options=nombres,
            default=nombres,
            key=f"p1_htmls_{tarea_p1}",
        )
        archivos_sel = [entregas_dir / n for n in sel]

    st.info(
        "Los nombres sin match en el CSV quedarán con correo vacío de forma preliminar "
        "Es necesario corregirlos manualmente desde **Datos → Feedback Tareas**."
    )

    if st.button("Ejecutar", type="primary", key="tar_btn_p1", disabled=not archivos_sel):
        cmd = [python(), "-m", "src.paso1_generar", tarea_p1, "--no-interactivo"]
        cmd += [str(p) for p in archivos_sel]
        _run_section(cmd, "tar_p1_out", "tar_p1_rc")

    _show_result("tar_p1_out", "tar_p1_rc")


with tab2:
    st.markdown("Envía las preguntas personalizadas a los alumnos con correo en el CSV.")

    tarea_p2 = runner.tarea_selector("p2")

    col_a, col_b = st.columns([1, 2])
    with col_b:
        dry_p2 = st.toggle("Modo prueba — no envía emails", value=True, key="tar_dry_p2")
        if not dry_p2:
            st.warning("Modo prueba desactivado — se enviarán emails reales.")

    if st.button("Ejecutar", type="primary", key="tar_btn_p2"):
        cmd = [python(), "-m", "src.paso2_enviar", tarea_p2]
        if dry_p2:
            cmd.append("--dry-run")
        _run_section(cmd, "tar_p2_out", "tar_p2_rc")

    _show_result("tar_p2_out", "tar_p2_rc")


with tab3:
    st.markdown("Busca las respuestas a los emails enviados y las guarda en CSV.")

    tarea_p3 = runner.tarea_selector("p3")

    st.info("No envía emails — solo lee el inbox y actualiza el CSV.")

    if st.button("Ejecutar", type="primary", key="tar_btn_p3"):
        cmd = [python(), "-m", "src.paso3_recolectar", tarea_p3]
        _run_section(cmd, "tar_p3_out", "tar_p3_rc")

    _show_result("tar_p3_out", "tar_p3_rc")


with tab4:
    st.markdown("Evalúa las respuestas con GPT, asigna notas y envía feedback por correo.")

    tarea_p4 = runner.tarea_selector("p4")

    col_a, col_b = st.columns(2)
    with col_a:
        dry_p4 = st.toggle("Modo prueba — no llama a GPT ni envía emails", value=True, key="tar_dry_p4")
        if not dry_p4:
            st.warning("Modo prueba desactivado — se consumirán tokens y se enviarán emails.")
    with col_b:
        no_enviar_p4 = st.toggle("Solo corregir, no enviar emails", value=False,
                                  key="tar_no_enviar_p4")

    if st.button("Ejecutar", type="primary", key="tar_btn_p4"):
        cmd = [python(), "-m", "src.paso4_corregir", tarea_p4]
        if dry_p4:
            cmd.append("--dry-run")
        if no_enviar_p4 and not dry_p4:
            cmd.append("--no-enviar")
        _run_section(cmd, "tar_p4_out", "tar_p4_rc")

    _show_result("tar_p4_out", "tar_p4_rc")
