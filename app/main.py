import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from modulos import datos
from utils import runner

st.set_page_config(
    page_title="IN5162",
    page_icon="📚",
    layout="wide",
)

# Altura común de los gráficos, para que la grilla quede pareja.
ALTO = 260

# La originalidad es una escala ordenada (Muy Baja → Muy Alta), no categorías
# sueltas, así que se pinta con un solo tono que va de claro a oscuro. Un color
# distinto por categoría sugeriría que no hay orden entre ellas.
RAMPA_ORIGINALIDAD = ["#d6e4f5", "#a9c7ea", "#6ea8db", "#3d82c4", "#1a5490"]


def _escala_originalidad(etiquetas: list[str]) -> alt.Scale:
    """Asigna el tono según el nivel, no según el orden de aparición.

    Si se filtra a dos semanas y desaparece una categoría, las que quedan
    conservan su color: el tono va pegado al nivel, no al puesto en la lista.
    """
    rango = []
    for e in etiquetas:
        nivel = datos.reportes.nivel_originalidad(e)
        rango.append(RAMPA_ORIGINALIDAD[nivel - 1] if nivel else "#9e9e9e")
    return alt.Scale(domain=etiquetas, range=rango)


@st.cache_data(show_spinner=False)
def _panel(semestre: str, flujo: str, firma: tuple) -> pd.DataFrame:
    """El panel del semestre como DataFrame.

    `firma` son los mtime de los CSV: no se usa dentro, está para que la caché
    se invalide sola cuando los datos cambian en disco.
    """
    return pd.DataFrame(datos.reportes.panel(semestre, flujo))


def _firma(semestre: str) -> tuple:
    raiz = runner.SEMESTRES_DIR / semestre if hasattr(runner, "SEMESTRES_DIR") else None
    if raiz is None:
        from modulos import semestre as _sem
        raiz = _sem.raiz(semestre)
    return tuple(
        (p.stat().st_mtime if p.exists() else 0)
        for p in (raiz / "alumnos.csv", raiz / "notas.csv", raiz / "log_envios.csv")
    )


def _kpi(col, etiqueta: str, valor, sufijo: str = "", ayuda: str | None = None):
    col.metric(etiqueta, "—" if valor is None else f"{valor}{sufijo}", help=ayuda)


def _linea(df: pd.DataFrame, y: str, titulo: str, dominio=None):
    """Serie por ítem. Devuelve None si no hay nada que dibujar."""
    datos_y = df.dropna(subset=[y])
    if datos_y.empty:
        return None
    escala = alt.Scale(domain=dominio) if dominio else alt.Scale(zero=False)
    return (
        alt.Chart(datos_y, height=ALTO, title=titulo)
        .mark_line(point=True)
        .encode(
            x=alt.X("Item:O", title="Semana", sort=list(df["Item"])),
            y=alt.Y(f"{y}:Q", title=titulo, scale=escala),
            tooltip=list(df.columns),
        )
    )


def _seccion_curso(df: pd.DataFrame):
    filas = df.to_dict("records")
    por_item = pd.DataFrame(datos.reportes.por_item(filas))
    if por_item.empty:
        st.info("Todavía no hay datos para graficar.")
        return

    c1, c2 = st.columns(2)
    g = _linea(por_item, "NotaMedia", "Nota media por semana", dominio=[1.0, 7.0])
    if g is not None:
        c1.altair_chart(g, use_container_width=True)
    else:
        c1.caption("Sin notas todavía.")

    g = _linea(por_item, "TasaRespuesta", "Tasa de respuesta por semana (%)", dominio=[0, 100])
    if g is not None:
        c2.altair_chart(g, use_container_width=True)
    else:
        c2.caption("Sin envíos todavía.")

    c3, c4 = st.columns(2)

    dist = pd.DataFrame(datos.reportes.distribucion_notas(filas))
    if not dist.empty:
        c3.altair_chart(
            alt.Chart(dist, height=ALTO, title="Distribución de notas")
            .mark_bar()
            .encode(
                x=alt.X("Etiqueta:O", title="Nota", sort=list(dist["Etiqueta"])),
                y=alt.Y("Alumnos:Q", title="Evaluaciones"),
                tooltip=["Etiqueta", "Alumnos"],
            ),
            use_container_width=True,
        )
    else:
        c3.caption("Sin notas para distribuir.")

    orig = pd.DataFrame(datos.reportes.distribucion_originalidad(filas))
    if not orig.empty:
        c4.altair_chart(
            alt.Chart(orig, height=ALTO, title="Originalidad según el modelo")
            .mark_bar()
            .encode(
                x=alt.X("Originalidad:O", title="", sort=list(orig["Originalidad"])),
                y=alt.Y("Evaluaciones:Q"),
                tooltip=["Originalidad", "Evaluaciones"],
            ),
            use_container_width=True,
        )
    else:
        c4.caption("Sin datos de originalidad.")

    with st.expander("Ver la tabla por semana"):
        st.dataframe(por_item, use_container_width=True, hide_index=True)


