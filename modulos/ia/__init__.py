"""Llamadas al modelo de lenguaje. Los prompts viven en cada flujo, no acá."""

from .cliente import Respuesta, Texto, ajustes, completar, configurar, consumo, linea_consumo, registrar_uso

__all__ = ["configurar", "completar", "Respuesta", "Texto", "ajustes", "consumo", "linea_consumo", "registrar_uso"]
