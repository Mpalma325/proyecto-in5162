import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from utils.runner import TAREAS_DIR, TESTS_DIR

st.set_page_config(
    page_title="IN5162",
    page_icon="📚",
    layout="wide",
)


def _estado_tests() -> dict:
    path = TESTS_DIR / "data" / "alumnos.csv"
    if not path.exists():
        return {"ok": False}
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    except Exception:
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
    salidas = TAREAS_DIR / "data" / "salidas"
    csvs = list(salidas.glob("feedback_*.csv")) if salidas.exists() else []
    if not csvs:
        return {"ok": False}

    # La más recientemente modificada es la activa
    latest = max(csvs, key=lambda p: p.stat().st_mtime)
    try:
        df = pd.read_csv(latest, encoding="utf-8-sig", dtype=str).fillna("")
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
    path = TESTS_DIR / "data" / "alumnos.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    except Exception:
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


def _inicio():
    ts = _estado_tests()
    tar = _estado_tareas()

    st.title("IN5162 — Panel de control")
    st.divider()

    col_ts, col_tar = st.columns(2, gap="large")

    with col_ts:
        st.subheader("Tests Semanales")
        if not ts["ok"]:
            st.warning("No se encontró `alumnos.csv`. Configura el proyecto en Configuración.")
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
    df_g = _grafico_tests()
    if not df_g.empty and len(df_g) >= 2:
        st.subheader("Analítica — Tests Semanales")
        gc1, gc2 = st.columns(2)

        with gc1:
            st.markdown("**Promedio de nota por semana**")
            serie_notas = df_g["Promedio nota"].dropna()
            if not serie_notas.empty:
                st.line_chart(serie_notas)
            else:
                st.caption("Sin datos de notas todavía.")

        with gc2:
            st.markdown("**Tasa de respuesta por semana (%)**")
            st.line_chart(df_g["Tasa de respuesta (%)"])

        st.divider()

    # ── Estado del sistema ─────────────────────────────────────────────────
    st.subheader("Estado del sistema")
    sc1, sc2 = st.columns(2)

    with sc1:
        st.caption("Tests Semanales")
        for nombre, existe in {
            ".env": (TESTS_DIR / ".env").exists(),
            "data/alumnos.csv": (TESTS_DIR / "data" / "alumnos.csv").exists(),
            "data/preguntas.csv": (TESTS_DIR / "data" / "preguntas.csv").exists(),
        }.items():
            st.markdown(f"{'✅' if existe else '❌'} `{nombre}`")

    with sc2:
        st.caption("Tareas")
        entregas_dir = TAREAS_DIR / "data" / "entregas"
        n_htmls = len(list(entregas_dir.glob("*.html"))) if entregas_dir.exists() else 0
        for nombre, existe in {
            ".env": (TAREAS_DIR / ".env").exists(),
            "data/alumnos.csv": (TAREAS_DIR / "data" / "alumnos.csv").exists(),
            f"data/entregas/ ({n_htmls} HTMLs)": entregas_dir.exists(),
        }.items():
            st.markdown(f"{'✅' if existe else '❌'} `{nombre}`")

    if not (TESTS_DIR / ".env").exists() or not (TAREAS_DIR / ".env").exists():
        st.page_link("pages/4_Configuracion.py", label="Configurar credenciales →")


pg = st.navigation([
    st.Page(_inicio, title="Inicio"),
    st.Page("pages/1_Tests_Semanales.py", title="Tests Semanales"),
    st.Page("pages/2_Tareas.py", title="Tareas"),
    st.Page("pages/3_Datos.py", title="Datos"),
    st.Page("pages/4_Configuracion.py", title="Configuración"),
])
pg.run()
