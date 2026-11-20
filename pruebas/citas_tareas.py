"""
Una pregunta de Tareas que cita código que no está en la entrega, o que cae en
una parte donde el integrante no declaró código.

En T2 de 2026-2 el modelo citó `ll.sg2s` y `myparam[3]`, que venían del
material del curso. generar revisa las citas (entre comillas invertidas, los
nombres con forma de código fuera de ellas y el campo "codigo_citado") contra
el HTML y el .Rmd de la entrega, rehace la pregunta una vez y, si sigue mal,
deja un aviso en feedback_<T>.csv. Lo mismo con la parte de la tarea, que se
compara con la tabla de roles leída en código. Sin red: el modelo está
reemplazado. Todos los nombres son inventados.
"""

import csv
import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402
from modulos.tareas.generar import codigo_ajeno, codigo_suelto  # noqa: E402

RELLENO = "<p>" + "Se estima el modelo con lm() sobre las ventas por semana. " * 50 + "</p>"


def entrega(autores: str) -> bytes:
    """Una entrega sin tabla de roles, con modelo_1..modelo_4 en el código."""
    cuerpo = "".join(f"<p>### Pregunta {n}</p>{RELLENO}<pre><code>modelo_{n} &lt;- lm(y ~ x)</code></pre>"
                     for n in (1, 2, 3, 4))
    return (f'<html><head><title>T9</title></head><body><h4 class="author">{autores}</h4>'
            f"{cuerpo}</body></html>").encode()

titulo("1. qué cuenta como código ajeno")
texto = "modelo_1 <- lm(y ~ x)\nres <- optim(par, fn = ll_norm)\ndatos$precio"
check("lo que está en la entrega no se marca",
      codigo_ajeno("¿Por qué `optim(par, fn = ll_norm)` y `modelo_1`?", texto) == [], None)
check("lo que viene de otra parte sí",
      codigo_ajeno("En `ll.sg2s` usas `myparam[3]`: ¿qué es?", texto) == ["ll.sg2s", "myparam"],
      codigo_ajeno("En `ll.sg2s` usas `myparam[3]`: ¿qué es?", texto))
check("un nombre que contiene a otro no cuenta como presente",
      codigo_ajeno("¿Qué hace `modelo`?", texto) == ["modelo"], codigo_ajeno("¿Qué hace `modelo`?", texto))
check("una función nombrada para contrastar no se marca (pasó con `floor()` en T2)",
      codigo_ajeno("¿Por qué `ceiling()` y no `floor()`?", texto) == [], codigo_ajeno("¿Por qué `ceiling()` y no `floor()`?", texto))
check("un argumento con punto inicial se encuentra (pasó con `.by_group` en T2)",
      codigo_ajeno("¿Qué hace `arrange(x, .by_group = TRUE)`?", texto + "\narrange(x, .by_group = TRUE)") == [],
      codigo_ajeno("¿Qué hace `arrange(x, .by_group = TRUE)`?", texto + "\narrange(x, .by_group = TRUE)"))
check("una palabra suelta sin forma de código no se revisa",
      codigo_ajeno("¿Qué pasa con myparam si cambia?", texto) == [], None)

titulo("1b. código sin comillas invertidas (el prompt de _template prohíbe Markdown)")
r4 = "En la función ll.sg2s, ¿qué representa myparam[3] dentro de la expresión?"
check("el caso de la prueba del 19/11: ll.sg2s y myparam[3] sin comillas",
      codigo_ajeno(r4, texto) == ["ll.sg2s", "myparam"], codigo_ajeno(r4, texto))
check("snake_case ausente se marca, presente no",
      codigo_ajeno("¿Por qué filtraste base_limpia antes de modelo_1?", texto) == ["base_limpia"],
      codigo_ajeno("¿Por qué filtraste base_limpia antes de modelo_1?", texto))
check("un nombre con punto al final de la frase se lee sin el punto",
      codigo_ajeno("¿Qué guarda modelo_1.", texto) == [], codigo_ajeno("¿Qué guarda modelo_1.", texto))
check("una función llamada sin comillas no se revisa (se nombra para contrastar)",
      codigo_ajeno("¿Por qué usaste ceiling() y no read.csv() ni floor()?", texto) == [],
      codigo_ajeno("¿Por qué usaste ceiling() y no read.csv() ni floor()?", texto))
