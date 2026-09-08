"""
El estado del curso: a quién se le envió qué, quién respondió y con qué nota.

Es la tabla que el flujo lee para saber qué le falta por hacer, y la que se
edita a mano cuando hay que corregir una nota.

Formato largo: una fila por (alumno, flujo, ítem). Antes esto vivía como cuatro
columnas por semana dentro de alumnos.csv, que llegaba a 55 columnas.
"""

from datetime import datetime, timezone

from . import _csv
from . import log as _log
from . import migracion as _migracion
from .esquema import COLUMNAS_NOTAS, NOTAS


def _ahora() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clave(fila: dict) -> tuple:
    return (fila.get("Correo", "").strip().lower(),
            fila.get("Flujo", ""), str(fila.get("Item", "")))


def leer(semestre_id: str | None = None, flujo: str | None = None,
         item: str | None = None) -> list[dict]:
    _migracion.asegurar(semestre_id)
    filas = _csv.leer(NOTAS, semestre_id)
    if flujo is not None:
        filas = [f for f in filas if f.get("Flujo") == flujo]
    if item is not None:
        filas = [f for f in filas if str(f.get("Item")) == str(item)]
    return filas


def estado(correo: str, flujo: str, item: str,
           semestre_id: str | None = None) -> dict | None:
    """En qué va un alumno en un ítem concreto, o None si no hay registro."""
    objetivo = (correo.strip().lower(), flujo, str(item))
    _migracion.asegurar(semestre_id)
    for fila in _csv.leer(NOTAS, semestre_id):
        if _clave(fila) == objetivo:
            return fila
    return None


def _upsert(correo: str, flujo: str, item: str, cambios: dict,
            semestre_id: str | None = None) -> None:
    _migracion.asegurar(semestre_id)
    filas = _csv.leer(NOTAS, semestre_id)
    objetivo = (correo.strip().lower(), flujo, str(item))

    for fila in filas:
        if _clave(fila) == objetivo:
            fila.update(cambios)
            break
    else:
        nueva = {"Correo": objetivo[0], "Flujo": flujo, "Item": str(item),
                 "Enviado": "", "Respondio": "", "Nota": "", "Originalidad": ""}
        nueva.update(cambios)
        filas.append(nueva)

    filas.sort(key=lambda f: (f.get("Flujo", ""), str(f.get("Item", "")), f.get("Correo", "")))
    _csv.escribir(NOTAS, filas, COLUMNAS_NOTAS, semestre_id)


def marcar_enviado(correo: str, flujo: str, item: str,
                   cuando: str | None = None, semestre_id: str | None = None) -> None:
    _upsert(correo, flujo, item, {"Enviado": cuando or _ahora()}, semestre_id)


def marcar_respondio(correo: str, flujo: str, item: str,
                     cuando: str | None = None, semestre_id: str | None = None) -> None:
    _upsert(correo, flujo, item, {"Respondio": cuando or _ahora()}, semestre_id)


def registrar_nota(correo: str, flujo: str, item: str, nota: str,
                   originalidad: str = "", semestre_id: str | None = None) -> None:
    _upsert(correo, flujo, item,
            {"Nota": nota, "Originalidad": originalidad}, semestre_id)


def ya_enviado(correo: str, flujo: str, item: str,
               semestre_id: str | None = None) -> bool:
    e = estado(correo, flujo, item, semestre_id)
    return bool(e and e.get("Enviado", "").strip())


def ya_evaluado(correo: str, flujo: str, item: str,
                semestre_id: str | None = None) -> bool:
    e = estado(correo, flujo, item, semestre_id)
    return bool(e and e.get("Nota", "").strip())


def pendientes_de_envio(correos: list[str], flujo: str, item: str,
                        semestre_id: str | None = None) -> list[str]:
    """De una lista de alumnos, los que todavía no reciben ese ítem."""
    enviados = {
        _clave(f)[0] for f in leer(semestre_id, flujo, item)
        if f.get("Enviado", "").strip()
    }
    return [c for c in correos if c.strip().lower() not in enviados]


def sincronizar_desde_log(semestre_id: str | None = None,
                          simular: bool = False) -> dict:
    """Completa esta tabla con lo que el log sabe y a ella le falta.

    El log es append-only y guarda todo lo que ocurrió; `notas.csv` es el
    estado y se reescribe. Cuando el curso se opera desde dos equipos, el log
    de cada uno se puede juntar sin conflicto, pero el estado no: quedan
    envíos, respuestas y notas registradas como evento y sin reflejo en la
    tabla, y entonces la reportería no las muestra y el flujo cree que están
    pendientes.

    **Solo agrega.** Crea la fila que falte y llena el campo que esté vacío;
    nunca borra una fila ni pisa un valor ya escrito. Las dos razones: la tabla
    también se edita a mano cuando el equipo docente corrige una nota, y los
    semestres que vienen del esquema viejo tienen filas que el log no conoce
    porque son anteriores a él.

    Con `simular` dice cuánto cambiaría sin escribir nada.
    """
    _migracion.asegurar(semestre_id)
    filas = _csv.leer(NOTAS, semestre_id)
    indice = {_clave(f): f for f in filas}

    resumen = {"FilasNuevas": 0, "Enviado": 0, "Respondio": 0, "Nota": 0}

    for clave, desde_log in _log.reconstruir_estado(semestre_id).items():
        correo, flujo, item = clave
        if not correo:
            continue
        fila = indice.get(clave)
        if fila is None:
            fila = {"Correo": correo, "Flujo": flujo, "Item": str(item),
                    "Enviado": "", "Respondio": "", "Nota": "", "Originalidad": ""}
            filas.append(fila)
            indice[clave] = fila
            resumen["FilasNuevas"] += 1

        for campo in ("Enviado", "Respondio", "Nota"):
            valor = (desde_log.get(campo) or "").strip()
            if valor and not (fila.get(campo) or "").strip():
                fila[campo] = valor
                resumen[campo] += 1
                # La originalidad viaja pegada a la nota: se escribieron juntas
                # y por separado no significan nada.
                if campo == "Nota":
                    fila["Originalidad"] = desde_log.get("Originalidad", "")

    if not simular and any(resumen.values()):
        filas.sort(key=lambda f: (f.get("Flujo", ""), str(f.get("Item", "")),
                                  f.get("Correo", "")))
        _csv.escribir(NOTAS, filas, COLUMNAS_NOTAS, semestre_id)

    return resumen
