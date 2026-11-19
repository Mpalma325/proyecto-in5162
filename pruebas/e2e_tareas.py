"""
Ciclo completo de Tareas sobre una copia desechable, sin red ni API.

Arranca desde la plantilla de semestre vacío y siembra un feedback_T1.csv con
dos alumnos, que es lo que dejaría el paso de generar preguntas.

La T2 repite el ciclo como se hace desde la página desde 2026-2: un correo
elegido a mano en el chequeo, un plazo que enviar guarda, una respuesta que
llega tarde, correcciones que esperan revisión y se mandan después, editadas.
"""

import contextlib
import csv
import io
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
    check("log: 2 evaluaciones", len(datos.log.leer(sid, evento="evaluacion")) == 2)
    anotadas = {e.get("Versiones", "") for e in datos.log.leer(sid, evento="evaluacion")}
    check("log: cada evaluación anota con qué prompt, pauta, escala y correo se hizo",
          len(anotadas) >= 1 and all(p in a for a in anotadas
                                     for p in ("corregir_respuesta.md@", "pauta.md@", "escala=", "correo_feedback.md@")),
          anotadas)
    check("con --no-enviar no se anota un correo que no salió",
          "correo_feedback" not in corregir._versiones({"pregunta": "¿P?", "pauta": "pauta"}, None))

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
    evaluaciones = {e["Correo"]: e for e in datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="evaluacion")}
    check("el log guarda la justificación y la marca de IA en Detalle",
          evaluaciones["dario@x.cl"]["Detalle"] == "Señales de IA. Frases genéricas.", evaluaciones.get("dario@x.cl"))

    titulo("7. T2: las correcciones se editan y se mandan después")
    texto = salida_de(feedback.main, "T2", dry_run=True)
    check("simular no manda nada ni las saca de la revisión",
          enviados == [] and all(f["feedback_pendiente"] for f in storage.leer_csv("T2") if f["nota"]), texto[-300:])
    storage.actualizar_fila("T2", "g1.html", "Dario Rojas", {"nota": "5.5", "comentario": "Revisado a mano."})
    texto = salida_de(feedback.main, "T2", solo={"dario@x.cl"})
    check("--solo manda solo a los elegidos", enviados == ["dario@x.cl"], enviados)
    m = mensajes[-1]
    mid = next(f["message_id"] for f in storage.leer_csv("T2") if f["alumno_nombre"] == "Dario Rojas")
    check("el feedback va en el hilo de la pregunta (In-Reply-To y asunto Re:)",
          mid and m["In-Reply-To"] == mid and m["References"] == mid and m["Subject"].startswith("Re: Pregunta de comprensión"),
          (m["In-Reply-To"], m["Subject"], mid))
    check("la nota editada se registra en datos",
          datos.notas.estado("dario@x.cl", datos.TAREAS, "T2", sid)["Nota"] == "5.5")
    ajustes = datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="ajuste")
    check("y queda un ajuste con lo que había puesto el modelo",
          len(ajustes) == 1 and "5.0" in ajustes[0]["Detalle"] and ajustes[0]["EvaluacionIA"] == "Revisado a mano.",
          ajustes)
    feedback.main("T2")
    check("después sale el resto", enviados == ["dario@x.cl", "carla@x.cl"], enviados)
    salidos = datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="feedback")
    check("cada correo que sale queda como evento 'feedback'", len(salidos) == 2, salidos)
    check("una corrección no editada no deja ajuste",
          len(datos.log.leer(sid, flujo=datos.TAREAS, item="T2", evento="ajuste")) == 1)
    check("ya no queda nada esperando revisión", not any(f["feedback_pendiente"] for f in storage.leer_csv("T2")))
    enviados.clear()
    feedback.main("T2")
    check("mandar otra vez no repite correos", enviados == [], enviados)

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
          corregir_una.call_count == 1 and datos.notas.estado("hugo@x.cl", datos.TAREAS, "T3", sid)["Nota"]
          and not datos.notas.estado("gina@x.cl", datos.TAREAS, "T3", sid)["Nota"], texto)

sys.exit(resultado())
