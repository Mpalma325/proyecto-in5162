"""
De dónde saca este módulo las credenciales del correo.

`mail` no lee ningún .env ni conoce la estructura del proyecto: el que lo usa
le dice cómo obtenerlas. Así el módulo sirve igual para tests, tareas o
cualquier flujo nuevo, sin acoplarse a un config en particular.

    from modulos import mail
    mail.configurar(config.cargar_correo_config)
"""

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

_proveedor = None


def configurar(proveedor) -> None:
    """Registra una función sin argumentos que devuelve {remitente, password}."""
    global _proveedor
    _proveedor = proveedor


def obtener(creds: dict | None = None) -> dict:
    """Credenciales a usar: las explícitas, o las del proveedor registrado."""
    if creds is not None:
        return creds
    if _proveedor is None:
        raise RuntimeError(
            "El módulo mail no tiene credenciales. Llama a mail.configurar(...) "
            "pasándole una función que devuelva {'remitente': ..., 'password': ...}."
        )
    return _proveedor()
