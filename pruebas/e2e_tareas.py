"""
Ciclo completo de Tareas sobre una copia desechable, sin red ni API.

Arranca desde la plantilla de semestre vacío y siembra un feedback_T1.csv con
dos alumnos, que es lo que dejaría el paso de generar preguntas.

La T2 repite el ciclo como se hace desde la página desde 2026-2: un correo
elegido a mano en el chequeo, un plazo que enviar guarda, una respuesta que
llega tarde, correcciones que esperan revisión y se mandan después, editadas.

La nota cuenta cuando sale el correo: corregir deja la propuesta (`correccion`,
Corregido) y solo el envío deja la `evaluacion` y la Nota. Quién espera su
correo lo decide el log, aunque el CSV de la tarea diga otra cosa.
"""

import contextlib
import csv
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import check, enviados, mensajes, resultado, semestre_desechable, sin_red, titulo

CAMPOS = ["tarea", "grupo_archivo", "alumno_nombre", "alumno_correo", "pregunta_tarea",
          "pregunta", "pauta", "motivo_sin_pregunta", "message_id"]


def sembrar_preguntas(tmp, tarea="T1", alumnos=(("Ana Perez", "ana@x.cl"), ("Beto Soto", "beto@x.cl"))):
    salidas = tmp / "tareas" / "data" / "salidas"
    salidas.mkdir(parents=True, exist_ok=True)
    destino = salidas / f"feedback_{tarea}.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for nombre, correo in alumnos:
            w.writerow({**{k: "" for k in CAMPOS}, "tarea": tarea, "grupo_archivo": "g1.html",
                        "alumno_nombre": nombre, "alumno_correo": correo,
                        "pregunta_tarea": "P1", "pregunta": "¿Por qué escalaste?",
                        "pauta": "Debe explicar."})
    return destino


