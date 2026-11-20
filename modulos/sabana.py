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
    "AjusteManual", "MotivoAjuste",
    # La revisión docente (fase 3): qué propuso quién corrigió, qué salió y quién lo revisó.
    "Logro", "NotaEnviada", "Editada", "RevisadoPor", "CorregidoPor", "ModoRevision",
    "FechaFeedback", "Descartada",
    # La escala de notas (fase 4): con qué escala se calculó la Nota vigente y si
    # la dejó así un cambio de escala (evento recalculo).
    "EscalaNota", "Recalculada",
    "Repreguntas", "Tutorias",
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
    """Por (correo, flujo, item): el último envío, corrección, evaluación, descarte,
    ajuste, recálculo y feedback, cuál de ellos dejó la nota vigente y cuántas
    repreguntas."""
    por = {}
    for e in sorted(datos.log.leer(semestre_id), key=lambda f: datos.log._instante(f.get("Timestamp"))):
        clave = (e.get("Correo", "").strip().lower(), e.get("Flujo", ""), str(e.get("Item", "")))
        d = por.setdefault(clave, {"repreguntas": 0, "tutorias": 0})
        ev = e.get("Evento")
        if ev in ("envio", "correccion", "evaluacion", "descarte", "ajuste", "feedback", "recalculo"):
            d[ev] = e
            # La nota vigente es la del último de estos tres (como reconstruir_estado).
            if ev in ("evaluacion", "ajuste", "recalculo") and (e.get("Nota") or "").strip():
                d["nota_por"] = e
            # La de antes (sin Message-ID) trae la nota del modelo; la del envío
            # después de una revisión trae la que salió.
            if ev == "evaluacion" and not (e.get("MessageId") or "").strip():
                d["evaluacion_modelo"] = e
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


def _salio(evaluacion: dict | None) -> bool:
    """Si una `evaluacion` de tareas fue el correo con la corrección.

    Con Message-ID, sí. Las de `corregir --no-enviar` de 2026-2 solo guardaban
    la nota del modelo, y se reconocen porque no anotan la plantilla del correo
    en Versiones. Las anteriores a Versiones se toman como enviadas.
    """
    if not evaluacion:
        return False
    if (evaluacion.get("MessageId") or "").strip():
        return True
    versiones = (evaluacion.get("Versiones") or "").strip()
    return not versiones or "correo_feedback.md@" in versiones


def _fecha_feedback_tarea(ev: dict) -> str:
    """Cuándo salió el correo con la corrección: la `evaluacion` que salió o,
    en 2026-2, el `feedback` de una corrección revisada antes de mandarla."""
    salidas = [ev["feedback"]] if ev.get("feedback") else []
    if _salio(ev.get("evaluacion")):
        salidas.append(ev["evaluacion"])
    if not salidas:
        return ""
    return max(salidas, key=lambda e: datos.log._instante(e.get("Timestamp"))).get("Timestamp", "")


def _estado(f: dict) -> str:
    if f["Nota"] is not None:
        return "evaluada"
    if f.get("Descartada"):
        return "descartada"
    if f.get("PorRevisar"):
        return "por revisar"
    if f["Respondio"]:
        return "respondió sin nota"
    return "sin responder" if f["Enviado"] else "sin enviar"


def _revision(flujo: str, correccion: dict, evaluacion: dict, descarte: dict) -> dict:
    """Las columnas de la revisión docente. Vacías en filas sin `correccion` (anteriores a la fase 3)."""
    salida = {}
    detalle = (evaluacion.get("Detalle") or "").strip()
    revisado = re.match(r"revisado por ([^;]+)", detalle)
    if revisado:
        salida["RevisadoPor"] = revisado.group(1).strip()
    elif descarte:
        salida["RevisadoPor"] = (descarte.get("Detalle") or "").rpartition("; por ")[2].strip()
    if correccion:
        modelo = correccion.get("Modelo") or ""
        salida["CorregidoPor"] = modelo.partition(":")[2] if modelo.startswith("docente:") else "modelo"
        modo = re.search(r"modo=(\w+)", correccion.get("Detalle") or "")
        salida["ModoRevision"] = modo.group(1) if modo else ""
    if flujo == datos.TESTS and evaluacion:
        # En Tests, `evaluacion` es el feedback que salió: su nota y su fecha.
        salida["NotaEnviada"] = evaluacion.get("Nota", "")
        salida["FechaFeedback"] = evaluacion.get("Timestamp", "")
        # Editada: el docente cambió la nota o el texto antes de mandarlo. Un
        # ajuste posterior no cuenta aquí: va en AjusteManual.
        salida["Editada"] = "sí" if revisado and ";" in detalle else "no"
    return salida