def _seccion_originalidad(df: pd.DataFrame):
    """Cómo se reparte la originalidad y qué relación tiene con la nota.

    Son dos juicios del mismo prompt sobre el mismo texto. Verlos juntos es lo
    que permite saber si la originalidad está midiendo algo propio o si viene
    pegada a la nota.
    """
    filas = df.to_dict("records")
    acumulado = pd.DataFrame(datos.reportes.distribucion_originalidad(filas))
    if acumulado.empty:
        st.info(
            "Ninguna evaluación de este corte trae categoría de originalidad. "
            "La escribe el prompt de evaluación en la línea `ORIGINALIDAD:`."
        )
        return

    etiquetas = list(acumulado["Originalidad"])
    escala = _escala_originalidad(etiquetas)
    corr = datos.reportes.correlacion_originalidad_nota(filas)

    k = st.columns(4)
    _kpi(k[0], "Evaluaciones con categoría", int(acumulado["Evaluaciones"].sum()))
    _kpi(k[1], "Nivel medio", corr["NivelMedio"],
         ayuda="Promedio en la escala 1 (Muy Baja) a 5 (Muy Alta).")
    _kpi(k[2], "Nota media de esas casillas", corr["NotaMedia"])
    _kpi(k[3], "Correlación con la nota", corr["R"],
         ayuda="Entre −1 y 1. Cerca de 0, la originalidad y la nota se mueven "
               "por separado; cerca de 1, el modelo le pone mejor nota a quien "
               "le ve más originalidad. Es una correlación de rangos: sirve "
               "para la dirección y la fuerza, no para leerla como regresión.")

    c1, c2 = st.columns(2)

    por_item = pd.DataFrame(datos.reportes.originalidad_por_item(filas))
    nivel_medio = por_item[["Item", "NivelMedio"]].drop_duplicates().dropna()
    if len(nivel_medio) >= 2:
        c1.altair_chart(
            alt.Chart(nivel_medio, height=ALTO, title="Nivel medio de originalidad por semana")
            .mark_line(point=True, strokeWidth=2, color=RAMPA_ORIGINALIDAD[-1])
            .encode(
                x=alt.X("Item:O", title="Semana", sort=list(nivel_medio["Item"])),
                y=alt.Y("NivelMedio:Q", title="Nivel (1 a 5)",
                        scale=alt.Scale(domain=[1, 5])),
                tooltip=["Item", "NivelMedio"],
            ),
            use_container_width=True,
        )
    else:
        c1.caption("Hace falta más de una semana para ver la evolución.")

    if not por_item.empty:
        c2.altair_chart(
            alt.Chart(por_item, height=ALTO, title="Composición por semana (%)")
            .mark_bar(stroke="white", strokeWidth=2)
            .encode(
                x=alt.X("Item:O", title="Semana", sort=list(por_item["Item"].unique())),
                y=alt.Y("Porcentaje:Q", title="% de las evaluadas esa semana",
                        stack="normalize", axis=alt.Axis(format="%")),
                color=alt.Color("Originalidad:N", scale=escala,
                                sort=etiquetas, title="Originalidad"),
                order=alt.Order("Nivel:Q"),
                tooltip=["Item", "Originalidad", "Evaluaciones", "Porcentaje"],
            ),
            use_container_width=True,
        )

    vs_nota = pd.DataFrame(datos.reportes.originalidad_vs_nota(filas))
    if not vs_nota.empty:
        st.altair_chart(
            alt.Chart(vs_nota, height=240, title="Nota media según la originalidad que se le vio")
            .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
            .encode(
                x=alt.X("Originalidad:O", title="", sort=etiquetas),
                y=alt.Y("NotaMedia:Q", title="Nota media",
                        scale=alt.Scale(domain=[1.0, 7.0])),
                color=alt.Color("Originalidad:N", scale=escala, sort=etiquetas,
                                legend=None),
                tooltip=["Originalidad", "Evaluaciones", "NotaMedia", "NotaMin", "NotaMax"],
            ),
            use_container_width=True,
        )
        st.caption(
            "Cada barra es el promedio de las notas que sacaron las respuestas de "
            "esa categoría. La cantidad de evaluaciones detrás de cada una está en "
            "la tabla; una categoría con tres casos no dice lo mismo que una con cien."
        )

    st.divider()
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("**Acumulado del corte**")
        st.dataframe(acumulado[["Originalidad", "Evaluaciones", "Porcentaje"]],
                     use_container_width=True, hide_index=True)
    with t2:
        st.markdown("**Originalidad contra nota**")
        st.dataframe(vs_nota[["Originalidad", "Evaluaciones", "NotaMedia",
                              "NotaMin", "NotaMax"]],
                     use_container_width=True, hide_index=True)

    with st.expander("Ver el detalle por semana"):
        st.dataframe(por_item, use_container_width=True, hide_index=True)


