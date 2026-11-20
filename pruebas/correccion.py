"""
La corrección de un test: modulos/tests/correccion.py y su gemela de la página,
web/public/correccion.js.

1. Lo que hace el Python: leer el JSON nuevo o el HTML viejo, validar los
   puntajes contra la rúbrica, calcular logro y nota con la escala, armar el
   bloque del correo según correo_muestra y el texto para el docente.
2. Python y JS dan lo mismo con las mismas entradas, en cinco escalas. El caso
   principal es `nota` (puntajes y nota en el correo), que es lo que trae la
   plantilla de un semestre nuevo; `puntajes` y `nada` van después.
3. De punta a punta: evaluar con la corrección en JSON, sobre una copia de
   2026-2 con escala y configuración propias, sin red y sin correos reales.
"""

import contextlib
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import (check, enviados, puntajes_ia, resultado, respuestas_falsas,  # noqa: E402
                   semestre_desechable, sin_red, titulo)

from modulos import escala as E  # noqa: E402
from modulos.tests import correccion as C  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent

titulo("1. leer y calcular")
c = C.leer(puntajes_ia(3, 2), E.POR_DEFECTO, 2)
check("JSON con 3 y 2 sobre 3: logro 5/6, nota 6,5 en 4–7",
      (c["formato"], c["puntajes"], c["logro"], c["nota"]) == (C.JSON, "3;2", "0.8333", "6,5"), c)
check("sin problemas ni avisos", c["problemas"] == [] and c["avisos"] == [], c)
check("trae respuesta, justificación, originalidad y retroalimentación",
      c["preguntas"][0]["respuesta"] == "Lo que respondió a P1." and c["originalidad"] == "Media"
      and c["retroalimentacion"] == "Bien encaminado.")
check("el JSON envuelto en ```json``` también se lee",
      C.leer("```json\n" + puntajes_ia(3, 3) + "\n```")["nota"] == "7,0")
check("0,5 y 0: el empate 4,25 redondea hacia arriba (4,3)", C.leer(puntajes_ia(0.5, 0))["nota"] == "4,3")
dos = E.Escala(decimales=2)
check("con dos decimales queda 4,25", C.leer(puntajes_ia(0.5, 0), dos)["nota"] == "4,25")
check("los puntajes se aceptan como número o texto, con coma o punto",
      C.leer(puntajes_ia("2,0", "0.5", 3.0))["puntajes"] == "2;0.5;3")
mala = C.leer(puntajes_ia(3, 1.5))
check("1,5 no está en la rúbrica: sin nota y con el problema dicho",
      (mala["nota"], mala["puntajes"], mala["logro"]) == ("", "", "")
      and mala["problemas"] == ["P2: el puntaje «1.5» no está en la rúbrica (0; 0,5; 1; 2; 3)."], mala)
for nombre, valor in (("un booleano", True), ("vacío", None), ("una lista", [3]), ("un 4", 4), ("texto", "tres")):
    check(f"puntaje inválido: {nombre}", C.leer(puntajes_ia(valor))["problemas"] != [])
check("sin preguntas: «La corrección no trae preguntas.»",
      C.leer('{"preguntas": []}')["problemas"] == ["La corrección no trae preguntas."])
menos = C.leer(puntajes_ia(3), E.POR_DEFECTO, 3)
check("un bloque para tres preguntas: avisa y la nota sale sobre un bloque",
      menos["nota"] == "7,0" and menos["avisos"] == ["La IA devolvió 1 bloque para 3 preguntas: puede haber juntado "
                                                       "preguntas. La nota se calculó sobre 1 bloque."], menos)
check("tres bloques para una pregunta también avisa",
      C.leer(puntajes_ia(3, 3, 3), E.POR_DEFECTO, 1)["avisos"] == ["La IA devolvió 3 bloques para 1 pregunta."])
viejo = C.leer("<p>Bien.</p><p><b>NOTA FINAL:</b> 6,5</p><p><b>ORIGINALIDAD:</b> Alta</p>")
check("el HTML viejo: su NOTA FINAL, su originalidad y el logro de la inversa",
      (viejo["formato"], viejo["nota"], viejo["originalidad"], viejo["logro"]) == (C.HTML, "6,5", "Alta", "0.8333"))
