"""
Ciclo completo de Tests Semanales, más los escenarios en que algo falla.

Corre sobre una copia desechable del semestre, con SMTP, IMAP y el modelo
simulados: no manda un solo correo ni gasta un token.

La segunda parte reproduce lo que pasa de verdad al operar el curso entre dos
personas: los envíos se hicieron en otro equipo, el proceso se cae a mitad, la
red se corta justo al final. Cada uno de esos casos corresponde a algo que ya
ocurrió.

La tercera cubre la tutoría: el alumno responde al feedback preguntando por qué
le fue así, y hay que atenderlo sin tocarle la nota.

La cuarta cubre el ensayo de prompts: reevaluar respuestas viejas con otro
prompt sin que eso toque la nota de nadie ni salga un correo.

La quinta, completar el estado desde el log, que es como se recupera lo que se
hizo desde el otro equipo.
"""

import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import (check, correo_entrante, enviados, nota_ia, resultado,
                   respuestas_falsas, semestre_desechable, sin_red, titulo)

TRES_TABLAS = ("alumnos.csv", "notas.csv", "log_envios.csv")


def ciclo_completo():
    """Semestre recién abierto: envío, evaluación, y que nada se repita."""
    with semestre_desechable(sid="_tmp_e2e", vaciar=TRES_TABLAS) as (sid, tmp), sin_red():
        from modulos import datos
        from modulos.tests import enviar, evaluar

        titulo("1. ENVIO semana 5 (nueva)")
        enviar.main(5, dry_run=False)
        check("envio a los 36", len(enviados) == 36, len(enviados))
        check("notas.csv registro 36",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, "5") if f["Enviado"]) == 36)
        check("log: 36 eventos de envio",
              len(datos.log.leer(sid, evento="envio", item="5")) == 36)

        titulo("2. REENVIO (no debe mandar nada)")
        enviados.clear()
        enviar.main(5, dry_run=False)
        check("no reenvio", len(enviados) == 0, enviados[:3])

        titulo("3. EVALUACION de 2 respuestas")
        correos = datos.alumnos.correos(sid)[:2]
        entrantes = respuestas_falsas(correos, 5)
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("6,5", "Baja")):
            evaluar.main(5, dry_run=False)
        check("feedback a los 2", len(enviados) == 2, enviados)
        estado = datos.notas.estado(correos[0], datos.TESTS, "5", sid)
        check("nota guardada", estado and estado["Nota"] == "6,5", estado)
        check("log: 2 evaluaciones",
              len(datos.log.leer(sid, evento="evaluacion", item="5")) == 2)

        titulo("4. RE-EVALUACION (a quien ya tiene nota no se le vuelve a cobrar la API)")
        llamadas = []
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia("7,0"))[1]):
            evaluar.main(5, dry_run=False)
        check("no re-llamo a la IA", len(llamadas) == 0, len(llamadas))
        check("nota intacta",
              datos.notas.estado(correos[0], datos.TESTS, "5", sid)["Nota"] == "6,5")

        titulo("4b. con correo_correccion.md, la corrección va dentro de la plantilla")
        from modulos.tests import config as config_tests
        from modulos.ia import Texto
        (config_tests.PROMPTS / "correo_correccion.md").write_text(
            "<div>{EVALUACION}<hr><p>Cierre fijo para {NOMBRE}.</p></div>", encoding="utf-8")
        tercero = datos.alumnos.correos(sid)[2]
        cuerpos = []
        # La IA a veces envuelve el HTML en ```html: no tiene que llegar así al alumno.
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas([tercero], 5, cantidad=1)), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   return_value=Texto("```html\n" + nota_ia("6,0") + "\n```",
                                      {"versiones": "evaluar_respuesta.md@1a2b3c4d; pauta.md@5e6f7a8b"})), \
             patch("modulos.tests.evaluar.enviar_correo",
                   side_effect=lambda *a, **k: (cuerpos.append(a[2]), "<id-4b@x>")[1]):
            evaluar.main(5, dry_run=False)
        check("el correo lleva la corrección y el cierre fijo",
              len(cuerpos) == 1 and nota_ia("6,0") in cuerpos[0] and "Cierre fijo para" in cuerpos[0]
              and "```" not in cuerpos[0], cuerpos)
        guardada = [e for e in datos.log.leer(sid, evento="evaluacion", item="5")
                    if e["Correo"].lower() == tercero.lower()]
        check("el log guarda solo la corrección, sin el cierre",
              len(guardada) == 1 and "Cierre fijo" not in guardada[0]["EvaluacionIA"], guardada)
        from modulos.ia import versiones
        plantilla = versiones.anotar(config_tests.PROMPTS / "correo_correccion.md",
                                     "<div>{EVALUACION}<hr><p>Cierre fijo para {NOMBRE}.</p></div>")
        check("el log anota con qué prompt, pauta y plantilla del correo se corrigió",
              len(guardada) == 1 and guardada[0].get("Versiones")
              == f"evaluar_respuesta.md@1a2b3c4d; pauta.md@5e6f7a8b; {plantilla}", guardada)
        check("la nota sale igual de la corrección", datos.notas.estado(tercero, datos.TESTS, "5", sid)["Nota"] == "6,0")