def _escala_nota(nota_por: dict) -> dict:
    """EscalaNota y Recalculada de una casilla de Tests, según el evento que dejó la nota.

    Una evaluación anota su escala en Versiones (escala=4-7/1); un recálculo, en
    el Detalle («escala 4-7/1 → 1-7/1; por X»). Un ajuste es una nota puesta a
    mano y no tiene escala. Las evaluaciones de antes de la escala no la anotan.
    """
    ev = nota_por.get("Evento")
    if ev == "recalculo":
        m = re.match(r"escala .+? → (.+?);", nota_por.get("Detalle") or "")
        return {"EscalaNota": m.group(1) if m else "", "Recalculada": "sí"}
    m = re.search(r"(?:^|; )escala=([^;]+)", nota_por.get("Versiones") or "") if ev == "evaluacion" else None
    return {"EscalaNota": m.group(1).strip() if m else "", "Recalculada": "no"}


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
            correccion, descarte = ev.get("correccion") or {}, ev.get("descarte") or {}
            # Los tokens se gastan al corregir: desde la revisión van en `correccion`.
            costo = correccion if (correccion.get("TokensEntrada") or correccion.get("TokensSalida")) else evaluacion
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
                # La nota que propuso quien corrigió; en filas viejas, la del feedback.
                "NotaDelModelo": correccion.get("Nota", "") if correccion else evaluacion.get("Nota", ""),
                "Originalidad": p["Originalidad"],
                "Modelo": p["Modelo"] or evaluacion.get("Modelo", "") or correccion.get("Modelo", ""),
                "Versiones": evaluacion.get("Versiones", "") or correccion.get("Versiones", ""),
                "TokensEntrada": costo.get("TokensEntrada", ""), "TokensSalida": costo.get("TokensSalida", ""),
                "EvaluacionTexto": _texto_plano(p["EvaluacionIA"]), "EvaluacionHTML": p["EvaluacionIA"],
                "AjusteManual": "sí" if ajuste else "no", "MotivoAjuste": ajuste.get("Detalle", ""),
                "Repreguntas": ev["repreguntas"], "Tutorias": ev["tutorias"],
                "Logro": "" if p.get("Logro") is None else p["Logro"],
                "Descartada": "sí" if p.get("Descartada") else "no",
            })
            fila.update(_revision(flujo, correccion, evaluacion, descarte))
            fila["Recalculada"] = "no"
            if flujo == datos.TESTS and p["Nota"] is not None:
                fila.update(_escala_nota(ev.get("nota_por") or {}))
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
                # La propuesta del modelo vive en `correccion` (con los tokens) y la
                # `evaluacion` es lo que salió. En 2026-2 no hay `correccion`: la
                # nota del modelo es la de la evaluación sin Message-ID.
                correccion = ev.get("correccion") or {}
                del_modelo = correccion or ev.get("evaluacion_modelo") or evaluacion
                fila.update({"FechaEvaluacion": (correccion or evaluacion).get("Timestamp", ""),
                             "FechaFeedback": _fecha_feedback_tarea(ev),
                             "NotaDelModelo": del_modelo.get("Nota", "")})
                if correccion:
                    fila.update({"Modelo": fila["Modelo"] or correccion.get("Modelo", ""),
                                 "Versiones": evaluacion.get("Versiones") or correccion.get("Versiones", ""),
                                 "TokensEntrada": correccion.get("TokensEntrada", ""),
                                 "TokensSalida": correccion.get("TokensSalida", "")})
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
