"""
Andamiaje compartido de las pruebas.

Todas siguen la misma forma: copiar un semestre a uno desechable, bloquear la
red, correr un flujo real contra esa copia y contar aciertos. Eso estaba escrito
igual en cada archivo; acá vive una sola vez.
"""

import os
import shutil
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

_ok = 0
_fail = 0

# Direcciones a las que se "envió" durante la prueba. Los flujos escriben acá
# en lugar de tocar SMTP, así que basta mirar la lista para saber qué salió.
enviados: list[str] = []


def check(nombre: str, condicion, extra="") -> None:
    global _ok, _fail
    if condicion:
        _ok += 1
        print(f"  [OK  ] {nombre}")
    else:
        _fail += 1
        print(f"  [FALL] {nombre}   <- {extra}")


def resultado() -> int:
    """Imprime el total y devuelve el código de salida del proceso."""
    print(f"\n{_ok} OK, {_fail} fallos")
    return 1 if _fail else 0


def titulo(texto: str) -> None:
    print(f"\n=== {texto} ===")


@contextmanager
def semestre_desechable(base: str = "2026-2", sid: str = "_tmp_prueba", vaciar=()):
    """Copia `base` a un semestre temporal y lo deja activo para este proceso.

    El semestre se fija con la variable de entorno, nunca escribiendo el
    activo.txt: ese archivo es compartido, y una prueba interrumpida a mitad lo
    dejaría apuntando a una carpeta que se borra al terminar.

    `vaciar` son archivos a eliminar de la copia, para simular un semestre que
    todavía no tiene datos nuevos.
    """
    from modulos import semestre

    tmp = semestre.SEMESTRES_DIR / sid
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(semestre.SEMESTRES_DIR / base, tmp)
    for nombre in vaciar:
        (tmp / nombre).unlink(missing_ok=True)

    previo = os.environ.get("IN5162_SEMESTRE")
    os.environ["IN5162_SEMESTRE"] = sid
    # Los módulos calculan sus rutas al importarse, así que hay que soltarlos
    # para que las recalculen apuntando a la copia.
    for m in [k for k in sys.modules if k.startswith("modulos.")]:
        del sys.modules[m]
    try:
        yield sid, tmp
    finally:
        if previo is None:
            os.environ.pop("IN5162_SEMESTRE", None)
        else:
            os.environ["IN5162_SEMESTRE"] = previo
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"limpieza OK (el activo.txt real nunca se tocó)")


def _smtp_falso(*a, **k):
    m = MagicMock()
    m.__enter__.return_value.send_message.side_effect = lambda msg: enviados.append(msg["To"])
    return m


def sin_red():
    """Bloquea SMTP e IMAP. Si algo intenta salir a la red, falla en vez de salir."""
    return _DobleParche(
        patch("smtplib.SMTP", side_effect=_smtp_falso),
        patch("imaplib.IMAP4_SSL"),
    )


class _DobleParche:
    def __init__(self, *parches):
        self._parches = parches

    def __enter__(self):
        for p in self._parches:
            p.__enter__()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._parches):
            p.__exit__(*exc)
        return False


def respuestas_falsas(correos, item, desde=0, cantidad=None):
    """Correos entrantes simulados, como los devolvería la lectura del inbox."""
    trozo = correos[desde:] if cantidad is None else correos[desde:desde + cantidad]
    return [
        {
            "uid": str(i).encode(),
            "remitente": c,
            "asunto": f"Re: Modulo {item}",
            "in_reply_to": "",
            "fecha": datetime.now(timezone.utc),
            "texto": f"Respuesta de {c} con contenido suficiente para evaluar.",
        }
        for i, c in enumerate(trozo, start=desde)
    ]


def nota_ia(nota="6,0", originalidad="Media"):
    return f"<p>NOTA FINAL: {nota}</p><p>ORIGINALIDAD: {originalidad}</p>"