check("un JSON sin «preguntas» no es del formato nuevo", C.leer('{"nota": 7}')["formato"] == C.HTML)
check("con otra escala, otra nota: 3 y 2 en 1–7 es 6,0",
      C.leer(puntajes_ia(3, 2), E.Escala(minima=1))["nota"] == "6,0")
check("y en la del 60 %, 5,8 (5,75 hacia arriba)",
      C.leer(puntajes_ia(3, 2), E.Escala(tipo="dos_tramos", minima=1, aprobacion=4, exigencia=0.6))["nota"] == "5,8")

titulo("2. el bloque del correo según correo_muestra")
html = C.armar_html(c, C.NOTA)
check("nota: cada pregunta con su EVALUACIÓN x / 3, PUNTAJE TOTAL y NOTA FINAL",
      "<b>EVALUACIÓN:</b> 3 / 3 puntos" in html and "<b>PUNTAJE TOTAL:</b> 5 de 6 puntos" in html
      and "<b>NOTA FINAL:</b> 6,5" in html and "<u>P2.</u>" in html, html)
html = C.armar_html(c, C.PUNTAJES)
check("puntajes: las EVALUACIÓN quedan; sin total ni nota",
      "EVALUACIÓN:" in html and "PUNTAJE TOTAL" not in html and "NOTA FINAL" not in html, html)
html = C.armar_html(c, C.NADA)
check("nada: sin ningún número", not any(x in html for x in ("EVALUACIÓN:", "PUNTAJE TOTAL", "NOTA FINAL")), html)
uno = C.leer(puntajes_ia(2))
check("con una sola pregunta no hay rótulo ni total",
      "<u>" not in C.armar_html(uno, C.NOTA) and "PUNTAJE TOTAL" not in C.armar_html(uno, C.NOTA))
raro = C.leer(json.dumps({"preguntas": [{"respuesta": "a < b & \"c\"\nfin", "puntaje": 3}]}))
check("lo del alumno se escapa y los saltos pasan a <br>",
      "a &lt; b &amp; &quot;c&quot;<br>\nfin" in C.armar_html(raro, C.NOTA), C.armar_html(raro, C.NOTA))
check("sin nota (puntaje inválido) no hay NOTA FINAL aunque la muestra sea nota",
      "NOTA FINAL" not in C.armar_html(mala, C.NOTA))
legado = "<p>P1.<br><b>EVALUACIÓN:</b> 3/3<br>bien</p><p><b>PUNTAJE TOTAL:</b> 6<br><b>NOTA FINAL:</b> 6,5</p>"
check("el HTML viejo con nota sale tal cual", C.armar_html(C.leer(legado), C.NOTA) == legado)
check("el HTML viejo con puntajes pierde total y nota",
      C.armar_html(C.leer(legado), C.PUNTAJES) == "<p>P1.<br><b>EVALUACIÓN:</b> 3/3<br>bien</p>")
check("y con nada, también las EVALUACIÓN", C.armar_html(C.leer(legado), C.NADA) == "<p>P1.<br>bien</p>")
docente = C.texto_docente(mala)
check("para el docente siempre hay NOTA FINAL (o «sin nota») y los avisos",
      "NOTA FINAL: sin nota" in docente and "AVISO: P2: el puntaje" in docente, docente)
check("pide_json: el prompt con JSON y «\"puntaje\"»",
      C.pide_json('Devuelve JSON: {"puntaje": 3}') and not C.pide_json("Termina con NOTA FINAL:")
      and not C.pide_json("Escribe en JSON la nota"))
plantilla = (RAIZ / "semestres" / "_template" / "tests_semanales" / "prompts" / "evaluar_respuesta.md").read_text(
    encoding="utf-8")
check("el prompt de la plantilla pide JSON", C.pide_json(plantilla))

