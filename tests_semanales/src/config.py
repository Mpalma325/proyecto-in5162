import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPTS = ROOT / "prompts"

ALUMNOS_CSV = DATA / "alumnos.csv"
PREGUNTAS_CSV = DATA / "preguntas.csv"
MESSAGE_IDS_FILE = DATA / ".message_ids.json"


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
MAX_TOKENS = int(_env.get("MAX_TOKENS", "3000"))

GRUPO_CONTROL_TRATAMIENTO = _env.get("GRUPO_CONTROL_TRATAMIENTO", "true").lower() == "true"
GRUPO_SEED = int(_env.get("GRUPO_SEED", "19"))

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def _obtener(var: str, descripcion: str) -> str:
    valor = _env.get(var)
    if not valor:
        raise RuntimeError(
            f"No encontré {var} ({descripcion}). "
            f"Agrégala al archivo .env en la raíz del proyecto."
        )
    return valor


def cargar_api_key() -> str:
    return _obtener("OPENAI_API_KEY", "API key de OpenAI")


def cargar_correo_config() -> dict:
    return {
        "remitente": _obtener("CORREO_REMITENTE", "correo desde el cual se envían los emails"),
        "password": _obtener("CORREO_APP_PASSWORD", "app password de Gmail (16 caracteres)"),
    }
