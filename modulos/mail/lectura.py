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
import re
from datetime import datetime
from email.utils import parseaddr

from . import credenciales
from .limpieza import _adjuntos, _decodificar_header, _extraer_cuerpo, _limpiar_respuesta


def buscar_no_leidos(filtro_asunto=None) -> list[dict]:
    """Los correos sin leer del INBOX, ya parseados y limpios.

    `filtro_asunto` es una función que recibe el asunto y dice si interesa. Se
    aplica acá, en Python, y no en el servidor: la búsqueda IMAP por asunto con
    acentos es poco confiable y la cantidad de no leídos siempre es chica.

    Leer no marca nada: se usa BODY.PEEK.
    """
    creds = credenciales.obtener()
    resultado = []

    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")

        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return resultado

        for msg_id in data[0].split():
            status, partes = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not partes or not partes[0]:
                continue

            msg = email.message_from_bytes(partes[0][1])
            asunto = _decodificar_header(msg.get("Subject", ""))
            if filtro_asunto is not None and not filtro_asunto(asunto):
                continue

            _, remitente = parseaddr(msg.get("From", ""))
            try:
                fecha = email.utils.parsedate_to_datetime(msg.get("Date", ""))
            except Exception:
                fecha = datetime.now()

            resultado.append({
                "uid": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                "remitente": remitente.lower(),
                "asunto": asunto,
                "message_id": (msg.get("Message-ID") or "").strip(),
                "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                "referencias": (msg.get("References") or "").strip(),
                "fecha": fecha,
                "texto": _limpiar_respuesta(_extraer_cuerpo(msg)),
            })

        resultado.sort(key=lambda r: r["fecha"])

    return resultado


def es_del_modulo(asunto: str, semana: int) -> bool:
    """Si el asunto corresponde a esa semana y no a otra que empiece igual.

    Con una comparación por subcadena, "Módulo 1" también encuentra "Módulo 10"
    y "Módulo 13". El límite de palabra al final lo evita.
    """
    return re.search(rf"m[oó]dulo\s*0*{int(semana)}\b", asunto or "", re.IGNORECASE) is not None


def buscar_respuestas_semana(semana: int, asunto_contiene: str = "Módulo") -> list[dict]:
    """Los correos sin leer que responden a la pregunta de esa semana."""
    return buscar_no_leidos(lambda asunto: es_del_modulo(asunto, semana))


def buscar_respuestas(message_ids: list[str]) -> dict[str, list[dict]]:
    """
    Busca en el inbox mensajes cuyo header In-Reply-To apunte a alguno
    de los message_ids dados.

    Devuelve {message_id_original: [{'remitente', 'texto', 'fecha', 'adjuntos'}, ...]},
    con todas las respuestas del hilo, sin orden. Qué cuenta (la primera, las que
    llegaron a tiempo) lo decide recolectar. Se incluyen las que vienen sin
    texto pero con adjuntos, para poder avisarlo.
    """
    if not message_ids:
        return {}
    creds = credenciales.obtener()
    resultado = {}

    # Normalizar ids (algunos clientes agregan o quitan < >)
    ids_buscar = {mid.strip().strip('<>'): mid for mid in message_ids if mid}

    with imaplib.IMAP4_SSL(credenciales.IMAP_HOST, credenciales.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        # Solo lectura, como el resto de este módulo: recorre el buzón entero y,
        # si abriera los correos, dejaría leídas las respuestas de tests
        # semanales que evaluar y tutoria buscan justamente por no leídas.
        imap.select("INBOX", readonly=True)

        status, data = imap.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return resultado

        ids_mensajes = data[0].split()

        for msg_id in reversed(ids_mensajes):  # más recientes primero
            status, data = imap.fetch(msg_id, "(BODY.PEEK[])")
            if status != "OK" or not data or not data[0]:
                continue

            raw = data[0][1]
            msg = email.message_from_bytes(raw)

            # ¿Este mensaje es respuesta a alguno de los que buscamos?
            in_reply_to = (msg.get("In-Reply-To") or "").strip()
            references = (msg.get("References") or "").strip()

            # Prioriza el padre directo; References puede incluir varios envíos.
            candidatos = re.findall(r'[^\s<>]+', in_reply_to)
            candidatos += list(reversed(re.findall(r'[^\s<>]+', references)))
            coincide_id = next((ids_buscar[mid] for mid in candidatos
                                if mid in ids_buscar), None)

            if not coincide_id:
                continue

            _, remitente = parseaddr(msg.get("From", ""))
            remitente = remitente.strip().lower()
            fecha_hdr = msg.get("Date", "")
            try:
                fecha = email.utils.parsedate_to_datetime(fecha_hdr).isoformat()
            except Exception:
                fecha = datetime.now().isoformat()

            cuerpo = _limpiar_respuesta(_extraer_cuerpo(msg))
            adjuntos = _adjuntos(msg)
            if not cuerpo.strip() and not adjuntos:
                continue

            # Todas las del hilo: quedarse con la más reciente hacía que un
            # "se me olvidó agregar…" reemplazara la respuesta.
            resultado.setdefault(coincide_id, []).append({
                "remitente": remitente,
                "texto": cuerpo,
                "fecha": fecha,
                "adjuntos": adjuntos,
            })

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