titulo("3. lo que cambia el docente en Revisar")
nueva, cambios = C.aplicar(c, {"puntajes": ["3", "3"]})
check("subir un puntaje recalcula la nota: 3;2 → 3;3 da 7,0",
      nueva["nota"] == "7,0" and cambios == ["puntajes 3;2 → 3;3"], (nueva["nota"], cambios))
nueva, cambios = C.aplicar(c, {"originalidad": "Alta", "retroalimentacion": "Otra cosa."})
check("originalidad y retroalimentación quedan en los cambios",
      cambios == ["originalidad Media → Alta", "retroalimentación"] and nueva["nota"] == "6,5", cambios)
nueva, _ = C.aplicar(c, {"puntajes": ["1.5", None]})
check("un puntaje fuera de la rúbrica deja la corrección sin nota", nueva["nota"] == "" and nueva["problemas"])
manual = C.desde_decision({"puntajes": ["3", "0.5"], "justificaciones": ["a", "b"], "originalidad": "Baja"}, 2)
check("la corrección a mano del docente, con puntajes: 3 y 0,5 dan 5,8",
      manual["nota"] == "5,8" and manual["preguntas"][1]["justificacion"] == "b", manual["nota"])
check("a mano con un puntaje vacío no tiene nota", C.desde_decision({"puntajes": ["3", ""]}, 2)["nota"] == "")


# --------------------------------------------------------------- Python contra JS

def _plano(v):
    if isinstance(v, Fraction):
        return str(v)
    if isinstance(v, (list, tuple)):
        return [_plano(x) for x in v]
    if isinstance(v, dict):
        return {k: _plano(x) for k, x in v.items()}
    return v


ESCALAS = {
    "4-7/1": E.POR_DEFECTO,
    "1-7/1": E.Escala(minima=1.0),
    "60 %": E.Escala(tipo="dos_tramos", minima=1.0, aprobacion=4.0, exigencia=0.6),
    "0-100/0": E.Escala(minima=0, maxima=100, decimales=0),
    "4-7/2": E.Escala(decimales=2),
}
TEXTOS = {
    "dos preguntas": (puntajes_ia(3, 2), 2),
    "el empate": (puntajes_ia(0.5, 0), 2),
    "una pregunta": (puntajes_ia(1), 1),
    "en ```json```": ("```json\n" + puntajes_ia(2, 3, 0.5) + "\n```", 3),
    "1,5 inválido": (puntajes_ia(3, 1.5), 2),
    "tipos raros": (json.dumps({"preguntas": [{"puntaje": "2,0"}, {"puntaje": 3.0}, {"puntaje": True},
                                              {"puntaje": None}, {"puntaje": [1]}, {}]}), 6),
    "sin preguntas": ('{"preguntas": []}', 2),
    "menos bloques": (puntajes_ia(2), 3),
    "más bloques": (puntajes_ia(2, 2, 2), 2),
    "escapes": (json.dumps({"preguntas": [{"rotulo": "P1.", "respuesta": "a < b & \"c\"\r\nfin", "puntaje": 3,
                                           "justificacion": "x > y"}, {"puntaje": 0}],
                            "originalidad": "Alta <b>", "justificacion_originalidad": "línea 1\nlínea 2",
                            "retroalimentacion": "Sigue así & mejora"}), 2),
    "HTML viejo": ("<p>Bien.</p>\n<p><b>EVALUACIÓN:</b> 3 / 3<br>\n<b>NOTA FINAL:</b> 6.5</p>\n"
                   "<p><b>ORIGINALIDAD:</b> Media. Algo más</p>", 1),
    "HTML en ```html```": ("```html\n<p>NOTA FINAL: 5,0</p>\n<p>PUNTAJE TOTAL: 3</p>\n```", 1),
    "texto sin nota": ("Hola, no sé qué pasó.", 1),
    "JSON sin preguntas": ('{"nota": 7}', 1),
    "vacío": ("", 1),
}
llamadas, esperado, nombres = [], [], []


def comparar(nombre: str, f: str, args: list, valor) -> None:
    llamadas.append({"f": f, "args": args})
    esperado.append(_plano(valor))
    nombres.append(nombre)


