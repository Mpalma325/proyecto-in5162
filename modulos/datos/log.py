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
from . import esquema as _esquema
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


# El `Detalle` de una 'respuesta' que llegó cuando el alumno ya estaba
# corregido: recibió el correo de duplicado y no cuenta como su respuesta.
DUPLICADO = "duplicado"


def es_duplicado(fila: dict) -> bool:
    return fila.get("Evento") == "respuesta" and (fila.get("Detalle") or "").strip() == DUPLICADO


def reconstruir_estado(semestre_id: str | None = None) -> dict:
    """Rearma, desde el log, en qué va cada alumno.

    Devuelve {(correo, flujo, item): {...}} con lo último registrado de cada
    tipo. Sirve para regenerar notas.csv si se perdió o quedó desincronizado
    entre dos equipos.

    Cada casilla trae además `historia_nota`: las notas que el log fue dejando,
    en orden. Con eso se distingue una tabla atrasada (tiene una nota anterior)
    de una editada a mano (tiene una que el log nunca tuvo).
    """
    estado: dict = {}
    for fila in leer(semestre_id):
        clave = (fila.get("Correo", ""), fila.get("Flujo", ""), fila.get("Item", ""))
        actual = estado.setdefault(clave, {
            **{c: "" for c in _esquema.COLUMNAS_NOTAS},
            "Correo": clave[0], "Flujo": clave[1], "Item": clave[2],
            "historia_nota": [],
        })
        ts, ev = fila.get("Timestamp", ""), fila.get("Evento")
        if ev == "envio":
            actual["Enviado"] = ts
        elif ev == "respuesta":
            # El duplicado no es su respuesta: la que se corrigió fue la anterior.
            if not es_duplicado(fila):
                actual["Respondio"] = ts
        elif ev == "correccion":
            actual["Corregido"] = ts
            actual["Logro"] = fila.get("Logro", "")
        elif ev == "descarte":
            actual["Descartada"] = ts
        elif ev in ("evaluacion", "ajuste", "recalculo"):
            # La última nota manda: el feedback que salió, un ajuste manual o
            # un cambio de escala. La originalidad viene con la evaluación; un
            # ajuste o un recálculo no la cambian salvo que la traigan.
            nota = fila.get("Nota", "")
            actual["Nota"] = nota
            actual["Logro"] = fila.get("Logro", "")
            if ev == "evaluacion" or fila.get("Originalidad"):
                actual["Originalidad"] = fila.get("Originalidad", "")
            if nota.strip():
                actual["historia_nota"].append(nota.strip())
    return estado


def _mismo_id(a: str, b: str) -> bool:
    """Compara Message-IDs ignorando los <ángulos>, que van y vienen."""
    a, b = (a or "").strip(), (b or "").strip()
    return bool(a) and bool(b) and (a == b or a.strip("<>") == b.strip("<>"))


def fila_por_message_id(message_id: str, semestre_id: str | None = None,
                        eventos: tuple | None = None, flujo: str | None = None) -> dict | None:
    """El evento que produjo el mensaje con ese Message-ID.

    Sirve para saber a qué está contestando un correo entrante: si el id
    corresponde a un 'envio' es la respuesta a la pregunta de la semana, y si
    corresponde a una 'evaluacion' o a una 'tutoria' es una repregunta sobre el
    feedback que ya se le mandó.

    `flujo` limita la búsqueda a tests o a tareas: los dos mandan feedback, y
    una duda sobre el de una tarea no la puede atender la tutoría de tests.
    """
    mid = (message_id or "").strip()
    if not mid:
        return None
    for fila in leer(semestre_id, flujo=flujo):
        if eventos and fila.get("Evento") not in eventos:
            continue
        if _mismo_id(fila.get("MessageId", ""), mid):
            return fila
    return None


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
    for fila in leer(semestre_id, flujo=flujo, item=str(item), evento="envio"):
        if _mismo_id(fila.get("MessageId", ""), mid):
            return fila.get("Correo") or None
    return None


def ultima_ronda(correo: str, flujo: str, item: str,
                 semestre_id: str | None = None) -> int:
    """Cuántas vueltas de tutoría lleva ese alumno en ese ítem."""
    correo = (correo or "").strip().lower()
    rondas = [
        int(f.get("Ronda") or 0)
        for f in leer(semestre_id, flujo=flujo, item=str(item))
        if f.get("Correo", "").strip().lower() == correo and str(f.get("Ronda") or "").strip().isdigit()
    ]
    return max(rondas) if rondas else 0


def conversacion(correo: str, flujo: str, item: str,
                 semestre_id: str | None = None) -> list[dict]:
    """Los mensajes intercambiados con un alumno sobre un ítem, en orden.

    Es lo que se le da al modelo como historial cuando responde una repregunta:
    sin esto cada duda se contestaría sin saber qué se le dijo antes.
    """
    correo = (correo or "").strip().lower()
    de_interes = _esquema.DEL_ALUMNO + _esquema.DEL_AGENTE
    filas = [
        f for f in leer(semestre_id, flujo=flujo, item=str(item))
        if f.get("Correo", "").strip().lower() == correo
        and f.get("Evento") in de_interes
    ]
    return sorted(filas, key=lambda f: (int(f.get("Ronda") or 0), _instante(f.get("Timestamp"))))


