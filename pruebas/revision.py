"""
La revisión docente de Tests: corregir y mandar el feedback como dos pasos.

Corre sobre una copia desechable de un semestre con SMTP, IMAP y el modelo
simulados. Cubre lo que no puede romperse:

- un semestre sin configuracion.json manda el mismo correo de siempre, byte a
  byte (la referencia se generó con el código de la fase 2);
- en `revisar`, el alumno no recibe nada hasta que el docente decide;
- una decisión sobre una corrección anterior no se aplica;
- la nota cuenta cuando sale el correo: evaluacion en el log y después Nota;
- si el envío falla en automático, la corrida siguiente lo manda, salvo que el
  semestre haya pasado a revisión;
- «Las corrijo yo» nunca sale sin la nota y el texto del docente.
"""

import contextlib
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import (check, enviados, mensajes, nota_ia, resultado, respuestas_falsas,  # noqa: E402
                   semestre_desechable, sin_red, titulo)

SEM = 4
REF = Path("pruebas/referencias")


def _vaciar_instancia(carpeta: Path, item: int) -> None:
    """Saca de la copia las notas y los eventos de esa instancia de tests."""
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


def _config(tmp: Path, modo: str | None) -> None:
    p = tmp / "configuracion.json"
    if modo is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps({"revision": modo, "correo_muestra": "nota"}), encoding="utf-8")


def _decidir(tmp: Path, item: int, decisiones: dict) -> None:
    p = tmp / "tests_semanales" / "revision" / f"{item}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(decisiones, ensure_ascii=False), encoding="utf-8")


def _huella(*rutas: Path) -> list[str]:
    return [hashlib.sha256(r.read_bytes()).hexdigest() if r.exists() else "" for r in rutas]


def _salida(funcion, *a, **k) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        funcion(*a, **k)
    texto = buf.getvalue()
    print(texto[-1500:])
    return texto


def cuerpo_identico():
    titulo("1. el cuerpo del correo es el de la fase 2, byte a byte")
    from modulos.tests import feedback
    entrada = (REF / "correccion_legado.html").read_text(encoding="utf-8")
    plantilla = (REF / "plantilla_correo_correccion.md").read_text(encoding="utf-8")
    for nombre, tpl in (("sin_plantilla", None), ("con_plantilla", plantilla)):
        esperado = (REF / f"cuerpo_correccion_{nombre}.html").read_bytes()
        hecho = feedback._construir_cuerpo_correccion(tpl, entrada, "Ana María Pérez").encode("utf-8")
        check(f"{nombre}: igual a la referencia", hecho == esperado, (hecho[:80], esperado[:80]))


