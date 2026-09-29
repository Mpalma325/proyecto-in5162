"""Llamadas al modelo de lenguaje. Los prompts viven en cada flujo, no acá."""

from .cliente import Respuesta, Texto, ajustes, completar, configurar

__all__ = ["configurar", "completar", "Respuesta", "Texto", "ajustes"]