def salida_de(funcion, *args, **kwargs) -> str:
    """Lo que imprime una función, para revisar sus avisos."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        funcion(*args, **kwargs)
    return buffer.getvalue()


with semestre_desechable(base="_template", sid="_tmp_tareas") as (sid, tmp), sin_red():
    feedback = sembrar_preguntas(tmp)
    from modulos import datos
    from modulos.tareas import corregir, enviar, recolectar

    titulo("1. ENVIO de preguntas (T1)")
    enviar.main("T1", dry_run=False)
    check("envio a los 2", len(enviados) == 2, enviados)
    check("notas.csv: 2 con envio",
          sum(1 for f in datos.notas.leer(sid, datos.TAREAS, "T1") if f["Enviado"]) == 2)
    check("log: 2 eventos de envio", len(datos.log.leer(sid, evento="envio")) == 2)

    titulo("2. RECOLECCION de respuestas")
    with feedback.open(encoding="utf-8-sig") as f:
        mids = [fila["message_id"] for fila in csv.DictReader(f)]
    entrantes = {m: {"remitente": "x@x.cl", "texto": "Mi respuesta a la tarea.",
                     "fecha": "2026-08-25T10:00:00"} for m in mids if m}
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes):
        recolectar.main("T1")
    check("log: 2 respuestas", len(datos.log.leer(sid, evento="respuesta")) == 2)

    titulo("3. CORRECCION")
    enviados.clear()
    with patch("modulos.tareas.corregir._corregir_una",
               return_value={"nota": 6.0, "comentario": "Bien.",
                             "justificacion": "ok", "senales_ia": False}):
        corregir.main("T1", dry_run=False, enviar=True)
    check("feedback a los 2", len(enviados) == 2, enviados)
    check("notas.csv con nota",
          sum(1 for f in datos.notas.leer(sid, datos.TAREAS, "T1") if f["Nota"]) == 2)
    check("log: 2 correcciones y 2 evaluaciones",
          len(datos.log.leer(sid, evento="correccion")) == 2 and len(datos.log.leer(sid, evento="evaluacion")) == 2)
    salidos = {m["Message-ID"] for m in mensajes[-2:]}
    check("cada evaluación guarda el Message-ID del correo que salió",
          {e["MessageId"] for e in datos.log.leer(sid, evento="evaluacion")} == salidos, salidos)
    anotadas = {e.get("Versiones", "") for e in datos.log.leer(sid, evento="evaluacion")}
    check("log: cada evaluación anota con qué prompt, pauta, escala y correo se hizo",
          len(anotadas) >= 1 and all(p in a for a in anotadas
                                     for p in ("corregir_respuesta.md@", "pauta.md@", "escala=", "correo_feedback.md@")),
          anotadas)
    check("con --no-enviar no se anota un correo que no salió",
          "correo_feedback" not in corregir._versiones({"pregunta": "¿P?", "pauta": "pauta"}, None))
    escala = tmp / "tareas" / "prompts" / "escala.json"
    escala.write_text('{"valores": [-0.2, 0.0, 0.2]}', encoding="utf-8")
    con_escala = corregir._versiones({"pregunta": "¿P?", "pauta": "pauta"}, None)
    escala.unlink()
    check("con escala.json se anota esa escala, no NOTA_MIN-NOTA_MAX",
          "escala.json@" in con_escala and "escala=" not in con_escala, con_escala)

    titulo("4. tests y tareas conviven en las mismas tablas")
    datos.notas.marcar_enviado("ana@x.cl", datos.TESTS, "1", semestre_id=sid)
    check("mismo alumno, dos flujos sin pisarse",
          datos.notas.estado("ana@x.cl", datos.TAREAS, "T1", sid)["Nota"] == "6.0"
          and datos.notas.estado("ana@x.cl", datos.TESTS, "1", sid)["Nota"] == "")
    flujos = {f["Flujo"] for f in datos.notas.leer(sid)}
    check("ambos flujos en notas.csv", flujos == {"test", "tarea"}, flujos)

    titulo("5. T2: el correo elegido a mano en el chequeo llega a enviar")
    from modulos.tareas import asignacion, feedback, storage
    sembrar_preguntas(tmp, "T2", (("Carla Diaz", "carla@x.cl"), ("Dario Rojas", "dario@x.cl"),
                                  ("Eva Lagos", "")))
    asignacion.escribir_correos("T2", {("g1.html", "Eva  LAGOS"): "Eva@X.cl"})
    enviados.clear()
    texto = salida_de(enviar.main, "T2", dry_run=False, minutos=25)
    check("enviar le manda a quien no calzó, con el correo elegido a mano",
          sorted(enviados) == ["carla@x.cl", "dario@x.cl", "eva@x.cl"], enviados)
    filas = {f["alumno_nombre"]: f for f in storage.leer_csv("T2")}
    check("el correo elegido queda en el CSV de la tarea", filas["Eva Lagos"]["alumno_correo"] == "eva@x.cl")
    plazo = datetime.fromisoformat(filas["Carla Diaz"]["plazo"])
    check("enviar guarda el plazo de cada alumno, al minuto",
          all(f["plazo"] == filas["Carla Diaz"]["plazo"] for f in filas.values()) and plazo.second == 0)
    check("enviar dice hasta cuándo pueden responder", f"hasta las {plazo:%H:%M}" in texto, texto[-300:])

    titulo("6. T2: recolectar y corregir avisan a quien respondió tarde")
    a_tiempo = (plazo + timedelta(seconds=40)).isoformat()  # "hasta las 10:25" incluye 10:25:40
    tarde = (plazo + timedelta(minutes=3)).isoformat()
    mids = {f["alumno_correo"]: f["message_id"] for f in filas.values()}
    entrantes = {mids["carla@x.cl"]: {"remitente": "carla@x.cl", "texto": "Escalé para comparar.", "fecha": a_tiempo},
                 mids["dario@x.cl"]: {"remitente": "dario@x.cl", "texto": "Era necesario.", "fecha": a_tiempo},
                 mids["eva@x.cl"]: {"remitente": "eva@x.cl", "texto": "Llegué tarde.", "fecha": tarde}}
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes):
        texto = salida_de(recolectar.main, "T2")
    check("recolectar avisa la respuesta fuera de plazo, y solo esa",
          texto.count("fuera de plazo") == 1 and "Eva Lagos" in texto.split("fuera de plazo")[0].splitlines()[-2],
          texto)
    enviados.clear()
    resultado_modelo = {"nota": 6.0, "comentario": "Bien explicado.", "justificacion_interna": "Entiende el escalamiento.",
                        "señales_copia_ia": False}
    with patch("modulos.tareas.corregir._corregir_una", side_effect=[
            resultado_modelo, {**resultado_modelo, "nota": 5.0, "señales_copia_ia": True,
                               "justificacion_interna": "Frases genéricas."}]):
        texto = salida_de(corregir.main, "T2", dry_run=False, enviar=False)
    check("corregir deja fuera a quien respondió tarde, con aviso",
          "Eva Lagos" in texto and "fuera de plazo" in texto
          and not datos.notas.estado("eva@x.cl", datos.TAREAS, "T2", sid)["Nota"], texto)
    check("sin mandar el feedback no sale ningún correo", enviados == [], enviados)
    filas = {f["alumno_nombre"]: f for f in storage.leer_csv("T2")}
    check("la corrección queda en el CSV esperando revisión",
          filas["Carla Diaz"]["feedback_pendiente"] == "sí" and filas["Carla Diaz"]["comentario"] == "Bien explicado."
          and filas["Dario Rojas"]["nota"] == "5.0", filas["Dario Rojas"])
    check("la marca de IA y la justificación quedan para el equipo docente",
          filas["Dario Rojas"]["senales_ia"] == "sí" and filas["Dario Rojas"]["justificacion"] == "Frases genéricas."
          and not filas["Carla Diaz"]["senales_ia"])
    correcciones = {e["Correo"]: e for e in datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="correccion")}
    propuesta = json.loads(correcciones["dario@x.cl"]["EvaluacionIA"])
    check("el log guarda la propuesta con el JSON completo, justificación y marca de IA incluidas",
          correcciones["dario@x.cl"]["Nota"] == "5.0" and propuesta["justificacion_interna"] == "Frases genéricas."
          and propuesta["señales_copia_ia"] is True and correcciones["dario@x.cl"]["Detalle"] == "modo=revisar",
          correcciones.get("dario@x.cl"))
    carla = datos.notas.estado("carla@x.cl", datos.TAREAS, "T2", sid)
    check("sin mandar el feedback no hay nota: queda Corregido y ninguna evaluación",
          carla["Corregido"] and not carla["Nota"]
          and not datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="evaluacion"), carla)
    check("rearmar el estado desde el log tampoco le pone nota",
          datos.log.reconstruir_estado(sid)[("carla@x.cl", datos.TAREAS, "T2")]["Nota"] == ""
          and datos.notas.sincronizar_desde_log(sid, simular=True)["Nota"] == 0)
    with patch("modulos.tareas.corregir._corregir_una", return_value=resultado_modelo) as corregir_una:
        texto = salida_de(corregir.main, "T2", dry_run=False, enviar=False)
    check("una segunda corrida no vuelve a llamar al modelo para las que esperan revisión",
          corregir_una.call_count == 0 and len(datos.log.leer(sid, item="T2", evento="correccion")) == 2, texto)

    titulo("7. T2: las correcciones se editan y se mandan después")
    texto = salida_de(feedback.main, "T2", dry_run=True)
    check("simular no manda nada ni las saca de la revisión",
          enviados == [] and all(f["feedback_pendiente"] for f in storage.leer_csv("T2") if f["nota"]), texto[-300:])
    storage.actualizar_fila("T2", "g1.html", "Dario Rojas", {"nota": "5.5", "comentario": "Revisado a mano."})
    texto = salida_de(feedback.main, "T2", solo={"dario@x.cl"}, por="profe@x.cl")
    check("--solo manda solo a los elegidos", enviados == ["dario@x.cl"], enviados)
    m = mensajes[-1]
    mid = next(f["message_id"] for f in storage.leer_csv("T2") if f["alumno_nombre"] == "Dario Rojas")
    check("el feedback va en el hilo de la pregunta (In-Reply-To y asunto Re:)",
          mid and m["In-Reply-To"] == mid and m["References"] == mid and m["Subject"].startswith("Re: Pregunta de comprensión"),
          (m["In-Reply-To"], m["Subject"], mid))
    check("la nota editada se registra en datos",
          datos.notas.estado("dario@x.cl", datos.TAREAS, "T2", sid)["Nota"] == "5.5")
    salio = datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="evaluacion")
    check("queda una evaluación con lo que salió, el Message-ID y quién la revisó",
          len(salio) == 1 and salio[0]["MessageId"] == m["Message-ID"] and salio[0]["Nota"] == "5.5"
          and salio[0]["EvaluacionIA"] == "Revisado a mano."
          and salio[0]["Detalle"] == "revisado por profe@x.cl; nota 5.0 → 5.5; comentario editado"
          and "correo_feedback.md@" in salio[0]["Versiones"], salio)
    check("ya no se anotan 'ajuste' ni 'feedback'",
          not datos.log.leer(sid, item="T2", evento="ajuste") and not datos.log.leer(sid, item="T2", evento="feedback"))
    feedback.main("T2", por="profe@x.cl")
    check("después sale el resto", enviados == ["dario@x.cl", "carla@x.cl"], enviados)
    salio = {e["Correo"]: e for e in datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="evaluacion")}
    check("cada correo que sale queda como evaluación", len(salio) == 2, salio)
    check("una corrección no editada solo dice quién la revisó",
          salio["carla@x.cl"]["Detalle"] == "revisado por profe@x.cl", salio["carla@x.cl"]["Detalle"])
    check("ya no queda nada esperando revisión", not any(f["feedback_pendiente"] for f in storage.leer_csv("T2")))
    enviados.clear()
    feedback.main("T2")
    check("mandar otra vez no repite correos", enviados == [], enviados)

    titulo("7b. T2: el CSV dice pendiente pero el log ya tiene la evaluación (R12)")
    # La página guardó el CSV mientras corría el envío: el CSV del trabajo no
    # se subió (etag) y la nube conserva feedback_pendiente = "sí".
    storage.actualizar_fila("T2", "g1.html", "Carla Diaz", {"feedback_pendiente": "sí"})
    texto = salida_de(feedback.main, "T2", dry_run=True)
    check("simular no la muestra como correo por salir ni toca el CSV",
          enviados == [] and "ya salió" in texto and "Para:" not in texto
          and storage.leer_csv("T2")[0]["feedback_pendiente"] == "sí", texto)
    texto = salida_de(feedback.main, "T2", solo={"carla@x.cl"}, por="profe@x.cl")
    check("en real no se reenvía", enviados == [] and len(datos.log.leer(sid, item="T2", evento="evaluacion")) == 2,
          texto)
    check("y deja de figurar como pendiente en el CSV",
          not any(f["feedback_pendiente"] for f in storage.leer_csv("T2")))

    titulo("8. un envío programado cuenta el plazo desde la hora programada")
    ahora = datetime.now().astimezone().replace(microsecond=0)
    programado = ahora - timedelta(seconds=50)
    inicio, aviso = enviar.inicio_del_plazo(programado.astimezone().isoformat(), ahora)
    check("si la cola lo despachó con unos segundos de atraso, cuenta desde la hora programada",
          inicio == programado and not aviso, (inicio, aviso))
    utc = programado.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    check("la hora puede venir en UTC, como la guarda el sitio",
          enviar.inicio_del_plazo(utc, ahora)[0] == programado)
    inicio, aviso = enviar.inicio_del_plazo((ahora - timedelta(minutes=12)).isoformat(), ahora)
    check("si salió mucho después, cuenta desde ahora y lo avisa",
          inicio == ahora and "12 minutos después" in aviso, aviso)
    check("sin hora programada, desde ahora y sin aviso", enviar.inicio_del_plazo(None, ahora) == (ahora, ""))
    check("una hora que no se entiende no detiene el envío",
          enviar.inicio_del_plazo("mañana", ahora)[0] == ahora)

    titulo("9. T3: un envío a un grupo chico no toma respuestas de otro envío")
    # En la mañana salió a Fabio y Gina; en la tarde se recupera a Hugo. La
    # respuesta tardía de Gina no debe entrar en la recolección ni en la
    # corrección programadas de Hugo (TRASPASO_TAREAS.md, brecha 4).
    sembrar_preguntas(tmp, "T3", (("Fabio Nuñez", "fabio@x.cl"), ("Gina Toro", "gina@x.cl")))
    enviar.main("T3", dry_run=False)
    filas_t3 = storage.leer_csv("T3")
    filas_t3.append({**{k: "" for k in filas_t3[0]}, "tarea": "T3", "grupo_archivo": "g2.html",
                     "alumno_nombre": "Hugo Vera", "alumno_correo": "hugo@x.cl", "pregunta_tarea": "P1",
                     "pregunta": "¿Por qué escalaste?", "pauta": "Debe explicar."})
    with (tmp / "tareas" / "data" / "salidas" / "feedback_T3.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_t3[0]))
        w.writeheader()
        w.writerows(filas_t3)
    enviados.clear()
    enviar.main("T3", dry_run=False)
    check("el segundo envío sale solo a Hugo", enviados == ["hugo@x.cl"], enviados)
    filas = {f["alumno_correo"]: f for f in storage.leer_csv("T3")}
    plazo_gina = datetime.fromisoformat(filas["gina@x.cl"]["plazo"])
    entrantes = {filas["gina@x.cl"]["message_id"]: {"remitente": "gina@x.cl", "texto": "Tarde.",
                                                    "fecha": (plazo_gina + timedelta(minutes=30)).isoformat()},
                 filas["hugo@x.cl"]["message_id"]: {"remitente": "hugo@x.cl", "texto": "Para comparar.",
                                                    "fecha": datetime.now().astimezone().isoformat()}}
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes) as buscar:
        recolectar.main("T3", solo={"hugo@x.cl"})
    check("recolectar con 'solo' busca solo el correo de ese grupo",
          buscar.call_args.args[0] == [filas["hugo@x.cl"]["message_id"]], buscar.call_args)
    check("la respuesta tardía del otro envío no se registra",
          not datos.notas.estado("gina@x.cl", datos.TAREAS, "T3", sid)["Respondio"]
          and datos.notas.estado("hugo@x.cl", datos.TAREAS, "T3", sid)["Respondio"])
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes):
        recolectar.main("T3")
    with patch("modulos.tareas.corregir._corregir_una", return_value=resultado_modelo) as corregir_una:
        texto = salida_de(corregir.main, "T3", dry_run=False, enviar=False,
                          solo={"hugo@x.cl", "gina@x.cl"}, sin_tarde=True)
    check("corregir con 'solo' y sin_tarde deja fuera lo que llegó tarde",
          corregir_una.call_count == 1 and datos.notas.estado("hugo@x.cl", datos.TAREAS, "T3", sid)["Corregido"]
          and not datos.notas.estado("gina@x.cl", datos.TAREAS, "T3", sid)["Corregido"], texto)

    titulo("10. T3: la corrección que el CSV perdió se recupera del log")
    # corregir guardó en el log y en notas.csv, pero su CSV no se subió porque
    # la página lo guardó entretanto (etag).
    storage.actualizar_fila("T3", "g2.html", "Hugo Vera",
                            {"nota": "", "comentario": "", "justificacion": "", "feedback_pendiente": ""})
    enviados.clear()
    texto = salida_de(feedback.main, "T3", dry_run=True)
    hugo = next(f for f in storage.leer_csv("T3") if f["alumno_correo"] == "hugo@x.cl")
    check("simular la muestra con la corrección del log, sin escribir el CSV",
          enviados == [] and "al mandar de verdad se copia" in texto and "Bien explicado." in texto
          and not hugo["feedback_pendiente"], texto[-400:])
    texto = salida_de(feedback.main, "T3", solo={"nadie@x.cl"}, por="profe@x.cl")
    hugo = next(f for f in storage.leer_csv("T3") if f["alumno_correo"] == "hugo@x.cl")
    check("en real la copia al CSV, sin mandar a quien no se eligió",
          enviados == [] and hugo["feedback_pendiente"] == "sí" and hugo["nota"] == "6.0"
          and hugo["comentario"] == "Bien explicado." and hugo["justificacion"] == "Entiende el escalamiento.",
          (hugo, texto))

    titulo("11. T3: un envío que falla no deja nota y se reintenta")
    with patch("modulos.tareas.corregir.enviar_correo", side_effect=OSError("SMTP caído")):
        texto = salida_de(feedback.main, "T3", por="profe@x.cl")
    hugo = datos.notas.estado("hugo@x.cl", datos.TAREAS, "T3", sid)
    check("sin correo no hay evaluación ni nota, y sigue pendiente",
          "Sigue pendiente" in texto and not hugo["Nota"] and hugo["Corregido"]
          and not datos.log.leer(sid, item="T3", evento="evaluacion")
          and any(f["feedback_pendiente"] for f in storage.leer_csv("T3")), texto)
    feedback.main("T3", por="profe@x.cl")
    check("la corrida siguiente lo manda", enviados == ["hugo@x.cl"]
          and datos.notas.estado("hugo@x.cl", datos.TAREAS, "T3", sid)["Nota"] == "6.0", enviados)

    titulo("12. filas de antes (2026-2): Nota al corregir, y 'feedback' al mandar")
    # corregir --no-enviar registraba una evaluacion sin Message-ID y la Nota;
    # feedback.py anotaba 'feedback' al mandar. Iris espera su correo; Juan ya
    # lo recibió, pero el CSV no alcanzó a quitarle el pendiente.
    sembrar_preguntas(tmp, "T4", (("Iris Mora", "iris@x.cl"), ("Juan Paz", "juan@x.cl")))
    for nombre, correo in (("Iris Mora", "iris@x.cl"), ("Juan Paz", "juan@x.cl")):
        datos.notas.marcar_enviado(correo, datos.TAREAS, "T4", semestre_id=sid)
        datos.notas.marcar_respondio(correo, datos.TAREAS, "T4", semestre_id=sid)
        datos.notas.registrar_nota(correo, datos.TAREAS, "T4", "5.0", semestre_id=sid)
        datos.log.registrar("respuesta", datos.TAREAS, "T4", correo, sid, Respuesta="Respuesta antigua.")
        datos.log.registrar("evaluacion", datos.TAREAS, "T4", correo, sid, Modelo="gpt-viejo", Nota="5.0",
                            EvaluacionIA="Comentario del modelo.")
        storage.actualizar_fila("T4", "g1.html", nombre,
                                {"nota": "5.0", "comentario": "Comentario del modelo.", "feedback_pendiente": "sí"})
    datos.log.registrar("feedback", datos.TAREAS, "T4", "juan@x.cl", sid, Nota="5.0",
                        EvaluacionIA="Comentario del modelo.")
    with patch("modulos.tareas.corregir._corregir_una", return_value=resultado_modelo) as corregir_una:
        corregir.main("T4", dry_run=False, enviar=False)
    check("con Nota de antes no se vuelve a corregir", corregir_una.call_count == 0)
    storage.actualizar_fila("T4", "g1.html", "Iris Mora", {"nota": "5.5"})
    enviados.clear()
    texto = salida_de(feedback.main, "T4", por="profe@x.cl")
    nuevas = datos.log.leer(sid, item="T4", evento="evaluacion")[-1:]
    check("sale la de Iris, que esperaba; la de Juan no se repite", enviados == ["iris@x.cl"], (enviados, texto))
    check("y queda como evaluación con Message-ID, comparada con la nota de antes",
          nuevas and nuevas[0]["Correo"] == "iris@x.cl" and nuevas[0]["MessageId"] == mensajes[-1]["Message-ID"]
          and nuevas[0]["Detalle"] == "revisado por profe@x.cl; nota 5.0 → 5.5" and nuevas[0]["Modelo"] == "gpt-viejo"
          and datos.notas.estado("iris@x.cl", datos.TAREAS, "T4", sid)["Nota"] == "5.5", nuevas)
    check("el 'feedback' de antes se sigue leyendo: Juan ya no figura pendiente",
          not any(f["feedback_pendiente"] for f in storage.leer_csv("T4"))
          and len(datos.log.leer(sid, item="T4", evento="feedback")) == 1)

    titulo("10. T4: respuestas raras (prueba de punta a punta del 19/11/2026)")
    from modulos.mail.limpieza import _limpiar_respuesta
    alumnos_t4 = (("Ana Perez", "ana@x.cl"), ("Beto Soto", "beto@x.cl"), ("Carla Diaz", "carla@x.cl"),
                  ("Dario Rojas", "dario@x.cl"), ("Eva Lagos", "eva@x.cl"), ("Fabio Nuñez", "fabio@x.cl"))
    sembrar_preguntas(tmp, "T4", alumnos_t4)
    mensajes.clear()
    enviar.main("T4", dry_run=False, minutos=20)
    cuerpos = {m["To"]: m.get_payload()[0].get_payload(decode=True).decode("utf-8") for m in mensajes}
    filas = {f["alumno_correo"]: f for f in storage.leer_csv("T4")}
    plazo = datetime.fromisoformat(filas["ana@x.cl"]["plazo"])
    antes = lambda minutos: (plazo - timedelta(minutes=minutos)).isoformat()  # noqa: E731
    despues = (plazo + timedelta(minutes=3)).isoformat()
    # Lo que deja buscar_respuestas de un correo que trae solo la cita: la
    # limpieza la toma por una respuesta escrita dentro de ella.
    cita = "\n".join(f"> {l}" if l.strip() else ">" for l in cuerpos["ana@x.cl"].splitlines())
    solo_cita = _limpiar_respuesta(f"\nEl jue, 19 nov 2026 a las 17:20, Curso <curso@x.cl> escribió:\n{cita}\n")
    check("(el correo de prueba es el del informe: la limpieza deja nuestra pregunta como texto)",
          "¿Por qué escalaste?" in solo_cita, solo_cita[:200])

    def correo(remitente, texto, fecha, adjuntos=()):
        return {"remitente": remitente, "texto": texto, "fecha": fecha, "adjuntos": list(adjuntos)}

    entrantes = {
        filas["ana@x.cl"]["message_id"]: [correo("ana@x.cl", solo_cita, antes(10))],
        filas["beto@x.cl"]["message_id"]: [
            # Desordenados a propósito: buscar_respuestas no los ordena.
            correo("beto@x.cl", "Perdón, se me olvidó agregar: lo revisé con mi grupo.", antes(2)),
            correo("beto@x.cl", "Escalé para que los coeficientes sean comparables.", antes(9))],
        filas["carla@x.cl"]["message_id"]: [
            correo("carla@x.cl", "Escalé porque las variables tienen unidades distintas.", antes(5)),
            correo("carla@x.cl", "Una aclaración tardía.", despues)],
        filas["dario@x.cl"]["message_id"]: [correo("dario.rojas@otro.cl", "Escalé para comparar.", antes(4))],
        filas["eva@x.cl"]["message_id"]: [correo("eva@x.cl", "Adjunto mi respuesta.", antes(4), ["respuesta.docx"])],
        filas["fabio@x.cl"]["message_id"]: [correo("fabio@x.cl", "", antes(4), ["respuesta.pdf"])],
    }
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes):
        texto = salida_de(recolectar.main, "T4")
    respuestas = {e["Correo"]: e["Respuesta"]
                  for e in datos.log.leer(sid, flujo=datos.TAREAS, item="T4", evento="respuesta")}
    estado = lambda c: datos.notas.estado(c, datos.TAREAS, "T4", sid) or {}  # noqa: E731
    filas = {f["alumno_correo"]: f for f in storage.leer_csv("T4")}

    check("1) un correo con solo la cita no es una respuesta: el alumno sigue sin responder",
          "ana@x.cl" not in respuestas and not estado("ana@x.cl").get("Respondio"), respuestas.get("ana@x.cl"))
    check("1) y queda anotado", "solo la cita" in filas["ana@x.cl"]["aviso"], filas["ana@x.cl"]["aviso"])
    beto = respuestas.get("beto@x.cl", "")
    check("2) dos correos a tiempo se corrigen juntos, en orden y con una línea entre ellos",
          beto.startswith("Escalé para que") and "--- correo 2 de 2," in beto and beto.endswith("con mi grupo."), beto)
    check("2) el plazo se mide con el primero", estado("beto@x.cl").get("Respondio") == antes(9),
          estado("beto@x.cl"))
    check("2) y se avisa que fueron dos", "2 correos" in filas["beto@x.cl"]["aviso"], filas["beto@x.cl"]["aviso"])
    check("2) una aclaración después del plazo no deja tarde la respuesta a tiempo ni entra en ella",
          respuestas.get("carla@x.cl") == "Escalé porque las variables tienen unidades distintas."
          and not storage.respondio_tarde(filas["carla@x.cl"], estado("carla@x.cl").get("Respondio")),
          (respuestas.get("carla@x.cl"), estado("carla@x.cl")))
    check("2) la tardía queda en el aviso", "después del plazo" in filas["carla@x.cl"]["aviso"],
          filas["carla@x.cl"]["aviso"])
    check("6) la respuesta desde otra dirección se acepta y se avisa",
          respuestas.get("dario@x.cl") == "Escalé para comparar."
          and "otra dirección (dario.rojas@otro.cl)" in filas["dario@x.cl"]["aviso"], filas["dario@x.cl"])
    check("7) con adjunto: se corrige el texto y se avisa que el adjunto no se leyó",
          respuestas.get("eva@x.cl") == "Adjunto mi respuesta." and "respuesta.docx" in filas["eva@x.cl"]["aviso"],
          filas["eva@x.cl"])
    check("7) solo un adjunto, sin texto: sin respuesta, con aviso",
          "fabio@x.cl" not in respuestas and "respuesta.pdf" in filas["fabio@x.cl"]["aviso"], filas["fabio@x.cl"])
    check("los avisos también salen en pantalla", "otra dirección" in texto and "solo la cita" in texto, texto[-800:])
    with patch("modulos.tareas.recolectar.buscar_respuestas", return_value=entrantes):
        recolectar.main("T4")
    check("recolectar de nuevo no repite los avisos",
          storage.leer_csv("T4")[0]["aviso"].count("solo la cita") == 1, storage.leer_csv("T4")[0]["aviso"])

    with patch("modulos.tareas.corregir._corregir_una", return_value=resultado_modelo) as corregir_una:
        salida_de(corregir.main, "T4", dry_run=False, enviar=False)
    corregidas = {c.args[2]["alumno_correo"]: c.args[2]["respuesta"] for c in corregir_una.call_args_list}
    check("corregir recibe las dos de Beto juntas y a Carla sin la tardía, y no a Ana ni a Fabio",
          set(corregidas) == {"beto@x.cl", "carla@x.cl", "dario@x.cl", "eva@x.cl"}
          and corregidas["beto@x.cl"] == beto and "tardía" not in corregidas["carla@x.cl"], corregidas)

    titulo("11. buscar_respuestas trae todo el hilo, con los adjuntos")
    from email.message import EmailMessage
    from modulos.mail import lectura

    def eml(de, texto, fecha, responde_a, adjunto=None):
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = de, "curso@x.cl", "Re: Pregunta"
        m["Date"], m["In-Reply-To"], m["References"] = fecha, responde_a, responde_a
        m["Message-ID"] = f"<{abs(hash((de, texto)))}@alumno.test>"
        m.set_content(texto)
        if adjunto:
            m.add_attachment(b"PK", maintype="application", subtype="octet-stream", filename=adjunto)
        return m.as_bytes()

    buzon = [eml("Beto <beto@x.cl>", "Primera.", "Thu, 19 Nov 2026 17:30:00 -0300", "<p1@curso>"),
             eml("beto@x.cl", "Se me olvidó agregar algo.", "Thu, 19 Nov 2026 17:35:00 -0300", "<p1@curso>"),
             eml("eva@x.cl", "", "Thu, 19 Nov 2026 17:31:00 -0300", "<p2@curso>", adjunto="respuesta.docx"),
             eml("otro@x.cl", "Ruido.", "Thu, 19 Nov 2026 17:32:00 -0300", "<ajeno@x>")]

    class ImapFalso:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): return "OK", []
        def select(self, *a, **k): return "OK", []
        def search(self, *a): return "OK", [b" ".join(str(i + 1).encode() for i in range(len(buzon)))]
        def fetch(self, i, _): return "OK", [(b"", buzon[int(i) - 1])]

    with patch.object(lectura.imaplib, "IMAP4_SSL", ImapFalso):
        hallado = lectura.buscar_respuestas(["<p1@curso>", "<p2@curso>"])
    check("las dos respuestas de Beto, no solo la última",
          sorted(r["texto"] for r in hallado.get("<p1@curso>", [])) == ["Primera.", "Se me olvidó agregar algo."],
          hallado.get("<p1@curso>"))
    check("un correo sin texto pero con adjunto se informa con el nombre del archivo",
          [r["adjuntos"] for r in hallado.get("<p2@curso>", [])] == [["respuesta.docx"]], hallado.get("<p2@curso>"))
    check("el ruido no se asocia a nadie", set(hallado) == {"<p1@curso>", "<p2@curso>"}, set(hallado))

    titulo("12. el plazo escrito a mano en la plantilla no sale callado")
    from modulos.tareas import config as config_tareas
    plantilla = config_tareas.PROMPTS / "correo_pregunta.md"
    original = plantilla.read_text(encoding="utf-8")
    sembrar_preguntas(tmp, "T5", (("Gina Toro", "gina@x.cl"),))
    plantilla.write_text("Hola {nombre},\n\n{pregunta}\n\nPlazo de respuesta: hoy lunes 3 de agosto de 2026, "
                         "hasta las 10:20 hrs.\n", encoding="utf-8")
    enviados.clear()
    texto = salida_de(enviar.main, "T5", dry_run=True)
    check("en simulación avisa que la fecha está escrita a mano", "{plazo}" in texto and "3 de agosto" in texto
          and enviados == [], texto[-500:])
    texto = salida_de(enviar.main, "T5", dry_run=False)
    check("y no envía nada de verdad", enviados == [] and "No se envía" in texto, texto[-500:])
    check("ni marca el envío", not datos.notas.ya_enviado("gina@x.cl", datos.TAREAS, "T5", sid))
    check("y termina en error (el trabajo de la página queda como fallido)",
          enviar.main("T5", dry_run=False) is False)
    plazo_envio = enviar.calcular_plazo(datetime.now().astimezone(), 20)
    revisar = enviar.revisar_plazo_plantilla
    check("si la fecha escrita es justo la de este envío, pasa con un aviso",
          revisar(f"Plazo: {enviar.texto_plazo(plazo_envio)} hrs.", plazo_envio)[1] is False)
    aviso, detener = revisar("Tienes 20 minutos para responder.", plazo_envio)
    check("sin fecha ni hora («tienes 20 minutos»), se envía con un aviso", not detener and "{plazo}" in aviso, aviso)
    check("con {plazo}, nada que decir", revisar("Plazo: {plazo} hrs.", plazo_envio) == ("", False))
    for texto in ("Responde en 2-3 líneas.", "Preguntas 1-2 de la tarea.", "Ver la tabla 40/50."):
        check(f"«{texto}» no es una fecha: no detiene el envío", revisar(texto, plazo_envio)[1] is False, texto)
    for texto in ("Hasta el 11/09.", "Hasta el 11-09-2026.", "Hasta las 10:20."):
        check(f"«{texto}» sí es una fecha escrita: detiene", revisar(texto, plazo_envio)[1] is True, texto)
    plantilla.write_text(original, encoding="utf-8")

    titulo("13. el saludo usa el nombre de la nómina")
    with (tmp / "alumnos.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Nombre", "Correo", "Grupo"])
        w.writerow(["Gina Paz Toro", "gina@x.cl", ""])
    storage.actualizar_fila("T5", "g1.html", "Gina Toro", {"alumno_nombre": "Toro"})
    mensajes.clear()
    enviar.main("T5", dry_run=False)
    cuerpo = mensajes[-1].get_payload()[0].get_payload(decode=True).decode("utf-8") if mensajes else ""
    check("quien firmó con el apellido recibe «Hola Gina,»", cuerpo.startswith("Hola Gina,"), cuerpo[:40])
    fila_gina = {**storage.leer_csv("T5")[0], "respuesta": "R", "comentario": "C", "nota": "0.3"}
    check("el feedback también", corregir._construir_cuerpo_feedback("Hola {nombre}:", fila_gina) == "Hola Gina:")
    check("si no está en la nómina, la primera palabra de la tabla",
          corregir._construir_cuerpo_feedback("Hola {nombre}:", {**fila_gina, "alumno_correo": "nadie@x.cl"})
          == "Hola Toro:")

sys.exit(resultado())
