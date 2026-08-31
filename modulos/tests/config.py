"""Config de Tests Semanales: lo común más las rutas propias de este flujo."""

from modulos.config import *  # noqa: F401,F403
from modulos.config import data as _data, prompts as _prompts

FLUJO = "tests_semanales"

DATA = _data(FLUJO)
PROMPTS = _prompts(FLUJO)
ALUMNOS_CSV = DATA / "alumnos.csv"
PREGUNTAS_CSV = DATA / "preguntas.csv"