check("las fórmulas de LaTeX no cuentan (\\sum_j, n_i)",
      codigo_ajeno(r"La restricción \(\lfloor n_i/2\rfloor \le \sum_j x_{ij}\) se cumple?", texto) == [],
      codigo_ajeno(r"La restricción \(\lfloor n_i/2\rfloor \le \sum_j x_{ij}\) se cumple?", texto))
castellano = ("¿Por qué, p.ej. en la P2.a y en la p3.b, el modelo (y la(s) variable(s)) usa efectos "
              "fijos por colegio? Explica qué pasa en EE.UU. y en el resto, e.g. en la sección 2, "
              "con la escala de 1.0 a 7.0, etc. Responde en 2-3 oraciones; el profe lo revisa.")
check("en un texto en castellano corriente no hay nada con forma de código",
      codigo_suelto(castellano) == [], codigo_suelto(castellano))
check("el campo codigo_citado se revisa, también las funciones",
      codigo_ajeno("¿Qué representa el tercer parámetro?", texto, ["ll.sg2s()", "modelo_1", "optim"]) == ["ll.sg2s"],
      codigo_ajeno("¿Qué representa el tercer parámetro?", texto, ["ll.sg2s()", "modelo_1", "optim"]))
check("un codigo_citado que viene como texto suelto también sirve",
      codigo_ajeno("¿Qué guarda?", texto, "myalpha") == ["myalpha"], None)

