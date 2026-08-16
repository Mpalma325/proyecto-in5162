"""
Reconstruye la evaluación "Extra T1" (Discusión Tarea 1) de 2025-2.

Es un caso aparte: ocurrió entre la semana 4 y la 5, y su asunto es
"Módulo Extra: ..." en vez de "Módulo <n>: ...", así que no entra en el
esquema numérico del resto del sistema. Por eso vive en sus propios archivos
(alumnos_extra.csv / interacciones_extra.csv) y no contamina las 13 semanas.

Solo lectura sobre el correo (readonly + BODY.PEEK).

Uso:
    python -m src.reconstruir_extra_2025_2
"""

import csv
import email
import imaplib
import re
from email.utils import parseaddr

import pandas as pd

from . import config
from .correo import _decodificar_header, _extraer_cuerpo, _limpiar_respuesta
from .evaluar_respuestas import extraer_nota_y_originalidad
from .reconstruir_interacciones import LOTE_CUERPOS, LOTE_HEADERS, barra, fecha_del_mensaje, log

SEMESTRE = "2025-2"
DATA = config.PROJECT_ROOT / "semestres" / SEMESTRE / "tests_semanales" / "data"
EXCEL = config.PROJECT_ROOT / "semestres" / "2026-1" / "Preguntas_GPTIN5162_2025-2.xlsx"

# el asunto aparece con uno o dos espacios antes de "Extra"
ES_EXTRA = re.compile(r'm[oó]dulo\s+extra\b', re.IGNORECASE)

COLUMNAS = [
    "Semestre", "Nombre", "Correo", "Grupo", "Evaluacion", "Tema",
    "Pregunta", "Respuesta", "EvaluacionGPT",
    "NotaGPT", "OriginalidadGPT", "NotaFinal", "OriginalidadFinal",
    "FechaRespuesta",
]


def preguntas_extra() -> dict:
    """Las preguntas de la fila 'Extra' del Excel, por grupo."""
    pr = pd.read_excel(EXCEL, sheet_name="Preguntas y Respuestas")
    pr.columns = [str(c).strip() for c in pr.columns]
    for _, r in pr.iterrows():
        if str(r.get("Semana", "")).strip().strip("'").lower() != "extra":
            continue
        salida = {"tema": str(r.get("Tema", "")).strip()}
        for grupo, origen in (("control", "Grupo Control"), ("tratamiento", "Grupo Tratamiento")):
            preguntas = []
            for i in (1, 2, 3):
                v = r.get(f"{origen}- P{i}")
                v = "" if v is None or pd.isna(v) else str(v).strip()
                if v:
                    preguntas.append(v)
            salida[grupo] = preguntas
        return salida
    return {"tema": "", "control": [], "tratamiento": []}


def recolectar(imap, buzon: str, etiqueta: str, solo_respuestas: bool) -> list:
    campo = "From" if buzon == "INBOX" else "To"
    imap.select(buzon, readonly=True)
    status, data = imap.search(None, "ALL")
    if status != "OK" or not data or not data[0]:
        return []

    ids = data[0].split()
    candidatos = []
    for inicio in range(0, len(ids), LOTE_HEADERS):
        trozo = ids[inicio:inicio + LOTE_HEADERS]
        st, data = imap.fetch(b",".join(trozo).decode(),
                              "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO DATE)])")
        if st != "OK" or not data:
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
            if not ES_EXTRA.search(asunto):
                continue
            # en Enviados solo interesan las respuestas (evaluaciones), no el envío inicial
            if not solo_respuestas and not asunto.lower().strip().startswith("re:"):
                continue
            _, direccion = parseaddr(msg.get(campo, ""))
            candidatos.append({"id": msg_id, "correo": direccion.strip().lower(),
                               "fecha": fecha_del_mensaje(msg)})
        barra(min(inicio + LOTE_HEADERS, len(ids)), len(ids), f"{etiqueta} (cabeceras)")
    barra(len(ids), len(ids), f"{etiqueta} (cabeceras)")

    if not candidatos:
        return []

    salida = []
    for inicio in range(0, len(candidatos), LOTE_CUERPOS):
        trozo = candidatos[inicio:inicio + LOTE_CUERPOS]
        st, data = imap.fetch(b",".join(c["id"] for c in trozo).decode(), "(BODY.PEEK[])")
        if st != "OK" or not data:
            continue
        cuerpos = [it[1] for it in data if isinstance(it, tuple) and len(it) >= 2]
        for cand, raw in zip(trozo, cuerpos):
            reg = dict(cand)
            reg["msg"] = email.message_from_bytes(raw)
            salida.append(reg)
        barra(min(inicio + LOTE_CUERPOS, len(candidatos)), len(candidatos), f"{etiqueta} (cuerpos)")
    barra(len(candidatos), len(candidatos), f"{etiqueta} (cuerpos)")
    return salida