def _vaciar_semana(carpeta, semana):
    """Borra de la copia las notas y los eventos de esa semana de tests."""
    import csv as _csv

    notas = carpeta / "notas.csv"
    with notas.open(encoding="utf-8-sig", newline="") as f:
        lector = _csv.DictReader(f)
        campos, filas = lector.fieldnames, list(lector)
    filas = [x for x in filas
             if not (x["Flujo"] == "test" and x["Item"] == str(semana))]
    with notas.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    log = carpeta / "log_envios.csv"
    if log.exists():
        with log.open(encoding="utf-8-sig", newline="") as f:
            lector = _csv.DictReader(f)
            campos, filas = lector.fieldnames, list(lector)
        filas = [x for x in filas
                 if not (x.get("Flujo") == "test" and x.get("Item") == str(semana))]
        with log.open("w", encoding="utf-8", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            w.writerows(filas)


def fallos_y_recuperacion():
    """Semestre en curso: los envíos los hizo otra persona y las cosas se caen."""
    SEM = 4
    with semestre_desechable(sid="_tmp_fallos") as (sid, tmp), sin_red():
        # La semana de prueba se deja sin evaluar. Antes se daba por hecho que
        # estaba vacía, y la prueba empezó a fallar el día que el curso la
        # evaluó de verdad: dependía del estado real del semestre.
        _vaciar_semana(tmp, SEM)
        from modulos import datos
        import modulos.mail.lectura as lectura
        from modulos.tests import evaluar

        curso = datos.alumnos.correos(sid)

        titulo("6. identifica a los alumnos sin tener los message_ids del otro equipo")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, cantidad=5)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia()):
            evaluar.main(SEM, dry_run=False)
        check("identifico y evaluo los 5 por remitente", len(enviados) == 5, enviados)
        check("notas guardadas",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 5)

        titulo("7. el proceso MUERE a mitad (falla la IA en el 3ro de 4)")
        llamadas = []

        def ia_que_falla(*a):
            llamadas.append(1)
            if len(llamadas) == 3:
                raise RuntimeError("timeout de OpenAI")
            return nota_ia("5,5", "Baja")

        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=5, cantidad=4)), \
             patch("modulos.tests.evaluar.evaluar_respuesta", side_effect=ia_que_falla):
            evaluar.main(SEM, dry_run=False)
        hechas = sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"])
        check("lo evaluado antes del fallo NO se perdio", hechas == 8, hechas)

        titulo("8. al reanudar, solo evalua al que falto")
        llamadas.clear()
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(curso, SEM, desde=5, cantidad=4)), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]):
            evaluar.main(SEM, dry_run=False)
        check("solo re-llamo a la IA 1 vez", len(llamadas) == 1, len(llamadas))
        check("total evaluados ahora 9",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 9)

        titulo("9. se cae la red al marcar leidos (ya pasó una vez)")
        enviados.clear()
        entrantes = respuestas_falsas(curso, SEM, desde=9, cantidad=2, message_ids=True)
        # evaluar importa marcar_leidos desde el paquete modulos.mail: ahí es
        # donde hay que hacerlo fallar (en lectura no lo intercepta).
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("7,0", "Alta")), \
             patch.object(lectura, "marcar_leidos",
                          side_effect=OSError("[Errno 11001] getaddrinfo failed")), \
             patch("modulos.mail.marcar_leidos",
                   side_effect=OSError("[Errno 11001] getaddrinfo failed")):
            evaluar.main(SEM, dry_run=False)
        check("no revento pese al fallo de red", True)
        check("las 2 notas nuevas quedaron guardadas",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]) == 11)

        def respuestas_de(correo):
            return [e for e in datos.log.leer(sid, evento="respuesta", item=str(SEM))
                    if e["Correo"] == correo.lower()]

        r9 = respuestas_de(curso[9])
        check("la respuesta guarda su Message-ID", len(r9) == 1
              and r9[0]["MessageId"] == entrantes[0]["message_id"] and not r9[0]["Detalle"], r9)

        titulo("9b. al repetir, lo que ya se procesó solo se marca leído: sin correo de duplicado")
        enviados.clear()
        llamadas.clear()
        marcados = []
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]), \
             patch("modulos.mail.marcar_leidos", side_effect=lambda uids: marcados.extend(uids)):
            evaluar.main(SEM, dry_run=False)
        check("no le manda el 'ya respondiste' a nadie", enviados == [], enviados)
        check("ni llama al modelo", llamadas == [], llamadas)
        check("los dos quedan marcados como leídos",
              sorted(marcados) == sorted(e["uid"] for e in entrantes), marcados)
        check("y no se registra nada nuevo en el log",
              len(respuestas_de(curso[9])) == 1 and len(respuestas_de(curso[10])) == 1)

        titulo("9c. una segunda respuesta de quien ya tiene nota queda como duplicado")
        segunda = correo_entrante(curso[9], SEM, "Se me olvido agregar esto a mi respuesta.",
                                  uid="950", message_id="<segunda-9@correo.test>")
        enviados.clear()
        marcados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[segunda]), \
             patch("modulos.tests.evaluar.evaluar_respuesta",
                   side_effect=lambda *a: (llamadas.append(1), nota_ia())[1]), \
             patch("modulos.mail.marcar_leidos", side_effect=lambda uids: marcados.extend(uids)):
            evaluar.main(SEM, dry_run=False)
        check("recibe el correo de duplicado, como siempre", enviados == [curso[9]], enviados)
        dup = [e for e in respuestas_de(curso[9]) if datos.log.es_duplicado(e)]
        check("queda en el log como respuesta duplicada, con su texto y su Message-ID",
              len(dup) == 1 and dup[0]["MessageId"] == "<segunda-9@correo.test>"
              and "Se me olvido" in dup[0]["Respuesta"] and dup[0]["Detalle"] == "duplicado", dup)
        primera = [e for e in respuestas_de(curso[9]) if not datos.log.es_duplicado(e)][0]
        estado = datos.log.reconstruir_estado(sid)[(curso[9].lower(), datos.TESTS, str(SEM))]
        check("Respondio sigue siendo la primera respuesta", estado["Respondio"] == primera["Timestamp"],
              (estado["Respondio"], primera["Timestamp"]))
        vista = [f for f in datos.log.como_interacciones(sid)
                 if f["Correo"] == curso[9].lower() and f["Item"] == str(SEM)]
        check("la reportería sigue mostrando la respuesta corregida",
              vista and vista[0]["Respuesta"] == entrantes[0]["texto"], vista[:1])
        check("la tutoría no la ve como parte de la conversación",
              not any(datos.log.es_duplicado(f)
                      for f in datos.log.conversacion(curso[9], datos.TESTS, str(SEM), sid)))
        respuestas_al_resumen = []
        with patch("modulos.tests.resumen.evaluar_respuesta",
                   side_effect=lambda p, pa, r: (respuestas_al_resumen.append(r), nota_ia())[1]), \
             patch("modulos.tests.resumen.generar_resumen", return_value="resumen"):
            from modulos.tests import resumen
            resumen.main(SEM)
        check("el resumen usa la respuesta corregida, no la duplicada",
              entrantes[0]["texto"] in respuestas_al_resumen
              and not any("Se me olvido" in r for r in respuestas_al_resumen), respuestas_al_resumen[:3])

        titulo("9d. si ese duplicado vuelve a aparecer sin leer, no se le escribe otra vez")
        enviados.clear()
        marcados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[segunda]), \
             patch("modulos.mail.marcar_leidos", side_effect=lambda uids: marcados.extend(uids)):
            evaluar.main(SEM, dry_run=False)
        check("sin un segundo correo de duplicado", enviados == [], enviados)
        check("solo se marca leído", marcados == [segunda["uid"]], marcados)
        check("y el log no suma otro duplicado",
              sum(1 for e in respuestas_de(curso[9]) if datos.log.es_duplicado(e)) == 1)


