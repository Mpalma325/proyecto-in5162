"""
Lectura del buzón por IMAP.

Dos formas de encontrar la respuesta de un alumno, según cómo se envió:

- por asunto  (tests semanales): busca los no leídos cuyo asunto sea el del
  módulo de esa semana.
- por Message-ID (tareas): busca los que responden a un envío concreto,
  mirando los headers In-Reply-To y References.

Ambas venían duplicadas con implementaciones distintas; acá conviven.
"""

import email
import email.utils
import imaplib
from datetime import datetime
from email.utils import parseaddr

from . import credenciales
from .limpieza import _decodificar_header, _extraer_cuerpo, _limpiar_respuesta


def buscar_respuestas_semana(semana: int, asunto_contiene: str = "Módulo") -> list[dict]:
    creds = credenciales.obtener()
    resultado = []

    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")

        patron_asunto = f'Módulo {semana}'
        try:
            asunto_bytes = patron_asunto.encode('utf-8')
            status, data = imap.search('UTF-8', 'UNSEEN', 'SUBJECT', asunto_bytes)
        except (imaplib.IMAP4.error, UnicodeEncodeError):
            status, data = imap.search(None, 'UNSEEN')

        if status != "OK" or not data or not data[0]:
            return resultado

        ids_mensajes = data[0].split()
        patrones_asunto = [f'módulo {semana}', f'modulo {semana}']

        for msg_id in ids_mensajes:
            status, data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not data or not data[0]:
                continue

            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            asunto = _decodificar_header(msg.get("Subject", ""))
            asunto_lower = asunto.lower()
            if not any(p in asunto_lower for p in patrones_asunto):
                continue
            in_reply_to = (msg.get("In-Reply-To") or "").strip()
            _, remitente = parseaddr(msg.get("From", ""))
            fecha_hdr = msg.get("Date", "")
            try:
                fecha = email.utils.parsedate_to_datetime(fecha_hdr)
            except Exception:
                fecha = datetime.now()

            cuerpo = _limpiar_respuesta(_extraer_cuerpo(msg))

            resultado.append({
                "uid": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                "remitente": remitente.lower(),
                "asunto": asunto,
                "in_reply_to": in_reply_to,
                "fecha": fecha,
                "texto": cuerpo,
            })

        resultado.sort(key=lambda r: r["fecha"])

    return resultado


def buscar_respuestas(message_ids: list[str]) -> dict[str, dict]:
    """
    Busca en el inbox mensajes cuyo header In-Reply-To apunte a alguno
    de los message_ids dados.

    Devuelve {message_id_original: {'remitente': ..., 'texto': ..., 'fecha': ...}}
    """
    creds = credenciales.obtener()
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

    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
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


def marcar_leido(uid: str) -> None:
    creds = credenciales.obtener()
    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")
        imap.store(uid, "+FLAGS", "\\Seen")


def marcar_leidos(uids: list[str]) -> None:
    """Marca múltiples correos como leídos en una sola conexión."""
    if not uids:
        return
    creds = credenciales.obtener()
    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")
        for uid in uids:
            imap.store(uid, "+FLAGS", "\\Seen")
