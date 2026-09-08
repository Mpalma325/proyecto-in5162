"""
Reconstruye el historial completo de interacciones de los Tests Semanales
leyendo el buzon de correo, y lo deja en un CSV por semestre.

Por cada (alumno, semana) junta:
  - el envío de la pregunta, con su Message-ID   (Enviados, sin "Re:")
  - la respuesta que mandó el alumno             (INBOX)
  - la evaluación que le devolvió GPT            (Enviados, con "Re:")
  - la nota y la originalidad extraídas de esa evaluación

Cada evento queda con la fecha del correo, no con la del momento de correr
esto, para que el log sirva para mirar la evolución en el tiempo.

El resultado se agrega a  semestres/<id>/log_envios.csv, que es la fuente
unica de lo que fue pasando. Para verlo como tabla de una fila por
alumno-semana: datos.log.como_interacciones().

Es de solo lectura sobre el correo: abre los buzones en readonly y usa
BODY.PEEK, así que no marca nada como leído ni envía nada.

Se puede correr las veces que haga falta: antes de escribir mira lo que el log
ya tiene y solo agrega lo que falta.

Uso:
    python -m modulos.tests.reconstruir                # todos los semestres
    python -m modulos.tests.reconstruir 2026-2         # uno en particular
    python -m modulos.tests.reconstruir --sin-envios   # omite recorrer Enviados
    python -m modulos.tests.reconstruir --simular      # dice que haria, sin escribir
    python -m modulos.tests.reconstruir --solo-estado  # no abre el correo; solo
                                                       # completa notas.csv con lo
                                                       # que el log ya sabe
"""

import csv
import email
import email.utils
import imaplib
import re
import sys
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

from . import config
from modulos.mail import _decodificar_header, _extraer_cuerpo, _limpiar_respuesta
from .evaluar import extraer_nota_y_originalidad

PROJECT_ROOT = config.PROJECT_ROOT
SEMESTRES_DIR = PROJECT_ROOT / "semestres"

# Todos los semestres comparten el mismo buzón, así que para los correos que
# aparecen en más de un roster (típicamente el profesor y los ayudantes) se
# desambigua por la fecha del mensaje.

LOTE_HEADERS = 200  # las cabeceras son livianas: lotes grandes
LOTE_CUERPOS = 25   # los cuerpos pesan, lotes chicos para ver avance


# ----------------------------------------------------------------- utilidades

def barra(actual: int, total: int, etiqueta: str, ancho: int = 34) -> None:
    total = max(total, 1)
    frac = actual / total
    lleno = int(ancho * frac)
    bar = "#" * lleno + "-" * (ancho - lleno)
    sys.stdout.write(f"\r  {etiqueta:22s} [{bar}] {actual:5d}/{total:<5d} {frac:4.0%}")
    sys.stdout.flush()
    if actual >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()


def log(msg: str = "") -> None:
    print(msg, flush=True)


def semana_del_asunto(asunto: str) -> int | None:
    m = re.search(r'm[oó]dulo\s+(\d+)', asunto, re.IGNORECASE)
    return int(m.group(1)) if m else None


def fecha_del_mensaje(msg) -> datetime:
    try:
        d = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


# --------------------------------------------------------------- datos locales

def cargar_semestres(filtro: str | None) -> dict:
    """{semestre: {correo: fila_alumno}} para los semestres que tengan gente.

    Se mira primero el alumnos.csv de la raíz, que es el del esquema vigente, y
    solo si no está se cae al del formato viejo. Antes se miraba únicamente el
    viejo, así que un semestre ya limpio era invisible para la reconstrucción.
    """
    salida = {}
    for carpeta in sorted(SEMESTRES_DIR.iterdir()):
        if not carpeta.is_dir() or carpeta.name.startswith("_"):
            continue
        if filtro and carpeta.name != filtro:
            continue
        for roster in (carpeta / "alumnos.csv",
                       carpeta / "tests_semanales" / "data" / "alumnos.csv"):
            if not roster.exists():
                continue
            with roster.open(encoding="utf-8-sig", newline="") as f:
                filas = list(csv.DictReader(f))
            gente = {
                fila["Correo"].strip().lower(): fila
                for fila in filas
                if fila.get("Correo", "").strip()
            }
            if gente:
                salida[carpeta.name] = gente
                break
    return salida