def _seccion_grupos(df: pd.DataFrame):
    filas = df.to_dict("records")
    pg = pd.DataFrame(datos.reportes.por_grupo(filas))
    if pg.empty or pg["Grupo"].nunique() < 2:
        st.info(
            "Este semestre no tiene dos grupos comparables. La división "
            "Control / Tratamiento se activa con `GRUPO_CONTROL_TRATAMIENTO`."
        )
        if not pg.empty:
            st.dataframe(pg, use_container_width=True, hide_index=True)
        return

    st.caption(
        "Control y Tratamiento reciben preguntas distintas sobre el mismo tema. "
        "El grupo de cada alumno se fija una sola vez y no cambia."
    )

    c1, c2 = st.columns(2)
    for col, campo, titulo, dominio in (
        (c1, "NotaMedia", "Nota media por grupo", [1.0, 7.0]),
        (c2, "TasaRespuesta", "Tasa de respuesta por grupo (%)", [0, 100]),
    ):
        sub = pg.dropna(subset=[campo])
        if sub.empty:
            col.caption("Sin datos.")
            continue
        col.altair_chart(
            alt.Chart(sub, height=ALTO, title=titulo)
            .mark_line(point=True)
            .encode(
                x=alt.X("Item:O", title="Semana", sort=list(pg["Item"].unique())),
                y=alt.Y(f"{campo}:Q", title=titulo, scale=alt.Scale(domain=dominio)),
                color=alt.Color("Grupo:N", title="Grupo"),
                tooltip=["Item", "Grupo", "NotaMedia", "TasaRespuesta", "Evaluados"],
            ),
            use_container_width=True,
        )

    # La diferencia entre brazos es el número que interesa del estudio.
    pivote = pg.pivot_table(index="Item", columns="Grupo", values="NotaMedia")
    if {"control", "tratamiento"}.issubset(pivote.columns):
        pivote = pivote.reset_index()
        pivote["Diferencia"] = (pivote["tratamiento"] - pivote["control"]).round(2)
        st.altair_chart(
            alt.Chart(pivote.dropna(subset=["Diferencia"]), height=200,
                      title="Diferencia de nota (Tratamiento − Control)")
            .mark_bar()
            .encode(
                x=alt.X("Item:O", title="Semana", sort=list(pivote["Item"])),
                y=alt.Y("Diferencia:Q", title="Puntos de nota"),
                color=alt.condition(
                    alt.datum.Diferencia > 0,
                    alt.value("#2e7d32"), alt.value("#c62828"),
                ),
                tooltip=["Item", "control", "tratamiento", "Diferencia"],
            ),
            use_container_width=True,
        )

    with st.expander("Ver la tabla por grupo"):
        st.dataframe(pg, use_container_width=True, hide_index=True)


