#!/usr/bin/env python3
"""
Instala el sistema del curso en las cuentas de Cloudflare y Google Cloud de
quien lo corre. Pensado para Google Cloud Shell, que ya trae gcloud, Node,
Python y git.

    python3 instalar.py                 # instala (o completa lo que falte)
    python3 instalar.py actualizar      # trae el código nuevo y vuelve a publicar
    python3 instalar.py estado          # qué existe y qué falta, sin cambiar nada
    python3 instalar.py credenciales    # cambiar la clave de OpenAI, la del correo o el token
    python3 instalar.py --simular       # muestra cada comando en vez de correrlo

Las respuestas quedan en el .env de esta carpeta, que nunca se sube a git.
Detalle técnico: docs/instalador.md.
"""

import sys

if sys.version_info < (3, 11):
    print(f"Este instalador necesita Python 3.11 o más nuevo (tienes {sys.version.split()[0]}).")
    sys.exit(1)

from instalador.principal import main  # noqa: E402

if __name__ == "__main__":
    # Que un ✓ no corte la instalación en una consola sin UTF-8.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
