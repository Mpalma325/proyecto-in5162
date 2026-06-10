"""
Envío y recepción de correos vía SMTP/IMAP de Gmail.

Trackeo de respuestas: al enviar, guardamos el Message-ID generado.
Cuando un alumno responde (dándole Reply), su respuesta incluye el header
In-Reply-To con ese mismo Message-ID. Así matcheamos sin ensuciar el asunto.

Requiere en .env:
    CORREO_REMITENTE=in5162@gmail.com
    CORREO_APP_PASSWORD=xxxxxxxxxxxxxxxx

Para crear el app password de Gmail necesitas tener 2FA activado y
generarlo en: https://myaccount.google.com/apppasswords
"""

import email
import email.utils
import imaplib
import smtplib
from datetime import datetime
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, parseaddr

from . import config


# ================================================================
# ENVÍO
# ================================================================

def enviar_correo(destinatario: str, asunto: str, cuerpo: str) -> str:
    """
    Envía un correo en texto plano desde CORREO_REMITENTE al destinatario.
    Devuelve el Message-ID generado (útil para matchear respuestas después).
    """
    creds = config.cargar_correo_config()

    # Generamos Message-ID explícitamente para poder guardarlo y trackear
    message_id = make_msgid(domain="in5162.local")

    msg = MIMEMultipart()
    msg["From"] = creds["remitente"]
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg["Message-ID"] = message_id
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(creds["remitente"], creds["password"])
        servidor.send_message(msg)

    return message_id


# ================================================================
# LECTURA
# ================================================================

def _decodificar_header(raw: str) -> str:
    """Decodifica un header que puede venir en formato MIME."""
    if not raw:
        return ""
    partes = decode_header(raw)
    resultado = []
    for texto, encoding in partes:
        if isinstance(texto, bytes):
            try:
                resultado.append(texto.decode(encoding or "utf-8", errors="replace"))
            except LookupError:
                resultado.append(texto.decode("utf-8", errors="replace"))
        else:
            resultado.append(texto)
    return "".join(resultado)


def _extraer_cuerpo(msg: email.message.Message) -> str:
    """Extrae el texto plano del cuerpo de un mensaje, aun si es multipart."""
    if msg.is_multipart():
        for parte in msg.walk():
            ctype = parte.get_content_type()
            dispo = str(parte.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in dispo:
                try:
                    payload = parte.get_payload(decode=True)
                    if payload:
                        return payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
        # fallback: primer text/html
        for parte in msg.walk():
            if parte.get_content_type() == "text/html":
                try:
                    payload = parte.get_payload(decode=True)
                    if payload:
                        return payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            pass
    return ""


def _limpiar_respuesta(texto: str) -> str:
    """
    Intenta quedarse solo con lo que escribió el alumno, sacando
    el quote del correo original y firmas típicas.
    """
    marcadores = [
        "\nEl ", "\nOn ",                   # "El <fecha> escribió:" / "On <date> wrote:"
        "\n-----Mensaje original-----",
        "\n-----Original Message-----",
        "\n________________________________",
        "\n> ",
    ]
    idx_mas_temprano = len(texto)
    for m in marcadores:
        i = texto.find(m)
        if 0 <= i < idx_mas_temprano:
            idx_mas_temprano = i
    texto = texto[:idx_mas_temprano].strip()
    # Normalizar espacios en líneas
    lineas = [l.rstrip() for l in texto.splitlines()]
    return "\n".join(lineas).strip()


def buscar_respuestas(message_ids: list[str]) -> dict[str, dict]:
    """
    Busca en el inbox mensajes cuyo header In-Reply-To apunte a alguno
    de los message_ids dados.

    Devuelve {message_id_original: {'remitente': ..., 'texto': ..., 'fecha': ...}}
    """
    creds = config.cargar_correo_config()
    resultado = {}

    # Normalizar ids (algunos clientes agregan o quitan < >)
    ids_buscar = set()
    for mid in message_ids:
        if not mid:
            continue
        mid = mid.strip()
        ids_buscar.add(mid)
        if not mid.startswith("<"):
            ids_buscar.add(f"<{mid}>")
        if mid.startswith("<") and mid.endswith(">"):
            ids_buscar.add(mid[1:-1])

    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")

        status, data = imap.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return resultado

        ids_mensajes = data[0].split()

        for msg_id in reversed(ids_mensajes):  # más recientes primero
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK" or not data or not data[0]:
                continue

            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            # ¿Este mensaje es respuesta a alguno de los que buscamos?
            in_reply_to = (msg.get("In-Reply-To") or "").strip()
            references = (msg.get("References") or "").strip()

            coincide_id = None
            for original_id in message_ids:
                if not original_id:
                    continue
                # El In-Reply-To puede venir con o sin <>
                if original_id in in_reply_to or original_id in references:
                    coincide_id = original_id
                    break

            if not coincide_id:
                continue

            # Si ya encontré una respuesta para ese id, quedarme con la más reciente
            # (al iterar en reversed, la primera que encuentro es la más reciente)
            if coincide_id in resultado:
                continue

            _, remitente = parseaddr(msg.get("From", ""))
            fecha_hdr = msg.get("Date", "")
            try:
                fecha = email.utils.parsedate_to_datetime(fecha_hdr).isoformat()
            except Exception:
                fecha = datetime.now().isoformat()

            cuerpo = _limpiar_respuesta(_extraer_cuerpo(msg))

            resultado[coincide_id] = {
                "remitente": remitente,
                "texto": cuerpo,
                "fecha": fecha,
            }

            if len(resultado) == len(message_ids):
                break

    return resultado