with semestre_desechable(base="_template", sid="_tmp_citas_tareas") as (sid, tmp):
    with (tmp / "alumnos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Nombre", "Correo", "Grupo"])
        w.writerow(["Elena Vidal Araya", "elena@x.cl", ""])
        w.writerow(["Bruno Díaz Lagos", "bruno@x.cl", ""])
    carpeta = tmp / "tareas" / "data" / "entregas" / "T9"
    carpeta.mkdir(parents=True)
    (carpeta / "T9-Elena.html").write_bytes(entrega("Elena Vidal Araya"))
    (carpeta / "T9-Bruno.html").write_bytes(entrega("Bruno Díaz Lagos"))

    from modulos.tareas import generar, storage

    def modelo(secciones, roles_html, asignacion, nota="", rehacer=False, **_):
        """Elena recibe siempre una pregunta ajena; Bruno, una ajena y después una buena."""
        n, parte = next(iter(asignacion.items()))
        if n.startswith("Elena") or not nota:
            q = "¿Qué guarda `ll.sg2s` en `myparam[3]`?"
        else:
            q = "¿Qué estima `modelo_2` con `lm`?"
        return {"integrantes": [{"nombre": n, "pregunta_tarea": parte, "pregunta": q,
                                 "pauta": "-", "motivo_sin_pregunta": None}]}

    titulo("2. generar rehace la pregunta y avisa si sigue mal")
    with patch.object(generar, "generar_preguntas", side_effect=modelo) as m:
        generar.main("T9", sorted(carpeta.glob("*.html")), interactivo=False)
    filas = {f["alumno_nombre"]: f for f in storage.leer_csv("T9")}
    check("se rehízo una vez por cada pregunta ajena (2 entregas, 2 reintentos)", m.call_count == 4, m.call_count)
    check("la nota del reintento nombra lo que no estaba",
          any("ll.sg2s" in (c.kwargs.get("nota") or "") for c in m.call_args_list), m.call_args_list)
    bruno, elena = filas["Bruno Díaz Lagos"], filas["Elena Vidal Araya"]
    check("si el reintento sale bien, queda la nueva y sin aviso",
          "modelo_2" in bruno["pregunta"] and bruno["aviso"] == "", bruno)
    check("si sigue mal, queda el aviso para revisarla",
          "ll.sg2s" in elena["aviso"] and "myparam" in elena["aviso"], elena)
    reintentos = [c for c in m.call_args_list if c.kwargs.get("nota")]
    check("el reintento se pide como «rehacer», sobre la misma parte (vale para grupos con roles)",
          all(c.kwargs.get("rehacer") for c in reintentos)
          and [list(c.args[2].values()) for c in reintentos] == [[bruno["pregunta_tarea"]], [elena["pregunta_tarea"]]],
          reintentos)

    titulo("3. con el mismo nombre dos veces, queda la entrada que trae pregunta")
    unicos = generar._uno_por_nombre([{"nombre": "Ana Soto", "pregunta": None},
                                     {"nombre": "ana  soto", "pregunta": "¿Qué hace `modelo_1`?"}])
    check("una sola, y con pregunta", len(unicos) == 1 and unicos[0]["pregunta"], unicos)

    titulo("4. sin comillas y con codigo_citado: se rehace con las preguntas del resto del grupo")
    for v in carpeta.iterdir():
        v.unlink()
    (carpeta / "T9-Duo.html").write_bytes(entrega("Elena Vidal Araya, Bruno Díaz Lagos"))
    pedidos = []

    def modelo_sin_comillas(secciones, roles_html, asignacion, nota="", rehacer=False, **kw):
        pedidos.append(kw)
        if not rehacer:
            return {"integrantes": [
                {"nombre": "Elena Vidal Araya", "pregunta_tarea": asignacion["Elena Vidal Araya"],
                 "pregunta": "¿Qué estima modelo_1 con lm?", "pauta": "-", "codigo_citado": ["modelo_1", "lm"]},
                {"nombre": "Bruno Díaz Lagos", "pregunta_tarea": asignacion["Bruno Díaz Lagos"],
                 "pregunta": "En la función ll.sg2s, ¿qué representa myparam[3]?", "pauta": "-",
                 "codigo_citado": ["ll.sg2s", "myparam"]}]}
        n, parte = next(iter(asignacion.items()))
        return {"integrantes": [{"nombre": n, "pregunta_tarea": parte, "pregunta": "¿Qué guarda modelo_3?",
                                 "pauta": "-", "codigo_citado": ["modelo_3"]}]}

    with patch.object(generar, "generar_preguntas", side_effect=modelo_sin_comillas) as m:
        generar.main("T7", [carpeta / "T9-Duo.html"], interactivo=False)
    filas = {f["alumno_nombre"]: f for f in storage.leer_csv("T7")}
    check("la pregunta sin comillas que cita código ajeno se rehace", m.call_count == 2, m.call_count)
    check("y queda la nueva, sin aviso",
          filas["Bruno Díaz Lagos"]["pregunta"] == "¿Qué guarda modelo_3?" and not filas["Bruno Díaz Lagos"]["aviso"],
          filas["Bruno Díaz Lagos"])
    check("al rehacer se le pasan las preguntas que ya tiene el resto del grupo",
          pedidos[1].get("evitar") == ["¿Qué estima modelo_1 con lm?"], pedidos[1])

    titulo("5. la parte de la pregunta se compara con la tabla de roles leída en código")
    from modulos.tareas import ia_prompts
    from modulos.tareas.limpieza_html import extraer_tabla_roles, partes_declaradas

    def tabla(filas_roles):
        cuerpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas_roles)
        # Como la deja kable: el caption va dentro de la tabla.
        return ("<table><caption><strong>Tabla 5:</strong> Roles de los Participantes</caption><thead><tr>"
                "<th>Integrante</th><th>Transformaciones</th><th>P1</th><th>P2</th><th>P3</th><th>P4</th>"
                f"<th>Resumen</th></tr></thead><tbody>{cuerpo}</tbody></table>")

    roles = tabla([("Elena Vidal Araya", "código", "código e interpretación", "interpretación", "Código", "—", "código"),
                   ("Bruno Díaz Lagos", "", "", "Revisión de código", "", "ambos", "redacción"),
                   ("Carla Rojas Mena", "código", "interpretación", "redacción", "", "—", "")])
    declaradas = partes_declaradas(extraer_tabla_roles(roles))
    check("Transformaciones y Resumen no cuentan como partes; «ambos» y «Revisión de código» sí",
          declaradas == {"Elena Vidal Araya": ["P1", "P3"], "Bruno Díaz Lagos": ["P2", "P4"],
                         "Carla Rojas Mena": []}, declaradas)
    sub = ("<table><thead><tr><th>Nombre</th><th>p2.a</th><th>p2.b</th><th>Pregunta 3</th></tr></thead>"
           "<tbody><tr><td>Elena Vidal Araya</td><td></td><td>Código</td><td>código</td></tr></tbody></table>")
    check("las columnas por sub-pregunta (p2.a, p2.b) son de su pregunta",
          partes_declaradas(extraer_tabla_roles(sub)) == {"Elena Vidal Araya": ["P2", "P3"]},
          partes_declaradas(extraer_tabla_roles(sub)))
    check("sin columnas de preguntas no se decide nada",
          partes_declaradas([{"Integrante": "Elena", "Resumen": "código"}]) is None)
    bloque = ia_prompts._bloque_roles(declaradas)
    check("al modelo le llegan las partes ya leídas, con «ninguna» para quien no declaró código",
          "- Elena Vidal Araya: P1, P3" in bloque and "- Carla Rojas Mena: ninguna" in bloque, bloque)
    rehacer = ia_prompts._bloque_rehacer({"Elena Vidal Araya": ["P1", "P3"]}, ["¿Qué estima modelo_1?"])
    check("al rehacer se ofrecen sus partes y se piden otras que las del grupo",
          "P1 o P3 (elige una)" in rehacer and "¿Qué estima modelo_1?" in rehacer, rehacer)

    for v in carpeta.iterdir():
        v.unlink()
    (carpeta / "T9-Trio.html").write_bytes(entrega("x").replace(b"</body>", roles.encode() + b"</body>"))
    llamadas = []

    def modelo_roles(secciones, roles_html, asignacion, nota="", rehacer=False, **kw):
        llamadas.append({"asignacion": asignacion, "rehacer": rehacer, **kw})
        if not rehacer and asignacion is None:
            # Las columnas corridas: P2 para Elena (declaró P1 y P3) y P1 para Bruno (P2 y P4).
            return {"integrantes": [
                {"nombre": "Elena Vidal Araya", "pregunta_tarea": "P2", "pregunta": "¿Qué estima modelo_2?", "pauta": "-"},
                {"nombre": "Bruno Díaz Lagos", "pregunta_tarea": "P1", "pregunta": "¿Qué estima modelo_1?", "pauta": "-"},
                {"nombre": "Carla Rojas Mena", "pregunta_tarea": None, "pregunta": None, "pauta": None,
                 "motivo_sin_pregunta": "no declaró código"}]}
        if not rehacer:  # el rescate de Carla, con una parte asignada
            return {"integrantes": [{"nombre": n, "pregunta_tarea": p, "pregunta": f"¿Qué estima modelo_{p[1]}?",
                                     "pauta": "-"} for n, p in asignacion.items()]}
        n, partes = next(iter(asignacion.items()))
        parte = "P3" if n.startswith("Elena") else "P1"  # Bruno insiste en la equivocada
        return {"integrantes": [{"nombre": n, "pregunta_tarea": parte, "pregunta": f"¿Qué estima modelo_{parte[1]}?",
                                 "pauta": "-"}]}

    with patch.object(generar, "generar_preguntas", side_effect=modelo_roles):
        generar.main("T6", [carpeta / "T9-Trio.html"], interactivo=False)
    filas = {f["alumno_nombre"]: f for f in storage.leer_csv("T6")}
    check("al modelo se le pasan las partes declaradas, no el HTML de la tabla",
          llamadas[0].get("declaradas") == declaradas, llamadas[0])
    rehechas = [c for c in llamadas if c["rehacer"]]
    check("se rehace la de quien quedó fuera de sus partes, ofreciéndole las suyas",
          [c["asignacion"] for c in rehechas] == [{"Elena Vidal Araya": ["P1", "P3"]}, {"Bruno Díaz Lagos": ["P2", "P4"]}],
          [c["asignacion"] for c in rehechas])
    check("si la rehecha calza, queda con su parte y sin aviso",
          filas["Elena Vidal Araya"]["pregunta_tarea"] == "P3" and not filas["Elena Vidal Araya"]["aviso"],
          filas["Elena Vidal Araya"])
    check("si no calza, queda la primera con aviso",
          filas["Bruno Díaz Lagos"]["pregunta_tarea"] == "P1"
          and "declaró código en P2, P4" in filas["Bruno Díaz Lagos"]["aviso"], filas["Bruno Díaz Lagos"])
    check("quien no declaró código se rescata con una parte asignada y no se revisa contra la tabla",
          filas["Carla Rojas Mena"]["pregunta"] and not filas["Carla Rojas Mena"]["aviso"], filas["Carla Rojas Mena"])
    check("la rehecha de Bruno sabe qué se les preguntó a los demás",
          "¿Qué estima modelo_3?" in rehechas[1].get("evitar", []), rehechas[1].get("evitar"))

sys.exit(resultado())