def flujo_completo():
    with semestre_desechable(sid="_tmp_revision") as (sid, tmp), sin_red():
        _vaciar_instancia(tmp, SEM)
        from modulos import datos
        from modulos.tests import evaluar, feedback, decisiones

        curso = datos.alumnos.correos(sid)
        log = tmp / "log_envios.csv"
        notas = tmp / "notas.csv"

        def eventos(evento, correo=None):
            return [e for e in datos.log.leer(sid, flujo=datos.TESTS, item=str(SEM), evento=evento)
                    if correo is None or e["Correo"] == correo.lower()]

        def estado(correo):
            return datos.notas.estado(correo, datos.TESTS, str(SEM), sid) or {}

        # ------------------------------------------------------------------
        titulo("2. sin configuracion.json: automático, y el correo es el de siempre")
        _config(tmp, None)
        entrada = (REF / "correccion_legado.html").read_text(encoding="utf-8")
        cuerpos = []
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, cantidad=1, message_ids=True)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=entrada), \
             patch("modulos.tests.feedback.enviar_correo",
                   side_effect=lambda *a, **k: (cuerpos.append(a[2]), "<fb-0@x>")[1]):
            texto = _salida(evaluar.main, SEM, dry_run=False)
        check("la primera línea dice el modo", texto.splitlines()[0].startswith("Modo automático"),
              texto.splitlines()[:1])
        nombre = next(a["Nombre"] for a in datos.alumnos.leer(sid) if a["Correo"].lower() == curso[0].lower())
        esperado = evaluar._construir_cuerpo_correccion(None, entrada, nombre)
        check("el cuerpo enviado es el armado de siempre (2026-2 no tiene correo_correccion.md)",
              cuerpos == [esperado], cuerpos[:1])
        check("y es la referencia de la fase 2 cuando el nombre es el de la referencia",
              evaluar._construir_cuerpo_correccion(None, entrada, "Ana María Pérez").encode("utf-8")
              == (REF / "cuerpo_correccion_sin_plantilla.html").read_bytes())
        corr = eventos("correccion", curso[0])
        ev = eventos("evaluacion", curso[0])
        check("queda la corrección con modo=auto", len(corr) == 1 and corr[0]["Detalle"] == "modo=auto", corr)
        check("y la evaluacion con el Message-ID y el bloque enviado",
              len(ev) == 1 and ev[0]["MessageId"] == "<fb-0@x>" and ev[0]["EvaluacionIA"] == entrada
              and ev[0]["Detalle"] == "auto", ev)
        check("la nota cuenta porque salió el correo", estado(curso[0]).get("Nota") == "6,0", estado(curso[0]))
        check("los tokens van en la corrección, no en la evaluacion",
              ev and not ev[0].get("TokensEntrada"), ev[:1])

        # ------------------------------------------------------------------
        titulo("3. en automático, si el envío falla, queda corregida y la corrida siguiente la manda")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=1, cantidad=1, message_ids=True)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("5,5")), \
             patch("modulos.tests.feedback.enviar_correo", side_effect=RuntimeError("SMTP caído")):
            _salida(evaluar.main, SEM, dry_run=False)
        check("sin nota: el alumno no recibió nada", not estado(curso[1]).get("Nota") and estado(curso[1]).get("Corregido"),
              estado(curso[1]))
        check("sin evaluacion en el log", eventos("evaluacion", curso[1]) == [])
        llamadas = []
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[]), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]):
            _salida(evaluar.main, SEM, dry_run=False)
        check("la corrida siguiente la manda sin volver a corregir",
              enviados == [curso[1]] and llamadas == [] and estado(curso[1]).get("Nota") == "5,5",
              (enviados, llamadas, estado(curso[1])))

        # ------------------------------------------------------------------
        titulo("4. en revisar, corregir no manda nada")
        _config(tmp, "revisar")
        enviados.clear()
        cuatro = respuestas_falsas(curso, SEM, desde=2, cantidad=4, message_ids=True)
        for r in cuatro:
            r["in_reply_to"] = f"<envio-{r['remitente']}@correo.test>"
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=cuatro), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("5,0", "Alta")):
            texto = _salida(evaluar.main, SEM, dry_run=False)
        check("la primera línea dice que es modo revisión", texto.splitlines()[0].startswith("Modo revisión"),
              texto.splitlines()[:1])
        check("no sale ningún correo", enviados == [], enviados)
        check("los 4 quedan por revisar, sin nota",
              all(datos.notas.esta_por_revisar(estado(c)) for c in curso[2:6]), [estado(c) for c in curso[2:6]])
        check("cada corrección dice modo=revisar",
              all(eventos("correccion", c)[-1]["Detalle"] == "modo=revisar" for c in curso[2:6]))

        titulo("4b. tests.feedback sin decisiones no manda nada")
        texto = _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("nadie recibe nada", enviados == [], enviados)
        check("dice cuántas esperan revisión", "Esperando revisión: 4" in texto, texto[-300:])

        # ------------------------------------------------------------------
        titulo("5. las decisiones: enviar, editar la nota, descartar, y una vieja")
        base = {c: eventos("correccion", c)[-1]["Timestamp"] for c in curso[2:6]}
        _decidir(tmp, SEM, {
            curso[2]: {"estado": "enviar", "base": base[curso[2]], "por": "profe@x.cl"},
            curso[3]: {"estado": "enviar", "base": base[curso[3]], "nota_legado": "6,5", "por": "ayudante@x.cl"},
            curso[4]: {"estado": "descartada", "base": base[curso[4]], "retroalimentacion": "copió la respuesta",
                       "por": "profe@x.cl"},
            curso[5]: {"estado": "enviar", "base": "2020-01-01T00:00:00-03:00", "por": "profe@x.cl"},
        })

        titulo("5a. en prueba elige igual, muestra los correos y no escribe nada")
        antes = _huella(log, notas)
        texto = _salida(feedback.main, SEM, prueba=True, por="profe@x.cl")
        check("no toca notas.csv ni el log", _huella(log, notas) == antes)
        check("no manda nada", enviados == [], enviados)
        check("dice que mandaría 2 y descartaría 1", "Feedback se enviarían: 2" in texto and "Descartes: 1" in texto,
              texto[-300:])

        titulo("5b. en real")
        mensajes.clear()
        texto = _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("salen los dos aprobados", sorted(enviados) == sorted([curso[2], curso[3]]), enviados)
        check("la nota de cada uno es la que salió",
              estado(curso[2]).get("Nota") == "5,0" and estado(curso[3]).get("Nota") == "6,5",
              (estado(curso[2]), estado(curso[3])))
        cuerpo = next((m.get_payload()[0].get_payload(decode=True).decode("utf-8")
                       for m in mensajes if m["To"] == curso[3]), "")
        check("el correo editado dice la nota nueva en NOTA FINAL", "NOTA FINAL: 6,5" in cuerpo, cuerpo[:200])
        ev3 = eventos("evaluacion", curso[3])
        check("la evaluacion dice quién revisó y qué cambió",
              ev3 and ev3[-1]["Detalle"] == "revisado por ayudante@x.cl; nota 5,0 → 6,5", ev3[-1:])
        check("el correo responde en el mismo hilo que la respuesta del alumno (RespondeA)",
              sorted(m["In-Reply-To"] for m in mensajes)
              == sorted(f"<envio-{c}@correo.test>" for c in (curso[2], curso[3])),
              [m["In-Reply-To"] for m in mensajes])
        check("el descarte queda registrado, sin correo",
              estado(curso[4]).get("Descartada") and not estado(curso[4]).get("Nota")
              and eventos("descarte", curso[4])
              and eventos("descarte", curso[4])[-1]["Detalle"] == "copió la respuesta; por profe@x.cl")
        check("la decisión vieja no se aplica", not estado(curso[5]).get("Nota") and curso[5] not in enviados)
        check("y la salida lo dice", "corrección anterior" in texto, texto[-400:])

        titulo("5c. repetir no repite correos")
        enviados.clear()
        _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("nada sale dos veces", enviados == [], enviados)

        # ------------------------------------------------------------------
        titulo("6. un corte entre el log y notas.csv no reenvía, y la nota se completa")
        _decidir(tmp, SEM, {curso[5]: {"estado": "enviar", "base": base[curso[5]], "por": "profe@x.cl"}})
        enviados.clear()
        with patch("modulos.datos.notas.registrar_nota", side_effect=RuntimeError("se cortó")):
            _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("salió el correo y quedó la evaluacion", enviados == [curso[5]] and eventos("evaluacion", curso[5]),
              enviados)
        check("pero sin Nota en la tabla", not estado(curso[5]).get("Nota"), estado(curso[5]))
        enviados.clear()
        _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("la corrida siguiente no lo reenvía", enviados == [], enviados)
        check("y completa la nota desde el log", estado(curso[5]).get("Nota") == "5,0", estado(curso[5]))

        # ------------------------------------------------------------------
        titulo("7. si el semestre pasa a revisar, lo automático que falló espera revisión")
        _config(tmp, None)
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=6, cantidad=1, message_ids=True)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("6,2")), \
             patch("modulos.tests.feedback.enviar_correo", side_effect=RuntimeError("SMTP caído")):
            _salida(evaluar.main, SEM, dry_run=False)
        _config(tmp, "revisar")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[]):
            _salida(evaluar.main, SEM, dry_run=False)
        _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("no sale sin revisión", enviados == [] and datos.notas.esta_por_revisar(estado(curso[6])),
              (enviados, estado(curso[6])))

        # ------------------------------------------------------------------
        titulo("8. candidatos de la simulación con estado, y chequeo con por revisar")
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=0, cantidad=8, message_ids=False)):
            _salida(evaluar.main, SEM, dry_run=True)
        from modulos.datos import candidatos as _cand
        lista = json.loads(_cand.ruta("tests_semanales", SEM).read_text(encoding="utf-8"))
        por_correo = {c["correo"]: c["estado"] for c in lista}
        check("cada candidato trae su estado", por_correo.get(curso[0].lower()) == "con nota 6,0"
              and por_correo.get(curso[4].lower()) == "descartada"
              and por_correo.get(curso[6].lower()) == "por revisar", por_correo)
        check("y ya no ya_tiene_nota", all("ya_tiene_nota" not in c for c in lista))

        titulo("9. el resumen toma las corregidas sin nota y no las descartadas")
        al_resumen = []
        with patch("modulos.tests.resumen.generar_resumen",
                   side_effect=lambda c, t, evs: (al_resumen.extend(evs), "resumen")[1]):
            from modulos.tests import resumen
            _salida(resumen.main, SEM)
        nombres = {a["Correo"].lower(): a["Nombre"] for a in datos.alumnos.leer(sid)}
        check("incluye una por revisar", any(nombres[curso[6].lower()] in e for e in al_resumen))
        check("no incluye la descartada", not any(nombres[curso[4].lower()] in e for e in al_resumen))

        # ------------------------------------------------------------------
        titulo("10. «Las corrijo yo» en un semestre automático: no llama al modelo ni manda nada")
        _config(tmp, None)
        llamadas = []
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=7, cantidad=1, message_ids=True)), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]):
            texto = _salida(evaluar.main, SEM, dry_run=False, sin_modelo=True, por="profe@x.cl")
        corr = eventos("correccion", curso[7])
        check("la primera línea dice revisión aunque el semestre esté en automático",
              texto.splitlines()[0].startswith("Modo revisión"), texto.splitlines()[:1])
        check("no llama al modelo y no sale nada", llamadas == [] and enviados == [], (llamadas, enviados))
        check("la corrección queda a nombre del docente, vacía",
              corr and corr[-1]["Modelo"] == "docente:profe@x.cl" and not corr[-1]["EvaluacionIA"]
              and corr[-1]["Detalle"] == "modo=revisar", corr[-1:])
        _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("sin decisión, tests.feedback no la manda (aunque el semestre sea automático)",
              curso[7] not in enviados, enviados)
        check("y sí manda la automática que esperaba, porque el semestre volvió a automático",
              curso[6] in enviados, enviados)
        enviados.clear()
        _decidir(tmp, SEM, {curso[7]: {"estado": "enviar", "base": corr[-1]["Timestamp"], "manual": True,
                                       "nota_legado": "6,0", "por": "profe@x.cl"}})
        texto = _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("con la nota y sin el texto, se salta y lo dice",
              enviados == [] and "falta el texto" in texto, (enviados, texto[-300:]))
        _decidir(tmp, SEM, {curso[7]: {"estado": "enviar", "base": corr[-1]["Timestamp"], "manual": True,
                                       "nota_legado": "6,0", "html_legado": "<p>Bien.</p><p>NOTA FINAL: 6,0</p>",
                                       "por": "profe@x.cl"}})
        _salida(feedback.main, SEM, prueba=False, por="profe@x.cl")
        check("completa, sale", enviados == [curso[7]] and estado(curso[7]).get("Nota") == "6,0",
              (enviados, estado(curso[7])))

        titulo("11. decisiones: base igual al Timestamp, y la vieja no es vigente")
        c6 = eventos("correccion", curso[6])[-1]
        check("vigente con el Timestamp exacto", decisiones.vigente({"base": c6["Timestamp"]}, c6))
        check("no vigente con otro", not decisiones.vigente({"base": c6["Timestamp"] + " "}, c6))
        check("reescribe NOTA FINAL con etiquetas en medio",
              decisiones.reescribir_nota_final("<p><b>NOTA FINAL:</b> 5,0</p>", "6,5") == "<p><b>NOTA FINAL:</b> 6,5</p>")


def nombres_repetidos():
    titulo("12. dos instancias con el mismo Tipo y Número se avisan")
    import tempfile
    from modulos.tests import preguntas
    cabecera = "Instancia,Tipo,Numero,Tema,Control P1,Control Pauta P1\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "preguntas.csv"
        p.write_text(cabecera + "1,Control,1,A,¿a?,x\n2,Control,2,B,¿b?,x\n3,control,2,C,¿c?,x\n", encoding="utf-8")
        a = preguntas.leer_archivo(p)
        check("avisa el par repetido", any("aparece dos veces" in x and "2 y 3" in x for x in a.problemas), a.problemas)
        check("las dos filas se siguen usando", set(a.filas) == {1, 2, 3}, a.filas.keys())
        p.write_text(cabecera.replace("Instancia", "Semana") + "1,Control,1,A,¿a?,x\n2,Control,1,B,¿b?,x\n",
                     encoding="utf-8")
        check("en el formato antiguo no aplica", preguntas.leer_archivo(p).problemas == [])


cuerpo_identico()
flujo_completo()
nombres_repetidos()
sys.exit(resultado())
