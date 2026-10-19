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

check("un 7,0 cae en el tramo 6,5–7,0: no hay un tramo 7,0–7,5",
      reportes.distribucion_notas([{"Nota": 7.0}, {"Nota": 6.7}, {"Nota": 6.4}])
      == [{"Tramo": 6.0, "Etiqueta": "6.0–6.5", "Alumnos": 1}, {"Tramo": 6.5, "Etiqueta": "6.5–7.0", "Alumnos": 2}])
for sem, filas in paneles.items():
    barras = {d["Tramo"]: d["Alumnos"] for d in reportes.distribucion_notas(filas)}
    check(f"{sem}: ningún tramo empieza en 7,0", all(tramo < 7.0 for tramo in barras))
    if 6.5 in barras:
        check(f"{sem}: la barra 6,5–7,0 y la lista que abre cuentan lo mismo",
              len(reportes.casillas(filas, tramo=6.5)) == barras[6.5], (len(reportes.casillas(filas, tramo=6.5)), barras[6.5]))

titulo("9. la originalidad se lee como escala ordenada")
check("'Muy Baja' -> 1", reportes.nivel_originalidad("Muy Baja") == 1)
check("'media' -> 3", reportes.nivel_originalidad("media") == 3)
check("'MUY ALTA' -> 5", reportes.nivel_originalidad("MUY ALTA") == 5)
check("vacío -> None", reportes.nivel_originalidad("") is None)
check("una categoría inventada -> None", reportes.nivel_originalidad("regular") is None)

titulo("10. los cortes de originalidad cuadran entre sí")
for sem, filas in paneles.items():
    dist = reportes.distribucion_originalidad(filas)
    if not dist:
        continue
    total = sum(x["Evaluaciones"] for x in dist)
    check(f"{sem}: los porcentajes suman 100",
          abs(sum(x["Porcentaje"] for x in dist) - 100) < 0.5,
          sum(x["Porcentaje"] for x in dist))
    check(f"{sem}: van de menor a mayor nivel",
          [x["Nivel"] for x in dist if x["Nivel"]] ==
          sorted(x["Nivel"] for x in dist if x["Nivel"]))

    por_item = reportes.originalidad_por_item(filas)
    check(f"{sem}: por semana suma lo mismo que el acumulado",
          sum(x["Evaluaciones"] for x in por_item) == total,
          f"{sum(x['Evaluaciones'] for x in por_item)} vs {total}")

    vs_nota = reportes.originalidad_vs_nota(filas)
    check(f"{sem}: contra nota no cuenta más de lo que hay",
          sum(x["Evaluaciones"] for x in vs_nota) <= total)
    check(f"{sem}: las notas medias están en escala",
          all(1.0 <= x["NotaMedia"] <= 7.0 for x in vs_nota),
          [x["NotaMedia"] for x in vs_nota])

    corr = reportes.correlacion_originalidad_nota(filas)
    check(f"{sem}: la correlación está entre -1 y 1",
          corr["R"] is None or -1 <= corr["R"] <= 1, corr["R"])
    # Solo las categorías reconocidas entran a la correlación. Hay etiquetas
    # basura en los semestres viejos ("-", un pedazo de la retroalimentación),
    # que salieron de una extracción que después se arregló: se siguen mostrando
    # en las tablas, pero no se pueden ubicar en la escala 1–5.
    reconocidas = sum(x["Evaluaciones"] for x in vs_nota if x["Nivel"])
    check(f"{sem}: la correlación usa las casillas con las dos cosas",
          corr["N"] == reconocidas, f"{corr['N']} vs {reconocidas}")

titulo("11. correlaciones construidas a mano")
perfecta = [{"Originalidad": o, "Nota": n} for o, n in
            [("Muy Baja", 1.0), ("Baja", 2.0), ("Media", 3.0),
             ("Alta", 4.0), ("Muy Alta", 5.0)]]
