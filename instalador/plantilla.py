"""
La plantilla de semestre con los datos del curso.

Los prompts y correos de semestres/_template/ no nombran a ningún curso: donde
va el nombre tienen una marca, «CURSO», «NOMBRE_CURSO» o «FIRMA». Se llenan
al subir la plantilla al sitio, y la copia del repositorio queda intacta:
`git pull` nunca choca con ella. Un semestre creado en el PC (la app) las llena
al copiar la plantilla, con la misma función (modulos/semestre/gestion.py).
"""

from __future__ import annotations

from pathlib import Path

from modulos.semestre.gestion import MARCA, MARCAS, llenar_marcas

from .comun import RAIZ

PLANTILLA = RAIZ / "semestres" / "_template"
# Los que se leen como texto. El resto (por ahora solo .gitkeep) sube tal cual.
TEXTO = (".md", ".csv", ".txt", ".json")
renderizar = llenar_marcas
__all__ = ["MARCA", "MARCAS", "PLANTILLA", "TEXTO", "archivos", "renderizar"]


def archivos(valores: dict[str, str], carpeta: Path = PLANTILLA) -> list[tuple[str, bytes]]:
    """[(ruta relativa, contenido)] de la plantilla, ya con los datos del curso."""
    salida = []
    for p in sorted(carpeta.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.name.endswith((".pyc", ".tmp")):
            continue
        ruta = p.relative_to(carpeta).as_posix()
        datos = p.read_bytes()
        if p.suffix.lower() in TEXTO:
            # Mismo contenido desde Windows (CRLF al clonar) que desde Cloud Shell.
            texto = datos.decode("utf-8").replace("\r\n", "\n")
            datos = renderizar(texto, valores).encode("utf-8")
        salida.append((ruta, datos))
    return salida
