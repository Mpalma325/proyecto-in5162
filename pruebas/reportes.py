"""
Agregaciones de la reportería.

Corre sobre los semestres reales en modo lectura: no escribe nada, y por eso no
necesita copia desechable. Lo que verifica no es el número exacto —cambia cada
semana— sino que las métricas sean coherentes entre sí.

Los dos bugs que motivaron estas comprobaciones eran de ese tipo: una tasa de
respuesta de 114,9% porque los envíos de una semana se hicieron desde otro
equipo y no quedaron registrados, y "pendientes de evaluar" en -87 porque en los
semestres migrados hay nota pero la columna `Respondio` quedó vacía.
"""

import sys

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo

from modulos import semestre
from modulos.datos import reportes

SEMESTRES = [s for s in semestre.listar() if not s.startswith("_")]


def coherencia(nombre, r):
    """Las relaciones que deben cumplirse siempre, en cualquier corte."""
    check(f"{nombre}: sin responder no es negativo", r["SinResponder"] >= 0, r["SinResponder"])
    check(f"{nombre}: pendientes de evaluar no es negativo",
          r["PendientesEvaluar"] >= 0, r["PendientesEvaluar"])
    check(f"{nombre}: tasa de respuesta entre 0 y 100",
          r["TasaRespuesta"] is None or 0 <= r["TasaRespuesta"] <= 100, r["TasaRespuesta"])
    check(f"{nombre}: respondieron <= enviados",
          r["Respondieron"] <= r["Enviados"], f"{r['Respondieron']} > {r['Enviados']}")
    check(f"{nombre}: evaluados <= respondieron",
          r["Evaluados"] <= r["Respondieron"], f"{r['Evaluados']} > {r['Respondieron']}")
    check(f"{nombre}: nota media dentro de escala",
          r["NotaMedia"] is None or 1.0 <= r["NotaMedia"] <= 7.0, r["NotaMedia"])


titulo("1. la nota chilena con coma se lee como numero")
check("'6,5' -> 6.5", reportes.nota_a_float("6,5") == 6.5)
check("'7.0' -> 7.0", reportes.nota_a_float("7.0") == 7.0)
check("vacio -> None", reportes.nota_a_float("") is None)
check("basura -> None", reportes.nota_a_float("sin nota") is None)
check("None -> None", reportes.nota_a_float(None) is None)

titulo("2. cada semestre es coherente consigo mismo")
paneles = {}
for sem in SEMESTRES:
    filas = reportes.filtrar(reportes.panel(sem))
    paneles[sem] = filas
    check(f"{sem}: tiene filas", len(filas) > 0, len(filas))
    if filas:
        coherencia(sem, reportes.resumen(filas))

titulo("3. los cortes suman lo mismo que el total")
for sem, filas in paneles.items():
    if not filas:
        continue
    total = reportes.resumen(filas)
    por_item = reportes.por_item(filas)
    por_alumno = reportes.por_alumno(filas)
    check(f"{sem}: las semanas suman las casillas del total",
          sum(x["Casillas"] for x in por_item) == total["Casillas"])
    check(f"{sem}: los alumnos suman las casillas del total",
          sum(x["Casillas"] for x in por_alumno) == total["Casillas"])
    check(f"{sem}: un alumno por correo distinto",
          len(por_alumno) == total["Alumnos"], f"{len(por_alumno)} vs {total['Alumnos']}")
    check(f"{sem}: una fila por semana distinta",
          len(por_item) == total["Items"], f"{len(por_item)} vs {total['Items']}")

titulo("4. cada semana y cada grupo tambien son coherentes")
for sem, filas in paneles.items():
    for corte in reportes.por_item(filas):
        coherencia(f"{sem} semana {corte['Item']}", corte)
    for corte in reportes.por_grupo(filas):
        coherencia(f"{sem} {corte['Item']}/{corte['Grupo']}", corte)

titulo("5. tener nota implica haber respondido, y responder implica envio")
for sem, filas in paneles.items():
    malas = [f for f in filas if f["Nota"] is not None and not f["Respondio"]]
    check(f"{sem}: nadie con nota sin respuesta", not malas, len(malas))
    malas = [f for f in filas if f["Respondio"] and not f["Enviado"]]
    check(f"{sem}: nadie respondió sin envío", not malas, len(malas))

titulo("6. los filtros recortan de verdad")
sem = SEMESTRES[-1]
filas = paneles[sem]
semanas = reportes.items(filas)
if semanas:
    una = reportes.filtrar(filas, items=[semanas[0]])
    check("filtrar por una semana deja solo esa",
          {f["Item"] for f in una} == {semanas[0]}, {f["Item"] for f in una})
    check("filtrar por una semana reduce el total", len(una) < len(filas))
gs = reportes.grupos(filas)
if len(gs) >= 2:
    solo = reportes.filtrar(filas, grupos=[gs[0]])
    check("filtrar por grupo deja solo ese", {f["Grupo"] for f in solo} == {gs[0]})

titulo("7. la ficha de un alumno trae sus casillas")
if filas:
    correo = filas[0]["Correo"]
    f = reportes.ficha(correo, filas)
    suyas = [x for x in filas if x["Correo"] == correo]
    check("la ficha existe", bool(f))
    check("trae todas sus casillas", len(f["Casillas"]) == len(suyas))
    check("todas son de esa persona", all(c["Correo"] == correo for c in f["Casillas"]))
    coherencia("ficha", f["Resumen"])
    check("un correo inexistente devuelve vacío", reportes.ficha("nadie@x.cl", filas) == {})

titulo("8. las distribuciones cuadran con los evaluados")
for sem, filas in paneles.items():
    total = reportes.resumen(filas)
    dist = reportes.distribucion_notas(filas)
    check(f"{sem}: el histograma suma los evaluados",
          sum(x["Alumnos"] for x in dist) == total["Evaluados"],
          f"{sum(x['Alumnos'] for x in dist)} vs {total['Evaluados']}")
    orig = reportes.distribucion_originalidad(filas)
    check(f"{sem}: originalidad no supera los evaluados",
          sum(x["Evaluaciones"] for x in orig) <= total["Evaluados"])

titulo("9. las listas accionables son consistentes")
for sem, filas in paneles.items():
    total = reportes.resumen(filas)
    check(f"{sem}: sin responder cuadra con el KPI",
          len(reportes.sin_responder(filas)) == total["SinResponder"])
    check(f"{sem}: pendientes de evaluar cuadra con el KPI",
          len(reportes.pendientes_de_evaluar(filas)) == total["PendientesEvaluar"])

sys.exit(resultado())
