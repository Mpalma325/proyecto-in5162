import csv
import json
import random
from pathlib import Path

from . import config


def col_envio(semana: int) -> str:
    return f"Envío {semana}"


def col_nota(semana: int) -> str:
    return f"Nota Test {semana}"


def col_originalidad(semana: int) -> str:
    return f"Originalidad {semana}"


def col_respuesta(semana: int) -> str:
    return f"Respuesta {semana}"


def leer_alumnos() -> tuple[list[dict], list[str]]:
    if not config.ALUMNOS_CSV.exists():
        raise FileNotFoundError(
            f"No existe {config.ALUMNOS_CSV}. "
            f"Pon el CSV de alumnos descargado del Google Sheet ahí."
        )
    with config.ALUMNOS_CSV.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        filas = list(reader)
    return filas, headers


def escribir_alumnos(filas: list[dict], headers: list[str]) -> Path:
    config.ALUMNOS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with config.ALUMNOS_CSV.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        for fila in filas:
            completa = {h: fila.get(h, '') for h in headers}
            writer.writerow(completa)
    return config.ALUMNOS_CSV


def asegurar_columnas_semana(headers: list[str], semana: int) -> list[str]:
    columnas_requeridas = [
        col_envio(semana),
        col_nota(semana),
        col_originalidad(semana),
        col_respuesta(semana),
    ]
    for c in columnas_requeridas:
        if c not in headers:
            headers.append(c)
    return headers


def asegurar_columna_grupo(headers: list[str]) -> list[str]:
    if "Grupo" in headers:
        return headers
    try:
        idx = headers.index("Correo") + 1
    except ValueError:
        idx = 2  # fallback: tercera columna
    headers.insert(idx, "Grupo")
    return headers


def asignar_grupos_si_falta(filas: list[dict], headers: list[str]) -> list[str]:
    if not config.GRUPO_CONTROL_TRATAMIENTO:
        return headers

    headers = asegurar_columna_grupo(headers)

    sin_grupo = [f for f in filas if not f.get("Grupo", "").strip()]
    if not sin_grupo:
        return headers

    rng = random.Random(config.GRUPO_SEED)
    asignaciones = ["control"] * (len(sin_grupo) // 2) + ["tratamiento"] * (len(sin_grupo) - len(sin_grupo) // 2)
    rng.shuffle(asignaciones)
    for fila, grupo in zip(sin_grupo, asignaciones):
        fila["Grupo"] = grupo

    return headers


def cargar_message_ids() -> dict:
    if not config.MESSAGE_IDS_FILE.exists():
        return {}
    return json.loads(config.MESSAGE_IDS_FILE.read_text(encoding='utf-8'))


def guardar_message_ids(mapeo: dict) -> None:
    config.MESSAGE_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MESSAGE_IDS_FILE.write_text(
        json.dumps(mapeo, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def registrar_message_id(correo: str, semana: int, message_id: str) -> None:
    mapeo = cargar_message_ids()
    mapeo[f"{correo}|{semana}"] = message_id
    guardar_message_ids(mapeo)


def buscar_alumno_por_message_id(message_id: str, semana: int) -> str | None:
    mapeo = cargar_message_ids()
    sufijo = f"|{semana}"
    for key, mid in mapeo.items():
        if mid == message_id and key.endswith(sufijo):
            return key.rsplit("|", 1)[0]
    return None


# --------------------------------------------------------- interacciones.csv
# Registro largo (una fila por alumno-semana) con la respuesta del alumno y la
# evaluación completa del agente. Va aparte de alumnos.csv porque el texto de
# las evaluaciones lo haría inmanejable; se cruzan por la columna Correo.
# El histórico se reconstruye con  python -m src.reconstruir_interacciones

INTERACCIONES_COLUMNAS = [
    "Semestre", "Nombre", "Correo", "Grupo", "Semana", "Tema",
    "Pregunta", "Respuesta", "EvaluacionGPT",
    "NotaGPT", "OriginalidadGPT", "NotaFinal", "OriginalidadFinal",
    "FechaRespuesta",
]

INTERACCIONES_CSV = config.DATA / "interacciones.csv"


def registrar_interaccion(fila: dict) -> Path:
    """Agrega (o reemplaza) la interacción de un alumno en una semana."""
    existentes = []
    if INTERACCIONES_CSV.exists():
        with INTERACCIONES_CSV.open(encoding="utf-8-sig", newline="") as f:
            existentes = list(csv.DictReader(f))

    clave = (fila.get("Correo", "").strip().lower(), str(fila.get("Semana", "")))
    existentes = [
        f for f in existentes
        if (f.get("Correo", "").strip().lower(), str(f.get("Semana", ""))) != clave
    ]
    existentes.append({c: fila.get(c, "") for c in INTERACCIONES_COLUMNAS})

    existentes.sort(key=lambda f: (f.get("Correo", ""), int(f.get("Semana") or 0)))

    INTERACCIONES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with INTERACCIONES_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INTERACCIONES_COLUMNAS)
        w.writeheader()
        w.writerows(existentes)
    return INTERACCIONES_CSV
