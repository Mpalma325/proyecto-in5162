"""
Cambiar una nota a mano: queda en notas.csv, en el log con motivo y nota
anterior, y sobrevive a una reconstrucción desde el log. Sin aviso no manda
correos; con aviso, uno en el hilo del último feedback.
"""

import sys

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, enviados, resultado, semestre_desechable, sin_red, titulo  # noqa: E402

with semestre_desechable(sid="_tmp_ajuste") as (sid, tmp), sin_red():
    from modulos import datos
    from modulos.datos import ajustar

    con_nota = [f for f in datos.notas.leer(sid, datos.TESTS) if (f.get("Nota") or "").strip()]
    f = con_nota[0]
    correo, item, antes = f["Correo"], f["Item"], f["Nota"]
    enviados.clear()

    titulo("1. el ajuste cambia la nota y deja constancia")
    r = ajustar.ajustar(datos.TESTS, item, correo, "6.5", "el modelo castigó la firma del correo",
                        "profe@x.cl", sid)
    check("devuelve la nota anterior y la nueva, con coma",
          (r["antes"], r["despues"], r["aviso"]) == (antes, "6,5", None), r)
    check("notas.csv tiene la nota nueva",
          datos.notas.estado(correo, datos.TESTS, item, sid)["Nota"] == "6,5")
    ev = [e for e in datos.log.leer(sid, evento="ajuste") if e["Correo"] == correo.lower()]
    check("el log tiene el evento, con motivo, nota anterior y quién",
          len(ev) == 1 and "castigó la firma" in ev[0]["Detalle"] and f"antes: {antes}" in ev[0]["Detalle"]
          and "profe@x.cl" in ev[0]["Detalle"], ev)
    check("no se mandó ningún correo", enviados == [], enviados)

    titulo("2. sobrevive a una reconstrucción desde el log")
    estado = datos.log.reconstruir_estado(sid)[(correo.lower(), datos.TESTS, item)]
    check("reconstruir_estado toma el ajuste, no la evaluación del modelo", estado["Nota"] == "6,5", estado)

    titulo("3. lo que no corresponde se rechaza")
    for nombre, args in (("nota fuera de escala", ("8,0", "motivo largo")),
                         ("nota mal escrita", ("seis", "motivo largo"))):
        try:
            ajustar.ajustar(datos.TESTS, item, correo, *args, "profe@x.cl", sid)
            check(nombre, False)
        except ValueError:
            check(nombre, True)
    r = ajustar.ajustar(datos.TESTS, item, correo, "6,0", "  ", "profe@x.cl", sid)
    check("sin motivo también se puede", r["despues"] == "6,0", r)
    try:
        ajustar.ajustar(datos.TESTS, "99", correo, "6,0", "motivo largo", "profe@x.cl", sid)
        check("un alumno sin registro en esa semana", False)
    except ValueError:
        check("un alumno sin registro en esa semana", True)

    titulo("4. con aviso: un correo en el hilo del último feedback, sin la etiqueta NOTA FINAL")
    from comun import mensajes
    datos.log.registrar("evaluacion", datos.TESTS, item, correo, sid,
                        MessageId="<feedback-aviso@correo.test>", Nota="6,0")
    enviados.clear()
    mensajes.clear()
    r = ajustar.ajustar(datos.TESTS, item, correo, "6,8", "revisión del equipo", "profe@x.cl", sid,
                        avisar=True)
    check("sale un correo al alumno", enviados == [correo], enviados)
    m = mensajes[-1] if mensajes else {}
    cuerpo = m.get_payload()[0].get_payload(decode=True).decode("utf-8") if mensajes else ""
    check("responde en el hilo del último feedback",
          mensajes and m["In-Reply-To"] == "<feedback-aviso@correo.test>", mensajes and m["In-Reply-To"])
    check("con el asunto de la instancia", mensajes and m["Subject"].startswith("Re: "), mensajes and m["Subject"])
    check("dice la nota nueva y no usa NOTA FINAL", "6,8" in cuerpo and "NOTA FINAL" not in cuerpo.upper(), cuerpo)
    ev = [e for e in datos.log.leer(sid, evento="ajuste") if e["Correo"] == correo.lower()]
    check("el ajuste guarda el Message-ID del aviso", ev and ev[-1]["MessageId"] == r["aviso"] and r["aviso"], ev[-1:])

    titulo("5. sin feedback con Message-ID, el aviso sale como correo nuevo")
    otra = next(x for x in con_nota if x["Correo"] != correo)
    mensajes.clear()
    with_id = [e for e in datos.log.leer(sid, flujo=datos.TESTS, item=otra["Item"])
               if e["Correo"] == otra["Correo"].lower() and e.get("MessageId") and e["Evento"] in ("evaluacion", "ajuste")]
    if not with_id:
        ajustar.ajustar(datos.TESTS, otra["Item"], otra["Correo"], "5,5", "", "profe@x.cl", sid, avisar=True)
        check("sin In-Reply-To", mensajes and not mensajes[-1]["In-Reply-To"], mensajes and mensajes[-1]["In-Reply-To"])
    else:
        check("(la copia ya trae feedback con Message-ID: el caso no aplica)", True)

    titulo("6. una corrección por revisar no se ajusta")
    sin_nota = next(x for x in datos.notas.leer(sid, datos.TESTS) if not (x.get("Nota") or "").strip())
    datos.notas.marcar_corregido(sin_nota["Correo"], datos.TESTS, sin_nota["Item"], semestre_id=sid)
    enviados.clear()
    try:
        ajustar.ajustar(datos.TESTS, sin_nota["Item"], sin_nota["Correo"], "6,0", "", "profe@x.cl", sid, avisar=True)
        check("se rechaza y dice dónde se cambia", False)
    except ValueError as e:
        check("se rechaza y dice dónde se cambia", "Revisar" in str(e), str(e))
    check("y no sale ningún correo", enviados == [], enviados)

    titulo("7. el aviso es solo de Tests")
    tarea = next((x for x in datos.notas.leer(sid, datos.TAREAS) if (x.get("Nota") or "").strip()), None)
    if tarea:
        try:
            ajustar.ajustar(datos.TAREAS, tarea["Item"], tarea["Correo"], "5,0", "", "profe@x.cl", sid, avisar=True)
            check("tareas con aviso se rechaza", False)
        except ValueError:
            check("tareas con aviso se rechaza", True)

    titulo("8. en Tests la nota se valida con la escala del semestre y guarda su logro")
    import json

    from modulos import escala as _escala
    r = ajustar.ajustar(datos.TESTS, item, correo, "6,5", "", "profe@x.cl", sid)
    fila = datos.notas.estado(correo, datos.TESTS, item, sid)
    ev = [e for e in datos.log.leer(sid, evento="ajuste") if e["Correo"] == correo.lower()][-1]
    check("dentro de 4–7: el logro es la inversa (6,5 → 0.8333), en notas.csv y en el log",
          (fila["Logro"], ev["Logro"]) == ("0.8333", "0.8333"), (fila["Logro"], ev["Logro"]))
    r = ajustar.ajustar(datos.TESTS, item, correo, "3,0", "copia comprobada", "profe@x.cl", sid)
    fila = datos.notas.estado(correo, datos.TESTS, item, sid)
    ev = [e for e in datos.log.leer(sid, evento="ajuste") if e["Correo"] == correo.lower()][-1]
    check("bajo la mínima (3,0 en 4–7) se acepta, sin logro: queda fija",
          (r["despues"], fila["Logro"], ev["Logro"]) == ("3,0", "", ""), (r, fila["Logro"], ev["Logro"]))
    for nombre, nota in (("bajo 1,0 en una escala de 4 a 7", "0,5"), ("dos decimales en una escala de uno", "6,55"),
                         ("sobre la máxima", "7,1")):
        try:
            ajustar.ajustar(datos.TESTS, item, correo, nota, "", "profe@x.cl", sid)
            check(f"se rechaza: {nombre}", False)
        except ValueError:
            check(f"se rechaza: {nombre}", True)
    (tmp / _escala.ARCHIVO).write_text(json.dumps({"tipo": "lineal", "minima": 0, "maxima": 100, "decimales": 0}),
                                       encoding="utf-8")
    r = ajustar.ajustar(datos.TESTS, item, correo, "83", "", "profe@x.cl", sid)
    fila = datos.notas.estado(correo, datos.TESTS, item, sid)
    check("con una escala de 0 a 100 vale 83, sin decimales, y su logro", (r["despues"], fila["Logro"]) == ("83", "0.8300"),
          (r, fila["Logro"]))
    try:
        ajustar.ajustar(datos.TESTS, item, correo, "83,5", "", "profe@x.cl", sid)
        check("y rechaza 83,5 (la escala no tiene decimales)", False)
    except ValueError:
        check("y rechaza 83,5 (la escala no tiene decimales)", True)
    if tarea:
        r = ajustar.ajustar(datos.TAREAS, tarea["Item"], tarea["Correo"], "5,0", "", "profe@x.cl", sid)
        check("Tareas no usa la escala de Tests: sigue de 1,0 a 7,0 y sin logro",
              datos.notas.estado(tarea["Correo"], datos.TAREAS, tarea["Item"], sid)["Logro"] == "", r)
    (tmp / _escala.ARCHIVO).unlink()

sys.exit(resultado())