def cargar_preguntas(semestre: str) -> dict:
    """{semana: {'control': [preguntas], 'tratamiento': [preguntas], 'tema': str}}"""
    path = SEMESTRES_DIR / semestre / "tests_semanales" / "data" / "preguntas.csv"
    if not path.exists():
        return {}
    salida = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            try:
                semana = int((fila.get("Semana") or "").strip())
            except ValueError:
                continue
            entrada = {"tema": (fila.get("Tema") or "").strip()}
            for grupo, prefijo in (("control", "Control"), ("tratamiento", "Tratamiento")):
                preguntas = [
                    (fila.get(f"{prefijo} P{i}") or "").strip()
                    for i in (1, 2, 3)
                ]
                entrada[grupo] = [p for p in preguntas if p]
            if not entrada["tratamiento"]:
                entrada["tratamiento"] = list(entrada["control"])
            salida[semana] = entrada
    return salida


def rango_semestre(semestre_id: str) -> tuple[datetime, datetime] | None:
    """Ventana de fechas de un semestre, deducida de su id (ej. '2026-1').

    En Chile el primer semestre va de marzo a julio y el segundo de agosto a
    diciembre; se toman márgenes anchos para no dejar correos fuera.
    """
    try:
        anio_txt, periodo = semestre_id.split("-")
        anio = int(anio_txt)
    except ValueError:
        return None
    if periodo == "1":
        return (datetime(anio, 1, 1, tzinfo=timezone.utc),
                datetime(anio, 7, 20, 23, 59, 59, tzinfo=timezone.utc))
    if periodo == "2":
        return (datetime(anio, 7, 21, tzinfo=timezone.utc),
                datetime(anio, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    return None


def semestre_de(correo: str, fecha: datetime, rosters: dict) -> str | None:
    """A qué semestre pertenece este mensaje."""
    candidatos = [s for s, roster in rosters.items() if correo in roster]
    if not candidatos:
        return None
    if len(candidatos) == 1:
        return candidatos[0]

    # el correo está en varios rosters: se queda con el semestre cuya ventana
    # de fechas contiene el mensaje
    for sid in sorted(candidatos):
        rango = rango_semestre(sid)
        if rango and rango[0] <= fecha <= rango[1]:
            return sid

    # fuera de toda ventana conocida: el semestre más cercano en el tiempo
    def distancia(sid: str) -> float:
        rango = rango_semestre(sid)
        if not rango:
            return float("inf")
        if fecha < rango[0]:
            return (rango[0] - fecha).total_seconds()
        if fecha > rango[1]:
            return (fecha - rango[1]).total_seconds()
        return 0.0

    return min(sorted(candidatos), key=distancia)


# ------------------------------------------------------------------ lectura

def recorrer_buzon(imap, buzon: str, etiqueta: str, quedarse_con,
                   solo_cabeceras: bool = False) -> list:
    """Recolecta los mensajes de Tests Semanales de un buzón.

    La búsqueda por asunto del servidor no sirve acá: con tilde ("Módulo")
    imaplib no puede construir el comando, y sin tilde no encuentra nada
    porque Gmail busca literal. Se recorre entonces el buzón completo en dos
    fases: primero solo las cabeceras (muy barato) para decidir qué mensajes
    interesan, y después el cuerpo únicamente de esos.

    quedarse_con(asunto_lower) decide si el mensaje interesa.

    Con solo_cabeceras no se baja ningun cuerpo. Sirve para los envios, donde
    lo unico que hace falta es el Message-ID y a quien se le mando.
    """
    status, _ = imap.select(buzon, readonly=True)
    if status != "OK":
        log(f"  no pude abrir {buzon}")
        return []

    status, data = imap.search(None, "ALL")
    if status != "OK" or not data or not data[0]:
        log(f"  {etiqueta}: buzón vacío")
        return []

    ids = data[0].split()
    total = len(ids)
    campo = "From" if buzon == "INBOX" else "To"

    # --- fase 1: cabeceras ---
    candidatos = []
    for inicio in range(0, total, LOTE_HEADERS):
        trozo = ids[inicio:inicio + LOTE_HEADERS]
        rango = b",".join(trozo).decode()
        status, data = imap.fetch(
            rango, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE MESSAGE-ID)])")
        if status != "OK" or not data:
            continue

        pos = 0
        for item in data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            msg = email.message_from_bytes(item[1])
            msg_id = trozo[pos] if pos < len(trozo) else None
            pos += 1
            if msg_id is None:
                continue

            asunto = _decodificar_header(msg.get("Subject", ""))
            if not quedarse_con(asunto.lower()):
                continue
            semana = semana_del_asunto(asunto)
            if semana is None:
                continue
            _, direccion = parseaddr(msg.get(campo, ""))
            candidatos.append({
                "id": msg_id,
                "correo": direccion.strip().lower(),
                "semana": semana,
                "fecha": fecha_del_mensaje(msg),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "asunto": asunto,
            })

        barra(min(inicio + LOTE_HEADERS, total), total, f"{etiqueta} (cabeceras)")

    barra(total, total, f"{etiqueta} (cabeceras)")
    log(f"    {len(candidatos)} de {total} mensajes son de Tests Semanales")

    if not candidatos or solo_cabeceras:
        return candidatos

    # --- fase 2: cuerpos, solo de los que sirven ---
    recolectados = []
    n = len(candidatos)
    for inicio in range(0, n, LOTE_CUERPOS):
        trozo = candidatos[inicio:inicio + LOTE_CUERPOS]
        rango = b",".join(c["id"] for c in trozo).decode()
        status, data = imap.fetch(rango, "(BODY.PEEK[])")
        if status != "OK" or not data:
            continue

        cuerpos = [item[1] for item in data if isinstance(item, tuple) and len(item) >= 2]
        for cand, raw in zip(trozo, cuerpos):
            registro = dict(cand)
            registro["msg"] = email.message_from_bytes(raw)
            recolectados.append(registro)

        barra(min(inicio + LOTE_CUERPOS, n), n, f"{etiqueta} (cuerpos)")

    barra(n, n, f"{etiqueta} (cuerpos)")
    return recolectados


