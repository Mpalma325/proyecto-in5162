"""
Una pregunta de Tareas que cita código que no está en la entrega.

En T2 de 2026-2 el modelo citó `ll.sg2s` y `myparam[3]`, que venían del
material del curso. generar revisa las citas entre comillas invertidas contra
el HTML y el .Rmd de la entrega, rehace la pregunta una vez y, si sigue mal,
deja un aviso en feedback_<T>.csv. Sin red: el modelo está reemplazado.
"""

import csv
import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import check, resultado, semestre_desechable, titulo  # noqa: E402
from modulos.tareas.generar import codigo_ajeno  # noqa: E402

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
check("el texto fuera de comillas invertidas no se revisa",
      codigo_ajeno("¿Qué pasa con myparam si cambia?", texto) == [], None)

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

    def modelo(secciones, roles_html, asignacion, nota="", rehacer=False):
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

sys.exit(resultado())
