"""
Un correo dentro de la salida de un trabajo, para verlo como lo recibe el alumno.

La página muestra la salida de un trabajo como texto, línea por línea: un
cuerpo HTML impreso tal cual se veía con sus <p> y <blockquote>. Cada correo
va entonces en una sola línea marcada, con el cuerpo dentro de un JSON, y la
página la dibuja como en Gmail; el resto de la salida sigue siendo texto.

Fuera del motor (una corrida en la consola) se imprime legible, sin marca.
"""

import json
import os

MARCA = "@@correo "


def en_motor() -> bool:
    return bool(os.environ.get("IN5162_TRABAJO"))


def mostrar_correo(destinatario: str, asunto: str, cuerpo: str, html: bool = False,
                   nombre: str = "", remitente: str = "", enviado: bool = False) -> None:
    if not en_motor():
        print(f"\nPara: {nombre + ' ' if nombre else ''}<{destinatario}>")
        print(f"Asunto: {asunto}")
        print(cuerpo)
        return
    # json.dumps deja los saltos de línea como \n: el correo ocupa una línea.
    print(MARCA + json.dumps({
        "para": destinatario, "nombre": nombre, "de": remitente, "asunto": asunto,
        "cuerpo": cuerpo, "html": html, "enviado": enviado,
    }, ensure_ascii=False), flush=True)
