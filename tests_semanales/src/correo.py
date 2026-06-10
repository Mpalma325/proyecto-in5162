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


def enviar_correo(destinatario: str, asunto: str, cuerpo: str,
                  html: bool = True, in_reply_to: str | None = None) -> str:
    creds = config.cargar_correo_config()
    message_id = make_msgid(domain="in5162.local")

    msg = MIMEMultipart("alternative")
    msg["From"] = creds["remitente"]
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg["Message-ID"] = message_id

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    subtype = "html" if html else "plain"
    msg.attach(MIMEText(cuerpo, subtype, "utf-8"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(creds["remitente"], creds["password"])
        servidor.send_message(msg)

    return message_id


def _decodificar_header(raw: str) -> str:
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
    texto_plano = ""
    texto_html = ""

    if msg.is_multipart():
        for parte in msg.walk():
            ctype = parte.get_content_type()
            dispo = str(parte.get("Content-Disposition") or "")
            if "attachment" in dispo:
                continue
            try:
                payload = parte.get_payload(decode=True)
                if not payload:
                    continue
                decoded = payload.decode(parte.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue

            if ctype == "text/plain" and not texto_plano:
                texto_plano = decoded
            elif ctype == "text/html" and not texto_html:
                texto_html = decoded
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    texto_html = decoded
                else:
                    texto_plano = decoded
        except Exception:
            pass

    if texto_plano.strip():
        return texto_plano

    if texto_html.strip():
        return _html_a_texto(texto_html)

    return ""


def _html_a_texto(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        import re
        texto = re.sub(r'<br\s*/?>', '\n', html)
        texto = re.sub(r'</(p|div|tr|li)>', '\n', texto)
        texto = re.sub(r'<[^>]+>', '', texto)
        return texto.strip()

    soup = BeautifulSoup(html, "html.parser")

    for quote in soup.select(".gmail_quote, .yahoo_quoted, blockquote"):
        quote.decompose()

    for tag in soup.find_all(["style", "script"]):
        tag.decompose()

    return soup.get_text("\n", strip=True)


def _limpiar_respuesta(texto: str) -> str:
    import re

    lineas = texto.split('\n')

    es_citada = [l.lstrip().startswith(">") for l in lineas]
    n_citadas = sum(es_citada)

    if n_citadas >= 2:
        primera_cita = next(i for i, c in enumerate(es_citada) if c)
        ultima_cita = max(i for i, c in enumerate(es_citada) if c)

        fin_antes = primera_cita
        if fin_antes > 0:
            linea_prev = lineas[fin_antes - 1].strip()
            if re.match(r'^(El |On ).*(escribió|wrote|escribio)\s*:?\s*$', linea_prev):
                fin_antes -= 1

        texto_antes = "\n".join(lineas[:fin_antes]).strip()
        texto_despues = "\n".join(lineas[ultima_cita + 1:]).strip()

        if len(texto_despues) > len(texto_antes):
            return _limpiar_lineas(texto_despues)
        elif texto_antes:
            return _limpiar_lineas(texto_antes)
        else:
            # Ambos vacíos o solo cita: devolver lo que haya después
            return _limpiar_lineas(texto_despues)

    marcadores_fijos = [
        "\n-----Mensaje original-----",
        "\n-----Original Message-----",
        "\n________________________________",
    ]
    patrones_regex = [
        r'\nEl \w{3},?\s+\d{1,2}\s+\w{3,4}\.?\s+\d{4}',          # Gmail español: "El lun, 4 may 2026"
        r'\nOn \w{3},?\s+\w{3,4}\.?\s+\d{1,2},?\s+\d{4}',        # Gmail inglés
        r'\nEl \d{2}-\d{2}-\d{4},? a las',                       # Apple Mail español: "El 29-05-2026, a las"
    ]

    idx_corte = len(texto)
    for m in marcadores_fijos:
        i = texto.find(m)
        if 0 <= i < idx_corte:
            idx_corte = i
    for patron in patrones_regex:
        m = re.search(patron, texto)
        if m and m.start() < idx_corte:
            idx_corte = m.start()

    if idx_corte < 50:
        ultimo = idx_corte
        for m in marcadores_fijos:
            i = texto.rfind(m)
            if i > ultimo:
                ultimo = i
        return _limpiar_lineas(texto[idx_corte:])

    return _limpiar_lineas(texto[:idx_corte])


def _limpiar_lineas(texto: str) -> str:
    lineas = [l.rstrip() for l in texto.splitlines()]
    return "\n".join(lineas).strip()


def buscar_respuestas_semana(semana: int, asunto_contiene: str = "Módulo") -> list[dict]:
    creds = config.cargar_correo_config()
    resultado = []

    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
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


def marcar_leido(uid: str) -> None:
    creds = config.cargar_correo_config()
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")
        imap.store(uid, "+FLAGS", "\\Seen")


def marcar_leidos(uids: list[str]) -> None:
    """Marca múltiples correos como leídos en una sola conexión."""
    if not uids:
        return
    creds = config.cargar_correo_config()
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        imap.select("INBOX")
        for uid in uids:
            imap.store(uid, "+FLAGS", "\\Seen")
