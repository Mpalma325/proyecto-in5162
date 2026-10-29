"""
Envío de correo por SMTP.

Unifica las dos versiones que existían: la de tests (HTML y respuesta en hilo
vía In-Reply-To) y la de tareas (texto plano). El parámetro `html` viene en
False por defecto, que es como lo llamaba tareas; tests siempre lo pasa en True
de forma explícita.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid

from . import credenciales
from .vista import en_motor, mostrar_correo


def enviar_correo(destinatario: str, asunto: str, cuerpo: str,
                  html: bool = False, in_reply_to: str | None = None,
                  creds: dict | None = None) -> str:
    """Envía un correo y devuelve el Message-ID generado.

    El Message-ID se guarda para poder reconocer después la respuesta del
    alumno, que llega con ese valor en su header In-Reply-To.
    """
    c = credenciales.obtener(creds)
    message_id = make_msgid(domain=credenciales.MSGID_DOMINIO)

    msg = MIMEMultipart("alternative")
    msg["From"] = c["remitente"]
    msg["To"] = destinatario
    msg["Subject"] = asunto
    msg["Message-ID"] = message_id

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.attach(MIMEText(cuerpo, "html" if html else "plain", "utf-8"))

    with smtplib.SMTP(credenciales.SMTP_HOST, credenciales.SMTP_PORT) as servidor:
        servidor.starttls()
        servidor.login(c["remitente"], c["password"])
        servidor.send_message(msg)

    # En el motor, lo enviado queda en la salida del trabajo y la página lo
    # muestra como le llegó al alumno. En la consola no: serían cuerpos enteros.
    if en_motor():
        mostrar_correo(destinatario, asunto, cuerpo, html=html, remitente=c["remitente"], enviado=True)
    return message_id
