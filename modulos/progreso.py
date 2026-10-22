"""
Avance de un trabajo largo, para la barra de la página, y el punto donde se
puede detener.

Los flujos que recorren alumnos imprimen "@@progreso hechos/total unidad" antes
de cada uno y al terminar. El motor manda esa línea al sitio con el resto de la
salida; la página no la muestra como texto: con la última dibuja la barra
(web/public/comun.js, progresoDe). En la terminal se ve tal cual, y no estorba.

Si alguien pide detener el trabajo desde la página, el motor crea el archivo
que indica IN5162_CANCELAR y el recorrido termina antes del alumno siguiente.
Cortar ahí, y no a la mitad de uno, es lo que evita que un correo quede enviado
sin registrar. Lo que viene después del ciclo (guardar, marcar leídos) corre
igual.
"""

import os
from pathlib import Path

PREFIJO = "@@progreso"


def progreso(hechos: int, total: int, unidad: str = "") -> None:
    if total > 0:
        print(f"{PREFIJO} {hechos}/{total} {unidad}".rstrip(), flush=True)


def pidieron_detener() -> bool:
    ruta = os.environ.get("IN5162_CANCELAR")
    return bool(ruta) and Path(ruta).exists()


def avanzar(items, unidad: str = ""):
    """Recorre `items` anunciando el avance, y para entre uno y otro si se pidió detener."""
    items = list(items)
    for i, x in enumerate(items):
        if pidieron_detener():
            print(f"⊘ Detenido a pedido: quedaron {len(items) - i} {unidad or 'pendientes'} sin procesar.",
                  flush=True)
            return
        progreso(i, len(items), unidad)
        yield x
    progreso(len(items), len(items), unidad)
