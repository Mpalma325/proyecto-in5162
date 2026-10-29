"""
Cada correo, simulado o enviado, queda en la salida del trabajo en una línea.

La página dibuja esa línea como el correo que recibe el alumno. Si el cuerpo
se partiera en varias líneas o se perdiera un acento, la página volvería a
mostrar etiquetas HTML sueltas. Nombres y correos inventados: el repo es público.
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo  # noqa: E402

from modulos.mail import envio  # noqa: E402
from modulos.mail.vista import MARCA, mostrar_correo  # noqa: E402

CUERPO = '<div style="color:#333">\n<p>Hola Ana,</p>\n<blockquote>¿Qué es la densidad?</blockquote>\n</div>'


def salida(f, *args, motor=True, **kwargs):
    entorno = {"IN5162_TRABAJO": "abc"} if motor else {}
    buf = io.StringIO()
    with patch.dict(os.environ, entorno, clear=False), redirect_stdout(buf):
        if not motor:
            os.environ.pop("IN5162_TRABAJO", None)
        f(*args, **kwargs)
    return buf.getvalue()


titulo("1. en el motor, un correo es una sola línea marcada que se lee de vuelta igual")
texto = salida(mostrar_correo, "ana.perez@ejemplo.cl", "Módulo 3: Bayes", CUERPO, html=True, nombre="Ana Pérez")
lineas = texto.splitlines()
check("una sola línea", len(lineas) == 1, lineas)
check("empieza con la marca", lineas[0].startswith(MARCA), lineas[0][:40])
datos = json.loads(lineas[0][len(MARCA):])
check("el cuerpo vuelve idéntico, con saltos y acentos", datos["cuerpo"] == CUERPO, datos["cuerpo"])
check("lleva asunto, destinatario y nombre",
      (datos["asunto"], datos["para"], datos["nombre"]) == ("Módulo 3: Bayes", "ana.perez@ejemplo.cl", "Ana Pérez"))
check("una simulación no figura como enviada", datos["enviado"] is False and datos["html"] is True)

titulo("2. en la consola se lee como texto, sin la marca")
texto = salida(mostrar_correo, "ana.perez@ejemplo.cl", "Asunto X", "Hola", motor=False)
check("sin marca", MARCA not in texto, texto)
check("con asunto y cuerpo", "Asunto: Asunto X" in texto and "Hola" in texto, texto)

titulo("3. un envío real queda en la salida del motor, con el remitente")
smtp = MagicMock()
with patch.object(envio.smtplib, "SMTP", return_value=smtp), \
        patch.object(envio.credenciales, "obtener", return_value={"remitente": "curso@ejemplo.cl", "password": "x"}):
    texto = salida(envio.enviar_correo, "ana.perez@ejemplo.cl", "Re: Módulo 3", CUERPO, html=True)
    consola = salida(envio.enviar_correo, "ana.perez@ejemplo.cl", "Re: Módulo 3", CUERPO, html=True, motor=False)
marcadas = [l for l in texto.splitlines() if l.startswith(MARCA)]
check("se envió por SMTP", smtp.__enter__.return_value.send_message.called)
check("deja una línea de correo", len(marcadas) == 1, texto)
datos = json.loads(marcadas[0][len(MARCA):]) if marcadas else {}
check("marcado como enviado, con remitente", datos.get("enviado") is True and datos.get("de") == "curso@ejemplo.cl", datos)
check("en la consola, un envío real no imprime el cuerpo", consola == "", consola)

sys.exit(resultado())