# ------------------------------------------------------------------- proceso

def _ya_en_el_log(semestre_id: str) -> set:
    """Claves (correo, semana, evento) que el log ya tiene para ese semestre.

    Es lo que hace que correr esto dos veces no duplique nada. Antes cada
    corrida agregaba otra vez todas las filas.
    """
    from modulos import datos

    return {
        (f.get("Correo", "").strip().lower(), str(f.get("Item")), f.get("Evento"))
        for f in datos.log.leer(semestre_id)
    }


def sincronizar_estado(semestre_id: str, simular: bool = False) -> None:
    """Pasa al estado lo que quedó en el log y todavía no estaba en la tabla.

    El log guarda cada evento, pero quien decide qué está pendiente es
    `notas.csv`. Si los envíos o las correcciones se hicieron en otro equipo,
    llegan por acá como eventos y hay que reflejarlos en la tabla; si no, la
    reportería no los muestra y el flujo los cree sin hacer.
    """
    from modulos import datos

    r = datos.notas.sincronizar_desde_log(semestre_id, simular=simular)
    if not any(r.values()):
        log(f"{semestre_id}: el estado ya estaba al dia")
        return
    prefijo = "[simulacion] " if simular else ""
    log(f"{prefijo}{semestre_id}: estado completado con "
        f"{r['FilasNuevas']} casilla(s) nueva(s), {r['Enviado']} envio(s), "
        f"{r['Respondio']} respuesta(s), {r['Nota']} nota(s)")


