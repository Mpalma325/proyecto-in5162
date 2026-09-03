"""
Todo lo relacionado con correo: enviar, leer el buzón y limpiar los cuerpos.

Antes vivía duplicado en tests_semanales/src/correo.py y tareas/src/correo.py,
con implementaciones que ya habían divergido entre sí.

Antes de usarlo hay que decirle de dónde saca las credenciales:

    from modulos import mail
    mail.configurar(config.cargar_correo_config)
"""

from .credenciales import (
    IMAP_HOST,
    IMAP_PORT,
    SMTP_HOST,
    SMTP_PORT,
    configurar,
)
from .envio import enviar_correo
from .lectura import (
    buscar_respuestas,
    buscar_no_leidos,
    buscar_respuestas_semana,
    marcar_leido,
    marcar_leidos,
)
from .limpieza import (
    _decodificar_header,
    _extraer_cuerpo,
    _html_a_texto,
    _limpiar_lineas,
    _limpiar_respuesta,
)

__all__ = [
    "configurar",
    "enviar_correo",
    "buscar_no_leidos",
    "buscar_respuestas_semana",
    "buscar_respuestas",
    "marcar_leido",
    "marcar_leidos",
    "SMTP_HOST", "SMTP_PORT", "IMAP_HOST", "IMAP_PORT",
]
