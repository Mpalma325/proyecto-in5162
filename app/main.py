import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from utils import runner

st.set_page_config(
    page_title="IN5162",
    page_icon="📚",
    layout="wide",
)


def _mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


@st.cache_data(show_spinner=False)
def _cargar_csv(path: Path, mtime: float | None) -> pd.DataFrame:
    if mtime is None:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")


def _estado_tests() -> dict:
    path = runner.tests_data_dir() / "alumnos.csv"
    try:
        df = _cargar_csv(path, _mtime(path))
    except Exception:
        return {"ok": False}
    if df.empty and not path.exists():
        return {"ok": False}

    envio_cols = [c for c in df.columns if c.startswith("Envío ")]
    semanas_con_envios = []
    for col in envio_cols:
        try:
            n = int(col.replace("Envío ", ""))
            if (df[col] == "SI").any():
                semanas_con_envios.append(n)
        except ValueError:
            pass

    if not semanas_con_envios:
        return {"ok": True, "total": len(df), "semana_activa": None,
                "enviados": 0, "respondieron": 0, "sin_responder": 0, "evaluados": 0}

    s = max(semanas_con_envios)
    col_resp = f"Respuesta {s}"
    col_nota = f"Nota Test {s}"

    enviados = int((df[f"Envío {s}"] == "SI").sum())
    respondieron = int((df[col_resp] != "").sum()) if col_resp in df.columns else 0
    evaluados = int((df[col_nota] != "").sum()) if col_nota in df.columns else 0

    return {
        "ok": True,
        "total": len(df),
        "semana_activa": s,
        "enviados": enviados,
        "respondieron": respondieron,
        "sin_responder": enviados - respondieron,
        "evaluados": evaluados,
    }


def _estado_tareas() -> dict:
    salidas = runner.tareas_salidas_dir()
    csvs = list(salidas.glob("feedback_*.csv")) if salidas.exists() else []
    if not csvs:
        return {"ok": False}

    # La más recientemente modificada es la activa
    latest = max(csvs, key=lambda p: p.stat().st_mtime)
    try:
        df = _cargar_csv(latest, _mtime(latest))
    except Exception:
        return {"ok": False}

    def _count(col: str) -> int:
        return int((df[col] != "").sum()) if col in df.columns else 0

    return {
        "ok": True,
        "tarea": latest.stem.replace("feedback_", "").upper(),
        "total": len(df),
        "enviados": _count("fecha_envio"),
        "respondidos": _count("respuesta"),
        "corregidos": _count("nota"),
    }