def main() -> None:
    with (DATA / "alumnos_extra.csv").open(encoding="utf-8-sig", newline="") as f:
        planilla = {r["Correo"].strip().lower(): r for r in csv.DictReader(f)}
    log(f"planilla Extra T1: {len(planilla)} alumnos")

    info = preguntas_extra()
    log(f"tema: {info['tema']!r}  ({len(info['control'])} preguntas)\n")

    creds = config.cargar_correo_config()
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT) as imap:
        imap.login(creds["remitente"], creds["password"])
        log("[1/2] Respuestas de los alumnos (INBOX)")
        respuestas = recolectar(imap, "INBOX", "leyendo INBOX", solo_respuestas=True)
        log(f"  -> {len(respuestas)}\n")
        log("[2/2] Evaluaciones enviadas (Enviados)")
        evaluaciones = recolectar(imap, '"[Gmail]/Enviados"', "leyendo Enviados", solo_respuestas=False)
        log(f"  -> {len(evaluaciones)}\n")

    registros = {}

    def slot(correo):
        if correo not in planilla:
            return None
        if correo not in registros:
            a = planilla[correo]
            registros[correo] = {
                "Semestre": SEMESTRE, "Nombre": a.get("Nombre", ""), "Correo": correo,
                "Grupo": a.get("Grupo", "control"), "Evaluacion": "Extra T1",
                "Tema": info["tema"],
                "Pregunta": "\n\n".join(
                    f"P{i}: {p}" for i, p in enumerate(info.get(a.get("Grupo", "control"), []), 1)
                ),
                "Respuesta": "", "FechaRespuesta": "", "_fr": None,
                "EvaluacionGPT": "", "NotaGPT": "", "OriginalidadGPT": "", "_fe": None,
                "NotaFinal": a.get("Nota", ""), "OriginalidadFinal": a.get("Originalidad", ""),
            }
        return registros[correo]

    for item in respuestas:
        reg = slot(item["correo"])
        if reg is None:
            continue
        texto = _limpiar_respuesta(_extraer_cuerpo(item["msg"])).strip()
        if texto and (reg["_fr"] is None or item["fecha"] < reg["_fr"]):
            reg["Respuesta"] = texto
            reg["FechaRespuesta"] = item["fecha"].isoformat()
            reg["_fr"] = item["fecha"]

    for item in evaluaciones:
        reg = slot(item["correo"])
        if reg is None:
            continue
        cuerpo = _extraer_cuerpo(item["msg"]).strip()
        nota, orig = extraer_nota_y_originalidad(cuerpo)
        if nota and (reg["_fe"] is None or item["fecha"] < reg["_fe"]):
            reg["EvaluacionGPT"] = cuerpo
            reg["NotaGPT"] = nota
            reg["OriginalidadGPT"] = orig
            reg["_fe"] = item["fecha"]

    filas = [{c: reg.get(c, "") for c in COLUMNAS}
             for _, reg in sorted(registros.items())]

    destino = DATA / "interacciones_extra.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)

    con_r = sum(1 for f in filas if f["Respuesta"])
    con_e = sum(1 for f in filas if f["EvaluacionGPT"])
    log(f"\n{len(filas)} interacciones ({con_r} con respuesta, {con_e} con evaluación)")
    log(f"-> {destino.relative_to(config.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
