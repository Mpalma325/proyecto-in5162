"""
Las tablas del semestre: quiénes son, en qué van, y qué fue pasando.

Este módulo sabe leer y escribir los CSV, y nada más: no manda correos, no
llama a la IA y no sabe qué es una semana o una tarea. Son los flujos (tests,
tareas) los que orquestan las tres cosas.
"""

from . import alumnos, log, notas, reportes
from ._csv import lector as lector_csv
from .esquema import TAREAS, TESTS

__all__ = ["alumnos", "notas", "log", "reportes", "lector_csv", "TESTS", "TAREAS"]
