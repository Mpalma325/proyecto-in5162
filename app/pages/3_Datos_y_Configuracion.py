import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils import runner
from utils.runner import TAREAS_DIR, TESTS_DIR

st.title("Datos y Configuración")


# ── Barra de semestre ────────────────────────────────────────────────────

def _barra_semestre() -> None:
    semestres = runner.listar_semestres()
    activo = runner.semestre_activo()

    col_sel, col_nuevo = st.columns([2, 1])

    with col_sel:
        if not semestres:
            st.warning("No hay ningún semestre creado todavía. Crea el primero al lado →")
        else:
            idx = semestres.index(activo) if activo in semestres else 0
            seleccion = st.selectbox("Semestre activo", semestres, index=idx, key="sel_semestre")
            if seleccion != activo:
                runner.set_semestre_activo(seleccion)
                st.rerun()

    with col_nuevo:
        with st.popover("+ Nuevo semestre"):
            st.caption(
                "Crea una carpeta nueva con los CSV y prompts de ejemplo. "
                "No copia los datos del semestre activo actual."
            )
            nuevo_id = st.text_input("Identificador (ej. 2026-2)", key="nuevo_semestre_id")
            if st.button("Crear y activar", key="btn_crear_semestre", type="primary"):
                try:
                    runner.crear_semestre(nuevo_id)
                    runner.set_semestre_activo(nuevo_id)
                    st.success(f"Semestre '{nuevo_id}' creado y activado.")
                    st.rerun()
                except (ValueError, RuntimeError) as e:
                    st.error(str(e))

    _estado_del_sistema()


def _estado_del_sistema() -> None:
    st.subheader("Estado del sistema")

    if not runner.semestre_activo():
        st.info("Selecciona o crea un semestre para ver su estado.")
        return

    sc1, sc2 = st.columns(2)

    with sc1:
        st.caption("Tests Semanales")
        for nombre, existe in {
            ".env (global)": (TESTS_DIR / ".env").exists(),
            "alumnos.csv": (runner.tests_data_dir() / "alumnos.csv").exists(),
            "preguntas.csv": (runner.tests_data_dir() / "preguntas.csv").exists(),
        }.items():
            st.markdown(f"{'✅' if existe else '❌'} `{nombre}`")

    with sc2:
        st.caption("Tareas")
        entregas_dir = runner.tareas_entregas_dir()
        n_htmls = len(list(entregas_dir.glob("*/*.html"))) if entregas_dir.exists() else 0
        n_tareas = len(runner.tareas_conocidas())
        for nombre, existe in {
            ".env (global)": (TAREAS_DIR / ".env").exists(),
            "alumnos.csv": (runner.tareas_data_dir() / "alumnos.csv").exists(),
            f"entregas/ ({n_htmls} HTMLs en {n_tareas} tarea(s))": entregas_dir.exists(),
        }.items():
            st.markdown(f"{'✅' if existe else '❌'} `{nombre}`")

    if not (TESTS_DIR / ".env").exists() or not (TAREAS_DIR / ".env").exists():
        st.warning("Faltan credenciales — configúralas en la pestaña Parámetros de la revisión.")


_barra_semestre()
st.divider()


# ── Datos del curso / Parámetros de la revisión ──────────────────────────

def _leer_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    except Exception as e:
        st.error(f"Error al leer {path.name}: {e}")
        return None


def _guardar_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    st.success(f"Guardado en `{path.name}`")


def _csv_to_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8").encode("utf-8")


def _editor_csv(path: Path, label: str, readonly: bool = False) -> None:
    df = _leer_csv(path)

    if df is None:
        st.warning(f"Archivo no encontrado: `{path.name}`")
        uploaded = st.file_uploader(f"Subir {path.name}", type="csv", key=f"up_{label}")
        if uploaded:
            df = pd.read_csv(uploaded, dtype=str).fillna("")
            _guardar_csv(df, path)
        return

    st.caption(f"{len(df)} filas · {len(df.columns)} columnas · `{path.name}`")

    if readonly:
        st.dataframe(df, use_container_width=True)
    else:
        edited = st.data_editor(
            df,
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_{label}",
        )
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("Guardar cambios", key=f"save_{label}", type="primary"):
                _guardar_csv(edited, path)
        with col2:
            st.download_button(
                "Descargar CSV",
                data=_csv_to_bytes(edited),
                file_name=path.name,
                mime="text/csv",
                key=f"dl_{label}",
            )


