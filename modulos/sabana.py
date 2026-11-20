"""
La sábana de datos de un semestre: una fila por alumno e ítem, con todo.

Junta lo que está repartido en varios archivos: quién es el alumno y en qué
variante está, qué pregunta exacta recibió y con qué pauta se corrigió, cuándo
se le envió, qué respondió y cuándo, qué dijo el modelo, cuánto costó, si la
nota se ajustó a mano y por qué, y si después preguntó algo (tutoría). Sirve
para análisis fuera del sistema (R, Excel) y para auditar una nota.

    python -m modulos.sabana                 # semestre activo -> exportes/sabana.csv
    python -m modulos.sabana 2026-2

Solo lee: no manda correos, no llama al modelo y no cambia datos. Es un
orquestador (como los flujos): usa datos, las preguntas de tests y las salidas
de tareas, que entre ellos no se importan.
"""

import csv
import html
import re
import sys
from pathlib import Path

from modulos import datos
from modulos import semestre as _semestre

COLUMNAS = [
    "Semestre", "Flujo", "Item", "Tema", "FechaEntrega",
    "Nombre", "Correo", "EnRoster", "Variante", "GrupoTarea", "ParteTarea",
    "Estado", "NumPreguntas", "Pregunta", "Pauta", "SegundaOportunidad",
    "Enviado", "FechaEnvio", "MessageIdEnvio",
    "Respondio", "FechaRespuesta", "Respuesta", "LargoRespuesta",
    "FechaEvaluacion", "Nota", "NotaTexto", "NotaDelModelo", "Originalidad",
    "Modelo", "Versiones", "TokensEntrada", "TokensSalida", "EvaluacionTexto", "EvaluacionHTML",
    "AjusteManual", "MotivoAjuste", "Repreguntas", "Tutorias",
]


def _texto_plano(html_ia: str) -> str:
    """La evaluación del modelo sin etiquetas, para leerla en una planilla."""
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", html_ia or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def _numerar(textos: list[str]) -> str:
    if len(textos) <= 1:
        return textos[0] if textos else ""
    return "\n".join(f"P{i}: {t}" for i, t in enumerate(textos, 1))


def _eventos(semestre_id: str) -> dict:
    """Por (correo, flujo, item): el último envío, evaluación y ajuste, y cuántas repreguntas."""
    por = {}
    for e in sorted(datos.log.leer(semestre_id), key=lambda f: datos.log._instante(f.get("Timestamp"))):
        clave = (e.get("Correo", "").strip().lower(), e.get("Flujo", ""), str(e.get("Item", "")))
        d = por.setdefault(clave, {"repreguntas": 0, "tutorias": 0})
        ev = e.get("Evento")
        if ev in ("envio", "evaluacion", "ajuste"):
            d[ev] = e
        elif ev == "repregunta":
            d["repreguntas"] += 1
        elif ev == "tutoria":
            d["tutorias"] += 1
    return por


def _preguntas_tests() -> dict:
    """{id: SemanaInfo} de las instancias que se pueden leer.

    Si preguntas.csv no se puede leer entero (Semana e Instancia a la vez), la
    sábana sale igual, con las columnas de preguntas vacías, y lo dice.
    """
    from modulos.tests import preguntas
    try:
        return {str(n): info for n, info in preguntas.instancias(avisar=True).items()}
    except preguntas.PreguntasError as e:
        print(f"⚠ {e} La sábana sale sin las preguntas de los tests.")
        return {}


def _preguntas_tareas() -> dict:
    """{(correo, tarea): fila de feedback_<tarea>.csv} y las tareas con segunda oportunidad."""
    from modulos.tareas import config as tconf
    filas, segunda = {}, set()
    for ruta in sorted(tconf.SALIDAS.glob("feedback_T*.csv")) if tconf.SALIDAS.exists() else []:
        tarea = ruta.stem.split("_", 1)[1]
        with ruta.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                filas[((r.get("alumno_correo") or "").strip().lower(), tarea)] = r
    for ruta in sorted(tconf.SALIDAS.glob("segunda_oportunidad_T*.csv")) if tconf.SALIDAS.exists() else []:
        tarea = ruta.stem.rsplit("_", 1)[1]
        with ruta.open(encoding="utf-8") as f:
            segunda |= {((r.get("correo") or "").strip().lower(), tarea) for r in csv.DictReader(f)
                        if (r.get("message_id") or "").strip()}
    return {"filas": filas, "segunda": segunda}


