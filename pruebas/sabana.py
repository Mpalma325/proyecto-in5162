"""
La sábana de datos: una fila por alumno e ítem, con la pregunta que recibió
según su variante, la pauta, la respuesta, la evaluación y los ajustes.
"""

import sys

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402

with semestre_desechable(sid="_tmp_sabana") as (sid, tmp):
    from modulos import datos, sabana
    from modulos.datos import ajustar

    filas = sabana.construir(sid)
    tests = [f for f in filas if f["Flujo"] == datos.TESTS]

    titulo("1. una fila por alumno e ítem, con todas las columnas")
    check("mismas filas que la reportería de tests", len(tests) == len(datos.reportes.panel(sid, datos.TESTS)))
    check("todas las columnas en el orden declarado", all(list(f) == sabana.COLUMNAS for f in filas))

    titulo("2. la pregunta es la de su variante")
    con_pregunta = [f for f in tests if f["Pregunta"]]
    check("las semanas con preguntas traen pregunta, pauta y tema",
          con_pregunta and all(f["Pauta"] and f["Tema"] for f in con_pregunta), con_pregunta[:1])
    from modulos.tests import preguntas
    f = next(x for x in con_pregunta if x["Variante"] == "tratamiento")
    info = preguntas.cargar_semana(int(f["Item"]))
    check("un alumno de tratamiento recibe la pregunta de tratamiento",
          info.tratamiento.preguntas[0] in f["Pregunta"], f["Pregunta"][:120])

    titulo("3. el ajuste manual se ve")
    ev = next(x for x in tests if x["NotaTexto"])
    ajustar.ajustar(datos.TESTS, ev["Item"], ev["Correo"], "6,8", "prueba de la sábana", "profe@x.cl", sid)
    f2 = next(x for x in sabana.construir(sid) if x["Correo"] == ev["Correo"] and x["Item"] == ev["Item"]
              and x["Flujo"] == datos.TESTS)
    check("nota nueva, nota del modelo aparte y el motivo",
          f2["NotaTexto"] == "6,8" and f2["AjusteManual"] == "sí" and "prueba de la sábana" in f2["MotivoAjuste"],
          {k: f2[k] for k in ("NotaTexto", "NotaDelModelo", "AjusteManual", "MotivoAjuste")})

    titulo("4. la evaluación viene también en texto plano")
    con_eval = [x for x in tests if x["EvaluacionHTML"]]
    import re
    check("sin etiquetas HTML", con_eval and not any(re.search(r"</?(p|br|b|strong|div|span|hr)\b", x["EvaluacionTexto"], re.I) for x in con_eval))

sys.exit(resultado())
