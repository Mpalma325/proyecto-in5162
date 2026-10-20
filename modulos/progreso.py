"""
Avance de un trabajo largo, para la barra de la página.

Los flujos que recorren alumnos imprimen "@@progreso hechos/total unidad" antes
de cada uno y al terminar. El motor manda esa línea al sitio con el resto de la
salida; la página no la muestra como texto: con la última dibuja la barra
(web/public/comun.js, progresoDe). En la terminal se ve tal cual, y no estorba.
"""

PREFIJO = "@@progreso"


def progreso(hechos: int, total: int, unidad: str = "") -> None:
    if total > 0:
        print(f"{PREFIJO} {hechos}/{total} {unidad}".rstrip(), flush=True)


def avanzar(items, unidad: str = ""):
    """Recorre `items` anunciando el avance: antes de cada uno y al terminar todos."""
    items = list(items)
    for i, x in enumerate(items):
        progreso(i, len(items), unidad)
        yield x
    progreso(len(items), len(items), unidad)
