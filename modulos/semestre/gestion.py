"""
Qué semestre está activo y cómo se crean los nuevos.

Esta lógica estaba escrita tres veces (los dos config.py y app/utils/runner.py),
las tres con un comentario "mantener sincronizado con...". Ahora vive acá.
"""

import os
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEMESTRES_DIR = PROJECT_ROOT / "semestres"
TEMPLATE_DIR = SEMESTRES_DIR / "_template"
ACTIVO_FILE = SEMESTRES_DIR / "activo.txt"

_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


def activo() -> str | None:
    """Semestre en uso, o None si todavía no hay ninguno.

    La variable de entorno IN5162_SEMESTRE tiene prioridad sobre el archivo.
    Sirve para trabajar sobre otro semestre en un proceso puntual —las pruebas
    la usan— sin escribir el activo.txt, que es compartido: si un proceso que
    lo modifica muere antes de restaurarlo, deja al resto apuntando al semestre
    equivocado.
    """
    forzado = os.environ.get("IN5162_SEMESTRE", "").strip()
    if forzado:
        return forzado
    if not ACTIVO_FILE.exists():
        return None
    return ACTIVO_FILE.read_text(encoding="utf-8").strip() or None


def activo_o_error() -> str:
    """Igual que activo(), pero falla si no hay ninguno.

    Lo usan los scripts, que no tienen forma de mostrar un mensaje en pantalla
    y necesitan cortar de inmediato.
    """
    valor = activo()
    if not valor:
        raise RuntimeError(
            f"No hay un semestre activo en {ACTIVO_FILE}. Créalo con semestre.crear "
            f"y semestre.activar, o trae la carpeta de uno ya corrido, antes de ejecutar scripts."
        )
    return valor


def listar() -> list[str]:
    if not SEMESTRES_DIR.exists():
        return []
    return sorted(
        p.name for p in SEMESTRES_DIR.iterdir()
        if p.is_dir() and p.name != "_template"
    )


def activar(semestre_id: str) -> None:
    if not (SEMESTRES_DIR / semestre_id).is_dir():
        raise ValueError(f"El semestre '{semestre_id}' no existe.")
    ACTIVO_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVO_FILE.write_text(semestre_id, encoding="utf-8")


def crear(semestre_id: str) -> None:
    """Crea un semestre nuevo copiando la plantilla. No lo activa."""
    semestre_id = semestre_id.strip()
    if not semestre_id or not _ID_VALIDO.match(semestre_id):
        raise ValueError(
            "El identificador del semestre solo puede contener letras, "
            "números, puntos, guiones y guiones bajos."
        )
    destino = SEMESTRES_DIR / semestre_id
    if destino.exists():
        raise ValueError(f"El semestre '{semestre_id}' ya existe.")
    if not TEMPLATE_DIR.exists():
        raise RuntimeError(f"No encontré la plantilla en {TEMPLATE_DIR}.")
    shutil.copytree(TEMPLATE_DIR, destino)


def raiz(semestre_id: str | None = None) -> Path:
    """Carpeta de un semestre (el activo si no se indica cuál)."""
    return SEMESTRES_DIR / (semestre_id or activo_o_error())


def datos(flujo: str, semestre_id: str | None = None) -> Path:
    """Carpeta de datos de un flujo: 'tests_semanales' o 'tareas'."""
    return raiz(semestre_id) / flujo / "data"


def prompts(flujo: str, semestre_id: str | None = None) -> Path:
    return raiz(semestre_id) / flujo / "prompts"
