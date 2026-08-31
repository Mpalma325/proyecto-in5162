"""
Configuración compartida: credenciales, modelo y rutas del semestre.

Antes había un `config.py` por subproyecto, con 40 de 50 líneas idénticas y un
comentario de "mantener sincronizado con...". Ese comentario era la señal de
que faltaba este archivo.

Las credenciales salen del `.env` de la raíz del proyecto.
"""

import os
from pathlib import Path

from modulos import semestre as _semestre

PROJECT_ROOT = _semestre.PROJECT_ROOT


def _leer_env() -> dict:
    """Lee el .env de la raíz del proyecto."""
    f = PROJECT_ROOT / ".env"
    if not f.exists():
        return {}
    env = {}
    for linea in f.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# las variables de entorno pisan al .env: útil para pruebas puntuales
_env = {**_leer_env(), **os.environ}


def _flag(nombre: str, default: str) -> bool:
    return _env.get(nombre, default).strip().lower() == "true"


SEMESTRE = _semestre.activo_o_error()

# --- modelo ---
MODELO = _env.get("MODELO", "gpt-5.4-mini")
TEMPERATURA = float(_env.get("TEMPERATURA", "0.2"))
MAX_TOKENS = int(_env.get("MAX_TOKENS", "3000"))

# --- correo ---
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# --- tests semanales ---
GRUPO_CONTROL_TRATAMIENTO = _flag("GRUPO_CONTROL_TRATAMIENTO", "true")
GRUPO_SEED = int(_env.get("GRUPO_SEED", "19"))

# --- tareas ---
TAREA_DEFAULT = _env.get("TAREA_DEFAULT", "T1")
NOTA_MIN = float(_env.get("NOTA_MIN", "4.0"))
NOTA_MAX = float(_env.get("NOTA_MAX", "7.0"))
INCLUIR_CONTEXTO_CLASES = True


def _obtener(var: str, descripcion: str) -> str:
    valor = _env.get(var)
    if not valor:
        raise RuntimeError(
            f"No encontré {var} ({descripcion}). Agrégala al .env de la raíz "
            f"del proyecto o como variable de entorno."
        )
    return valor


def cargar_api_key() -> str:
    return _obtener("OPENAI_API_KEY", "API key de OpenAI")


def cargar_correo_config() -> dict:
    return {
        "remitente": _obtener("CORREO_REMITENTE", "correo desde el cual se envían los emails"),
        # Gmail muestra los app passwords con espacios ("abcd efgh ijkl mnop"),
        # y copiarlos tal cual es la causa típica de "Invalid credentials".
        "password": _obtener("CORREO_APP_PASSWORD", "app password de Gmail").replace(" ", ""),
    }


# --- rutas del semestre ---
def data(flujo: str) -> Path:
    return _semestre.datos(flujo, SEMESTRE)


def prompts(flujo: str) -> Path:
    return _semestre.prompts(flujo, SEMESTRE)
