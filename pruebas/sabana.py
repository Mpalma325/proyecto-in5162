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

    titulo("5. tareas: la propuesta del modelo y cuándo salió el correo")
    # Tres casillas de una tarea: una revisada con el flujo nuevo (correccion y
    # después la evaluacion con Message-ID), una de 2026-2 revisada antes de
    # mandarla (evaluacion sin el correo en Versiones, y después 'feedback') y
    # otra de 2026-2 que quedó sin mandar.
    de_tarea = datos.reportes.panel(sid, datos.TAREAS)
    item = de_tarea[0]["Item"]
    nueva, revisada, sin_mandar = [p["Correo"] for p in de_tarea if p["Item"] == item][:3]
    datos.log.registrar("correccion", datos.TAREAS, item, nueva, sid, Modelo="gpt-x", Nota="5.0",
                        TokensEntrada="900", TokensSalida="80", Versiones="corregir_respuesta.md@aaaa1111")
    datos.log.registrar("evaluacion", datos.TAREAS, item, nueva, sid, Modelo="gpt-x", Nota="5.5",
                        MessageId="<feedback-nueva@correo.test>", EvaluacionIA="Comentario revisado.",
                        Versiones="corregir_respuesta.md@aaaa1111; correo_feedback.md@bbbb2222")
    for correo in (revisada, sin_mandar):
        datos.log.registrar("evaluacion", datos.TAREAS, item, correo, sid, Modelo="gpt-x", Nota="4.0",
                            Versiones="corregir_respuesta.md@aaaa1111; escala=-0.3-0.3")
    datos.log.registrar("feedback", datos.TAREAS, item, revisada, sid, Nota="4.0")
    log = {(e["Correo"], e["Evento"]): e["Timestamp"] for e in datos.log.leer(sid, flujo=datos.TAREAS, item=item)}
    filas = {x["Correo"]: x for x in sabana.construir(sid) if x["Flujo"] == datos.TAREAS and x["Item"] == item}
    f = filas[nueva]
    check("flujo nuevo: la nota del modelo y los tokens salen de la corrección; la fecha, de la evaluación",
          f["NotaDelModelo"] == "5.0" and f["TokensEntrada"] == "900"
          and f["FechaEvaluacion"] == log[(nueva, "correccion")]
          and f["FechaFeedback"] == log[(nueva, "evaluacion")], {k: f[k] for k in ("NotaDelModelo", "TokensEntrada",
                                                                                    "FechaEvaluacion", "FechaFeedback")})
    check("2026-2: el 'feedback' cuenta como cuándo salió el correo",
          filas[revisada]["FechaFeedback"] == log[(revisada, "feedback")] and filas[revisada]["NotaDelModelo"] == "4.0",
          filas[revisada]["FechaFeedback"])
    check("2026-2: corregida sin mandar no tiene fecha de feedback", filas[sin_mandar]["FechaFeedback"] == "")
    # En Tests la `evaluacion` es el correo que salió, antes y después de la revisión.
    check("tests: la fecha de feedback es la de la evaluación que salió",
          all(x["FechaFeedback"] == x["FechaEvaluacion"] for x in tests))

    titulo("6. la revisión: propuesta, lo que salió, quién y los descartes")
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

    titulo("7. la escala de la nota y el recálculo")
    import contextlib
    import io
    import json

    from modulos.datos import escala_trabajo
    # b: la evaluación anota la escala en Versiones, como lo hace tests.feedback.
    item_b = fb["Item"]
    datos.log.registrar("evaluacion", datos.TESTS, item_b, b, sid, Nota="6,5", MessageId="<fb-b@x>",
                        Versiones="evaluar_respuesta.md@1a2b3c4d; escala=4-7/1",
                        EvaluacionIA="<p><b>NOTA FINAL:</b> 6,5</p>", Detalle="revisado por profe@x.cl")
    datos.notas.registrar_nota(b, datos.TESTS, item_b, "6,5", "", sid, logro="0.8333")
    filas = {(x["Correo"], x["Item"]): x for x in sabana.construir(sid) if x["Flujo"] == datos.TESTS}
    f_b = filas[(b.lower(), item_b)]
    check("la nota de una evaluación con escala: EscalaNota 4-7/1, sin recalcular",
          (f_b["EscalaNota"], f_b["Recalculada"]) == ("4-7/1", "no"), (f_b["EscalaNota"], f_b["Recalculada"]))
    check("la de 2026-2 (sin escala en Versiones) queda vacía",
          filas[(a.lower(), item)]["EscalaNota"] == "" and filas[(a.lower(), item)]["Recalculada"] == "no")
    with contextlib.redirect_stdout(io.StringIO()):
        escala_trabajo.main(["--escala", json.dumps({"minima": 1.0}), "--por", "profe@x.cl"])
    filas = {(x["Correo"], x["Item"]): x for x in sabana.construir(sid) if x["Flujo"] == datos.TESTS}
    f_b = filas[(b.lower(), item_b)]
    check("después de cambiar la escala: la nota nueva, recalculada, con su escala",
          (f_b["Nota"], f_b["EscalaNota"], f_b["Recalculada"]) == (6.0, "1-7/1", "sí"),
          {k: f_b[k] for k in ("Nota", "EscalaNota", "Recalculada")})
    check("y NotaEnviada sigue diciendo lo que recibió el alumno", f_b["NotaEnviada"] == "6,5", f_b["NotaEnviada"])
    check("un recálculo no es un ajuste manual", f_b["AjusteManual"] == "no", f_b["AjusteManual"])
    sin = next(x for x in filas.values() if x["Nota"] == "")
    check("una casilla sin nota no tiene escala", (sin["EscalaNota"], sin["Recalculada"]) == ("", "no"))

sys.exit(resultado())