def _estado(f: dict) -> str:
    if f["Nota"] is not None:
        return "evaluada"
    if f["Respondio"]:
        return "respondió sin nota"
    return "sin responder" if f["Enviado"] else "sin enviar"


def construir(semestre_id: str | None = None) -> list[dict]:
    sid = semestre_id or _semestre.activo_o_error()
    eventos = _eventos(sid)
    semanas = _preguntas_tests()
    tareas = _preguntas_tareas()
    filas = []
    for flujo in (datos.TESTS, datos.TAREAS):
        for p in datos.reportes.panel(sid, flujo):
            ev = eventos.get((p["Correo"], flujo, str(p["Item"])), {"repreguntas": 0, "tutorias": 0})
            evaluacion, ajuste, envio = ev.get("evaluacion") or {}, ev.get("ajuste") or {}, ev.get("envio") or {}
            fila = {c: "" for c in COLUMNAS}
            fila.update({
                "Semestre": sid, "Flujo": flujo, "Item": p["Item"],
                "Nombre": p["Nombre"], "Correo": p["Correo"], "EnRoster": "sí" if p["EnRoster"] else "no",
                "Estado": _estado(p),
                "Enviado": "sí" if p["Enviado"] else "no", "FechaEnvio": p["FechaEnvio"] or envio.get("Timestamp", ""),
                "MessageIdEnvio": envio.get("MessageId", ""),
                "Respondio": "sí" if p["Respondio"] else "no", "FechaRespuesta": p["FechaRespuesta"],
                "Respuesta": p["Respuesta"], "LargoRespuesta": len(p["Respuesta"] or ""),
                "FechaEvaluacion": evaluacion.get("Timestamp", ""),
                "Nota": "" if p["Nota"] is None else p["Nota"], "NotaTexto": p["NotaTexto"],
                "NotaDelModelo": evaluacion.get("Nota", ""), "Originalidad": p["Originalidad"],
                "Modelo": p["Modelo"] or evaluacion.get("Modelo", ""),
                "Versiones": evaluacion.get("Versiones", ""),
                "TokensEntrada": evaluacion.get("TokensEntrada", ""), "TokensSalida": evaluacion.get("TokensSalida", ""),
                "EvaluacionTexto": _texto_plano(p["EvaluacionIA"]), "EvaluacionHTML": p["EvaluacionIA"],
                "AjusteManual": "sí" if ajuste else "no", "MotivoAjuste": ajuste.get("Detalle", ""),
                "Repreguntas": ev["repreguntas"], "Tutorias": ev["tutorias"],
            })
            if flujo == datos.TESTS:
                info = semanas.get(str(p["Item"]))
                fila["Variante"] = p["Grupo"]
                if info:
                    g = info.para_grupo(p["Grupo"] or "control")
                    fila.update({"Tema": info.tema, "FechaEntrega": info.fecha_entrega,
                                 "NumPreguntas": g.n_preguntas, "Pregunta": _numerar(g.preguntas),
                                 "Pauta": _numerar(g.pautas)})
            else:
                t = tareas["filas"].get((p["Correo"], str(p["Item"])), {})
                fila.update({"GrupoTarea": t.get("grupo_archivo", ""), "ParteTarea": t.get("pregunta_tarea", ""),
                             "NumPreguntas": 1 if t.get("pregunta") else "", "Pregunta": t.get("pregunta", ""),
                             "Pauta": t.get("pauta", ""),
                             "SegundaOportunidad": "sí" if (p["Correo"], str(p["Item"])) in tareas["segunda"] else "no"})
            filas.append(fila)
    return filas


def guardar(semestre_id: str | None = None) -> tuple[Path, int]:
    sid = semestre_id or _semestre.activo_o_error()
    filas = construir(sid)
    destino = _semestre.raiz(sid) / "exportes" / "sabana.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel lo abre con los acentos bien.
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS)
        w.writeheader()
        w.writerows(filas)
    return destino, len(filas)


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    ruta, n = guardar(sid)
    print(f"✓ Sábana de {sid or _semestre.activo_o_error()}: {n} filas, {len(COLUMNAS)} columnas → {ruta.name}")
