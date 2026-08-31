"""
Flujo de Tareas: generar una pregunta de comprensión distinta por integrante a
partir del código que entregó su grupo, enviarla, recolectar la respuesta y
corregirla.

A diferencia de los tests semanales, acá cada alumno recibe una pregunta
personalizada sobre la parte del trabajo que le tocó, para que no pueda
responder copiándole a un compañero.
"""

from modulos import ia, mail

from . import config

# Igual que en tests: el flujo le dice a los módulos compartidos de dónde salen
# las credenciales, antes de que ningún submódulo las necesite.
mail.configurar(config.cargar_correo_config)
ia.configurar(config.cargar_api_key, config.MODELO,
              config.TEMPERATURA, config.MAX_TOKENS)

__all__ = ["generar", "enviar", "recolectar", "corregir", "config"]

# Los submódulos NO se importan acá. Si se importaran, `python -m modulos.X.Y`
# ejecutaría Y dos veces: una al cargar el paquete y otra como __main__.
# Con esto se cargan solo cuando alguien los pide.
def __getattr__(nombre):
    if nombre in __all__:
        import importlib
        return importlib.import_module(f"{__name__}.{nombre}")
    raise AttributeError(f"{__name__} no tiene '{nombre}'")