def _seccion_alumnos(df: pd.DataFrame):
    filas = df.to_dict("records")
    pa = pd.DataFrame(datos.reportes.por_alumno(filas))
    if pa.empty:
        st.info("Sin alumnos que mostrar con estos filtros.")
        return

    st.caption("Ordenado de la nota media más baja a la más alta.")
    st.dataframe(
        pa[["Nombre", "Grupo", "NotaMedia", "TasaRespuesta", "Respondieron",
            "Evaluados", "SinResponder", "NotaMin", "NotaMax", "Correo"]],
        use_container_width=True, hide_index=True,
    )

    st.divider()
    st.markdown("#### Ficha individual")
    opciones = {f"{r['Nombre']}  ·  {r['Correo']}": r["Correo"] for r in pa.to_dict("records")}
    elegido = st.selectbox("Alumno", list(opciones.keys()), key="rep_alumno")
    if not elegido:
        return

    ficha = datos.reportes.ficha(opciones[elegido], filas)
    if not ficha:
        return

    r = ficha["Resumen"]
    k = st.columns(5)
    _kpi(k[0], "Nota media", r["NotaMedia"])
    _kpi(k[1], "Respondió", f"{r['Respondieron']}/{r['Enviados']}")
    _kpi(k[2], "Evaluadas", r["Evaluados"])
    _kpi(k[3], "Sin responder", r["SinResponder"])
    _kpi(k[4], "Grupo", ficha["Grupo"] or "—")

    casillas = pd.DataFrame(ficha["Casillas"])
    serie = casillas.dropna(subset=["Nota"])
    if len(serie) >= 2:
        st.altair_chart(
            alt.Chart(serie, height=220, title=f"Notas de {ficha['Nombre']}")
            .mark_line(point=True)
            .encode(
                x=alt.X("Item:O", title="Semana", sort=list(casillas["Item"])),
                y=alt.Y("Nota:Q", scale=alt.Scale(domain=[1.0, 7.0])),
                tooltip=["Item", "Nota", "Originalidad"],
            ),
            use_container_width=True,
        )

    for casilla in ficha["Casillas"]:
        estado = (f"nota {casilla['NotaTexto']}" if casilla["NotaTexto"]
                  else "respondió, sin evaluar" if casilla["Respondio"]
                  else "sin responder")
        with st.expander(f"Semana {casilla['Item']} — {estado}"):
            if casilla["Respuesta"]:
                st.markdown("**Lo que respondió**")
                st.text(casilla["Respuesta"])
            else:
                st.caption("No hay texto de respuesta guardado.")
            if casilla["EvaluacionIA"]:
                st.markdown("**Lo que le respondió el agente**")
                st.markdown(casilla["EvaluacionIA"], unsafe_allow_html=True)
            if casilla["Modelo"]:
                st.caption(f"Modelo: {casilla['Modelo']}")


def _seccion_pendientes(df: pd.DataFrame):
    filas = df.to_dict("records")
    cols = ["Nombre", "Item", "Grupo", "Correo"]

    sin_resp = datos.reportes.sin_responder(filas)
    st.markdown(f"#### Sin responder — {len(sin_resp)}")
    if sin_resp:
        st.dataframe(pd.DataFrame(sin_resp)[cols], use_container_width=True, hide_index=True)
    else:
        st.success("Todos respondieron lo que se les envió.")

    st.divider()
    pend = datos.reportes.pendientes_de_evaluar(filas)
    st.markdown(f"#### Respondieron pero no tienen nota — {len(pend)}")
    if pend:
        st.caption(
            "Puede ser que respondieran después de la fecha de revisión, en cuyo "
            "caso no corresponde evaluarlos."
        )
        st.dataframe(pd.DataFrame(pend)[cols], use_container_width=True, hide_index=True)
    else:
        st.success("No hay respuestas pendientes de evaluación.")


