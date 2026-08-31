"""
El log de lo que fue pasando. Append-only.

El flujo normal **solo escribe** acá. Se lee para reconstruir la historia,
investigar una anomalía o rearmar el estado si se perdió, no para operar.

Cada fila es un evento, no una interacción: un mismo alumno en una misma semana
deja varias filas (envío, respuesta, evaluación). Así nunca hay que editar algo
ya escrito, que es lo que rompe cuando dos personas trabajan en paralelo.
"""

from datetime import datetime, timezone

from modulos import semestre as _semestre

from . import _csv
from .esquema import COLUMNAS_LOG, EVENTOS, LOG


def _ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def registrar(evento: str, flujo: str, item: str, correo: str,
              semestre_id: str | None = None, **campos) -> None:
    """Deja constancia de algo que ocurrió.

    Nunca levanta excepción hacia el flujo: si el log falla, el envío o la
    corrección ya ocurrieron igual y perderlos sería peor que perder la traza.
    """
    if evento not in EVENTOS:
        raise ValueError(f"Evento desconocido: {evento!r}. Válidos: {EVENTOS}")

    fila = {
        "Timestamp": _ahora(),
        "Semestre": semestre_id or _semestre.activo() or "",
        "Flujo": flujo,
        "Item": str(item),
        "Correo": correo.strip().lower(),
        "Evento": evento,
    }
    fila.update({k: ("" if v is None else v) for k, v in campos.items()})

    try:
        _csv.agregar(LOG, fila, COLUMNAS_LOG, semestre_id)
    except Exception as e:  # noqa: BLE001
        print(f"     ⚠ no pude escribir en el log ({evento}, {correo}): {e}")


def leer(semestre_id: str | None = None, flujo: str | None = None,
         item: str | None = None, evento: str | None = None) -> list[dict]:
    """Eventos registrados, opcionalmente filtrados."""
    filas = _csv.leer(LOG, semestre_id)
    if flujo is not None:
        filas = [f for f in filas if f.get("Flujo") == flujo]
    if item is not None:
        filas = [f for f in filas if f.get("Item") == str(item)]
    if evento is not None:
        filas = [f for f in filas if f.get("Evento") == evento]
    return filas


def reconstruir_estado(semestre_id: str | None = None) -> dict:
    """Rearma, desde el log, en qué va cada alumno.

    Devuelve {(correo, flujo, item): {...}} con lo último registrado de cada
    tipo. Sirve para regenerar notas.csv si se perdió o quedó desincronizado
    entre dos equipos.
    """
    estado: dict = {}
    for fila in leer(semestre_id):
        clave = (fila.get("Correo", ""), fila.get("Flujo", ""), fila.get("Item", ""))
        actual = estado.setdefault(clave, {
            "Correo": clave[0], "Flujo": clave[1], "Item": clave[2],
            "Enviado": "", "Respondio": "", "Nota": "", "Originalidad": "",
        })
        ts, ev = fila.get("Timestamp", ""), fila.get("Evento")
        if ev == "envio":
            actual["Enviado"] = ts
        elif ev == "respuesta":
            actual["Respondio"] = ts
        elif ev == "evaluacion":
            actual["Nota"] = fila.get("Nota", "")
            actual["Originalidad"] = fila.get("Originalidad", "")
    return estado


def correo_de_message_id(message_id: str, flujo: str, item: str,
                         semestre_id: str | None = None) -> str | None:
    """A quién se le envió un correo, según su Message-ID.

    Reemplaza al viejo .message_ids.json: el dato ya queda en el log cuando se
    registra el envío. Sirve para reconocer la respuesta de un alumno que
    contesta desde otra dirección, porque su cliente de correo conserva el
    Message-ID original en el header In-Reply-To.
    """
    mid = (message_id or "").strip()
    if not mid:
        return None
    sin_angulos = mid.strip("<>")
    for fila in leer(semestre_id, flujo=flujo, item=str(item), evento="envio"):
        guardado = (fila.get("MessageId") or "").strip()
        if guardado and (guardado == mid or guardado.strip("<>") == sin_angulos):
            return fila.get("Correo") or None
    return None


def como_interacciones(semestre_id: str | None = None) -> list[dict]:
    """Vista del log en formato "una fila por alumno-ítem".

    Es lo que antes se guardaba aparte en `interacciones.csv`: la pregunta, la
    respuesta del alumno y la evaluación del agente, todo junto. Ahora se
    deriva del log en vez de mantenerse como archivo propio, así no hay dos
    fuentes que puedan quedar desalineadas.

    Se usa para análisis y para exportar; el flujo del curso no la necesita.
    """
    filas: dict = {}
    for e in leer(semestre_id):
        clave = (e.get("Flujo", ""), e.get("Item", ""), e.get("Correo", ""))
        fila = filas.setdefault(clave, {
            "Semestre": e.get("Semestre", ""), "Flujo": clave[0],
            "Item": clave[1], "Correo": clave[2],
            "Respuesta": "", "EvaluacionIA": "",
            "Nota": "", "Originalidad": "", "Modelo": "",
            "FechaEnvio": "", "FechaRespuesta": "",
        })
        ev, ts = e.get("Evento"), e.get("Timestamp", "")
        if ev == "envio":
            fila["FechaEnvio"] = ts
        elif ev == "respuesta":
            fila["FechaRespuesta"] = ts
            if e.get("Respuesta", "").strip():
                fila["Respuesta"] = e["Respuesta"]
        elif ev == "evaluacion":
            fila["EvaluacionIA"] = e.get("EvaluacionIA", "")
            fila["Nota"] = e.get("Nota", "")
            fila["Originalidad"] = e.get("Originalidad", "")
            fila["Modelo"] = e.get("Modelo", "")
    return sorted(filas.values(),
                  key=lambda f: (f["Flujo"], f["Item"], f["Correo"]))


def exportar_interacciones(destino=None, semestre_id: str | None = None):
    """Escribe la vista `como_interacciones()` a un CSV.

    Se genera cuando se necesita (análisis, entregar datos) en vez de
    mantenerse siempre al día como archivo aparte. Así el log es la única
    fuente y no hay dos versiones que puedan discrepar.
    """
    import csv as _csvmod

    filas = como_interacciones(semestre_id)
    if not filas:
        return None
    destino = destino or (_semestre.raiz(semestre_id) / "interacciones_export.csv")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = _csvmod.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    return destino
