"""Lectura y escritura de los CSV del semestre. Detalle interno del módulo."""

import csv
from pathlib import Path

from modulos import semestre as _semestre


def ruta(nombre: str, semestre_id: str | None = None) -> Path:
    """Ubicación de una de las tablas, en la raíz del semestre."""
    return _semestre.raiz(semestre_id) / nombre


def leer(nombre: str, semestre_id: str | None = None) -> list[dict]:
    p = ruta(nombre, semestre_id)
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def escribir(nombre: str, filas: list[dict], columnas: list[str],
             semestre_id: str | None = None) -> Path:
    """Reescribe la tabla completa. No usar para el log."""
    p = ruta(nombre, semestre_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: fila.get(c, "") for c in columnas})
    return p


def agregar(nombre: str, fila: dict, columnas: list[str],
            semestre_id: str | None = None) -> Path:
    """Agrega una fila al final, sin leer ni reescribir lo que ya está.

    Es lo que hace seguro el log: dos procesos escribiendo a la vez pueden
    intercalar filas, pero ninguno pisa lo del otro.
    """
    p = ruta(nombre, semestre_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not p.exists()
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in columnas})
    return p
