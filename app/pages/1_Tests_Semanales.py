import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import runner
from utils.runner import TESTS_DIR, python, run_command, render_output

st.title("Tests Semanales")

for key in ["ts_enviar_out", "ts_enviar_rc",
            "ts_evaluar_out", "ts_evaluar_rc",
            "ts_resumen_out", "ts_resumen_rc"]:
    if key not in st.session_state:
        st.session_state[key] = None


def _run_section(cmd: list[str], out_key: str, rc_key: str) -> None:
    st.session_state[out_key] = None
    st.session_state[rc_key] = None
    area = st.empty()
    with st.spinner("Ejecutando..."):
        rc, output = run_command(
            cmd, TESTS_DIR,
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


tab1, tab2, tab3 = st.tabs(["1 · Enviar preguntas", "2 · Evaluar respuestas", "3 · Resumen semana"])

with tab1:
    st.markdown("Envía la pregunta de la semana a todos los alumnos pendientes.")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        semana_env = st.number_input("Número de semana", min_value=1, max_value=52,
                                     value=1, step=1, key="ts_semana_env")
    with col_b:
        dry_env = st.toggle("Modo prueba — no envía emails", value=True, key="ts_dry_env")
        if not dry_env:
            st.warning("Modo prueba desactivado — se enviarán emails reales.")

    if st.button("Ejecutar", type="primary", key="ts_btn_env"):
        cmd = [python(), "-m", "src.enviar_preguntas", str(semana_env)]
        if dry_env:
            cmd.append("--dry-run")
        _run_section(cmd, "ts_enviar_out", "ts_enviar_rc")

    _show_result("ts_enviar_out", "ts_enviar_rc")


with tab2:
    st.markdown("Lee el inbox, evalúa respuestas con GPT y envía feedback a cada alumno.")
    col_a, col_b = st.columns([1, 2])
    with col_a:
        semana_eval = st.number_input("Número de semana", min_value=1, max_value=52,
                                      value=1, step=1, key="ts_semana_eval")
    with col_b:
        dry_eval = st.toggle("Modo prueba — no envía ni guarda cambios", value=True,
                             key="ts_dry_eval")
        if not dry_eval:
            st.warning("Modo prueba desactivado — se evaluarán y enviarán emails reales.")

    if st.button("Ejecutar", type="primary", key="ts_btn_eval"):
        cmd = [python(), "-m", "src.evaluar_respuestas", str(semana_eval)]
        if dry_eval:
            cmd.append("--dry-run")
        _run_section(cmd, "ts_evaluar_out", "ts_evaluar_rc")

    _show_result("ts_evaluar_out", "ts_evaluar_rc")


with tab3:
    st.markdown("Genera el resumen semanal para el profesor a partir de las evaluaciones del CSV.")
    semana_res = st.number_input("Número de semana", min_value=1, max_value=52,
                                 value=1, step=1, key="ts_semana_res")
    st.info("No envía emails ni modifica datos — solo genera un archivo de texto.")

    if st.button("Ejecutar", type="primary", key="ts_btn_res"):
        cmd = [python(), "-m", "src.resumen_semana", str(semana_res)]
        _run_section(cmd, "ts_resumen_out", "ts_resumen_rc")

        resumen_path = runner.tests_data_dir() / f"resumen_semana_{semana_res}.txt"
        if resumen_path.exists():
            st.download_button(
                label="Descargar resumen .txt",
                data=resumen_path.read_text(encoding="utf-8"),
                file_name=resumen_path.name,
                mime="text/plain",
            )

    _show_result("ts_resumen_out", "ts_resumen_rc")

    if st.session_state.ts_resumen_rc == 0:
        resumen_path = runner.tests_data_dir() / f"resumen_semana_{st.session_state.get('ts_semana_res', 1)}.txt"
        if resumen_path.exists() and st.session_state.ts_resumen_out:
            st.download_button(
                label="Descargar resumen .txt",
                data=resumen_path.read_text(encoding="utf-8"),
                file_name=resumen_path.name,
                mime="text/plain",
                key="ts_dl_res_2",
            )
