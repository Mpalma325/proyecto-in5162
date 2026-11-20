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

    titulo("5. la revisión: propuesta, lo que salió, quién y los descartes")
    sin_nota = [x for x in datos.notas.leer(sid, datos.TESTS) if not (x.get("Nota") or "").strip()][:3]
    a, b, c = (x["Correo"] for x in sin_nota)
    item = sin_nota[0]["Item"]
    # a: corregida por el modelo y editada en la revisión; b: por revisar; c: descartada.
    for correo in (a, b, c):
        if correo != a:
            item_c = next(x["Item"] for x in sin_nota if x["Correo"] == correo)
        else:
            item_c = item
        datos.log.registrar("correccion", datos.TESTS, item_c, correo, sid, Modelo="gpt-x", Nota="5,0",
                            TokensEntrada="900", TokensSalida="300", Detalle="modo=revisar",
                            EvaluacionIA="<p>NOTA FINAL: 5,0</p>")
        datos.notas.marcar_corregido(correo, datos.TESTS, item_c, semestre_id=sid)
    datos.log.registrar("evaluacion", datos.TESTS, item, a, sid, Modelo="gpt-x", Nota="6,0", MessageId="<fb@x>",
                        EvaluacionIA="<p>NOTA FINAL: 6,0</p>", Detalle="revisado por profe@x.cl; nota 5,0 → 6,0")
    datos.notas.registrar_nota(a, datos.TESTS, item, "6,0", "", sid)
    item_c = next(x["Item"] for x in sin_nota if x["Correo"] == c)
    datos.log.registrar("descarte", datos.TESTS, item_c, c, sid, Detalle="copió; por ayudante@x.cl")
    datos.notas.marcar_descartada(c, datos.TESTS, item_c, semestre_id=sid)
    filas = {(x["Correo"], x["Item"]): x for x in sabana.construir(sid) if x["Flujo"] == datos.TESTS}
    fa = filas[(a.lower(), item)]
    check("editada: nota del modelo, nota enviada y quién revisó",
          (fa["NotaDelModelo"], fa["NotaEnviada"], fa["Editada"], fa["RevisadoPor"], fa["CorregidoPor"],
           fa["ModoRevision"]) == ("5,0", "6,0", "sí", "profe@x.cl", "modelo", "revisar"),
          {k: fa[k] for k in ("NotaDelModelo", "NotaEnviada", "Editada", "RevisadoPor", "CorregidoPor", "ModoRevision")})
    check("los tokens salen de la corrección", fa["TokensEntrada"] == "900", fa["TokensEntrada"])
    check("una edición en la revisión no es un ajuste manual", fa["AjusteManual"] == "no", fa["AjusteManual"])
    fb = next(x for (co, _), x in filas.items() if co == b.lower() and x["NotaDelModelo"] == "5,0")
    check("por revisar: estado propio y sin nota enviada",
          fb["Estado"] == "por revisar" and fb["NotaEnviada"] == "" and fb["Nota"] == "", fb["Estado"])
    fc = next(x for (co, _), x in filas.items() if co == c.lower() and x["Descartada"] == "sí")
    check("descartada: estado, marca y quién", fc["Estado"] == "descartada" and fc["RevisadoPor"] == "ayudante@x.cl",
          (fc["Estado"], fc["RevisadoPor"]))

sys.exit(resultado())
