"""
Paquete del proyecto. Lo único que hace al importarse es dejar la salida en
condiciones de imprimir lo que los flujos imprimen.

Los mensajes de progreso usan flechas, tildes y símbolos como ⚠ o ✓. La consola
de Windows arranca en cp1252, que no sabe escribirlos: el `print` levanta
UnicodeEncodeError y corta el proceso. Eso pasaba a mitad de un envío, con los
correos ya mandados y el log a medio escribir.

La app y las pruebas ya lanzaban sus subprocesos con PYTHONIOENCODING=utf-8, así
que nunca lo vieron; el que corría los comandos a mano, sí.
"""

import sys


def _salida_en_utf8() -> None:
    for flujo in (sys.stdout, sys.stderr):
        # errors="replace" es lo que hace que esto no falle nunca: si la consola
        # igual no puede con un carácter, sale un reemplazo en vez de una
        # excepción. Perder un símbolo del progreso no es motivo para cortar.
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Salida redirigida a algo que no se puede reconfigurar. Queda como
            # estaba: es preferible a romper el import del paquete entero.
            pass


_salida_en_utf8()
