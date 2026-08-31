"""
Del esquema viejo al nuevo, sin intervención manual.

El esquema viejo guardaba el estado como columnas dentro de
`<semestre>/tests_semanales/data/alumnos.csv` ("Envío 3", "Nota Test 3", ...).
El nuevo lo guarda en `<semestre>/notas.csv` en formato largo.

Esto corre solo, la primera vez que alguien pide los datos de un semestre que
todavía no está migrado. Es a propósito: el curso lo operan dos personas desde
equipos distintos, y coordinar una migración manual entre ambas es justo el
tipo de cosa que deja los estados desalineados.

Es idempotente y no borra nada: el esquema viejo queda intacto por si hay que
volver atrás.
"""

import csv
import re

from modulos import semestre as _semestre

from . import _csv
from .esquema import ALUMNOS, COLUMNAS_ALUMNOS, COLUMNAS_NOTAS, LOG, NOTAS, TESTS

_COL_SEMANA = re.compile(r"^(Envío|Nota Test|Originalidad|Respuesta) (\d+)$")


def _alumnos_viejo(semestre_id: str | None) -> list[dict]:
    p = _semestre.raiz(semestre_id) / "tests_semanales" / "data" / "alumnos.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _interacciones_viejo(semestre_id: str | None) -> list[dict]:
    p = _semestre.raiz(semestre_id) / "tests_semanales" / "data" / "interacciones.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def hace_falta(semestre_id: str | None = None) -> bool:
    """True si hay datos viejos y todavía no existe el esquema nuevo."""
    if _csv.ruta(NOTAS, semestre_id).exists():
        return False
    return bool(_alumnos_viejo(semestre_id))


def migrar(semestre_id: str | None = None, verboso: bool = False) -> dict:
    """Genera alumnos.csv, notas.csv y log_envios.csv desde el formato viejo.

    Devuelve un resumen de lo migrado. No toca los archivos originales.
    """
    viejos = _alumnos_viejo(semestre_id)
    if not viejos:
        return {"alumnos": 0, "notas": 0, "log": 0}

    # --- alumnos: solo identidad, el estado se va a notas.csv ---
    alumnos = [
        {"Nombre": a.get("Nombre", ""), "Correo": a.get("Correo", "").strip().lower(),
         "Grupo": a.get("Grupo", "").strip().lower()}
        for a in viejos if a.get("Correo", "").strip()
    ]
    _csv.escribir(ALUMNOS, alumnos, COLUMNAS_ALUMNOS, semestre_id)

    # --- notas: una fila por (alumno, semana) con algo registrado ---
    semanas = sorted({
        int(m.group(2))
        for a in viejos for c in a
        if (m := _COL_SEMANA.match(c or ""))
    })

    filas_notas = []
    for a in viejos:
        correo = a.get("Correo", "").strip().lower()
        if not correo:
            continue
        for s in semanas:
            enviado = (a.get(f"Envío {s}") or "").strip().upper() == "SI"
            nota = (a.get(f"Nota Test {s}") or "").strip()
            orig = (a.get(f"Originalidad {s}") or "").strip()
            respondio = bool((a.get(f"Respuesta {s}") or "").strip())
            if not (enviado or nota or respondio):
                continue
            filas_notas.append({
                "Correo": correo, "Flujo": TESTS, "Item": str(s),
                # El formato viejo no guardaba cuándo, solo que sí: se marca con
                # "SI" para no inventar una fecha que no existió.
                #
                # Si tiene nota o respondió, se da por enviado aunque la columna
                # "Envío" esté vacía. Pasa cuando el envío se hizo desde otro
                # equipo y ese CSV nunca llegó acá: sin esto, el sistema creería
                # que nadie recibió la semana y se la reenviaría a todo el curso.
                "Enviado": "SI" if (enviado or nota or respondio) else "",
                "Respondio": "SI" if respondio else "",
                "Nota": nota, "Originalidad": orig,
            })
    _csv.escribir(NOTAS, filas_notas, COLUMNAS_NOTAS, semestre_id)

    # --- log: lo que se pueda reconstruir de interacciones.csv ---
    eventos = 0
    sem = semestre_id or _semestre.activo() or ""
    for it in _interacciones_viejo(semestre_id):
        correo = it.get("Correo", "").strip().lower()
        item = str(it.get("Semana", "")).strip()
        if not correo or not item:
            continue
        base = {"Semestre": sem, "Flujo": TESTS, "Item": item, "Correo": correo}
        if it.get("Respuesta", "").strip():
            _csv.agregar(LOG, {**base, "Timestamp": it.get("FechaRespuesta", ""),
                               "Evento": "respuesta",
                               "Respuesta": it["Respuesta"]}, _cols_log(), semestre_id)
            eventos += 1
        if it.get("EvaluacionGPT", "").strip():
            _csv.agregar(LOG, {**base, "Timestamp": it.get("FechaRespuesta", ""),
                               "Evento": "evaluacion",
                               "Nota": it.get("NotaGPT", ""),
                               "Originalidad": it.get("OriginalidadGPT", ""),
                               "EvaluacionIA": it["EvaluacionGPT"]}, _cols_log(), semestre_id)
            eventos += 1

    # Aviso: semanas donde unos tienen registro y otros no. Suele significar que
    # el envío se hizo en otro equipo; a los que no dejaron rastro se les podría
    # reenviar. Mejor decirlo que descubrirlo cuando ya salió el correo.
    for s in semanas:
        del_item = [f for f in filas_notas if f["Item"] == str(s)]
        con = sum(1 for f in del_item if f["Enviado"])
        if 0 < con < len(alumnos):
            print(f"  ⚠ semana {s}: {con} de {len(alumnos)} con registro de envío. "
                  f"A los {len(alumnos) - con} restantes se les enviaría de nuevo; "
                  f"revísalo antes de correr el envío.")

    resumen = {"alumnos": len(alumnos), "notas": len(filas_notas), "log": eventos}
    if verboso:
        print(f"  migrado {semestre_id or _semestre.activo()}: "
              f"{resumen['alumnos']} alumnos, {resumen['notas']} filas de estado, "
              f"{resumen['log']} eventos de log")
    return resumen


def _cols_log():
    from .esquema import COLUMNAS_LOG
    return COLUMNAS_LOG


def asegurar(semestre_id: str | None = None) -> None:
    """Migra si hace falta. Seguro de llamar siempre."""
    if hace_falta(semestre_id):
        migrar(semestre_id, verboso=True)
