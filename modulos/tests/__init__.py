"""
Flujo de Tests Semanales: enviar la pregunta de la semana, evaluar lo que
responden los alumnos y resumir cómo le fue al curso.

Es un flujo, así que sí orquesta a los otros módulos: le pide a `mail` que
envíe, a `ia` que evalúe y a `datos` que registre. Lo que no hace es meterse
en cómo funcionan por dentro.
"""

from modulos import ia, mail

from . import config

# Los módulos compartidos no leen ningún .env por su cuenta: el flujo les dice
# de dónde sacar las credenciales. Va acá arriba, antes de importar los
# submódulos, para que ya esté listo cuando alguien los use.
mail.configurar(config.cargar_correo_config, config.cargar_servidores())
ia.configurar(config.cargar_api_key, config.MODELO,
              config.TEMPERATURA, config.MAX_TOKENS)

__all__ = ["enviar", "evaluar", "feedback", "decisiones", "resumen", "chequeo", "tutoria", "reconstruir",
           "experimento", "preguntas", "respuestas", "config"]

# Los submódulos NO se importan acá. Si se importaran, `python -m modulos.X.Y`
# ejecutaría Y dos veces: una al cargar el paquete y otra como __main__.
# Con esto se cargan solo cuando alguien los pide.
def __getattr__(nombre):
    if nombre in __all__:
        import importlib
        return importlib.import_module(f"{__name__}.{nombre}")
    raise AttributeError(f"{__name__} no tiene '{nombre}'")

