"""
Con qué se reconocen en el buzón las respuestas a una instancia de test.

En el formato antiguo (2026-2), por «Módulo N» en el asunto, como siempre. En
los semestres nuevos, por el Message-ID de la pregunta que se le mandó a cada
alumno (el evento `envio` del log), y por el nombre visible («Control 2») en
el asunto si el correo no responde a ningún envío conocido. El buzón no sabe
del log: el flujo le pasa los ids (modulos/mail/lectura.py).
"""

from modulos import datos

from .preguntas import SemanaInfo


def criterio(info: SemanaInfo) -> dict:
    """Los argumentos extra de buscar_respuestas_semana para esta instancia ({} en el formato antiguo)."""
    if info.legado:
        return {}
    propios, ajenos = set(), set()
    for e in datos.log.leer(flujo=datos.TESTS, evento="envio"):
        mid = (e.get("MessageId") or "").strip()
        if mid:
            (propios if str(e.get("Item", "")).strip() == str(info.semana) else ajenos).add(mid)
    return {"nombre": info.nombre, "propios": propios, "ajenos": ajenos}