# Primero todo con `nota`, el caso principal; después las otras dos muestras.
for muestra in (C.NOTA, C.PUNTAJES, C.NADA):
    for ne, escala in ESCALAS.items():
        e = escala.como_dict()
        for nt, (texto, n) in TEXTOS.items():
            leida = C.leer(texto, escala, n)
            if muestra == C.NOTA:
                comparar(f"leer · {nt} · {ne}", "correccion.leer", [texto, e, n], leida)
                comparar(f"texto para el docente · {nt} · {ne}", "correccion.textoDocente", [leida, e],
                         C.texto_docente(leida, escala))
            comparar(f"correo con {muestra} · {nt} · {ne}", "correccion.armarHtml", [leida, muestra, e],
                     C.armar_html(leida, muestra, escala))
base = C.leer(TEXTOS["dos preguntas"][0])
for i, decision in enumerate(({}, {"puntajes": ["3", "3"]}, {"puntajes": ["1.5", None]}, {"puntajes": [2]},
                              {"justificaciones": ["Otra.", "Justificación de P2."]}, {"justificaciones": [5]},
                              {"originalidad": " Alta "}, {"originalidad": "Media"}, {"retroalimentacion": "Nueva."},
                              {"puntajes": ["0.5", "0,5"], "originalidad": "Baja", "retroalimentacion": "x"}), 1):
    for ne in ("4-7/1", "60 %"):
        nueva, cambios = C.aplicar(base, decision, ESCALAS[ne])
        comparar(f"aplicar {i} · {ne}", "correccion.aplicar", [base, decision, ESCALAS[ne].como_dict()],
                 {"correccion": nueva, "cambios": cambios})
for i, (decision, n) in enumerate((({"puntajes": ["3", "2"], "justificaciones": ["a", "b"], "originalidad": "Media",
                                     "retroalimentacion": "r"}, 2), ({"puntajes": ["3", ""]}, 2), ({}, 2),
                                   ({"puntajes": [3, 0.5, "1"]}, 1), (None, 1)), 1):
    comparar(f"a mano {i}", "correccion.desdeDecision", [decision, n, E.POR_DEFECTO.como_dict()],
             C.desde_decision(decision, n, E.POR_DEFECTO))
for muestra in (C.NOTA, C.PUNTAJES, C.NADA):
    for i, h in enumerate((TEXTOS["HTML viejo"][0],
                           "<p><strong>PUNTAJE TOTAL:</strong> 5<br/>\n<strong>NOTA FINAL</strong>: 6,0<br></p>",
                           "<p>EVALUACION: 2<br>EVALUACIÓN: 3</p><p>nota final 5</p>"), 1):
        comparar(f"quitar números {i} · {muestra}", "correccion.quitarNumeros", [h, muestra], C.quitar_numeros(h, muestra))
for ne, escala in ESCALAS.items():
    e = escala.como_dict()
    comparar(f"rúbrica · {ne}", "correccion.textoRubrica", [e], C.texto_rubrica(escala))
    comparar(f"describir · {ne}", "escala.describir", [e], escala.describir())
    comparar(f"rango · {ne}", "escala.rango", [e], escala.rango())
    for logro in ("0", "0.25", "0.5", "0.6", "0.75", "0.8333", "1"):
        comparar(f"nota del logro {logro} · {ne}", "escala.nota", [e, logro], escala.texto(escala.nota(logro)))
    for nota in ("1,0", "3,0", "4,0", "5,75", "6,5", "7,0", "83", "100"):
        comparar(f"inversa de {nota} · {ne}", "escala.logro", [e, nota], escala.logro(nota))
    for nota in ("6,25", "4,15", "82,5"):
        comparar(f"redondeo de {nota} · {ne}", "escala.texto", [e, nota], escala.texto(nota))
rubrica_2 = E.Escala(puntaje_maximo_pregunta=2)
comparar("rúbrica con máximo 2", "correccion.textoRubrica", [rubrica_2.como_dict()], C.texto_rubrica(rubrica_2))
comparar("con máximo 2, el 3 no vale", "correccion.leer", [puntajes_ia(3, 2), rubrica_2.como_dict(), 2],
         C.leer(puntajes_ia(3, 2), rubrica_2, 2))
