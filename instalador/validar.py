"""
Validación de cada dato apenas se escribe, sin efectos: no se manda ningún
correo, no se crea nada, no se gasta en la API.

Cada `probar_*` devuelve (ok, mensaje). `ok` es None cuando no se pudo saber
(sin conexión, o una API que no respondió) y la decisión queda para quien llama.
"""

from __future__ import annotations

import re
import smtplib
import socket
import ssl

from .comun import Ejecutor

CODIGO = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,20}$")
CORREO = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
REGION = re.compile(r"^[a-z]+-[a-z]+[0-9]+$")
PROYECTO = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
CUENTA_CF = re.compile(r"^[0-9a-f]{32}$")
SUBDOMINIO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

CF_API = "https://api.cloudflare.com/client/v4"
OPENAI_API = "https://api.openai.com/v1"
# El modelo que usa config.py si nadie lo cambia en Parámetros.
MODELO_POR_DEFECTO = "gpt-5.4-mini"


# ---------------------------------------------------------------- formato


def error_codigo(codigo: str) -> str | None:
    if not CODIGO.match(codigo or ""):
        return "Solo letras, números y guiones, empezando por una letra (ej. IN3401)."
    if codigo.lower() == "in5162":
        return ("IN5162 ya está instalado a mano y se actualiza con motor/desplegar.ps1 y "
                "npm run deploy. Este instalador es para cursos nuevos.")
    return None


def error_nombre(nombre: str) -> str | None:
    """Nombre del curso o del profesor: va en los prompts y en la firma de los correos."""
    if not (nombre or "").strip():
        return "No puede quedar vacío: va en la firma de los correos."
    if "{" in nombre or "}" in nombre:
        return "Sin llaves { }: los correos las usan para sus campos."
    return None


def error_correo(correo: str) -> str | None:
    return None if CORREO.match(correo or "") else "No parece un correo (nombre@dominio.cl)."


def lista_correos(texto: str) -> tuple[list[str], str | None]:
    correos = [c.strip().lower() for c in re.split(r"[,;\s]+", texto or "") if c.strip()]
    malos = [c for c in correos if not CORREO.match(c)]
    if not correos:
        return [], "Escribe al menos un correo."
    if malos:
        return [], f"No parecen correos: {', '.join(malos)}"
    return list(dict.fromkeys(correos)), None


def error_region(region: str) -> str | None:
    return None if REGION.match(region or "") else "Una región de Google Cloud, como us-central1."


def error_proyecto(proyecto: str) -> str | None:
    if PROYECTO.match(proyecto or ""):
        return None
    return ("El id del proyecto (no el nombre): 6 a 30 minúsculas, números y guiones, "
            "como aparece en console.cloud.google.com.")


def error_cuenta_cf(cuenta: str) -> str | None:
    if CUENTA_CF.match(cuenta or ""):
        return None
    return ("El Account ID son 32 letras y números. Está en dash.cloudflare.com, en la "
            "columna derecha de la página de cualquier dominio o en Workers & Pages.")


# ---------------------------------------------------------------- correo


def probar_correo(correo: str, clave: str, *, smtp=smtplib.SMTP,
                  host: str = "smtp.gmail.com", puerto: int = 587) -> tuple[bool | None, str]:
    """Inicia sesión en el SMTP con STARTTLS y sale. No manda nada."""
    try:
        s = smtp(host, puerto, timeout=20)
    except (OSError, smtplib.SMTPException) as e:
        return None, f"No pude conectarme a {host}:{puerto} ({e}). ¿Hay conexión?"
    try:
        s.ehlo()
        s.starttls(context=ssl.create_default_context())
        s.ehlo()
        s.login(correo, clave)
        return True, f"{correo} inició sesión en {host}."
    except smtplib.SMTPAuthenticationError:
        return False, ("Gmail rechazó el correo o la contraseña de aplicación. Revisa que la "
                       "cuenta tenga verificación en dos pasos y que la contraseña sea una de "
                       "aplicación (myaccount.google.com/apppasswords), no la de siempre.")
    except (OSError, smtplib.SMTPException, socket.timeout) as e:
        return None, f"El servidor de correo cortó la conexión ({e})."
    finally:
        try:
            s.quit()
        except Exception:
            pass


