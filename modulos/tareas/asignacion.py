"""
Qué pregunta le toca a cada integrante cuando el grupo no declaró roles.

Vive en `entregas/<TAREA>/asignacion_<TAREA>.csv`, con una fila por integrante:

    grupo_archivo,alumno_nombre,pregunta_tarea

El reparto automático es pseudo-aleatorio con semilla fija, así que sale igual
en cada corrida. Este archivo existe para poder cambiarlo: lo que esté acá manda
sobre el reparto, y lo que no esté se reparte como siempre. Se puede editar a
mano o desde la pestaña 1 de la app.

Queda junto a las entregas, no en salidas, porque describe cómo se leyó lo que
entregó el grupo y no un resultado del modelo.
"""

import csv
from pathlib import Path

from . import config

COLUMNAS = ["grupo_archivo", "alumno_nombre", "pregunta_tarea"]
PREGUNTAS_VALIDAS = ("P1", "P2", "P3", "P4")


def _path(tarea: str) -> Path:
    return config.ENTREGAS / tarea / f"asignacion_{tarea}.csv"


def leer(tarea: str) -> dict:
    """
    Lo elegido a mano, como {(grupo_archivo, nombre): "P2"}.

    Devuelve vacío si el archivo no existe todavía, que es el caso normal: solo
    aparece cuando alguien tocó la asignación.
    """
    path = _path(tarea)
    if not path.exists():
        return {}

    elegido = {}
    with path.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            grupo = (fila.get("grupo_archivo") or "").strip()
            nombre = (fila.get("alumno_nombre") or "").strip()
            pregunta = (fila.get("pregunta_tarea") or "").strip().upper()
            if grupo and nombre and pregunta in PREGUNTAS_VALIDAS:
                elegido[(grupo, nombre)] = pregunta
    return elegido


def escribir(tarea: str, elegido: dict) -> Path:
    """Reescribe el archivo completo con lo que se le pase."""
    path = _path(tarea)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
        escritor.writeheader()
        for (grupo, nombre), pregunta in sorted(elegido.items()):
            escritor.writerow({
                "grupo_archivo": grupo,
                "alumno_nombre": nombre,
                "pregunta_tarea": pregunta,
            })
    return path


def aplicar(automatica: dict, elegido: dict, grupo_archivo: str) -> dict:
    """
    El reparto automático de un grupo, con lo elegido a mano encima.

    Solo pisa a los integrantes que aparecen en el archivo; el resto conserva lo
    que le tocó por sorteo. Un valor que no sea P1..P4 se ignora: es preferible
    que quede el sorteo a mandarle al modelo una pregunta que no existe.
    """
    final = dict(automatica)
    for nombre in final:
        manual = (elegido.get((grupo_archivo, nombre)) or "").strip().upper()
        if manual in PREGUNTAS_VALIDAS:
            final[nombre] = manual
    return final