for prompt in ("Devuelve JSON con {\"puntaje\": 3}", "Termina con NOTA FINAL:", "json \"puntaje\"", plantilla, None):
    comparar(f"pide JSON · {str(prompt)[:20]!r}", "correccion.pideJson", [prompt], C.pide_json(prompt))

# Revisar: lo que sale en el correo, con la decisión del docente encima.
from modulos.tests import decisiones as D  # noqa: E402

fila_modelo = {"EvaluacionIA": TEXTOS["dos preguntas"][0], "Nota": "", "Modelo": "modelo-x"}
fila_docente = {"EvaluacionIA": "", "Nota": "", "Modelo": "docente:profe@correo.test"}
for muestra in (C.NOTA, C.PUNTAJES, C.NADA):
    for ne in ("4-7/1", "1-7/1"):
        for i, (fila, decision) in enumerate(((fila_modelo, None), (fila_modelo, {"puntajes": ["2", "2"]}),
                                              (fila_modelo, {"puntajes": ["9", "2"]}),
                                              (fila_docente, {"puntajes": ["3", "0.5"], "justificaciones": ["a", "b"],
                                                              "retroalimentacion": "Hecha a mano."}),
                                              (fila_docente, {"puntajes": ["3", ""]})), 1):
            sale = D.juntar(fila, decision, escala=ESCALAS[ne], muestra=muestra)
            comparar(f"juntar {i} · {muestra} · {ne}", "revision.juntar",
                     [fila, decision, {"escala": ESCALAS[ne].como_dict(), "muestra": muestra}],
                     {k: sale[k] for k in ("nota", "html", "cambios", "puntajes", "logro", "problemas")})
for decision in ({"estado": "enviar", "puntajes": ["3", "2"]}, {"estado": "enviar", "puntajes": ["3", None]},
                 {"estado": "enviar", "puntajes": []}):
    comparar(f"falta en la corrección a mano · {decision['puntajes']}", "revision.faltanteManual",
             [decision, E.POR_DEFECTO.como_dict()], D.faltante_manual(decision))

titulo("4. Python y la página dan lo mismo (el caso principal es «nota»)")
if not shutil.which("node"):
    print("  (sin node en el PATH: no se compara con correccion.js)")
else:
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / "llamadas.json"
        ruta.write_text(json.dumps(llamadas, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "probar-correccion.mjs"), str(ruta)],
                           capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        check("probar-correccion.mjs corre", False, r.stderr[-600:])
    else:
        hechos = json.loads(r.stdout)
        distintos = [(n, py, js) for n, py, js in zip(nombres, esperado, hechos) if js != {"ok": py}]
        check(f"las {len(llamadas)} llamadas dan lo mismo en Python y en JS", not distintos and len(hechos) == len(llamadas),
              distintos[:2])
        principal = [n for n in nombres if " con nota " in f" {n} " or n.startswith("leer")]
        check(f"incluye {len(principal)} casos con «nota» o de lectura, que van primero",
              len(principal) > 100 and nombres.index(principal[0]) == 0)


# --------------------------------------------------------------- de punta a punta

SEM = 4


def _vaciar_instancia(carpeta: Path, item: int) -> None:
    for nombre in ("notas.csv", "log_envios.csv"):
        p = carpeta / nombre
        if not p.exists():
            continue
        with p.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            campos, filas = lector.fieldnames, list(lector)
        filas = [x for x in filas if not (x.get("Flujo") == "test" and x.get("Item") == str(item))]
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)


def _silencio(funcion, *a, **k) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        funcion(*a, **k)
    return buf.getvalue()


