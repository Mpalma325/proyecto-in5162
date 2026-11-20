"""
Quiénes son los alumnos del semestre.

Refleja el archivo que sube el profesor (nombre y correo). El sistema solo le
agrega el grupo cuando lo asigna por primera vez. No se reescribe en cada
operación: el estado del curso vive en notas.csv, así este archivo no se toca
y no hay riesgo de perder datos al sobrescribirlo.

Es uno solo para todo el curso: antes había dos, uno para tests
(Nombre,Correo,Grupo) y otro para tareas (nombre,correo), con los mismos
alumnos escritos distinto.
"""

import random

from . import _csv
from . import migracion as _migracion
from .esquema import ALUMNOS, COLUMNAS_ALUMNOS

CONTROL = "control"
TRATAMIENTO = "tratamiento"


def leer(semestre_id: str | None = None) -> list[dict]:
    _migracion.asegurar(semestre_id)
    return _csv.leer(ALUMNOS, semestre_id)


def escribir(filas: list[dict], semestre_id: str | None = None):
    return _csv.escribir(ALUMNOS, filas, COLUMNAS_ALUMNOS, semestre_id)


def correos(semestre_id: str | None = None) -> list[str]:
    return [
        f["Correo"].strip().lower()
        for f in leer(semestre_id)
        if f.get("Correo", "").strip()
    ]


def por_correo(semestre_id: str | None = None) -> dict:
    return {
        f["Correo"].strip().lower(): f
        for f in leer(semestre_id)
        if f.get("Correo", "").strip()
    }


def grupo_de(correo: str, semestre_id: str | None = None) -> str:
    fila = por_correo(semestre_id).get(correo.strip().lower())
    return (fila or {}).get("Grupo", "").strip().lower() or CONTROL


def con_grupos(semilla: int, semestre_id: str | None = None) -> tuple[list[dict], int]:
    """Las filas de alumnos.csv con el grupo que les tocaría a quienes aún no
    tienen, y cuántos son. No guarda nada: es lo que usa una simulación.

    Mitad y mitad, y con semilla fija para que sea reproducible: con la misma
    lista, el envío real asigna lo mismo que mostró la simulación.
    """
    filas = leer(semestre_id)
    sin_grupo = [f for f in filas if not f.get("Grupo", "").strip()]
    mitad = len(sin_grupo) // 2
    asignaciones = [CONTROL] * mitad + [TRATAMIENTO] * (len(sin_grupo) - mitad)
    random.Random(semilla).shuffle(asignaciones)
    for fila, grupo in zip(sin_grupo, asignaciones):
        fila["Grupo"] = grupo
    return filas, len(sin_grupo)


def asignar_grupos_faltantes(semilla: int, semestre_id: str | None = None) -> int:
    """Reparte control/tratamiento entre quienes aún no tienen grupo, y lo guarda.

    Solo toca a los que están sin asignar: el grupo de un alumno no cambia
    nunca una vez puesto, porque define qué versión de pregunta le tocó.

    Devuelve cuántos se asignaron.
    """
    filas, nuevos = con_grupos(semilla, semestre_id)
    if nuevos:
        escribir(filas, semestre_id)
    return nuevos