tab_datos, tab_config = st.tabs(["Datos del curso", "Parámetros de la revisión"])

with tab_datos:
    if not runner.semestre_activo():
        st.info("Crea o selecciona un semestre arriba para cargar sus datos.")
    else:
        d_tab1, d_tab2, d_tab3, d_tab4, d_tab5, d_tab6 = st.tabs([
            "Alumnos (Tests)",
            "Preguntas",
            "Alumnos (Tareas)",
            "Entregas (Tareas)",
            "Feedback Tareas",
            "Prompts",
        ])

        with d_tab1:
            st.markdown("Lista de alumnos y seguimiento de tests semanales.")
            _editor_csv(runner.tests_data_dir() / "alumnos.csv", "ts_alumnos")

        with d_tab2:
            st.markdown(
                "Preguntas, pautas y fechas de entrega por semana. "
                "Columnas: `Semana`, `Tema`, `Fecha de Entrega`, "
                "`Control P1/P2/P3`, `Control Pauta P1/P2/P3`, "
                "`Tratamiento P1/P2/P3`, `Tratamiento Pauta P1/P2/P3`."
            )
            _editor_csv(runner.tests_data_dir() / "preguntas.csv", "ts_preguntas")

        with d_tab3:
            st.markdown("Lista de alumnos del proyecto de tareas (nombre → correo).")
            _editor_csv(runner.tareas_data_dir() / "alumnos.csv", "tar_alumnos")

        with d_tab4:
            st.markdown(
                "Sube las entregas de U-Cursos: un `.zip` con los HTML de cada grupo "
                "(puede traer un `.zip` anidado por grupo, se abre automáticamente), "
                "o archivos `.html` sueltos."
            )
            tarea_entregas = runner.tarea_selector("entregas")
            entregas_dir = runner.tareas_entregas_dir(tarea=tarea_entregas)
            st.caption(f"Se extraen a `entregas/{tarea_entregas}/` — no se mezclan con otras tareas.")

            subidos = st.file_uploader(
                "Entregas (.zip o .html)",
                type=["zip", "html"],
                accept_multiple_files=True,
                key=f"up_entregas_{tarea_entregas}",
            )
            if subidos and st.button("Procesar entregas", key="btn_procesar_entregas", type="primary"):
                agregados, omitidos = runner.extraer_entregas(subidos, entregas_dir)
                if agregados:
                    st.success(f"{len(agregados)} HTML(s) agregados a `entregas/{tarea_entregas}/`.")
                if omitidos:
                    st.warning(
                        f"{len(omitidos)} archivo(s) omitidos (ya existían o tenían "
                        f"una ruta inválida dentro del zip): {', '.join(omitidos[:10])}"
                    )
                if not agregados and not omitidos:
                    st.info("No se encontraron archivos .html para procesar.")

            existentes = sorted(entregas_dir.glob("*.html")) if entregas_dir.exists() else []
            st.caption(f"{len(existentes)} HTML(s) actualmente en `entregas/{tarea_entregas}/`.")
            if existentes:
                st.dataframe(
                    pd.DataFrame({"Archivo": [p.name for p in existentes]}),
                    use_container_width=True,
                )

        with d_tab5:
            st.markdown("CSV de estado del pipeline de tareas. Solo lectura — es generado por los scripts.")
            salidas_dir = runner.tareas_salidas_dir()
            csvs = sorted(salidas_dir.glob("feedback_*.csv")) if salidas_dir.exists() else []

            if not csvs:
                st.info("No hay archivos de feedback todavía. Se crean al ejecutar el Paso 1 en Tareas.")
            else:
                nombres = [p.name for p in csvs]
                sel = st.selectbox("Selecciona tarea", nombres, key="fb_sel")
                path_sel = salidas_dir / sel

                df = _leer_csv(path_sel)
                if df is not None:
                    st.caption(f"{len(df)} filas · {len(df.columns)} columnas")
                    st.dataframe(df, use_container_width=True)
                    st.download_button(
                        "Descargar CSV",
                        data=_csv_to_bytes(df),
                        file_name=sel,
                        mime="text/csv",
                        key="fb_dl",
                    )

        with d_tab6:
            st.markdown("Prompts y pautas de corrección del semestre activo.")
            prompts_dirs = {
                "Tests Semanales": runner.tests_prompts_dir(),
                "Tareas": runner.tareas_prompts_dir(),
            }
            for proyecto, prompts_dir in prompts_dirs.items():
                if not prompts_dir.exists():
                    continue
                mds = sorted(prompts_dir.glob("*.md"))
                if not mds:
                    continue
                st.markdown(f"**{proyecto}**")
                sel_md = st.selectbox(
                    "Archivo de prompt",
                    [p.name for p in mds],
                    key=f"sel_md_{proyecto}",
                )
                path_md = prompts_dir / sel_md
                contenido = path_md.read_text(encoding="utf-8")
                nuevo = st.text_area(sel_md, value=contenido, height=300, key=f"txt_{proyecto}_{sel_md}")
                if st.button(f"Guardar {sel_md}", key=f"save_md_{proyecto}_{sel_md}"):
                    path_md.write_text(nuevo, encoding="utf-8")
                    st.success(f"Guardado `{sel_md}`")


