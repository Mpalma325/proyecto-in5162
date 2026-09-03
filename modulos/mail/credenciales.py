"""
De dónde saca este módulo las credenciales del correo.

`mail` no lee ningún .env ni conoce la estructura del proyecto: el que lo usa
le dice cómo obtenerlas. Así el módulo sirve igual para tests, tareas o
cualquier flujo nuevo, sin acoplarse a un config en particular.

    from modulos import mail
    mail.configurar(config.cargar_correo_config)

Los servidores también se pueden inyectar. Los valores de acá son solo el
default de Gmail, para que el módulo funcione sin configurar nada; quien
quiera otro proveedor los pasa en `configurar()`, sin editar código.
"""

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
# Dominio de los Message-ID que se generan al enviar. No necesita existir.
MSGID_DOMINIO = "in5162.local"

_proveedor = None


def configurar(proveedor, servidores: dict | None = None) -> None:
    """Registra de dónde salen las credenciales y, opcionalmente, los servidores.

    `proveedor` es una función sin argumentos que devuelve
    {'remitente': ..., 'password': ...}.

    `servidores` puede traer SMTP_HOST, SMTP_PORT, IMAP_HOST, IMAP_PORT y
    MSGID_DOMINIO. Lo que no venga conserva el default de Gmail. Antes estos
    valores estaban escritos acá y otra vez en modulos/config.py, y solo los de
    acá se usaban de verdad: cambiar los del config no tenía ningún efecto.
    """
    global _proveedor
    _proveedor = proveedor
    for clave, valor in (servidores or {}).items():
        if valor is not None and clave in globals():
            globals()[clave] = valor


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
