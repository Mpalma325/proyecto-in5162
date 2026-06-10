import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENTREGAS = DATA / "entregas"
CLASES = DATA / "clases"
SALIDAS = DATA / "salidas"
PROMPTS = ROOT / "prompts"
CACHE = ROOT / "cache"


def _leer_env() -> dict:
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for linea in env_file.read_text(encoding='utf-8').splitlines():
            linea = linea.strip()
            if not linea or linea.startswith('#') or '=' not in linea:
                continue
            k, v = linea.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# .env values are base; actual env vars override them
_env = {**_leer_env(), **os.environ}

MODELO = _env.get("MODELO", "gpt-5.4-mini")
TEMPERATURA = float(_env.get("TEMPERATURA", "0.2"))
MAX_TOKENS = int(_env.get("MAX_TOKENS", "4000"))
TAREA_DEFAULT = _env.get("TAREA_DEFAULT", "T1")
INCLUIR_CONTEXTO_CLASES = True
NOTA_MIN = float(_env.get("NOTA_MIN", "4.0"))
NOTA_MAX = float(_env.get("NOTA_MAX", "7.0"))

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _obtener(var: str, descripcion: str) -> str:
    valor = _env.get(var)
    if not valor:
        raise RuntimeError(
            f"No encontré {var} ({descripcion}). "
            f"Agrégala a un archivo .env en la raíz del proyecto o como variable de entorno."
        )
    return valor


def cargar_api_key() -> str:
    return _obtener("OPENAI_API_KEY", "API key de OpenAI")


def cargar_correo_config() -> dict:
    return {
        "remitente": _obtener("CORREO_REMITENTE", "correo desde el cual se envían los emails"),
        "password": _obtener("CORREO_APP_PASSWORD", "app password de Gmail de 16 caracteres"),
    }