with tab_config:
    st.caption("Estos parámetros son globales — se comparten entre todos los semestres.")

    ENV_PATHS = {
        "tests_semanales": TESTS_DIR / ".env",
        "tareas": TAREAS_DIR / ".env",
    }

    def _leer_env(path: Path) -> dict:
        env = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        return env

    def _escribir_env(path: Path, updates: dict) -> None:
        env = _leer_env(path)
        env.update({k: v for k, v in updates.items() if v != ""})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"{k}={v}" for k, v in env.items()) + "\n",
            encoding="utf-8",
        )

    # tests_semanales/.env es la fuente de verdad para las variables compartidas
    env_ts = _leer_env(ENV_PATHS["tests_semanales"])
    env_tar = _leer_env(ENV_PATHS["tareas"])

    st.subheader("Credenciales")
    st.markdown(
        "Se guardan en el `.env` de cada subproyecto. "
        "Idénticas en ambos — al guardar se escribe en los dos."
    )

    with st.form("form_creds"):
        api_key = st.text_input(
            "OpenAI API Key",
            value=env_ts.get("OPENAI_API_KEY", ""),
            type="password",
            placeholder="sk-proj-...",
        )
        correo = st.text_input(
            "Correo remitente",
            value=env_ts.get("CORREO_REMITENTE", ""),
            placeholder="in5162@uchile.cl",
        )
        password = st.text_input(
            "App password de Gmail (16 caracteres)",
            value=env_ts.get("CORREO_APP_PASSWORD", ""),
            type="password",
            placeholder="xxxx xxxx xxxx xxxx",
        )
        submitted_creds = st.form_submit_button("Guardar credenciales", type="primary")

    if submitted_creds:
        updates = {}
        if api_key:
            updates["OPENAI_API_KEY"] = api_key
        if correo:
            updates["CORREO_REMITENTE"] = correo
        if password:
            updates["CORREO_APP_PASSWORD"] = password
        if updates:
            _escribir_env(ENV_PATHS["tests_semanales"], updates)
            _escribir_env(ENV_PATHS["tareas"], updates)
            st.success("Credenciales guardadas en ambos proyectos.")

    st.divider()

    st.subheader("Modelo OpenAI")
    st.markdown("Aplica a ambos proyectos.")

    MODELOS_CONOCIDOS = [
        "gpt-5.4-mini",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-nano",
        "gpt-5-mini",
        "gpt-4o-mini",
        "gpt-4o",
    ]
    modelo_actual = env_ts.get("MODELO", "gpt-5.4-mini")

    with st.form("form_modelo"):
        col1, col2 = st.columns(2)
        with col1:
            if modelo_actual in MODELOS_CONOCIDOS:
                modelo = st.selectbox(
                    "Modelo",
                    MODELOS_CONOCIDOS,
                    index=MODELOS_CONOCIDOS.index(modelo_actual),
                )
            else:
                modelo = st.text_input("Modelo", value=modelo_actual)

            temperatura = st.slider(
                "Temperatura",
                min_value=0.0,
                max_value=1.0,
                value=float(env_ts.get("TEMPERATURA", "0.2")),
                step=0.05,
            )
        with col2:
            max_tokens = st.number_input(
                "Max tokens (evaluaciones individuales)",
                min_value=500,
                max_value=8000,
                value=int(env_ts.get("MAX_TOKENS", "3000")),
                step=100,
            )

        submitted_modelo = st.form_submit_button("Guardar configuración de modelo", type="primary")

    if submitted_modelo:
        updates = {
            "MODELO": modelo,
            "TEMPERATURA": str(temperatura),
            "MAX_TOKENS": str(max_tokens),
        }
        _escribir_env(ENV_PATHS["tests_semanales"], updates)
        _escribir_env(ENV_PATHS["tareas"], updates)
        st.success("Configuración de modelo guardada en ambos proyectos.")

    st.divider()

    st.subheader("Escala de notas — Tareas")
    st.markdown("Define el rango de notas que usa GPT para corregir.")

    with st.form("form_notas"):
        col1, col2, col3 = st.columns(3)
        with col1:
            nota_min = st.number_input(
                "Nota mínima",
                min_value=1.0,
                max_value=6.9,
                value=float(env_tar.get("NOTA_MIN", "4.0")),
                step=0.1,
                format="%.1f",
            )
        with col2:
            nota_max = st.number_input(
                "Nota máxima",
                min_value=nota_min + 0.1,
                max_value=10.0,
                value=float(env_tar.get("NOTA_MAX", "7.0")),
                step=0.1,
                format="%.1f",
            )
        with col3:
            tarea_default = st.text_input(
                "Tarea por defecto",
                value=env_tar.get("TAREA_DEFAULT", "T1"),
            )

        submitted_notas = st.form_submit_button("Guardar", type="primary")

    if submitted_notas:
        updates = {
            "NOTA_MIN": f"{nota_min:.1f}",
            "NOTA_MAX": f"{nota_max:.1f}",
            "TAREA_DEFAULT": tarea_default,
        }
        _escribir_env(ENV_PATHS["tareas"], updates)
        st.success("Configuración de notas guardada en Tareas.")

    st.divider()

    st.subheader("Grupos control/tratamiento — Tests Semanales")
    st.markdown(
        "Cuando está activo, cada alumno es asignado aleatoriamente a un grupo "
        "y recibe la pregunta correspondiente."
    )

    with st.form("form_grupos"):
        col1, col2 = st.columns(2)
        with col1:
            grupo_activo = st.toggle(
                "Activar grupos control/tratamiento",
                value=env_ts.get("GRUPO_CONTROL_TRATAMIENTO", "true").lower() == "true",
            )
        with col2:
            grupo_seed = st.number_input(
                "Semilla aleatoria (GRUPO_SEED)",
                min_value=0,
                max_value=99999,
                value=int(env_ts.get("GRUPO_SEED", "19")),
                step=1,
                help="Cambiar la semilla reasigna los grupos.",
            )

        submitted_grupos = st.form_submit_button("Guardar", type="primary")

    if submitted_grupos:
        updates = {
            "GRUPO_CONTROL_TRATAMIENTO": "true" if grupo_activo else "false",
            "GRUPO_SEED": str(grupo_seed),
        }
        _escribir_env(ENV_PATHS["tests_semanales"], updates)
        st.success("Configuración de grupos guardada en Tests Semanales.")
