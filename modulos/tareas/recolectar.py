"""
Paso 3 del flujo: recolectar respuestas de los alumnos desde el inbox.

Lee el CSV de la tarea, identifica las filas con correo enviado pero sin
respuesta, busca en el inbox los correos que sean Reply a esos Message-IDs,
y guarda el texto de la respuesta + timestamp en el CSV.

Uso:
    python -m modulos.tareas.recolectar               # tarea = config.TAREA_DEFAULT
    python -m modulos.tareas.recolectar T1
    python -m modulos.tareas.recolectar T1 --solo a@x.cl,b@y.cl   # solo esos correos

Con --solo se busca la respuesta solo de esos alumnos; los demás pendientes
siguen igual. Lo usa el envío programado a un grupo chico, para que una
respuesta tardía de otro envío no entre en esta tanda.
"""

import sys

from modulos import datos as _datos
from modulos.datos import candidatos as _candidatos

from . import config, storage
from modulos.mail import buscar_respuestas
from modulos.progreso import avanzar


def main(tarea: str, solo: set[str] | None = None) -> None:
    """`solo`: si se pasa, busca solo las respuestas de esos correos."""
    filas = storage.leer_csv(tarea)
    if not filas:
        print(f"No hay CSV para tarea {tarea}.")
        return

    # Pendientes: ya se les envió (tienen message_id) pero aún no respondieron
    def _respondio(correo: str) -> bool:
        e = _datos.notas.estado(correo, _datos.TAREAS, tarea)
        return bool(e and e.get("Respondio", "").strip())

    pendientes = [
        f for f in filas
        if f.get("message_id") and not _respondio(f.get("alumno_correo", ""))
    ]
    if solo is not None:
        fuera = [f for f in pendientes if f.get("alumno_correo", "").strip().lower() not in solo]
        if fuera:
            print(f"{len(fuera)} pendiente(s) de otro envío quedan para después.")
        pendientes = [f for f in pendientes if f.get("alumno_correo", "").strip().lower() in solo]
    if not pendientes:
        print(f"No hay respuestas pendientes por buscar para {tarea}.")
        return

    message_ids = [f["message_id"] for f in pendientes]
    print(f"Buscando respuestas en inbox para {len(message_ids)} correo(s) pendiente(s)...")

    encontradas = buscar_respuestas(message_ids)
    print(f"Encontradas {len(encontradas)} respuesta(s) nuevas.\n")

    for fila in avanzar(pendientes, "alumnos"):
        mid = fila["message_id"]
        if mid not in encontradas:
            print(f"  ⋯ {fila['alumno_nombre']:30s}: sin respuesta aún")
            continue

        respuesta = encontradas[mid]
        try:
            _datos.notas.marcar_respondio(fila["alumno_correo"], _datos.TAREAS,
                                          tarea, respuesta["fecha"])
            _datos.log.registrar("respuesta", _datos.TAREAS, tarea,
                                 fila["alumno_correo"], Respuesta=respuesta["texto"])
        except Exception as _e:  # noqa: BLE001
            print(f"     ⚠ no pude registrar en el esquema nuevo: {_e}")

        vista_previa = respuesta["texto"][:80].replace("\n", " ")
        print(f"  ✓ {fila['alumno_nombre']:30s}: '{vista_previa}...'")
        if storage.respondio_tarde(fila, respuesta["fecha"]):
            # Se recolecta igual: corregir la deja fuera salvo que se elija a mano.
            print(f"     ⏰ fuera de plazo: respondió a las {storage.hora(respuesta['fecha'])}, "
                  f"el plazo era hasta las {storage.hora(fila['plazo'])}")


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = args[0].upper() if args and args[0].upper().startswith('T') else config.TAREA_DEFAULT
    main(tarea, solo=_candidatos.solo_de_argv())
