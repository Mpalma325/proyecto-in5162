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

Al lado vive `correos_<TAREA>.csv`, con el correo elegido a mano para un
integrante cuyo nombre no calzó solo con el roster (en T2 de 2026-2, un alumno
que firmó con sus dos apellidos y en la lista tenía uno solo):

    grupo_archivo,alumno_nombre,alumno_correo
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


COLUMNAS_CORREOS = ["grupo_archivo", "alumno_nombre", "alumno_correo"]


def _path_correos(tarea: str) -> Path:
    return config.ENTREGAS / tarea / f"correos_{tarea}.csv"


def leer_correos(tarea: str) -> dict:
    """Los correos elegidos a mano, como {(grupo_archivo, nombre): correo}."""
    path = _path_correos(tarea)
    if not path.exists():
        return {}

    elegido = {}
    with path.open(encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            grupo = (fila.get("grupo_archivo") or "").strip()
            nombre = (fila.get("alumno_nombre") or "").strip()
            correo = (fila.get("alumno_correo") or "").strip().lower()
            if grupo and nombre and "@" in correo:
                elegido[(grupo, nombre)] = correo
    return elegido


def escribir_correos(tarea: str, elegido: dict) -> Path:
    """Reescribe el archivo completo con lo que se le pase."""
    path = _path_correos(tarea)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CORREOS)
        escritor.writeheader()
        for (grupo, nombre), correo in sorted(elegido.items()):
            escritor.writerow({"grupo_archivo": grupo, "alumno_nombre": nombre,
                               "alumno_correo": correo})
    return path


def correo_elegido(correos: dict, grupo_archivo: str, nombre: str) -> str:
    """El correo elegido a mano para ese integrante, o vacío.

    El nombre puede venir con otro largo de espacios o mayúsculas según lo haya
    copiado el modelo al generar: se compara sin eso.
    """
    clave = " ".join(nombre.split()).lower()
    for (grupo, n), correo in correos.items():
        if grupo == grupo_archivo and " ".join(n.split()).lower() == clave:
            return correo
    return ""
