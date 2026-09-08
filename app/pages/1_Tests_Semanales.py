import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from modulos import datos
from utils import runner
from utils.runner import PROJECT_ROOT, python, run_command, render_output

st.title("Tests Semanales")

for key in ["ts_enviar_out", "ts_enviar_rc",
            "ts_evaluar_out", "ts_evaluar_rc",
            "ts_resumen_out", "ts_resumen_rc",
            "ts_tutoria_out", "ts_tutoria_rc",
            "ts_exp_out", "ts_exp_rc"]:
    if key not in st.session_state:
        st.session_state[key] = None


def _run_section(cmd: list[str], out_key: str, rc_key: str) -> None:
    st.session_state[out_key] = None
    st.session_state[rc_key] = None
    area = st.empty()
    with st.spinner("Ejecutando..."):
        rc, output = run_command(
            cmd, PROJECT_ROOT,
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


tab1, tab2, tab3, tab4, tab5 = st.tabs(["1 · Enviar preguntas", "2 · Evaluar respuestas",
                                        "3 · Resumen semana", "Tutoría",
                                        "Probar un prompt"])

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
        cmd = [python(), "-m", "modulos.tests.enviar", str(semana_env)]
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
        cmd = [python(), "-m", "modulos.tests.evaluar", str(semana_eval)]
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
        cmd = [python(), "-m", "modulos.tests.resumen", str(semana_res)]
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


with tab4:
    st.markdown(
        "Responde las dudas que los alumnos mandan sobre su corrección: por qué "
        "esa nota, qué se esperaba, o algún concepto que les quedó dando vueltas."
    )
    st.info(
        "**La nota no se modifica.** Acá el agente explica y enseña; corregir de "
        "nuevo sería otra cosa.",
        icon="🔒",
    )
    st.caption(
        "Va aparte del ciclo del curso: córrelo cuando quieras. Si nunca lo "
        "corres, no pasa nada — los correos quedan sin leer esperando."
    )

    col_a, col_b = st.columns([1, 2])
    with col_a:
        todas_sem = st.checkbox("Todas las semanas", value=True, key="ts_tut_todas")
        semana_tut = st.number_input("Número de semana", min_value=1, max_value=52,
                                     value=1, step=1, key="ts_semana_tut",
                                     disabled=todas_sem)
    with col_b:
        dry_tut = st.toggle("Modo prueba — no envía emails", value=True, key="ts_dry_tut")
        if not dry_tut:
            st.warning("Modo prueba desactivado — se enviarán respuestas reales.")

    if st.button("Ejecutar", type="primary", key="ts_btn_tut"):
        cmd = [python(), "-m", "modulos.tests.tutoria"]
        if not todas_sem:
            cmd.append(str(semana_tut))
        if dry_tut:
            cmd.append("--dry-run")
        _run_section(cmd, "ts_tutoria_out", "ts_tutoria_rc")

    _show_result("ts_tutoria_out", "ts_tutoria_rc")


with tab5:
    st.markdown(
        "Reevalúa respuestas que el curso **ya corrigió** con un prompt distinto "
        "y las compara una a una contra la nota y la originalidad que se les puso "
        "en su momento. Sirve para ver si un cambio en el prompt mueve la "
        "distribución de originalidad antes de aplicarlo al curso."
    )
    st.info(
        "**No manda correos, no cambia ninguna nota y no escribe en el log.** El "
        "resultado queda en un CSV aparte. Lo único que gasta es API: una llamada "
        "por respuesta.",
        icon="🔬",
    )

    prompt_actual_path = runner.tests_prompts_dir() / "evaluar_respuesta.md"
    if not prompt_actual_path.exists():
        st.error(f"No encuentro el prompt de evaluación en {prompt_actual_path}")
    else:
        st.caption(
            "Empieza con el prompt vigente. Edítalo acá y prueba: el archivo del "
            "semestre no se toca, así que la evaluación real sigue usando el de "
            "siempre hasta que decidas cambiarlo."
        )
        nuevo_prompt = st.text_area(
            "Prompt candidato",
            value=prompt_actual_path.read_text(encoding="utf-8"),
            height=320, key="ts_exp_prompt",
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            n_exp = st.number_input("Cuántas respuestas", min_value=1, max_value=300,
                                    value=20, step=5, key="ts_exp_n",
                                    help="Se eligen al azar entre las que ya tienen nota.")
        with col_b:
            todas_exp = st.checkbox("Todas las semanas", value=True, key="ts_exp_todas")
            semana_exp = st.number_input("Semana", min_value=1, max_value=52, value=1,
                                         step=1, key="ts_exp_semana", disabled=todas_exp)
        with col_c:
            semilla_exp = st.number_input("Semilla", min_value=0, max_value=99999,
                                          value=19, step=1, key="ts_exp_semilla",
                                          help="La misma semilla elige la misma "
                                               "muestra. Deja fija la semilla para "
                                               "comparar dos prompts sobre las "
                                               "mismas respuestas.")

        dry_exp = st.toggle("Solo mostrar la muestra — no llama al modelo",
                            value=True, key="ts_exp_dry")
        if not dry_exp:
            st.warning(
                f"Se harán hasta {n_exp} llamadas reales a la API. Las notas de los "
                f"alumnos no cambian."
            )

        if st.button("Ejecutar", type="primary", key="ts_btn_exp"):
            destino = runner.tests_data_dir() / "prompt_candidato.md"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(nuevo_prompt, encoding="utf-8")

            cmd = [python(), "-m", "modulos.tests.experimento",
                   "--prompt", str(destino), "-n", str(n_exp),
                   "--semilla", str(semilla_exp)]
            if not todas_exp:
                cmd += ["--semana", str(semana_exp)]
            if dry_exp:
                cmd.append("--dry-run")
            _run_section(cmd, "ts_exp_out", "ts_exp_rc")

        _show_result("ts_exp_out", "ts_exp_rc")

        salida = st.session_state.ts_exp_out or ""
        rutas = re.findall(r"^Detalle: (.+)$", salida, re.MULTILINE)
        if rutas and Path(rutas[-1].strip()).exists():
            csv_path = Path(rutas[-1].strip())
            tabla = pd.read_csv(csv_path)

            st.divider()
            st.markdown("#### Comparación 1 a 1")
            columnas = ["Nombre", "Semana", "NotaAntes", "NotaDespues", "DeltaNota",
                        "OriginalidadAntes", "OriginalidadDespues", "DeltaNivel"]
            st.dataframe(tabla[[c for c in columnas if c in tabla.columns]],
                         use_container_width=True, hide_index=True)

            # Las dos distribuciones salen de la misma función que la reportería,
            # así que los porcentajes se calculan igual acá y allá.
            def _dist(columna):
                return {d["Originalidad"].lower(): d
                        for d in datos.reportes.distribucion_originalidad(
                            [{"Originalidad": v} for v in tabla[columna].fillna("")])}

            antes, despues = _dist("OriginalidadAntes"), _dist("OriginalidadDespues")
            etiquetas = sorted(set(antes) | set(despues),
                               key=lambda e: (datos.reportes.nivel_originalidad(e) or 99, e))
            st.markdown("#### Cómo se movió la distribución")
            st.dataframe(pd.DataFrame([{
                "Originalidad": e.title(),
                "Antes": antes.get(e, {}).get("Evaluaciones", 0),
                "Antes %": antes.get(e, {}).get("Porcentaje", 0.0),
                "Después": despues.get(e, {}).get("Evaluaciones", 0),
                "Después %": despues.get(e, {}).get("Porcentaje", 0.0),
            } for e in etiquetas]), use_container_width=True, hide_index=True)

            st.download_button(
                "Descargar el detalle en CSV",
                csv_path.read_bytes(),
                file_name=csv_path.name,
                mime="text/csv",
                key="ts_dl_exp",
            )
