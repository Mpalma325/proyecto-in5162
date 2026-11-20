"""
Lectura del buzón por IMAP.

Dos formas de encontrar la respuesta de un alumno, según cómo se envió:

- por asunto  (tests semanales): busca los no leídos cuyo asunto sea el del
  módulo de esa semana. En los semestres nuevos, primero por In-Reply-To
  contra el envío de esa instancia, y el nombre visible («Control 2») en el
  asunto como respaldo.
- por Message-ID (tareas): busca los que responden a un envío concreto,
  mirando los headers In-Reply-To y References.

Ambas venían duplicadas con implementaciones distintas; acá conviven.
"""

import email
import email.utils
import imaplib
import re
import unicodedata
from datetime import datetime
from email.utils import parseaddr

from . import credenciales
from .limpieza import _decodificar_header, _extraer_cuerpo, _limpiar_respuesta


def buscar_no_leidos(filtro_asunto=None, filtro=None) -> list[dict]:
    """Los correos sin leer del INBOX, ya parseados y limpios.

    `filtro_asunto` es una función que recibe el asunto y dice si interesa. Se
    aplica acá, en Python, y no en el servidor: la búsqueda IMAP por asunto con
    acentos es poco confiable y la cantidad de no leídos siempre es chica.
    `filtro` recibe las cabeceras ({asunto, in_reply_to, referencias}), para
    reconocer una respuesta aunque el alumno le haya cambiado el asunto.

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
            if filtro is not None and not filtro({
                "asunto": asunto,
                "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                "referencias": (msg.get("References") or "").strip(),
            }):
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


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def es_del_nombre(asunto: str, nombre: str) -> bool:
    """Si el asunto nombra esa instancia («Control 2») como frase entera.

    «Control 2» no calza con «Control 21», «Control 2a» ni «Autocontrol 2».
    Sin importar mayúsculas, tildes ni cuántos espacios haya entre las palabras.
    """
    palabras = _sin_tildes(nombre).split()
    if not palabras:
        return False
    patron = r"\s+".join(re.escape(p) for p in palabras)
    return re.search(rf"(?<![\w]){patron}(?![\w])", _sin_tildes(asunto)) is not None


def ids_de_cabeceras(cabeceras: dict) -> list[str]:
    """Los Message-ID a los que responde un correo: el padre directo primero."""
    ids = re.findall(r"[^\s<>]+", cabeceras.get("in_reply_to") or "")
    ids += list(reversed(re.findall(r"[^\s<>]+", cabeceras.get("referencias") or "")))
    return ids


def es_respuesta_de_instancia(cabeceras: dict, nombre: str, propios=(), ajenos=()) -> bool:
    """Si un correo responde a la pregunta de esa instancia.

    Primero por In-Reply-To y References: si apunta a un envío de esta
    instancia (`propios`), sí, aunque el alumno le haya cambiado el asunto; si
    apunta a un envío de otra (`ajenos`), no. Si no apunta a ninguno de los dos
    (respondió un correo reenviado, o el envío no guardó su id), se mira si el
    asunto nombra la instancia.
    """
    limpia = lambda x: x.strip().strip("<>")  # noqa: E731
    propios = {limpia(x) for x in propios if x}
    ajenos = {limpia(x) for x in ajenos if x}
    for mid in ids_de_cabeceras(cabeceras):
        if mid in propios:
            return True
        if mid in ajenos:
            return False
    return es_del_nombre(cabeceras.get("asunto", ""), nombre)


def buscar_respuestas_semana(semana: int, nombre: str | None = None,
                             propios=(), ajenos=()) -> list[dict]:
    """Los correos sin leer que responden a la pregunta de esa semana o instancia.

    Sin `nombre` (formato antiguo, 2026-2) se reconoce por «Módulo N» en el
    asunto, como siempre. Con `nombre` («Control 2»), por es_respuesta_de_instancia.
    """
    if nombre is None:
        return buscar_no_leidos(lambda asunto: es_del_modulo(asunto, semana))
    return buscar_no_leidos(filtro=lambda c: es_respuesta_de_instancia(c, nombre, propios, ajenos))


def buscar_respuestas(message_ids: list[str]) -> dict[str, dict]:
    """
    Busca en el inbox mensajes cuyo header In-Reply-To apunte a alguno
    de los message_ids dados.

    Devuelve {message_id_original: {'remitente': ..., 'texto': ..., 'fecha': ...}}.
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

            # Si ya encontré una respuesta para ese id, quedarme con la más reciente
            # (al iterar en reversed, la primera que encuentro es la más reciente)
            if coincide_id in resultado:
                continue

            _, remitente = parseaddr(msg.get("From", ""))
            remitente = remitente.strip().lower()
            fecha_hdr = msg.get("Date", "")
            try:
                fecha = email.utils.parsedate_to_datetime(fecha_hdr).isoformat()
            except Exception:
                fecha = datetime.now().isoformat()

            cuerpo = _limpiar_respuesta(_extraer_cuerpo(msg))
            if not cuerpo.strip():
                continue

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
