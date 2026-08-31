"""
Paso 3 del flujo: recolectar respuestas de los alumnos desde el inbox.

Lee el CSV de la tarea, identifica las filas con correo enviado pero sin
respuesta, busca en el inbox los correos que sean Reply a esos Message-IDs,
y guarda el texto de la respuesta + timestamp en el CSV.

Uso:
    python -m modulos.tareas.recolectar               # tarea = config.TAREA_DEFAULT
    python -m modulos.tareas.recolectar T1
"""

import sys

from modulos import datos as _datos

from . import config, storage
from modulos.mail import buscar_respuestas


def main(tarea: str) -> None:
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
    if not pendientes:
        print(f"No hay respuestas pendientes por buscar para {tarea}.")
        return

    message_ids = [f["message_id"] for f in pendientes]
    print(f"Buscando respuestas en inbox para {len(message_ids)} correo(s) pendiente(s)...")

    encontradas = buscar_respuestas(message_ids)
    print(f"Encontradas {len(encontradas)} respuesta(s) nuevas.\n")

    for fila in pendientes:
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


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = args[0].upper() if args and args[0].upper().startswith('T') else config.TAREA_DEFAULT
    main(tarea)