def _inicio():
    activo = runner.semestre_activo()
    st.title("IN5162 — Reportería")

    if not activo:
        st.warning(
            "No hay ningún semestre activo. Crea uno en "
            "**Datos y Configuración** antes de continuar."
        )
        st.page_link("pages/3_Datos_y_Configuracion.py", label="Ir a Datos y Configuración →")
        return

    disponibles = runner.listar_semestres() or [activo]
    cab1, cab2 = st.columns([1, 3])
    with cab1:
        semestre = st.selectbox(
            "Semestre", disponibles,
            index=disponibles.index(activo) if activo in disponibles else 0,
            key="rep_semestre",
            help="Solo cambia lo que se ve acá. El semestre sobre el que operan "
                 "los envíos se cambia en Datos y Configuración.",
        )
    with cab2:
        if semestre != activo:
            st.warning(
                f"Estás viendo **{semestre}**, pero el semestre activo —sobre el "
                f"que corren los envíos— es **{activo}**.",
                icon="👁️",
            )

    try:
        df = _panel(semestre, datos.TESTS, _firma(semestre))
    except Exception as e:
        st.error(f"No pude leer los datos de {semestre}: {e}")
        return

    if df.empty:
        st.info(f"El semestre {semestre} todavía no tiene datos de tests semanales.")
        return

    df = df[df["EnRoster"]]
    todas = datos.reportes.items(df.to_dict("records"))
    todos_grupos = datos.reportes.grupos(df.to_dict("records"))

    f1, f2 = st.columns([3, 2])
    semanas = f1.multiselect("Semanas", todas, default=todas, key="rep_semanas")
    grupos_sel = f2.multiselect("Grupos", todos_grupos, default=todos_grupos, key="rep_grupos")

    filas = datos.reportes.filtrar(df.to_dict("records"), items=semanas, grupos=grupos_sel)
    if not filas:
        st.warning("Los filtros no dejan ninguna fila.")
        return

    vista = pd.DataFrame(filas)
    r = datos.reportes.resumen(filas)

    k = st.columns(6)
    _kpi(k[0], "Alumnos", r["Alumnos"])
    _kpi(k[1], "Semanas", r["Items"])
    _kpi(k[2], "Tasa de respuesta", r["TasaRespuesta"], "%",
         "Respondieron sobre los que recibieron la pregunta.")
    _kpi(k[3], "Nota media", r["NotaMedia"])
    _kpi(k[4], "Evaluadas", r["Evaluados"])
    _kpi(k[5], "Sin responder", r["SinResponder"])

    if r["EnviosSinRegistro"]:
        st.caption(
            f"⚠ {r['EnviosSinRegistro']} casilla(s) sin registro de envío: se dan "
            f"por enviadas porque hay respuesta o nota. Pasa cuando el envío se "
            f"hizo desde otro equipo."
        )
    if r["Modelos"]:
        st.caption(f"Modelos registrados: {', '.join(r['Modelos'])}")

    st.divider()
    t1, t2, t3, t4, t5 = st.tabs(["Curso", "Originalidad", "Grupos", "Alumnos",
                                  "Pendientes"])
    with t1:
        _seccion_curso(vista)
    with t2:
        _seccion_originalidad(vista)
    with t3:
        _seccion_grupos(vista)
    with t4:
        _seccion_alumnos(vista)
    with t5:
        _seccion_pendientes(vista)

    st.divider()
    st.download_button(
        "Descargar el panel en CSV",
        vista.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"panel_{semestre}_tests.csv",
        mime="text/csv",
    )


pg = st.navigation([
    st.Page(_inicio, title="Reportería"),
    st.Page("pages/1_Tests_Semanales.py", title="Tests Semanales"),
    st.Page("pages/2_Tareas.py", title="Tareas"),
    st.Page("pages/3_Datos_y_Configuracion.py", title="Datos y Configuración"),
])
pg.run()
