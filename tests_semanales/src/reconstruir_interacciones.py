"""
Reconstruye el historial completo de interacciones de los Tests Semanales
leyendo el buzon de correo, y lo deja en un CSV por semestre.

Por cada (alumno, semana) junta:
  - la pregunta que le tocó según su grupo (de preguntas.csv)
  - la respuesta que mandó el alumno            (INBOX)
  - la evaluación que le devolvió GPT           (Enviados)
  - la nota y la originalidad extraídas de esa evaluación

El resultado va a  semestres/<id>/tests_semanales/data/interacciones.csv
y se cruza con alumnos.csv por la columna Correo.

Es de solo lectura sobre el correo: abre los buzones en readonly y usa
BODY.PEEK, así que no marca nada como leído ni envía nada.

Uso:
    python -m src.reconstruir_interacciones                # todos los semestres
    python -m src.reconstruir_interacciones 2026-2         # uno en particular
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
from .correo import _decodificar_header, _extraer_cuerpo, _limpiar_respuesta
from .evaluar_respuestas import extraer_nota_y_originalidad

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
    """{semestre: {correo: fila_alumno}} para los semestres con roster."""
    salida = {}
    for carpeta in sorted(SEMESTRES_DIR.iterdir()):
        if not carpeta.is_dir() or carpeta.name == "_template":
            continue
        if filtro and carpeta.name != filtro:
            continue
        roster = carpeta / "tests_semanales" / "data" / "alumnos.csv"
        if not roster.exists():
            continue
        with roster.open(encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f))
        salida[carpeta.name] = {
            fila["Correo"].strip().lower(): fila
            for fila in filas
            if fila.get("Correo", "").strip()
        }
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

def recorrer_buzon(imap, buzon: str, etiqueta: str, quedarse_con) -> list:
    """Recolecta los mensajes de Tests Semanales de un buzón.

    La búsqueda por asunto del servidor no sirve acá: con tilde ("Módulo")
    imaplib no puede construir el comando, y sin tilde no encuentra nada
    porque Gmail busca literal. Se recorre entonces el buzón completo en dos
    fases: primero solo las cabeceras (muy barato) para decidir qué mensajes
    interesan, y después el cuerpo únicamente de esos.

    quedarse_con(asunto_lower) decide si el mensaje interesa.
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
        status, data = imap.fetch(rango, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])")
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
            })

        barra(min(inicio + LOTE_HEADERS, total), total, f"{etiqueta} (cabeceras)")

    barra(total, total, f"{etiqueta} (cabeceras)")
    log(f"    {len(candidatos)} de {total} mensajes son de Tests Semanales")

    if not candidatos:
        return []

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

def main(filtro: str | None = None) -> None:
    rosters = cargar_semestres(filtro)
    if not rosters:
        log("No encontré semestres con alumnos.csv.")
        return

    log(f"Semestres a reconstruir: {', '.join(sorted(rosters))}")
    log(f"Personas por semestre:   " + ", ".join(f"{s}={len(r)}" for s, r in sorted(rosters.items())))
    log()

    creds = config.cargar_correo_config()
    log("Conectando al correo...")
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        log("Conectado. Esto puede tardar varios minutos.\n")

        log("[1/2] Respuestas de los alumnos (INBOX)")
        respuestas = recorrer_buzon(
            imap, "INBOX", "leyendo INBOX",
            quedarse_con=lambda a: "modulo" in a or "módulo" in a,
        )
        log(f"  -> {len(respuestas)} mensajes con 'Módulo' en el asunto\n")

        log("[2/2] Evaluaciones enviadas por GPT (Enviados)")
        evaluaciones = recorrer_buzon(
            imap, '"[Gmail]/Enviados"', "leyendo Enviados",
            quedarse_con=lambda a: a.startswith("re:"),
        )
        log(f"  -> {len(evaluaciones)} respuestas enviadas\n")

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
                "Respuesta": "", "FechaRespuesta": "", "_fecha_resp": None,
                "EvaluacionGPT": "", "NotaGPT": "", "OriginalidadGPT": "",
                "_fecha_eval": None,
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
            reg["FechaRespuesta"] = item["fecha"].isoformat()
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

    # completar con lo que ya sabemos localmente y escribir por semestre
    # NotaGPT/OriginalidadGPT = lo que el agente puso en el correo.
    # NotaFinal/OriginalidadFinal = lo que quedó en alumnos.csv, que puede
    # traer correcciones hechas a mano. Se guardan las dos para poder
    # comparar el criterio del agente contra el del profesor.
    columnas = [
        "Semestre", "Nombre", "Correo", "Grupo", "Semana", "Tema",
        "Pregunta", "Respuesta", "EvaluacionGPT",
        "NotaGPT", "OriginalidadGPT", "NotaFinal", "OriginalidadFinal",
        "FechaRespuesta",
    ]

    log()
    for semestre, roster in sorted(rosters.items()):
        preguntas = cargar_preguntas(semestre)
        filas = []
        for (sem, correo, semana), reg in sorted(registros.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
            if sem != semestre:
                continue
            alumno = roster.get(correo, {})
            grupo = (alumno.get("Grupo") or "control").strip().lower()
            info = preguntas.get(semana, {})
            lista = info.get(grupo) or info.get("control") or []
            fila = dict(reg)
            fila["Nombre"] = alumno.get("Nombre", "")
            fila["Grupo"] = grupo
            fila["Tema"] = info.get("tema", "")
            fila["Pregunta"] = "\n\n".join(f"P{i}: {p}" for i, p in enumerate(lista, 1))
            fila["NotaFinal"] = (alumno.get(f"Nota Test {semana}") or "").strip()
            fila["OriginalidadFinal"] = (alumno.get(f"Originalidad {semana}") or "").strip()
            filas.append({c: fila.get(c, "") for c in columnas})

        destino = SEMESTRES_DIR / semestre / "tests_semanales" / "data" / "interacciones.csv"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=columnas)
            w.writeheader()
            w.writerows(filas)

        con_resp = sum(1 for f in filas if f["Respuesta"])
        con_eval = sum(1 for f in filas if f["EvaluacionGPT"])
        log(f"{semestre}: {len(filas):4d} interacciones  "
            f"({con_resp} con respuesta, {con_eval} con evaluación de GPT)")
        log(f"           -> {destino.relative_to(PROJECT_ROOT)}")

    log("\nListo.")


if __name__ == "__main__":
    arg = None
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            arg = a
    main(arg)
