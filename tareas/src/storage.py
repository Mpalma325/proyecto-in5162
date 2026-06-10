"""
Storage del estado del pipeline en CSV.

Archivo: data/salidas/feedback_<TAREA>.csv

Columnas (en orden):
    tarea               - etiqueta de la tarea (ej: T1, T2)
    grupo_archivo       - nombre del HTML de entrada
    alumno_nombre       - nombre como aparece en el HTML
    alumno_correo       - correo resuelto (del CSV o manual)
    pregunta_tarea      - P1 / P2 / P3 / P4 / vacío
    pregunta            - pregunta generada por GPT
    pauta               - pauta de corrección generada por GPT
    motivo_sin_pregunta - si no hay pregunta, por qué
    fecha_envio         - ISO timestamp cuando se envió el correo
    message_id          - Message-ID del correo enviado (para matchear respuestas)
    respuesta           - texto de la respuesta del alumno
    fecha_respuesta     - ISO timestamp cuando se recibió
    nota                - nota numérica asignada
    comentario          - feedback cualitativo del corrector
    fecha_correccion    - ISO timestamp de la corrección

La clave natural de cada fila es (tarea, grupo_archivo, alumno_nombre).
"""

import csv
from pathlib import Path

from . import config


COLUMNAS = [
    "tarea",
    "grupo_archivo",
    "alumno_nombre",
    "alumno_correo",
    "pregunta_tarea",
    "pregunta",
    "pauta",
    "motivo_sin_pregunta",
    "fecha_envio",
    "message_id",
    "respuesta",
    "fecha_respuesta",
    "nota",
    "comentario",
    "fecha_correccion",
]


def _path_tarea(tarea: str) -> Path:
    config.SALIDAS.mkdir(parents=True, exist_ok=True)
    return config.SALIDAS / f"feedback_{tarea}.csv"


def _clave(fila: dict) -> tuple:
    """Clave natural única de una fila."""
    return (fila.get("tarea", ""), fila.get("grupo_archivo", ""), fila.get("alumno_nombre", ""))


def leer_csv(tarea: str) -> list[dict]:
    """Lee el CSV de una tarea. Devuelve lista vacía si no existe aún."""
    path = _path_tarea(tarea)
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def escribir_csv(tarea: str, filas: list[dict]) -> Path:
    """Escribe el CSV completo. Rellena columnas faltantes con vacío."""
    path = _path_tarea(tarea)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction='ignore')
        writer.writeheader()
        for fila in filas:
            # Asegurar que todas las columnas existan (aunque sea vacías)
            completa = {col: fila.get(col, '') for col in COLUMNAS}
            writer.writerow(completa)
    return path


def agregar_filas(tarea: str, filas_nuevas: list[dict]) -> Path:
    """Agrega filas al CSV existente sin duplicar (por clave natural)."""
    filas = leer_csv(tarea)
    existentes = {_clave(f) for f in filas}
    for nueva in filas_nuevas:
        if _clave(nueva) not in existentes:
            filas.append(nueva)
    return escribir_csv(tarea, filas)


def actualizar_fila(tarea: str, grupo_archivo: str, alumno_nombre: str, campos: dict) -> bool:
    """
    Actualiza los campos especificados de una fila (identificada por clave natural).
    Devuelve True si la encontró y actualizó, False si no.
    """
    filas = leer_csv(tarea)
    encontrado = False
    for fila in filas:
        if fila.get("grupo_archivo") == grupo_archivo and fila.get("alumno_nombre") == alumno_nombre:
            fila.update(campos)
            encontrado = True
            break
    if encontrado:
        escribir_csv(tarea, filas)
    return encontrado


def actualizar_por_message_id(tarea: str, message_id: str, campos: dict) -> bool:
    filas = leer_csv(tarea)
    encontrado = False
    for fila in filas:
        if fila.get("message_id") == message_id:
            fila.update(campos)
            encontrado = True
            break
    if encontrado:
        escribir_csv(tarea, filas)
    return encontrado