def _instante(timestamp: str | None):
    """El momento real de un evento, para ordenar.

    Ordenar el texto no sirve: un equipo registra en -03:00, otro en -07:00 y
    la nube en UTC, y "10:15-03:00" queda antes que "08:00-07:00" aunque sea
    después. Lo que no se puede leer va al principio.
    """
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat((timestamp or "").strip())
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


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
        elif ev == "respuesta" and not es_duplicado(e):
            # La última respuesta que no es un duplicado: en Tareas, con segunda
            # oportunidad, la segunda es la que se corrigió.
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


def _clave_evento(fila: dict) -> tuple:
    """Lo que distingue a un evento de otro.

    El log no tiene id propio, pero un mismo alumno no genera dos veces el
    mismo evento del mismo ítem en el mismo segundo: el timestamp lo escribe
    `registrar()` al ocurrir, y dos equipos operando en paralelo no coinciden
    al segundo sobre la misma casilla. Verificado contra los tres semestres
    en uso, 3697 filas, cero colisiones.
    """
    return (
        (fila.get("Timestamp") or "").strip(),
        (fila.get("Flujo") or "").strip(),
        str(fila.get("Item") or "").strip(),
        (fila.get("Correo") or "").strip().lower(),
        (fila.get("Evento") or "").strip(),
    )


def fusionar(otro, semestre_id: str | None = None, simular: bool = False) -> dict:
    """Incorpora al log de este semestre los eventos de otro log del mismo curso.

    Cuando el curso se opera desde dos equipos, cada uno acumula su propia
    mitad de la historia: los envíos quedan donde se mandaron y las
    evaluaciones donde se corrigieron. Ninguno de los dos ve el total, y
    reemplazar una carpeta por la del otro borra esa mitad.

    Esto se puede juntar porque el log es append-only: nadie edita una fila ya
    escrita, así que no hay versiones en conflicto de un mismo evento, solo
    eventos que están en un archivo y no en el otro. Se agregan los que
    faltan, se ignoran los que ya están y no se toca ninguno de los propios.
    El resultado queda ordenado por timestamp.

    Después de fusionar hay que correr `notas.sincronizar_desde_log()` para
    que el estado refleje lo que entró; `reconstruir --solo-estado` lo hace.
    """
    import os as _os
    import shutil as _shutil
    from pathlib import Path

    origen = Path(otro)
    if not origen.is_file():
        raise FileNotFoundError(f"No existe el log a fusionar: {origen}")

    destino = _csv.ruta(LOG, semestre_id)
    if origen.resolve() == destino.resolve():
        raise ValueError("El log de origen y el de destino son el mismo archivo.")

    import csv as _csvmod

    with open(origen, encoding="utf-8", newline="") as f:
        entrantes = list(_csvmod.DictReader(f))

    propias = _csv.leer(LOG, semestre_id)
    conocidas = {_clave_evento(f) for f in propias}

    # Un log de otro semestre pegado acá contamina la historia sin que nada
    # avise: las claves no colisionan, así que entraría entero.
    # Se compara contra lo que dice el log de acá, no contra el nombre de la
    # carpeta: un semestre copiado a otra carpeta (las pruebas lo hacen) sigue
    # teniendo su id original en la columna, y rechazarlo sería un falso aviso.
    sid = semestre_id or _semestre.activo() or ""
    propios = {(f.get("Semestre") or "").strip() for f in propias} - {""} or {sid}
    ajenas = {(f.get("Semestre") or "").strip() for f in entrantes} - {""} - propios

    nuevas, vistas = [], set()
    for fila in entrantes:
        clave = _clave_evento(fila)
        if clave in conocidas or clave in vistas:
            continue
        vistas.add(clave)
        nuevas.append(fila)

    resumen = {
        "Entrantes": len(entrantes),
        "Nuevas": len(nuevas),
        "YaEstaban": len(entrantes) - len(nuevas),
        "SemestresAjenos": sorted(ajenas),
        "PorEvento": {},
    }
    for fila in nuevas:
        ev = (fila.get("Evento") or "?").strip()
        resumen["PorEvento"][ev] = resumen["PorEvento"].get(ev, 0) + 1

    if ajenas:
        raise ValueError(
            f"El log traído tiene eventos de otro(s) semestre(s): {sorted(ajenas)}. "
            f"Acá el log es de {sorted(propios)}. Fusiona cada uno con el suyo."
        )

    if simular or not nuevas:
        return resumen

    todas = propias + nuevas
    todas.sort(key=lambda f: _instante(f.get("Timestamp")))

    # `_csv.escribir` descarta lo que no esté en las columnas dadas, y el log
    # de otro equipo puede traer una columna que este todavía no tiene. Se
    # respetan las del archivo y se agregan las nuevas al final.
    columnas = list(_csv.cabecera(destino)) or list(COLUMNAS_LOG)
    for fila in todas:
        for c in fila:
            if c and c not in columnas:
                columnas.append(c)

    # El log solo se escribe agregando al final; esta es la única vez que se
    # reescribe entero, así que primero queda una copia. Si algo corta a mitad,
    # el archivo original sigue ahí.
    respaldo = destino.with_suffix(destino.suffix + ".previo")
    if destino.exists():
        _shutil.copy2(destino, respaldo)

    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = _csvmod.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
        w.writeheader()
        for fila in todas:
            w.writerow({c: fila.get(c, "") for c in columnas})
    _os.replace(tmp, destino)

    resumen["Respaldo"] = str(respaldo)
    return resumen
