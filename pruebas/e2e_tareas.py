"""
Ciclo completo de Tareas sobre una copia desechable, sin red ni API.

Arranca desde la plantilla de semestre vacío y siembra un feedback_T1.csv con
dos alumnos, que es lo que dejaría el paso de generar preguntas.
"""

import csv
import sys
from unittest.mock import patch

sys.path.insert(0, "pruebas")
from comun import check, enviados, resultado, semestre_desechable, sin_red, titulo

CAMPOS = ["tarea", "grupo_archivo", "alumno_nombre", "alumno_correo", "pregunta_tarea",
          "pregunta", "pauta", "motivo_sin_pregunta", "message_id"]


def sembrar_preguntas(tmp):
    salidas = tmp / "tareas" / "data" / "salidas"
    salidas.mkdir(parents=True, exist_ok=True)
    destino = salidas / "feedback_T1.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        for nombre, correo in (("Ana Perez", "ana@x.cl"), ("Beto Soto", "beto@x.cl")):
            w.writerow({**{k: "" for k in CAMPOS}, "tarea": "T1", "grupo_archivo": "g1.html",
                        "alumno_nombre": nombre, "alumno_correo": correo,
                        "pregunta_tarea": "P1", "pregunta": "¿Por qué escalaste?",
                        "pauta": "Debe explicar."})
    return destino


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

    titulo("4. tests y tareas conviven en las mismas tablas")
    datos.notas.marcar_enviado("ana@x.cl", datos.TESTS, "1", semestre_id=sid)
    check("mismo alumno, dos flujos sin pisarse",
          datos.notas.estado("ana@x.cl", datos.TAREAS, "T1", sid)["Nota"] == "6.0"
          and datos.notas.estado("ana@x.cl", datos.TESTS, "1", sid)["Nota"] == "")
    flujos = {f["Flujo"] for f in datos.notas.leer(sid)}
    check("ambos flujos en notas.csv", flujos == {"test", "tarea"}, flujos)

sys.exit(resultado())