# ---------------------------------------------------------------- OpenAI


def probar_openai(clave: str, ej: Ejecutor) -> tuple[bool | None, str]:
    """Lista los modelos: no cuesta nada y dice si la clave sirve."""
    estado, cuerpo = ej.pedir("GET", f"{OPENAI_API}/models", token=clave)
    if estado == 200 and isinstance(cuerpo, dict):
        modelos = {m.get("id") for m in cuerpo.get("data", []) if isinstance(m, dict)}
        if MODELO_POR_DEFECTO not in modelos:
            return True, (f"La clave sirve, pero no ve el modelo {MODELO_POR_DEFECTO}, que es el "
                          "que se usa por defecto. Se puede cambiar después en Parámetros.")
        return True, "La clave de OpenAI sirve."
    if estado == 401:
        return False, "OpenAI rechazó la clave. Cópiala de nuevo desde platform.openai.com/api-keys."
    if estado == 0:
        return None, f"No pude conectarme a OpenAI ({cuerpo})."
    return None, f"OpenAI respondió {estado}: {_mensaje_openai(cuerpo)}"


def _mensaje_openai(cuerpo) -> str:
    if isinstance(cuerpo, dict):
        return str((cuerpo.get("error") or {}).get("message", ""))[:200]
    return ""


# ---------------------------------------------------------------- Cloudflare

# Lo que el instalador necesita del token, y una consulta que lo prueba sin
# cambiar nada. Una consulta prueba que el permiso existe; que sea "Edit" y no
# solo "Read" no se puede saber sin escribir.
PERMISOS_CF = [
    ("Workers Scripts: Edit", "/workers/scripts"),
    ("D1: Edit", "/d1/database"),
    ("Workers R2 Storage: Edit", "/r2/buckets"),
    ("Access: Apps and Policies: Edit", "/access/apps"),
    ("Access: Organizations, Identity Providers, and Groups: Edit", "/access/organizations"),
]


def _errores_cf(cuerpo) -> list[dict]:
    return (cuerpo.get("errors") or []) if isinstance(cuerpo, dict) else []


def _codigos_cf(cuerpo) -> set[int]:
    return {e.get("code") for e in _errores_cf(cuerpo) if isinstance(e, dict)}


