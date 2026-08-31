"""Config de Tareas: lo común más las rutas propias de este flujo."""

from modulos.config import *  # noqa: F401,F403
from modulos.config import data as _data, prompts as _prompts
from modulos.semestre import raiz as _raiz

FLUJO = "tareas"

DATA = _data(FLUJO)
PROMPTS = _prompts(FLUJO)
ENTREGAS = DATA / "entregas"
CLASES = DATA / "clases"
SALIDAS = DATA / "salidas"
CACHE = _raiz() / FLUJO / "cache"

# tareas usa un tope mayor: los entregables traen mucho código
MAX_TOKENS = 4000
