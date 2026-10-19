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
# US$ por millón de tokens, por modelo: {"modelo": [entrada, salida]}. Solo
# sirve para que la línea "Consumo de API" de cada trabajo diga cuánto costó.
PRECIOS_API = _env.get("PRECIOS_API", "{}")

# --- correo ---
# Por defecto Gmail, que es lo que usa el curso. Se pueden cambiar por .env
# para correr sobre otro proveedor sin tocar código.
SMTP_HOST = _env.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env.get("SMTP_PORT", "587"))
IMAP_HOST = _env.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(_env.get("IMAP_PORT", "993"))
# El código del curso, como lo ven los alumnos en el asunto de los correos.
# Otro curso que use esto lo cambia en el .env (y el motor, en su despliegue).
CURSO = _env.get("CURSO", "IN5162").strip() or "IN5162"
# Dominio de los Message-ID que generamos. No tiene que existir; solo
# identifica de dónde salió el mensaje.
MSGID_DOMINIO = _env.get("MSGID_DOMINIO", f"{CURSO.lower()}.local")

# --- sitio web ---
# Dónde está el sitio del curso. Por defecto el de desarrollo local
# (`npm run dev` en web/); al desplegar se cambia por la URL de Cloudflare.
WEB_URL = _env.get("WEB_URL", "http://127.0.0.1:8787").rstrip("/")

# --- tests semanales ---
GRUPO_CONTROL_TRATAMIENTO = _flag("GRUPO_CONTROL_TRATAMIENTO", "true")
GRUPO_SEED = int(_env.get("GRUPO_SEED", "19"))

# --- tareas ---
TAREA_DEFAULT = _env.get("TAREA_DEFAULT", "T1")
NOTA_MIN = float(_env.get("NOTA_MIN", "4.0"))
NOTA_MAX = float(_env.get("NOTA_MAX", "7.0"))
INCLUIR_CONTEXTO_CLASES = _flag("INCLUIR_CONTEXTO_CLASES", "true")


def cargar_servidores() -> dict:
    """Servidores de correo, para inyectarlos en el módulo mail."""
    return {
        "SMTP_HOST": SMTP_HOST, "SMTP_PORT": SMTP_PORT,
        "IMAP_HOST": IMAP_HOST, "IMAP_PORT": IMAP_PORT,
        "MSGID_DOMINIO": MSGID_DOMINIO,
    }


def _obtener(var: str, descripcion: str) -> str:
    valor = _env.get(var)
    if not valor:
        raise RuntimeError(
            f"No encontré {var} ({descripcion}). Agrégala al .env de la raíz "
            f"del proyecto o como variable de entorno."
        )
    return valor


def cargar_token_web() -> str:
    """Token con el que este equipo sube datos al sitio. Solo sirve para subir."""
    return _obtener("WEB_TOKEN", "token del agente para subir datos al sitio web")


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
