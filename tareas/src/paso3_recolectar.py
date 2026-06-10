"""
Paso 3 del flujo: recolectar respuestas de los alumnos desde el inbox.

Lee el CSV de la tarea, identifica las filas con correo enviado pero sin
respuesta, busca en el inbox los correos que sean Reply a esos Message-IDs,
y guarda el texto de la respuesta + timestamp en el CSV.

Uso:
    python -m src.paso3_recolectar               # tarea = config.TAREA_DEFAULT
    python -m src.paso3_recolectar T1
"""

import sys

from . import config, storage
from .correo import buscar_respuestas


def main(tarea: str) -> None:
    filas = storage.leer_csv(tarea)
    if not filas:
        print(f"No hay CSV para tarea {tarea}.")
        return

    # Pendientes: enviados pero sin respuesta aún
    pendientes = [
        f for f in filas
        if f.get("fecha_envio") and f.get("message_id") and not f.get("respuesta")
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
        storage.actualizar_por_message_id(
            tarea,
            mid,
            {
                "respuesta": respuesta["texto"],
                "fecha_respuesta": respuesta["fecha"],
            },
        )
        vista_previa = respuesta["texto"][:80].replace("\n", " ")
        print(f"  ✓ {fila['alumno_nombre']:30s}: '{vista_previa}...'")


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = args[0].upper() if args and args[0].upper().startswith('T') else config.TAREA_DEFAULT
    main(tarea)
