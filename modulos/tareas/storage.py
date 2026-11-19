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
    message_id          - Message-ID del correo enviado (para matchear respuestas)
    plazo               - hasta cuándo podía responder (ISO, al minuto)
    nota, comentario    - la corrección del modelo, editable antes de mandarla
    senales_ia          - "sí" si el modelo vio señales de que la respuesta es de IA
    justificacion       - por qué el modelo puso esa nota; solo para el equipo docente
    feedback_pendiente  - "sí" si se corrigió sin mandar el correo: espera revisión

La respuesta del alumno y cuándo llegó viven en modulos/datos (log y notas).

La clave natural de cada fila es (tarea, grupo_archivo, alumno_nombre).
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path

from . import config


# Solo lo que es propio de tareas: la pregunta que la IA generó para cada
# integrante y su pauta. El estado (a quién se le envió, quién respondió, qué
# nota sacó) vive en modulos/datos, igual que en tests semanales.
#
# "message_id" se conserva porque acá la respuesta se busca por ese header, no
# por el asunto: es parte de cómo funciona este flujo, no estado duplicado.
COLUMNAS = [
    "tarea",
    "grupo_archivo",
    "alumno_nombre",
    "alumno_correo",
    "pregunta_tarea",
    "pregunta",
    "pauta",
    "motivo_sin_pregunta",
    # Algo que revisar antes de enviar la pregunta, p. ej. que cite código que
    # no está en la entrega (generar._revisar_citas).
    "aviso",
    "message_id",
    # Hasta cuándo podía responder: lo deja enviar y lo usan recolectar y corregir.
    "plazo",
    # La corrección, para revisarla antes de mandarla (modulos/tareas/feedback.py).
    # La nota que cuenta sigue viviendo en datos (notas.csv).
    "nota",
    "comentario",
    "senales_ia",
    "justificacion",
    "feedback_pendiente",
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
    # utf-8-sig: si alguien lo guardó desde Excel, la primera columna no queda
    # como "﻿tarea".
    with path.open(encoding='utf-8-sig') as f:
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
        # La clave se suma al agregar: si no, un lote con la misma fila
        # repetida entraba entero (T2 de 2026-2).
        if _clave(nueva) not in existentes:
            filas.append(nueva)
            existentes.add(_clave(nueva))
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


def respondio_tarde(fila: dict, respondio: str) -> bool:
    """
    Si la respuesta llegó después del plazo de esa fila.

    "hasta las 10:25" incluye todo el minuto 10:25: una respuesta de las
    10:25:20 llega a tiempo (pasó en T2 de 2026-2). Sin plazo guardado, o con una
    fecha que no se entiende, no es tarde: así se comportan T1 y T2, que se
    enviaron antes de que existiera la columna.
    """
    try:
        plazo = datetime.fromisoformat((fila.get("plazo") or "").strip())
        llegada = datetime.fromisoformat((respondio or "").strip())
        return llegada >= plazo + timedelta(minutes=1)
    except (ValueError, TypeError):
        return False


def hora(iso: str) -> str:
    """La hora local de una fecha ISO ("10:28"). El correo puede traerla en otra zona."""
    try:
        return f"{datetime.fromisoformat(iso).astimezone():%H:%M}"
    except (ValueError, TypeError):
        return iso
