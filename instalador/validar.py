"""
Validación de cada dato apenas se escribe: no se manda ningún correo ni se
crea nada. Lo único que se gasta es una respuesta de 1 token de OpenAI, la
única forma de saber si la cuenta tiene saldo.

Cada `probar_*` devuelve (ok, mensaje). `ok` es None cuando no se pudo saber
(sin conexión, o una API que no respondió) y la decisión queda para quien llama.
"""

from __future__ import annotations

import imaplib
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
# El modelo que usa config.py si nadie lo cambia en Configuración › La IA › Parámetros.
MODELO_POR_DEFECTO = "gpt-5.4-mini"
PARAMETROS = "Configuración › La IA › Parámetros"


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


SMTP_HOST, SMTP_PUERTO = "smtp.gmail.com", 587
IMAP_HOST, IMAP_PUERTO = "imap.gmail.com", 993


def probar_correo(correo: str, clave: str, *, smtp=smtplib.SMTP,
                  imap=imaplib.IMAP4_SSL) -> tuple[bool | None, str]:
    """Inicia sesión en los dos servidores que usa el sistema y sale: SMTP para
    mandar las preguntas e IMAP para leer las respuestas. No manda ni lee nada.
    El mensaje dice cuál de los dos falló."""
    ok, mensaje = _probar_smtp(correo, clave, smtp)
    if not ok:
        return ok, mensaje
    ok, mensaje = _probar_imap(correo, clave, imap)
    if not ok:
        return ok, mensaje
    return True, f"{correo} inició sesión en {SMTP_HOST} (envío) y en {IMAP_HOST} (lectura)."


def _probar_smtp(correo: str, clave: str, smtp) -> tuple[bool | None, str]:
    """STARTTLS, login y QUIT."""
    try:
        s = smtp(SMTP_HOST, SMTP_PUERTO, timeout=20)
    except (OSError, smtplib.SMTPException) as e:
        return None, (f"No pude conectarme a {SMTP_HOST}:{SMTP_PUERTO}, el servidor de envío "
                      f"(SMTP) ({e}). ¿Hay conexión?")
    try:
        s.ehlo()
        s.starttls(context=ssl.create_default_context())
        s.ehlo()
        s.login(correo, clave)
        return True, ""
    except smtplib.SMTPAuthenticationError:
        return False, ("Gmail rechazó el correo o la contraseña de aplicación al iniciar sesión "
                       f"para enviar (SMTP, {SMTP_HOST}). Revisa que la cuenta tenga verificación "
                       "en dos pasos y que la contraseña sea una de aplicación "
                       "(myaccount.google.com/apppasswords), no la de siempre.")
    except (OSError, smtplib.SMTPException, socket.timeout) as e:
        return None, f"El servidor de envío (SMTP, {SMTP_HOST}) cortó la conexión ({e})."
    finally:
        try:
            s.quit()
        except Exception:
            pass


def _probar_imap(correo: str, clave: str, imap) -> tuple[bool | None, str]:
    """Login y LOGOUT por IMAP con SSL, que es como el sistema lee el buzón."""
    try:
        m = imap(IMAP_HOST, IMAP_PUERTO, timeout=20)
    except (OSError, imaplib.IMAP4.error) as e:
        return None, (f"El envío (SMTP) funcionó, pero no pude conectarme a {IMAP_HOST}:{IMAP_PUERTO}, "
                      f"el servidor de lectura (IMAP) ({e}). ¿Hay conexión?")
    try:
        m.login(correo, clave)
        return True, ""
    except imaplib.IMAP4.error as e:
        detalle = e.args[0].decode("utf-8", "replace") if e.args and isinstance(e.args[0], bytes) else str(e)
        return False, ("Gmail aceptó la contraseña para enviar (SMTP), pero rechazó el inicio de sesión "
                       f"para leer el buzón (IMAP, {IMAP_HOST}): {detalle}. El sistema lee por IMAP las "
                       "respuestas de los alumnos. Si el correo es de Google Workspace (por ejemplo, de "
                       "una universidad), el administrador puede tener IMAP desactivado: usa una cuenta "
                       "@gmail.com.")
    except (OSError, socket.timeout) as e:
        return None, f"El servidor de lectura (IMAP, {IMAP_HOST}) cortó la conexión ({e})."
    finally:
        try:
            m.logout()
        except Exception:
            pass


# ---------------------------------------------------------------- OpenAI


# Lo que OpenAI responde cuando la cuenta no tiene saldo o no tiene la facturación activa.
SIN_SALDO = ("insufficient_quota", "billing_not_active")


def probar_openai(clave: str, ej: Ejecutor, modelo: str = MODELO_POR_DEFECTO) -> tuple[bool | None, str]:
    """Pide al modelo por defecto una respuesta de 1 token, como las llamadas
    del sistema (chat/completions). Listar los modelos funciona igual con saldo
    cero; esta llamada no, y cuesta una fracción de centavo."""
    estado, cuerpo = ej.pedir("POST", f"{OPENAI_API}/chat/completions", token=clave, lectura=False,
                              datos={"model": modelo, "max_completion_tokens": 1,
                                     "messages": [{"role": "user", "content": "Responde solo: ok"}]},
                              tiempo=60)
    codigo, mensaje = _error_openai(cuerpo)
    if estado == 200:
        return True, f"La clave de OpenAI sirve y la cuenta tiene saldo (una respuesta de 1 token de {modelo})."
    if estado == 0:
        return None, f"No pude conectarme a OpenAI ({cuerpo})."
    if codigo in SIN_SALDO:
        return False, ("La clave sirve, pero la cuenta de OpenAI no tiene saldo (insufficient_quota). "
                       "Carga saldo en platform.openai.com/settings/organization/billing y presiona "
                       "Enter para probar de nuevo; un pago recién hecho puede tardar unos minutos en "
                       "verse.")
    if estado in (401, 403) and re.search(r"scope|permission", mensaje, re.I):
        return False, ("La clave no tiene permiso para usar los modelos (" + mensaje[:120] + "). Crea "
                       "otra en platform.openai.com/api-keys con «Permissions» en «All» y pégala.")
    if estado == 401:
        return False, ("OpenAI rechazó la clave (401). Se copió incompleta o se borró: crea otra en "
                       "platform.openai.com/api-keys y pégala.")
    if estado == 429:
        return None, ("OpenAI respondió 429: demasiadas llamadas seguidas con esta clave. Espera un "
                      "minuto y presiona Enter dos veces: la primera responde que no a seguir sin "
                      "comprobar y la segunda deja la misma clave, que se prueba de nuevo.")
    if estado == 404 and codigo == "model_not_found":
        return True, (f"La clave sirve, pero la cuenta no tiene el modelo {modelo}, que es el que se usa "
                      "por defecto, así que no pude comprobar el saldo. Después de instalar, elige otro "
                      f"modelo en {PARAMETROS} y revisa el saldo en platform.openai.com.")
    if estado == 403:
        return False, (f"OpenAI no deja usar esta clave (403: {mensaje[:160]}). Revisa en "
                       "platform.openai.com que la cuenta y el proyecto de la clave estén activos.")
    return None, f"OpenAI respondió {estado}: {mensaje[:200]}"


def _error_openai(cuerpo) -> tuple[str, str]:
    """(código, mensaje) del error que devuelve OpenAI; vacíos si no hay."""
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    if not isinstance(error, dict):
        return "", ""
    return str(error.get("code") or error.get("type") or ""), str(error.get("message") or "")


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