def main(filtro: str | None = None, incluir_envios: bool = True,
         simular: bool = False, solo_estado: bool = False) -> None:
    # Se cargan SIEMPRE todos los rosters, aunque se pida uno solo: los
    # semestres comparten buzón y hay gente que aparece en varios (el profesor,
    # los ayudantes, quien recursa). Con un solo roster cargado no hay contra
    # qué desambiguar y sus correos de otros años terminan atribuidos al
    # semestre pedido. El filtro decide qué se escribe, no qué se mira.
    if solo_estado:
        # No se abre el correo: se completa la tabla de estado con lo que el log
        # ya tiene. Sirve cuando el log llegó de otro equipo, o después de una
        # reconstrucción, y no hace falta credencial de buzón.
        from modulos import semestre as _sem
        for sid in ([filtro] if filtro else _sem.listar()):
            sincronizar_estado(sid, simular)
        log("\nListo.")
        return

    rosters = cargar_semestres(None)
    if not rosters:
        log("No encontré semestres con alumnos.")
        return
    if filtro and filtro not in rosters:
        log(f"No encontré el semestre {filtro}. Hay: {', '.join(sorted(rosters))}")
        return

    destino = [filtro] if filtro else sorted(rosters)
    log(f"Semestres a reconstruir: {', '.join(destino)}")
    if filtro:
        log(f"Rosters cargados para desambiguar: {', '.join(sorted(rosters))}")
    log("Personas por semestre:   " + ", ".join(f"{s}={len(r)}" for s, r in sorted(rosters.items())))
    log()

    creds = config.cargar_correo_config()
    log("Conectando al correo...")
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        log("Conectado. Esto puede tardar varios minutos.\n")

        log("[1/3] Respuestas de los alumnos (INBOX)")
        respuestas = recorrer_buzon(
            imap, "INBOX", "leyendo INBOX",
            quedarse_con=lambda a: "modulo" in a or "módulo" in a,
        )
        log(f"  -> {len(respuestas)} mensajes con 'Módulo' en el asunto\n")

        log("[2/3] Evaluaciones enviadas por GPT (Enviados)")
        evaluaciones = recorrer_buzon(
            imap, '"[Gmail]/Enviados"', "leyendo Enviados",
            quedarse_con=lambda a: a.startswith("re:"),
        )
        log(f"  -> {len(evaluaciones)} respuestas enviadas\n")

        envios = []
        if incluir_envios:
            # Las preguntas originales: las que NO empiezan con "Re:". De acá
            # sale el evento de envío con su Message-ID y su fecha real, que es
            # lo único que permite saber a quién se le mandó qué y cuándo.
            # Basta con las cabeceras, así que no se baja ningún cuerpo.
            log("[3/3] Preguntas enviadas (Enviados)")
            envios = recorrer_buzon(
                imap, '"[Gmail]/Enviados"', "buscando envíos",
                quedarse_con=lambda a: not a.startswith("re:"),
                solo_cabeceras=True,
            )
            log(f"  -> {len(envios)} preguntas originales\n")

    log("Cruzando datos...")

    # (semestre, correo, semana) -> registro
    registros: dict = {}

    def slot(correo, semana, fecha):
        semestre = semestre_de(correo, fecha, rosters)
        if semestre is None:
            return None
        clave = (semestre, correo, semana)
        if clave not in registros:
            registros[clave] = {
                "Semestre": semestre, "Correo": correo, "Semana": semana,
                "Respuesta": "", "_fecha_resp": None,
                "EvaluacionGPT": "", "NotaGPT": "", "OriginalidadGPT": "",
                "_fecha_eval": None,
                "MessageIdEnvio": "", "_fecha_envio": None,
            }
        return registros[clave]

    for item in respuestas:
        reg = slot(item["correo"], item["semana"], item["fecha"])
        if reg is None:
            continue
        texto = _limpiar_respuesta(_extraer_cuerpo(item["msg"])).strip()
        if not texto:
            continue
        # si mandó varias, se evalúa la primera: quedarse con la más antigua
        previa = reg["_fecha_resp"]
        if previa is None or item["fecha"] < previa:
            reg["Respuesta"] = texto
            reg["_fecha_resp"] = item["fecha"]

    for item in evaluaciones:
        reg = slot(item["correo"], item["semana"], item["fecha"])
        if reg is None:
            continue
        cuerpo = _extraer_cuerpo(item["msg"]).strip()
        nota, originalidad = extraer_nota_y_originalidad(cuerpo)
        if not nota:
            continue  # los avisos de "ya tenías nota" no traen evaluación
        # si se evaluó más de una vez, vale la primera (la que quedó en la planilla)
        previa = reg["_fecha_eval"]
        if previa is None or item["fecha"] < previa:
            reg["EvaluacionGPT"] = cuerpo
            reg["NotaGPT"] = nota
            reg["OriginalidadGPT"] = originalidad
            reg["_fecha_eval"] = item["fecha"]

    for item in envios:
        reg = slot(item["correo"], item["semana"], item["fecha"])
        if reg is None:
            continue
        previa = reg["_fecha_envio"]
        if previa is None or item["fecha"] < previa:
            reg["MessageIdEnvio"] = item.get("message_id", "")
            reg["_fecha_envio"] = item["fecha"]

    # Se vuelca al log, que es la fuente unica. Antes esto escribia un
    # interacciones.csv aparte, que quedaba como segunda version del mismo dato.
    from modulos import datos

    log()
    for semestre_id in destino:
        existentes = _ya_en_el_log(semestre_id)
        n_env = n_resp = n_eval = 0
        repetidos = 0

        for (sem, correo, semana), reg in sorted(registros.items()):
            if sem != semestre_id:
                continue

            # El Timestamp es la fecha del correo, no la de ahora. Antes se
            # guardaba el momento de correr el script, lo que dejaba a todos
            # los eventos con la misma hora y arruinaba cualquier analisis
            # temporal del log.
            for evento, condicion, campos, fecha in (
                ("envio", reg["MessageIdEnvio"],
                 {"MessageId": reg["MessageIdEnvio"], "Ronda": 0}, reg["_fecha_envio"]),
                ("respuesta", reg["Respuesta"],
                 {"Respuesta": reg["Respuesta"], "Ronda": 0}, reg["_fecha_resp"]),
                ("evaluacion", reg["EvaluacionGPT"],
                 {"Nota": reg["NotaGPT"], "Originalidad": reg["OriginalidadGPT"],
                  "EvaluacionIA": reg["EvaluacionGPT"], "Ronda": 0}, reg["_fecha_eval"]),
            ):
                if not condicion:
                    continue
                if (correo, str(semana), evento) in existentes:
                    repetidos += 1
                    continue
                if simular:
                    existentes.add((correo, str(semana), evento))
                    if evento == "envio":
                        n_env += 1
                    elif evento == "respuesta":
                        n_resp += 1
                    else:
                        n_eval += 1
                    continue
                datos.log.registrar(
                    evento, datos.TESTS, semana, correo,
                    semestre_id=semestre_id,
                    Timestamp=fecha.isoformat(timespec="seconds") if fecha else "",
                    **campos,
                )
                existentes.add((correo, str(semana), evento))
                if evento == "envio":
                    n_env += 1
                elif evento == "respuesta":
                    n_resp += 1
                else:
                    n_eval += 1

        prefijo = "[simulacion] " if simular else ""
        log(f"{prefijo}{semestre_id}: +{n_env} envio(s), +{n_resp} respuesta(s), "
            f"+{n_eval} evaluacion(es)"
            + (f"  ({repetidos} ya estaban)" if repetidos else ""))

    log("\nListo.")


if __name__ == "__main__":
    _filtro, _envios, _sim, _solo = None, True, False, False
    for a in sys.argv[1:]:
        if a == "--sin-envios":
            _envios = False
        elif a in ("--simular", "--dry-run", "-n"):
            _sim = True
        elif a in ("--solo-estado", "--estado"):
            _solo = True
        elif not a.startswith("-"):
            _filtro = a
    main(_filtro, incluir_envios=_envios, simular=_sim, solo_estado=_solo)
