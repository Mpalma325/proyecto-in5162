"""
Qué versión de un prompt produjo cada respuesta del modelo.

Los prompts se editan a mitad de semestre: en 2026-2 el criterio de
originalidad cambió entre las semanas 6 y 7, y las notas de antes y después no
se comparan igual. Ese cambio se hizo en el PC y no quedó registrado en ninguna
parte; solo se nota en las notas. Cada llamada anota ahora en el log el archivo
y una huella de su texto, y la primera vez que aparece una huella el texto se
guarda aparte: cualquier corrección se puede leer junto al prompt que la produjo.
"""

import hashlib
from pathlib import Path

CARPETA = "prompts_usados"


def huella(texto: str) -> str:
    # Los fines de línea cambian entre Windows y la nube sin que cambie el prompt.
    normal = texto.replace("\r\n", "\n").strip()
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:8]


def anotar(ruta: Path, texto: str) -> str:
    """`evaluar_respuesta.md@1a2b3c4d`, y guarda esa versión si es nueva.

    Va en <flujo>/prompts_usados/, junto a prompts/: el motor sube los
    archivos nuevos del flujo al terminar. Si no se puede guardar, la huella
    igual queda en el log.
    """
    h = huella(texto)
    destino = ruta.parent.parent / CARPETA / f"{ruta.stem}@{h}{ruta.suffix}"
    try:
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8")
    except OSError as e:
        print(f"⚠ No pude guardar la versión del prompt {ruta.name}: {e}")
    return f"{ruta.name}@{h}"