titulo("5. evaluar con la corrección en JSON, de punta a punta")
with semestre_desechable(sid="_tmp_correccion") as (sid, tmp), sin_red():
    _vaciar_instancia(tmp, SEM)
    from modulos import datos
    from modulos.tests import evaluar
    from modulos.tests import feedback  # noqa: F401  (evaluar lo usa al enviar)

    curso = datos.alumnos.correos(sid)

    def configurar(muestra: str) -> None:
        (tmp / "configuracion.json").write_text(json.dumps({"revision": "auto", "correo_muestra": muestra}),
                                                encoding="utf-8")

    def eventos(evento, correo):
        return [e for e in datos.log.leer(sid, flujo=datos.TESTS, item=str(SEM), evento=evento)
                if e["Correo"] == correo.lower()]

    def correr(desde: int, correccion: str) -> list[str]:
        cuerpos = []
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=desde, cantidad=1, message_ids=True)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=correccion), \
             patch("modulos.tests.feedback.enviar_correo",
                   side_effect=lambda *a, **k: (cuerpos.append(a[2]), f"<fb-{desde}@x>")[1]):
            _silencio(evaluar.main, SEM, dry_run=False)
        return cuerpos

    configurar(C.NOTA)
    cuerpos = correr(0, puntajes_ia(3, 2))
    nota = datos.notas.estado(curso[0], datos.TESTS, str(SEM), sid) or {}
    corr, ev = eventos("correccion", curso[0]), eventos("evaluacion", curso[0])
    check("con «nota»: el correo trae cada puntaje y NOTA FINAL 6,5",
          len(cuerpos) == 1 and "EVALUACIÓN:</b> 3 / 3 puntos" in cuerpos[0] and "NOTA FINAL:</b> 6,5" in cuerpos[0],
          cuerpos[:1])
    check("la corrección guarda puntajes y logro; la nota cuenta al salir el correo",
          corr and corr[-1]["Puntajes"] == "3;2" and corr[-1]["Logro"] == "0.8333"
          and (nota.get("Nota"), nota.get("Logro")) == ("6,5", "0.8333"), (corr[-1:], nota))
    check("la evaluacion anota la escala con que se calculó",
          ev and ev[-1]["Versiones"].endswith("escala=4-7/1") and ev[-1]["Puntajes"] == "3;2", ev[-1:])

    configurar(C.PUNTAJES)
    cuerpos = correr(1, puntajes_ia(3, 3))
    nota = datos.notas.estado(curso[1], datos.TESTS, str(SEM), sid) or {}
    check("con «puntajes»: el correo trae los puntajes y no la nota",
          cuerpos and "EVALUACIÓN:</b> 3 / 3 puntos" in cuerpos[0] and "NOTA FINAL" not in cuerpos[0], cuerpos[:1])
    check("pero la nota queda registrada igual (7,0)", nota.get("Nota") == "7,0", nota)

    configurar(C.NADA)
    cuerpos = correr(2, puntajes_ia(2, 2))
    check("con «nada»: ni puntajes ni nota",
          cuerpos and not any(x in cuerpos[0] for x in ("EVALUACIÓN:", "NOTA FINAL", "PUNTAJE TOTAL")), cuerpos[:1])

    configurar(C.NOTA)
    enviados.clear()
    cuerpos = correr(3, puntajes_ia(3, 1.5))
    corr = eventos("correccion", curso[3])
    nota = datos.notas.estado(curso[3], datos.TESTS, str(SEM), sid) or {}
    check("un puntaje fuera de la rúbrica: no sale el correo aunque el semestre sea automático",
          cuerpos == [] and enviados == [], cuerpos)
    check("queda por revisar, con el problema en el log",
          datos.notas.esta_por_revisar(nota) and corr and "modo=revisar" in corr[-1]["Detalle"], (nota, corr[-1:]))

    (tmp / E.ARCHIVO).write_text(json.dumps({"minima": 1.0}), encoding="utf-8")
    cuerpos = correr(4, puntajes_ia(3, 2))
    nota = datos.notas.estado(curso[4], datos.TESTS, str(SEM), sid) or {}
    ev = eventos("evaluacion", curso[4])
    check("con escala_notas.json de 1 a 7, la misma corrección da 6,0",
          nota.get("Nota") == "6,0" and cuerpos and "NOTA FINAL:</b> 6,0" in cuerpos[0], (nota, cuerpos[:1]))
    check("y la evaluacion lo anota (escala=1-7/1)", ev and ev[-1]["Versiones"].endswith("escala=1-7/1"), ev[-1:])

sys.exit(resultado())
