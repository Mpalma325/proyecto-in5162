"""Gestión de semestres: cuál está activo, cuáles hay, cómo se crean."""

from .gestion import (
    ACTIVO_FILE,
    PROJECT_ROOT,
    SEMESTRES_DIR,
    TEMPLATE_DIR,
    activar,
    activo,
    activo_o_error,
    crear,
    datos,
    listar,
    prompts,
    raiz,
)

__all__ = [
    "activo", "activo_o_error", "listar", "activar", "crear",
    "raiz", "datos", "prompts",
    "PROJECT_ROOT", "SEMESTRES_DIR", "TEMPLATE_DIR", "ACTIVO_FILE",
]