def _grafico_tests() -> pd.DataFrame:
    path = runner.tests_data_dir() / "alumnos.csv"
    try:
        df = _cargar_csv(path, _mtime(path))
    except Exception:
        return pd.DataFrame()
    if df.empty and not path.exists():
        return pd.DataFrame()

    rows = []
    for col in df.columns:
        if not col.startswith("Nota Test "):
            continue
        try:
            n = int(col.replace("Nota Test ", ""))
        except ValueError:
            continue

        notas = pd.to_numeric(df[col].replace("", float("nan")), errors="coerce").dropna()
        col_envio = f"Envío {n}"
        col_resp = f"Respuesta {n}"
        enviados = int((df.get(col_envio, pd.Series([""] * len(df))) == "SI").sum())
        respondieron = int((df.get(col_resp, pd.Series([""] * len(df))) != "").sum())

        if enviados == 0 and len(notas) == 0:
            continue

        rows.append({
            "Semana": n,
            "Promedio nota": round(float(notas.mean()), 2) if len(notas) > 0 else None,
            "Tasa de respuesta (%)": round(respondieron / enviados * 100, 1) if enviados > 0 else 0.0,
            "Evaluados": int(len(notas)),
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(sorted(rows, key=lambda x: x["Semana"])).set_index("Semana")


def _grafico_tareas() -> pd.DataFrame:
    salidas = runner.tareas_salidas_dir()
    csvs = sorted(salidas.glob("feedback_*.csv")) if salidas.exists() else []
    if not csvs:
        return pd.DataFrame()

    rows = []
    for path in csvs:
        try:
            df = _cargar_csv(path, _mtime(path))
        except Exception:
            continue
        if df.empty:
            continue

        tarea = path.stem.replace("feedback_", "").upper()
        enviados = int((df.get("fecha_envio", pd.Series(dtype=str)) != "").sum())
        respondieron = int((df.get("respuesta", pd.Series(dtype=str)) != "").sum())
        notas = pd.to_numeric(
            df.get("nota", pd.Series(dtype=str)).replace("", float("nan")),
            errors="coerce",
        ).dropna()

        if enviados == 0 and len(notas) == 0:
            continue

        rows.append({
            "Tarea": tarea,
            "Promedio nota": round(float(notas.mean()), 2) if len(notas) > 0 else None,
            "Tasa de respuesta (%)": round(respondieron / enviados * 100, 1) if enviados > 0 else 0.0,
            "Tasa de corrección (%)": round(len(notas) / respondieron * 100, 1) if respondieron > 0 else 0.0,
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(sorted(rows, key=lambda x: x["Tarea"])).set_index("Tarea")


def _inicio():
    activo = runner.semestre_activo()

    st.title("IN5162 — Panel de control")
    if activo:
        st.caption(f"Semestre activo: **{activo}**")
    else:
        st.warning(
            "No hay ningún semestre activo. Crea uno en "
            "**Datos y Configuración** antes de continuar."
        )
        st.page_link("pages/3_Datos_y_Configuracion.py", label="Ir a Datos y Configuración →")
        return

    st.divider()

    ts = _estado_tests()
    tar = _estado_tareas()

    col_ts, col_tar = st.columns(2, gap="large")

    with col_ts:
        st.subheader("Tests Semanales")
        if not ts["ok"]:
            st.warning("No se encontró `alumnos.csv`. Cárgalo en Datos y Configuración.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Semana activa", ts["semana_activa"] if ts["semana_activa"] else "—")
            c2.metric("Respondieron", ts["respondieron"])
            c3.metric("Sin responder", ts["sin_responder"])
            c4.metric("Evaluados", ts["evaluados"])

            if ts["semana_activa"]:
                if ts["sin_responder"] > 0:
                    st.info(
                        f"{ts['sin_responder']} alumno(s) recibieron la pregunta "
                        f"de la semana {ts['semana_activa']} pero aún no han respondido."
                    )
                elif ts["respondieron"] > ts["evaluados"]:
                    st.info(
                        f"{ts['respondieron'] - ts['evaluados']} respuesta(s) "
                        f"de la semana {ts['semana_activa']} pendientes de evaluación."
                    )
                else:
                    st.success(f"Semana {ts['semana_activa']} completamente evaluada.")

        st.page_link("pages/1_Tests_Semanales.py", label="Ir a Tests Semanales →")

    with col_tar:
        st.subheader("Tareas")
        if not tar["ok"]:
            st.info("Sin tareas activas. Se crean al ejecutar el Paso 1.")
        else:
            st.caption(f"Tarea activa: **{tar['tarea']}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Enviados", tar["enviados"])
            c2.metric("Respondieron", tar["respondidos"])
            c3.metric("Corregidos", tar["corregidos"])

            paso_actual = sum([tar["enviados"] > 0, tar["respondidos"] > 0, tar["corregidos"] > 0])
            pasos = ["Generar", "Enviar", "Recolectar", "Corregir"]
            st.progress(paso_actual / 4, text=f"{tar['tarea']} — siguiente paso: {pasos[paso_actual]}")

        st.page_link("pages/2_Tareas.py", label="Ir a Tareas →")

    st.divider()

    # ── Analítica ──────────────────────────────────────────────────────────
    df_ts = _grafico_tests()
    df_tar = _grafico_tareas()

    if (not df_ts.empty and len(df_ts) >= 2) or not df_tar.empty:
        if not df_ts.empty and len(df_ts) >= 2:
            st.subheader("Analítica — Tests Semanales")
            gc1, gc2 = st.columns(2)

            with gc1:
                st.markdown("**Promedio de nota por semana**")
                serie_notas = df_ts["Promedio nota"].dropna()
                if not serie_notas.empty:
                    st.line_chart(serie_notas)
                else:
                    st.caption("Sin datos de notas todavía.")

            with gc2:
                st.markdown("**Tasa de respuesta por semana (%)**")
                st.line_chart(df_ts["Tasa de respuesta (%)"])

        if not df_tar.empty:
            st.subheader("Analítica — Tareas")
            gc3, gc4 = st.columns(2)

            with gc3:
                st.markdown("**Promedio de nota por tarea**")
                serie_notas_tar = df_tar["Promedio nota"].dropna()
                if not serie_notas_tar.empty:
                    st.bar_chart(serie_notas_tar)
                else:
                    st.caption("Sin datos de notas todavía.")

            with gc4:
                st.markdown("**Tasa de respuesta y corrección por tarea (%)**")
                st.bar_chart(df_tar[["Tasa de respuesta (%)", "Tasa de corrección (%)"]])

        st.divider()


pg = st.navigation([
    st.Page(_inicio, title="Inicio"),
    st.Page("pages/1_Tests_Semanales.py", title="Tests Semanales"),
    st.Page("pages/2_Tareas.py", title="Tareas"),
    st.Page("pages/3_Datos_y_Configuracion.py", title="Datos y Configuración"),
])
pg.run()
