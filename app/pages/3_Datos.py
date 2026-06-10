import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.runner import TAREAS_DIR, TESTS_DIR

st.title("Datos")


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
    st.success(f"Guardado en `{path.relative_to(path.parent.parent.parent)}`")


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


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Alumnos (Tests)",
    "Preguntas",
    "Alumnos (Tareas)",
    "Feedback Tareas",
    "Archivos de semestre",
])

with tab1:
    st.markdown("Lista de alumnos y seguimiento de tests semanales.")
    _editor_csv(TESTS_DIR / "data" / "alumnos.csv", "ts_alumnos")

with tab2:
    st.markdown(
        "Preguntas, pautas y fechas de entrega por semana. "
        "Columnas: `Semana`, `Tema`, `Fecha de Entrega`, "
        "`Control P1/P2/P3`, `Control Pauta P1/P2/P3`, "
        "`Tratamiento P1/P2/P3`, `Tratamiento Pauta P1/P2/P3`."
    )
    _editor_csv(TESTS_DIR / "data" / "preguntas.csv", "ts_preguntas")

with tab3:
    st.markdown("Lista de alumnos del proyecto de tareas (nombre → correo).")
    _editor_csv(TAREAS_DIR / "data" / "alumnos.csv", "tar_alumnos")

with tab4:
    st.markdown("CSV de estado del pipeline de tareas. Solo lectura — es generado por los scripts.")
    salidas_dir = TAREAS_DIR / "data" / "salidas"
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

with tab5:
    st.markdown("Reemplaza los archivos maestros al inicio de cada semestre.")

    st.subheader("Reemplazar alumnos.csv")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Tests Semanales**")
        up_ts = st.file_uploader("Nuevo alumnos.csv (tests)", type="csv", key="up_ts_alumnos")
        if up_ts:
            df = pd.read_csv(up_ts, dtype=str).fillna("")
            _guardar_csv(df, TESTS_DIR / "data" / "alumnos.csv")

    with col2:
        st.markdown("**Tareas**")
        up_tar = st.file_uploader("Nuevo alumnos.csv (tareas)", type="csv", key="up_tar_alumnos")
        if up_tar:
            df = pd.read_csv(up_tar, dtype=str).fillna("")
            _guardar_csv(df, TAREAS_DIR / "data" / "alumnos.csv")

    st.divider()
    st.subheader("Reemplazar preguntas.csv (Tests)")
    up_preguntas = st.file_uploader("Nuevo preguntas.csv", type="csv", key="up_preguntas")
    if up_preguntas:
        df = pd.read_csv(up_preguntas, dtype=str).fillna("")
        _guardar_csv(df, TESTS_DIR / "data" / "preguntas.csv")

    st.divider()
    st.subheader("Editar prompts")
    prompts_dirs = {
        "Tests Semanales": TESTS_DIR / "prompts",
        "Tareas": TAREAS_DIR / "prompts",
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