def tutoria_sobre_el_feedback():
    """El alumno pregunta sobre su corrección. Se le responde; la nota no se mueve."""
    with semestre_desechable(sid="_tmp_tutoria", vaciar=TRES_TABLAS) as (sid, tmp), sin_red():
        from modulos import datos
        from modulos.tests import enviar, evaluar, tutoria

        enviar.main(5, dry_run=False)
        correos = datos.alumnos.correos(sid)[:1]
        alumno = correos[0]

        titulo("10. al evaluar se guarda el id del feedback")
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   return_value=respuestas_falsas(correos, 5)),              patch("modulos.tests.evaluar.evaluar_respuesta",
                   return_value=nota_ia("6,0", "Media")):
            evaluar.main(5, dry_run=False)
        evaluacion = datos.log.leer(sid, evento="evaluacion", item="5")
        check("la evaluacion quedo con MessageId",
              bool(evaluacion and evaluacion[0]["MessageId"]), evaluacion[:1])
        check("la evaluacion quedo con el modelo",
              bool(evaluacion[0]["Modelo"]), evaluacion[0]["Modelo"])
        id_feedback = evaluacion[0]["MessageId"]
        nota_inicial = datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"]
        check("la nota inicial es 6,0", nota_inicial == "6,0", nota_inicial)

        titulo("11. una duda sobre el feedback NO es una respuesta atrasada")
        duda = correo_entrante(alumno, 5,
                               "Por que un 6 y no un 7? Que me falto exactamente?",
                               in_reply_to=id_feedback)
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[duda]),              patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("7,0")):
            evaluar.main(5, dry_run=False)
        check("evaluar no le mando el 'ya respondiste'", len(enviados) == 0, enviados)
        check("evaluar no le toco la nota",
              datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"] == "6,0")

        titulo("12. la tutoria si la atiende")
        enviados.clear()
        llamadas = []
        with patch("modulos.tests.tutoria.buscar_no_leidos", return_value=[duda]),              patch("modulos.tests.tutoria.responder_duda",
                   side_effect=lambda *a, **k: (llamadas.append(k.get("historial")),
                                                "```html\n<p>Te falto mencionar X.</p>\n```")[1]):
            tutoria.main(5, dry_run=False)
        check("le respondio la duda", len(enviados) == 1, enviados)
        check("llamo al modelo una vez", len(llamadas) == 1, len(llamadas))
        check("el modelo recibio el historial", bool(llamadas and llamadas[0]), llamadas[:1])
        check("quedo registrada la repregunta",
              len(datos.log.leer(sid, evento="repregunta", item="5")) == 1)
        check("quedo registrada la tutoria",
              len(datos.log.leer(sid, evento="tutoria", item="5")) == 1)
        check("sin las marcas ``` del modelo en lo que se envió y se guardó",
              [t["EvaluacionIA"] for t in datos.log.leer(sid, evento="tutoria", item="5")]
              == ["<p>Te falto mencionar X.</p>"])

        titulo("12b. en el historial que recibe el modelo, la respuesta original es del estudiante")
        from modulos.ia.cliente import Respuesta
        from modulos.tests import ia_prompts
        mensajes_al_modelo = []
        with patch.object(ia_prompts.ia, "completar",
                          side_effect=lambda s, u, **k: (mensajes_al_modelo.append(u), Respuesta("<p>ok</p>"))[1]):
            ia_prompts.responder_duda(["P1"], ["pauta"], "respuesta", "<p>eval</p>", "una duda", "Ana",
                                      historial=datos.log.conversacion(alumno, datos.TESTS, "5", sid))
        texto_alumno = respuestas_falsas(correos, 5)[0]["texto"]
        check("la respuesta va rotulada ESTUDIANTE",
              f"=== ESTUDIANTE (ronda 0) ===\n{texto_alumno}" in mensajes_al_modelo[0], mensajes_al_modelo[0][-600:])
        check("y no AYUDANTE", f"=== AYUDANTE (ronda 0) ===\n{texto_alumno}" not in mensajes_al_modelo[0])

        titulo("13. LA NOTA NO CAMBIA")
        check("sigue siendo 6,0",
              datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"] == "6,0",
              datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"])
        check("sigue habiendo una sola evaluacion",
              len(datos.log.leer(sid, evento="evaluacion", item="5")) == 1)

        titulo("14. una segunda vuelta se numera como ronda 2")
        tut = datos.log.leer(sid, evento="tutoria", item="5")[0]
        check("la primera vuelta fue ronda 1", tut["Ronda"] == "1", tut["Ronda"])
        duda2 = correo_entrante(alumno, 5, "Gracias! Y como se interpreta el parametro?",
                                in_reply_to=tut["MessageId"], uid="901")
        enviados.clear()
        with patch("modulos.tests.tutoria.buscar_no_leidos", return_value=[duda2]),              patch("modulos.tests.tutoria.responder_duda", return_value="<p>Se interpreta asi.</p>"):
            tutoria.main(5, dry_run=False)
        rondas = [t["Ronda"] for t in datos.log.leer(sid, evento="tutoria", item="5")]
        check("ahora hay ronda 1 y 2", sorted(rondas) == ["1", "2"], rondas)
        check("la nota sigue intacta",
              datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"] == "6,0")

        titulo("15. se corta despues de MAX_RONDAS")
        ultimo = [t for t in datos.log.leer(sid, evento="tutoria", item="5")
                  if t["Ronda"] == "2"][0]["MessageId"]
        for n in range(3, tutoria.MAX_RONDAS + 3):
            d = correo_entrante(alumno, 5, f"Otra duda mas ({n})",
                                in_reply_to=ultimo, uid=f"9{n:02d}")
            with patch("modulos.tests.tutoria.buscar_no_leidos", return_value=[d]),                  patch("modulos.tests.tutoria.responder_duda", return_value="<p>ok</p>"):
                tutoria.main(5, dry_run=False)
            hechas = datos.log.leer(sid, evento="tutoria", item="5")
            nuevo = [t for t in hechas if t["Ronda"] == str(n)]
            if nuevo:
                ultimo = nuevo[0]["MessageId"]
        total = len(datos.log.leer(sid, evento="tutoria", item="5"))
        check(f"no pasa de {tutoria.MAX_RONDAS} vueltas", total <= tutoria.MAX_RONDAS, total)
        check("y la nota nunca se movio",
              datos.notas.estado(alumno, datos.TESTS, "5", sid)["Nota"] == "6,0")

        titulo("15b. una respuesta al feedback de una TAREA no la atiende la tutoria de tests")
        datos.log.registrar("evaluacion", datos.TAREAS, "T1", alumno, sid,
                            MessageId="<feedback-tarea-T1@correo.test>", Nota="6.0")
        duda_tarea = correo_entrante(alumno, 5, "Por que me bajaron en la tarea?",
                                     in_reply_to="<feedback-tarea-T1@correo.test>", uid="990")
        errores_antes = len(datos.log.leer(sid, evento="error"))
        tutorias_antes = len(datos.log.leer(sid, evento="tutoria"))
        enviados.clear()
        llamadas = []
        import io
        from contextlib import redirect_stdout
        salida = io.StringIO()
        with patch("modulos.tests.tutoria.buscar_no_leidos", return_value=[duda_tarea]), \
             patch("modulos.tests.tutoria.responder_duda",
                   side_effect=lambda *a, **k: (llamadas.append(1), "<p>no</p>")[1]), \
             redirect_stdout(salida):
            tutoria.main(None, dry_run=False)
        check("no llama al modelo", llamadas == [], llamadas)
        check("no le responde", enviados == [], enviados)
        check("no registra un error con flujo test e item T1",
              len(datos.log.leer(sid, evento="error")) == errores_antes,
              datos.log.leer(sid, evento="error")[errores_antes:])
        check("ni una tutoria", len(datos.log.leer(sid, evento="tutoria")) == tutorias_antes)
        check("la cuenta aparte en la salida",
              "1 respuesta(s) a feedback de Tareas" in salida.getvalue(), salida.getvalue()[-300:])
        check("y no crea una casilla de tests para T1",
              datos.notas.estado(alumno, datos.TESTS, "T1", sid) is None)


PROMPT_CANDIDATO = """Evalúa la respuesta.
Preguntas: {{PREGUNTAS}}
Pautas: {{PAUTAS}}
Termina con NOTA FINAL: y ORIGINALIDAD:
"""


def ensayo_de_prompt():
    """Reevaluar con otro prompt no le mueve la nota a nadie ni manda correo."""
    with semestre_desechable(sid="_tmp_experimento") as (sid, tmp), sin_red():
        from modulos import datos
        from modulos.tests import experimento

        archivo = tmp / "prompt_candidato.md"
        archivo.write_text(PROMPT_CANDIDATO, encoding="utf-8")

        notas_antes = datos.notas.leer(sid, flujo=datos.TESTS)
        eventos_antes = len(datos.log.leer(sid))
        disponibles = experimento.candidatas(semestre_id=sid)

        titulo("16. la muestra sale de lo que ya se evaluó")
        check("hay respuestas reevaluables", len(disponibles) >= 3, len(disponibles))
        check("todas tienen texto y nota",
              all(f["Respuesta"].strip() and f["Nota"] is not None for f in disponibles))

        titulo("17. la misma semilla elige la misma muestra")
        a = experimento.muestrear(disponibles, 3, semilla=7)
        b = experimento.muestrear(disponibles, 3, semilla=7)
        c = experimento.muestrear(disponibles, 3, semilla=8)
        check("dos corridas con semilla 7 coinciden",
              [x["Correo"] for x in a] == [x["Correo"] for x in b])
        check("con otra semilla cambia",
              [x["Correo"] for x in a] != [x["Correo"] for x in c],
              "puede coincidir por azar con muestras chicas")

        titulo("18. reevalúa con el prompt candidato, no con el del semestre")
        recibidos = []
        # El semestre copiado puede traer experimentos anteriores (los hay en
        # 2026-2). Se cuentan solo los CSV que aparezcan durante esta prueba.
        previos = set((tmp / "tests_semanales" / "data").glob("experimento_*.csv"))
        enviados.clear()

        def ia_falsa(preguntas, pautas, respuesta, plantilla=None):
            recibidos.append(plantilla)
            return nota_ia("7,0", "Muy Alta")

        with patch("modulos.tests.experimento.evaluar_respuesta", side_effect=ia_falsa):
            resultados = experimento.main(archivo, n=3, semilla=7)

        check("reevaluó 3", len(resultados) == 3, len(resultados))
        check("el modelo recibió el prompt candidato",
              all(p == PROMPT_CANDIDATO for p in recibidos), recibidos[:1])
        check("leyó la nota nueva",
              all(r["NotaDespues"] == 7.0 for r in resultados),
              [r["NotaDespues"] for r in resultados])
        check("calculó el delta contra la nota original",
              all(r["DeltaNota"] == round(7.0 - r["NotaAntes"], 2) for r in resultados))

        titulo("19. NO TOCA NADA del curso")
        check("no salió ningún correo", len(enviados) == 0, enviados)
        check("notas.csv quedó igual",
              datos.notas.leer(sid, flujo=datos.TESTS) == notas_antes)
        check("el log no creció", len(datos.log.leer(sid)) == eventos_antes,
              len(datos.log.leer(sid)) - eventos_antes)

        titulo("20. deja el detalle en un CSV")
        csvs = [c for c in (tmp / "tests_semanales" / "data").glob("experimento_*.csv")
                if c not in previos]
        check("escribió el CSV", len(csvs) == 1, [p.name for p in csvs])
        if csvs:
            import csv as _csv
            with csvs[0].open(encoding="utf-8-sig", newline="") as f:
                filas = list(_csv.DictReader(f))
            check("una fila por respuesta reevaluada", len(filas) == 3, len(filas))
            check("trae el antes y el después",
                  all(f["OriginalidadAntes"] is not None and f["OriginalidadDespues"] == "Muy Alta"
                      for f in filas), filas[:1])
            check("guarda la corrección que recibió el alumno, para leerla al lado de la nueva",
                  all(f.get("EvaluacionAntes", "").strip() for f in filas), [f.get("EvaluacionAntes", "")[:40] for f in filas])

        titulo("21. el modo prueba no llama al modelo")
        llamadas = []
        with patch("modulos.tests.experimento.evaluar_respuesta",
                   side_effect=lambda *a, **k: llamadas.append(1)):
            vacio = experimento.main(archivo, n=3, semilla=7, dry_run=True)
        check("no llamó a la IA", len(llamadas) == 0, len(llamadas))
        check("no devolvió resultados", vacio == [], vacio)


def _desalinear_estado(carpeta, quitar=5, vaciar=4):
    """Deja notas.csv incompleto respecto del log, como cuando se opera en dos equipos.

    La prueba se fabrica su propio desajuste en vez de esperar que el semestre
    de partida lo traiga. Antes dependía de que los datos reales estuvieran
    desalineados, y empezó a fallar el día que se sincronizaron.
    """
    import csv as _csv

    notas = carpeta / "notas.csv"
    with notas.open(encoding="utf-8-sig", newline="") as f:
        lector = _csv.DictReader(f)
        campos, filas = lector.fieldnames, list(lector)

    # Solo se tocan casillas que el log conozca: son las que la sincronización
    # tiene con qué recomponer.
    conocidas = {(c, fl, it) for (c, fl, it) in _estado_del_log(carpeta)}
    elegibles = [f for f in filas
                 if (f["Correo"], f["Flujo"], f["Item"]) in conocidas]

    quitadas = elegibles[:quitar]
    for f in elegibles[quitar:quitar + vaciar]:
        f["Enviado"] = ""
    filas = [f for f in filas if f not in quitadas]

    with notas.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    return len(quitadas), vaciar


def _estado_del_log(carpeta):
    """Las casillas (correo, flujo, item) que el log describe."""
    import csv as _csv

    log = carpeta / "log_envios.csv"
    if not log.exists():
        return set()
    with log.open(encoding="utf-8-sig", newline="") as f:
        return {(x["Correo"], x["Flujo"], x["Item"]) for x in _csv.DictReader(f)
                if x.get("Evento") in ("envio", "respuesta", "evaluacion")}


def estado_desde_el_log():
    """Lo que el log sabe y la tabla de estado no, se pasa sin pisar nada."""
    with semestre_desechable(sid="_tmp_sync") as (sid, tmp), sin_red():
        from modulos import datos

        quitadas, vaciadas = _desalinear_estado(tmp)
        antes = datos.notas.leer(sid)
        indice_antes = {(f["Correo"], f["Flujo"], f["Item"]): f for f in antes}

        titulo("22. simular no escribe")
        sim = datos.notas.sincronizar_desde_log(sid, simular=True)
        check("ve las filas que faltan", sim["FilasNuevas"] == quitadas,
              f"{sim['FilasNuevas']} vs {quitadas}")
        check("ve los envios sin marcar", sim["Enviado"] >= vaciadas,
              f"{sim['Enviado']} vs {vaciadas}")
        check("pero no toco el archivo", len(datos.notas.leer(sid)) == len(antes))

        titulo("23. aplicar completa lo que faltaba")
        hecho = datos.notas.sincronizar_desde_log(sid)
        check("hizo lo mismo que dijo que haria", hecho == sim, f"{hecho} vs {sim}")
        despues = datos.notas.leer(sid)
        check("aparecieron las filas nuevas",
              len(despues) == len(antes) + sim["FilasNuevas"],
              f"{len(despues)} vs {len(antes)}+{sim['FilasNuevas']}")

        titulo("24. NO PISA NI BORRA lo que ya estaba")
        indice = {(f["Correo"], f["Flujo"], f["Item"]): f for f in despues}
        perdidas = [k for k in indice_antes if k not in indice]
        check("no se perdio ninguna fila", not perdidas, perdidas[:3])
        pisados = [
            k for k, vieja in indice_antes.items()
            for c in ("Enviado", "Respondio", "Nota", "Originalidad")
            if (vieja.get(c) or "").strip() and vieja[c] != indice[k].get(c)
        ]
        check("no se piso ningun valor escrito", not pisados, pisados[:3])

        titulo("25. correrlo dos veces no cambia nada")
        otra = datos.notas.sincronizar_desde_log(sid)
        check("la segunda pasada no hace nada", not any(otra.values()), otra)
        check("y la tabla quedo igual", len(datos.notas.leer(sid)) == len(despues))


def _partir_log(tmp, aparte):
    """Deja acá solo los envíos y escribe el resto en otro archivo.

    Es la situación real entre dos equipos: uno mandó los tests y el otro
    corrigió, así que cada log tiene una mitad y ninguno la historia completa.
    """
    import csv as _csv

    log = tmp / "log_envios.csv"
    with log.open(encoding="utf-8-sig", newline="") as f:
        lector = _csv.DictReader(f)
        columnas, filas = lector.fieldnames, list(lector)

    mias = [x for x in filas if x.get("Evento") == "envio"]
    suyas = [x for x in filas if x.get("Evento") != "envio"]

    for destino, cuales in ((log, mias), (aparte, suyas)):
        with destino.open("w", encoding="utf-8", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            w.writeheader()
            w.writerows(cuales)
    return filas, mias, suyas


def fusion_de_dos_logs():
    """Juntar el log del otro equipo con el de acá reconstruye la historia entera."""
    with semestre_desechable(sid="_tmp_fusion") as (sid, tmp), sin_red():
        from modulos import datos

        aparte = tmp / "log_del_otro_equipo.csv"
        todas, mias, suyas = _partir_log(tmp, aparte)
        if not suyas:
            check("el semestre base tiene eventos que no son envios", False,
                  "sin respuestas ni evaluaciones no hay nada que fusionar")
            return

        titulo("26. simular dice que entraria sin escribir nada")
        sim = datos.log.fusionar(aparte, sid, simular=True)
        check("cuenta los que faltan", sim["Nuevas"] == len(suyas),
              f"{sim['Nuevas']} vs {len(suyas)}")
        check("y no toco el log", len(datos.log.leer(sid)) == len(mias),
              f"{len(datos.log.leer(sid))} vs {len(mias)}")

        titulo("27. fusionar reconstruye la historia completa")
        r = datos.log.fusionar(aparte, sid)
        check("hizo lo que dijo que haria", r["Nuevas"] == sim["Nuevas"],
              f"{r['Nuevas']} vs {sim['Nuevas']}")

        clave = lambda f: (f["Timestamp"], f["Flujo"], f["Item"],  # noqa: E731
                           f["Correo"], f["Evento"])
        quedaron = datos.log.leer(sid)
        check("estan todos los eventos del original",
              {clave(f) for f in quedaron} == {clave(f) for f in todas},
              f"{len(quedaron)} vs {len(todas)}")

        titulo("28. NO PIERDE EL TEXTO de las respuestas")
        textos_antes = {clave(f): f.get("Respuesta", "") for f in todas}
        vacios = [k for k, v in ((clave(f), f.get("Respuesta", "")) for f in quedaron)
                  if textos_antes.get(k, "").strip() and not v.strip()]
        check("las respuestas llegaron con su contenido", not vacios, vacios[:2])

        titulo("29. correrlo dos veces no duplica")
        otra = datos.log.fusionar(aparte, sid)
        check("la segunda pasada no agrega nada", otra["Nuevas"] == 0, otra)
        check("y el log quedo igual", len(datos.log.leer(sid)) == len(quedaron),
              f"{len(datos.log.leer(sid))} vs {len(quedaron)}")

        titulo("30. deja copia del log anterior antes de reescribirlo")
        check("existe el respaldo", (tmp / "log_envios.csv.previo").exists())

        titulo("31. el estado refleja lo que entro por la fusion")
        datos.notas.sincronizar_desde_log(sid)
        panel = datos.reportes.panel(sid, datos.TESTS)
        # Solo las de tests: el panel es el de tests, y en el log también
        # están las respuestas de tareas (que tienen su propia reportería).
        respondieron = {f["Correo"] for f in quedaron
                        if f.get("Evento") == "respuesta" and f.get("Flujo") == "test"}
        faltan = [c for c in respondieron
                  if not any(f["Correo"] == c and f["Respondio"] for f in panel)]
        check("la reporteria ve las respuestas fusionadas", not faltan, faltan[:3])

        titulo("32. rechaza un log de otro semestre")
        ajeno = tmp / "log_de_otro_semestre.csv"
        import csv as _csv
        with aparte.open(encoding="utf-8-sig", newline="") as f:
            lector = _csv.DictReader(f)
            cols, filas = lector.fieldnames, list(lector)
        for f_ in filas:
            f_["Semestre"] = "1999-1"
        with ajeno.open("w", encoding="utf-8", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        try:
            datos.log.fusionar(ajeno, sid)
            check("avisa en vez de mezclar semestres", False, "no levanto nada")
        except ValueError as e:
            check("avisa en vez de mezclar semestres", "1999-1" in str(e), str(e))


def elegir_que_evaluar():
    """Ver primero las respuestas y evaluar solo las elegidas (las demás no se tocan)."""
    SEM = 4
    with semestre_desechable(sid="_tmp_elegir") as (sid, tmp), sin_red():
        _vaciar_semana(tmp, SEM)
        from modulos import datos
        from modulos.datos import candidatos
        from modulos.tests import evaluar

        curso = datos.alumnos.correos(sid)
        entrantes = respuestas_falsas(curso, SEM, cantidad=3)

        titulo("32. en modo prueba deja la lista para elegir")
        enviados.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes):
            evaluar.main(SEM, dry_run=True)
        import json
        lista = json.loads(candidatos.ruta("tests_semanales", SEM).read_text(encoding="utf-8"))
        check("están las 3 respuestas, con su texto", len(lista) == 3 and all(c["respuesta"] for c in lista),
              lista[:1])
        check("modo prueba no manda nada", enviados == [])

        titulo("33. evaluar solo la elegida")
        marcados = []
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=entrantes), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("6,0")), \
             patch("modulos.mail.marcar_leidos", side_effect=lambda uids: marcados.extend(uids)):
            evaluar.main(SEM, dry_run=False, solo={curso[1].lower()})
        check("feedback solo a la elegida", enviados == [curso[1]], enviados)
        check("solo su correo se marca como leído", marcados == [entrantes[1]["uid"]], marcados)
        con_nota = [f["Correo"] for f in datos.notas.leer(sid, datos.TESTS, str(SEM)) if f["Nota"]]
        check("solo ella queda con nota", con_nota == [curso[1].lower()], con_nota)

        titulo("34. quien tiene nota no sale como 'no entregó'")
        import io
        from contextlib import redirect_stdout
        salida = io.StringIO()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana", return_value=[]), redirect_stdout(salida):
            evaluar.main(SEM, dry_run=True)
        nombre = next(a["Nombre"] for a in datos.alumnos.leer(sid) if a["Correo"].lower() == curso[1].lower())
        check("la evaluada no aparece en 'no entregó'",
              f"→ {nombre}" not in salida.getvalue() or "no entregó" not in
              next((l for l in salida.getvalue().splitlines() if nombre in l), ""))


_CABECERA_NUEVA = ("Instancia,Tipo,Numero,Estado,Envio,Cierre,Tema,Fecha de Entrega,"
                   "Control P1,Control P2,Control P3,Control Pauta P1,Control Pauta P2,Control Pauta P3,"
                   "Tratamiento P1,Tratamiento P2,Tratamiento P3,"
                   "Tratamiento Pauta P1,Tratamiento Pauta P2,Tratamiento Pauta P3")


def _fila_nueva(instancia, tipo, numero, estado, tema, pregunta):
    """Una fila del formato nuevo, con preguntas inventadas (el repo es público)."""
    valores = {"Instancia": instancia, "Tipo": tipo, "Numero": numero, "Estado": estado,
               "Envio": "2026-11-23T10:15:00-03:00", "Cierre": "2026-11-30T10:15:00-03:00",
               "Tema": tema, "Control P1": pregunta, "Control Pauta P1": "Lo esperado."}
    return ",".join(f'"{valores.get(c, "")}"' for c in _CABECERA_NUEVA.split(","))


def instancias_nuevas():
    """Semestre nuevo (preguntas.csv con Instancia): nombres, borrador y respuestas por In-Reply-To.

    Antes, que el formato antiguo siga dando exactamente el mismo asunto y cuerpo.
    """
    with semestre_desechable(sid="_tmp_instancias", vaciar=TRES_TABLAS) as (sid, tmp), sin_red():
        from comun import mensajes
        from modulos import datos
        from modulos.mail import lectura
        from modulos.tests import config as config_tests
        from modulos.tests import enviar, evaluar, preguntas
        from modulos.tests.respuestas import criterio

        titulo("35. el formato antiguo (columna Semana) sigue igual")
        info5 = preguntas.cargar_semana(5)
        check("asunto de siempre", enviar._construir_asunto(info5)
              == f"Evaluación de Progreso Individual Módulo 5: {info5.tema}", enviar._construir_asunto(info5))
        cuerpo = enviar._construir_cuerpo("{BLOQUE_PREGUNTAS}|{SEMANA}", {"Nombre": "Ana Pérez", "Grupo": "control"},
                                          info5)
        check("cuerpo de siempre: «de la semana» y {SEMANA} = 5",
              "de la semana" in cuerpo and cuerpo.endswith("|5"), cuerpo[-80:])
        check("todas confirmadas, Tipo «Semana», número = id",
              info5.legado and info5.tipo == "Semana" and info5.numero == 5 and info5.estado == "confirmada")
        check("las respuestas se reconocen por «Módulo 5», como siempre", criterio(info5) == {})
        check("el feedback responde con el asunto de siempre", evaluar._construir_asunto_respuesta(info5)
              == f"Re: Evaluación de Progreso Individual Módulo 5: {info5.tema}")

        ruta = config_tests.PREGUNTAS_CSV
        titulo("36. archivo nuevo sin filas, y archivos que no se pueden usar")
        ruta.write_text(_CABECERA_NUEVA + "\n", encoding="utf-8")
        try:
            preguntas.cargar_semana(1)
            check("solo la cabecera: «todavía no hay tests»", False, "no levantó nada")
        except preguntas.PreguntasError as e:
            check("solo la cabecera: «todavía no hay tests»", "Todavía no hay tests" in str(e), str(e))
        check("y la sábana no ve ninguna", preguntas.instancias() == {})
        ruta.write_text("Semana," + _CABECERA_NUEVA + "\n", encoding="utf-8")
        try:
            preguntas.leer_archivo()
            check("Semana e Instancia a la vez: error claro", False, "no levantó nada")
        except preguntas.PreguntasError as e:
            check("Semana e Instancia a la vez: error claro", "Semana" in str(e) and "Instancia" in str(e), str(e))
        filas = [_fila_nueva(7, "Control", 2, "confirmada", "Logit anidado", "¿Qué resuelve un logit anidado?"),
                 _fila_nueva(9, "Test", 1, "borrador", "En preparación", "¿Algo?"),
                 _fila_nueva(10, "Control", 21, "confirmada", "Otro tema", "¿Otra cosa?"),
                 _fila_nueva("abc", "Control", 3, "", "Id malo", "¿X?"),
                 _fila_nueva(11, "Test", 2, "", "Repetida", "¿Una?"),
                 _fila_nueva(11, "Test", 3, "", "Repetida", "¿Dos?")]
        ruta.write_text(_CABECERA_NUEVA + "\n" + "\n".join(filas) + "\n", encoding="utf-8")
        archivo = preguntas.leer_archivo()
        check("un id que no es número se avisa y se salta; los demás se leen",
              any("abc" in p for p in archivo.problemas) and {7, 9, 10} <= set(archivo.filas), archivo.problemas)
        try:
            preguntas.cargar_semana(11)
            check("un id repetido no se usa", False, "no levantó nada")
        except preguntas.PreguntasError as e:
            check("un id repetido no se usa", "repetido" in str(e), str(e))
        info7 = preguntas.cargar_semana(7)
        check("nombre visible «Control 2» (el id 7 no se ve)", info7.nombre == "Control 2" and not info7.legado
              and info7.estado == "confirmada", info7.nombre)
        check("estado vacío cuenta como confirmada", preguntas.cargar_semana(10).estado == "confirmada")

        titulo("37. un borrador no sale de verdad")
        enviados.clear()
        check("enviar de verdad un borrador termina con error y no manda nada",
              enviar.main(9, dry_run=False) == 1 and enviados == [], enviados[:3])
        check("simularlo sí se puede", enviar.main(9, dry_run=True) == 0 and enviados == [])
        with patch("modulos.tests.evaluar.buscar_respuestas_semana") as buscar:
            evaluar.main(9, dry_run=False)
        check("evaluar de verdad un borrador no lee el buzón", not buscar.called)

        titulo("38. el envío de una instancia confirmada")
        curso = datos.alumnos.correos(sid)
        enviados.clear()
        mensajes.clear()
        check("se envía", enviar.main(7, dry_run=False) == 0 and len(enviados) == len(curso), len(enviados))
        check("con el asunto «Control 2: tema»", {m["Subject"] for m in mensajes} == {"Control 2: Logit anidado"},
              {m["Subject"] for m in mensajes})
        check("notas.csv lo guarda con el id como Item",
              sum(1 for f in datos.notas.leer(sid, datos.TESTS, "7") if f["Enviado"]) == len(curso))
        enviar.main(10, dry_run=False)  # «Control 21», para tener envíos de otra instancia

        titulo("39. las respuestas: por In-Reply-To, y el nombre entero como respaldo")
        c = criterio(info7)
        propio = next(iter(c["propios"]))
        ajeno = next(iter(c["ajenos"]))
        check("criterio: el nombre y los Message-ID de cada envío",
              c["nombre"] == "Control 2" and len(c["propios"]) == len(curso) and len(c["ajenos"]) == len(curso),
              (c["nombre"], len(c["propios"]), len(c["ajenos"])))
        buzon = [
            {"asunto": "mi respuesta (le cambié el asunto)", "in_reply_to": propio, "referencias": ""},
            {"asunto": "Re: Control 21: Otro tema", "in_reply_to": "", "referencias": ""},
            {"asunto": "Re: Control 2: Logit anidado", "in_reply_to": ajeno, "referencias": ""},
            {"asunto": "RE:  control   2 :  logit", "in_reply_to": "", "referencias": ""},
            {"asunto": "Re: Autocontrol 2", "in_reply_to": "", "referencias": ""},
            {"asunto": "Fwd", "in_reply_to": "<otro@x>", "referencias": f"<raiz@x> {propio}"},
        ]
        with patch.object(lectura, "buscar_no_leidos",
                          side_effect=lambda filtro_asunto=None, filtro=None: [m for m in buzon if filtro(m)]):
            halladas = [m["asunto"] for m in lectura.buscar_respuestas_semana(7, **c)]
        check("reconoce la respuesta aunque cambie el asunto (In-Reply-To)", buzon[0]["asunto"] in halladas, halladas)
        check("«Control 21» no es «Control 2»", buzon[1]["asunto"] not in halladas, halladas)
        check("una respuesta a otra instancia no cuenta aunque el asunto diga Control 2",
              buzon[2]["asunto"] not in halladas, halladas)
        check("sin cabeceras conocidas, el nombre en el asunto basta (mayúsculas y espacios aparte)",
              buzon[3]["asunto"] in halladas, halladas)
        check("«Autocontrol 2» no es «Control 2»", buzon[4]["asunto"] not in halladas, halladas)
        check("también por References", buzon[5]["asunto"] in halladas, halladas)

        titulo("40. evaluar una instancia: le pasa al buzón el criterio y responde con su asunto")
        pedidos = []
        mensajes.clear()
        with patch("modulos.tests.evaluar.buscar_respuestas_semana",
                   side_effect=lambda n, **k: (pedidos.append((n, k)), respuestas_falsas(curso, 7, cantidad=1))[1]), \
             patch("modulos.tests.evaluar.evaluar_respuesta", return_value=nota_ia("6,0")):
            evaluar.main(7, dry_run=False)
        check("busca con el nombre y los envíos de esa instancia",
              pedidos and pedidos[0][0] == 7 and pedidos[0][1].get("nombre") == "Control 2"
              and propio in pedidos[0][1].get("propios", ()), pedidos[:1])
        check("el feedback va con «Re: Control 2: tema»",
              [m["Subject"] for m in mensajes] == ["Re: Control 2: Logit anidado"], [m["Subject"] for m in mensajes])


ciclo_completo()
instancias_nuevas()
elegir_que_evaluar()
fallos_y_recuperacion()
tutoria_sobre_el_feedback()
ensayo_de_prompt()
estado_desde_el_log()
fusion_de_dos_logs()
sys.exit(resultado())
