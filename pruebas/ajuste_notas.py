"""
Cambiar una nota a mano: queda en notas.csv, en el log con motivo y nota
anterior, y sobrevive a una reconstrucción desde el log. No manda correos.
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
    check("devuelve la nota anterior y la nueva, con coma", r == {"antes": antes, "despues": "6,5"}, r)
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

sys.exit(resultado())
