"""
Las respuestas que un paso procesaría, para elegir cuáles procesar de verdad.

Evaluar (tests) y corregir (tareas) toman todo lo pendiente. A veces no se
quiere eso: una respuesta atrasada con buena justificación se acepta y otra no.
Por eso, en modo prueba, los dos dejan la lista de lo que procesarían en
`<flujo>/cache/candidatos_<item>.json`, y la página la muestra con casillas.
Después se corre de verdad con `--solo correo1,correo2`: los que no se eligen
se saltan y quedan como estaban (sin leer en el buzón, sin nota).
"""

import json
import sys
from pathlib import Path

from modulos import semestre as _semestre


def ruta(flujo: str, item: str | int) -> Path:
    """flujo: "tests_semanales" o "tareas"."""
    return _semestre.raiz() / flujo / "cache" / f"candidatos_{item}.json"


def guardar(flujo: str, item: str | int, candidatos: list[dict]) -> Path:
    destino = ruta(flujo, item)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(candidatos, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
    return destino


def solo_de_argv(argv: list[str] | None = None) -> set[str] | None:
    """Los correos de `--solo a@x,b@y`, en minúscula. None si no se pidió filtro."""
    argv = sys.argv[1:] if argv is None else argv
    for i, a in enumerate(argv):
        if a == "--solo" and i + 1 < len(argv):
            return {c.strip().lower() for c in argv[i + 1].split(",") if c.strip()}
        if a.startswith("--solo="):
            return {c.strip().lower() for c in a[len("--solo="):].split(",") if c.strip()}
    return None