def probar_cloudflare(token: str, cuenta: str, ej: Ejecutor) -> tuple[bool | None, str, dict]:
    """Verifica el token y que alcance a cada cosa que el instalador toca.

    Devuelve (ok, mensaje, detalle). detalle["zero_trust"] dice si Zero Trust
    está activado (sin él, Access no se puede configurar).
    """
    detalle = {"faltan": [], "zero_trust": None, "r2": None}
    estado, cuerpo = ej.pedir("GET", f"{CF_API}/user/tokens/verify", token=token)
    if estado != 200:
        # Los tokens que pertenecen a la cuenta (no a una persona) se verifican aparte.
        estado, cuerpo = ej.pedir("GET", f"{CF_API}/accounts/{cuenta}/tokens/verify", token=token)
    if estado == 0:
        return None, f"No pude conectarme a Cloudflare ({cuerpo}).", detalle
    activo = isinstance(cuerpo, dict) and cuerpo.get("success") and \
        (cuerpo.get("result") or {}).get("status") == "active"
    if not activo:
        return False, ("Cloudflare no reconoce el token o no está activo. Cópialo de nuevo: "
                       "dash.cloudflare.com → My Profile → API Tokens."), detalle

    no_alcanza = 0
    sin_respuesta = []
    for permiso, ruta in PERMISOS_CF:
        estado, cuerpo = ej.pedir("GET", f"{CF_API}/accounts/{cuenta}{ruta}", token=token)
        codigos = _codigos_cf(cuerpo)
        if estado == 200 and isinstance(cuerpo, dict) and cuerpo.get("success"):
            if ruta == "/access/organizations":
                detalle["zero_trust"] = bool((cuerpo.get("result") or {}).get("auth_domain"))
            if ruta == "/r2/buckets":
                detalle["r2"] = True
            continue
        if 7003 in codigos or 7000 in codigos:
            no_alcanza += 1
        elif ruta == "/r2/buckets" and 10042 in codigos:
            # R2 se activa una vez en el panel (plan gratuito).
            detalle["r2"] = False
        elif ruta == "/access/organizations" and estado == 404:
            detalle["zero_trust"] = False
        elif estado in (401, 403) or 10000 in codigos or 9109 in codigos:
            detalle["faltan"].append(permiso)
        elif estado == 0 or estado >= 500:
            # Cloudflare no respondió: no se sabe si el permiso está.
            sin_respuesta.append(permiso)
        else:
            no_alcanza += 1
    if no_alcanza == len(PERMISOS_CF):
        return False, ("El token es válido pero no encuentro la cuenta "
                       f"{cuenta}. Revisa el Account ID."), detalle
    if detalle["faltan"]:
        return False, ("Al token le faltan permisos: " + "; ".join(detalle["faltan"]) +
                       ". Edítalo en My Profile → API Tokens y agrégalos (sobre esta cuenta)."), detalle
    avisos = []
    if detalle["r2"] is False:
        avisos.append("R2 no está activado: actívalo en dash.cloudflare.com → R2 (plan gratuito) "
                      "antes de seguir")
    if detalle["zero_trust"] is False:
        avisos.append("Zero Trust no está activado: actívalo en one.dash.cloudflare.com con el plan "
                      "Free; sin él nadie podrá entrar al sitio")
    if avisos:
        return False, ". ".join(avisos) + ".", detalle
    if sin_respuesta:
        return None, ("Cloudflare no respondió al revisar: " + "; ".join(sin_respuesta) +
                      ". No pude comprobar esos permisos."), detalle
    return True, "El token de Cloudflare sirve y tiene los permisos que hacen falta.", detalle


# ---------------------------------------------------------------- Google Cloud


def probar_gcloud_sesion(ej: Ejecutor) -> tuple[bool | None, str]:
    r = ej.correr(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
                  lectura=True, puede_fallar=True, simulado="profesor@ejemplo.cl")
    cuenta = r.salida.strip().splitlines()[0] if r.ok and r.salida.strip() else ""
    if not cuenta:
        return False, ("gcloud no tiene una sesión iniciada. En Cloud Shell viene iniciada; "
                       "si no, corre: gcloud auth login")
    return True, cuenta


def probar_proyecto(proyecto: str, ej: Ejecutor) -> tuple[bool | None, str]:
    """El proyecto existe, se puede usar y tiene la facturación activada."""
    r = ej.correr(["gcloud", "projects", "describe", proyecto, "--format=value(projectNumber)"],
                  lectura=True, puede_fallar=True, simulado="000000000000")
    if not r.ok or not r.salida.strip():
        return False, (f"No encuentro el proyecto {proyecto}, o tu cuenta no tiene acceso. Revisa "
                       "el id en console.cloud.google.com (arriba, al lado del logo).")
    r = ej.correr(["gcloud", "billing", "projects", "describe", proyecto,
                   "--format=value(billingEnabled)"], lectura=True, puede_fallar=True,
                  simulado="True")
    if r.ok and r.salida.strip() == "True":
        return True, f"El proyecto {proyecto} existe y tiene la facturación activada."
    if r.ok:
        return False, (f"El proyecto {proyecto} no tiene la facturación activada. Actívala en "
                       f"console.cloud.google.com/billing/linkedaccount?project={proyecto}.")
    return None, ("No pude revisar la facturación del proyecto "
                  f"({(r.error or r.salida).strip()[:200]}).")