check("una relación perfecta da R = 1",
      reportes.correlacion_originalidad_nota(perfecta)["R"] == 1.0)
invertida = [{"Originalidad": f["Originalidad"], "Nota": 6.0 - f["Nota"]} for f in perfecta]
check("invertida da R = -1",
      reportes.correlacion_originalidad_nota(invertida)["R"] == -1.0)
plana = [{"Originalidad": f["Originalidad"], "Nota": 5.0} for f in perfecta]
check("sin variación en la nota, R es None",
      reportes.correlacion_originalidad_nota(plana)["R"] is None)
check("con menos de tres pares, R es None",
      reportes.correlacion_originalidad_nota(perfecta[:2])["R"] is None)

titulo("11b. la pestaña de correlaciones")
ic = reportes.intervalo_r(0.5, 28)
check("intervalo de Fisher para r = 0,5 con 28 datos: de 0,156 a 0,736",
      ic and round(ic[0], 3) == 0.156 and round(ic[1], 3) == 0.736, ic)
check("sin intervalo con r = 1 o con muy pocos datos",
      reportes.intervalo_r(1.0, 30) is None and reportes.intervalo_r(0.3, 3) is None)
check("cuenta las palabras de una respuesta", reportes.palabras("  dos   palabras\n") == 2)
check("sin texto no hay largo (no es cero)", reportes.palabras("  ") is None)
check("horas entre envío y respuesta, con zona horaria",
      reportes.horas_en_responder("2026-10-09T09:00:00-03:00", "2026-10-10T12:30:00+00:00") == 24.5)
check("fechas que no se leen o al revés no dan horas",
      reportes.horas_en_responder("SI", "2026-10-10T12:30:00-03:00") is None
      and reportes.horas_en_responder("2026-10-10T12:00:00-03:00", "2026-10-09T12:00:00-03:00") is None)


def casilla(correo, grupo, item, nota, palabras_resp):
    return {"Correo": correo, "Nombre": correo, "Grupo": grupo, "Item": item, "Enviado": True,
            "EnvioRegistrado": True, "Respondio": nota is not None, "Nota": nota, "Originalidad": "",
            "Respuesta": " ".join(["x"] * palabras_resp), "FechaEnvio": "", "FechaRespuesta": ""}


# Más palabras, mejor nota, exacto: la correlación por alumno tiene que dar 1.
hecho = [casilla(f"a{i}@x.cl", "control" if i % 2 else "tratamiento", "1", 4.0 + i * 0.5, 10 + i * 5)
         for i in range(5)]
m = reportes.correlaciones_por_alumno(hecho)
celda = next(c for c in m["Celdas"] if {c["X"], c["Y"]} == {"NotaMedia", "Palabras"})
check("nota y palabras que suben juntas dan r = 1", celda["R"] == 1.0, celda)
check("sin originalidad ni fechas, esas variables no aparecen",
      [v["Campo"] for v in m["Variables"]] == ["NotaMedia", "Palabras", "Tratamiento"],
      [v["Campo"] for v in m["Variables"]])
solo_control = [f for f in hecho if f["Grupo"] == "control"] + [casilla("z@x.cl", "control", "1", 6.9, 3)]
check("con un solo grupo en el corte, Tratamiento no aparece",
      "Tratamiento" not in [v["Campo"] for v in reportes.correlaciones_por_alumno(solo_control)["Variables"]])
check("por respuesta no lleva intervalo",
      all(c["Bajo"] is None for c in reportes.correlaciones_por_respuesta(hecho)["Celdas"]))

titulo("12. las listas accionables son consistentes")
for sem, filas in paneles.items():
    total = reportes.resumen(filas)
    check(f"{sem}: sin responder cuadra con el KPI",
          len(reportes.sin_responder(filas)) == total["SinResponder"])
    check(f"{sem}: pendientes de evaluar cuadra con el KPI",
          len(reportes.pendientes_de_evaluar(filas)) == total["PendientesEvaluar"])

sys.exit(resultado())
