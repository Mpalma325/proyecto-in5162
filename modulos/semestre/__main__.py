"""Muestra qué semestre está activo y cuáles hay. No modifica nada.

Los comandos de envío y evaluación toman el semestre activo sin preguntarlo, así
que conviene mirarlo antes de una corrida real.
"""

import sys

from . import ACTIVO_FILE, activo, listar, raiz

actual = activo()
if not actual:
    print("No hay semestre activo.")
    sys.exit(1)

print(f"Semestre activo: {actual}")
print(f"  carpeta: {raiz(actual)}")
otros = [s for s in listar() if s != actual]
if otros:
    print(f"  otros:   {', '.join(otros)}")
if not ACTIVO_FILE.exists() or ACTIVO_FILE.read_text(encoding="utf-8").strip() != actual:
    print("  (forzado por la variable de entorno IN5162_SEMESTRE)")
