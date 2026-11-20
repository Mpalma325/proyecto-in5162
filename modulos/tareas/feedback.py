"""
Paso 5 del flujo: mandar las correcciones que se guardaron para revisarlas.

`corregir --no-enviar` deja la propuesta del modelo en el log (evento
`correccion`, con el JSON completo) y en feedback_<TAREA>.csv la nota, el
comentario, la marca de IA y la justificación, con feedback_pendiente = "sí".
En la página se leen y se pueden editar la nota y el comentario. Esto manda el
correo con lo que quedó escrito, y recién entonces la nota cuenta: el evento
`evaluacion` (con el Message-ID, la nota y el comentario que salieron, y en
Detalle quién lo revisó y qué cambió) y después la nota en notas.csv.

Quién espera su correo lo decide el log, no el CSV: la última `correccion` de
cada alumno que no tenga una `evaluacion` después. El CSV lo escriben la página
y los trabajos; si alguien editaba mientras corría un trabajo, el CSV de ese
trabajo no se guardó (etag) y puede decir "pendiente" de algo que ya salió, o
no saber de una corrección nueva. Por eso, al empezar:
  - lo que el log dice que ya salió no se reenvía, aunque el CSV diga pendiente;
  - la corrección que está en el log y no en el CSV se copia al CSV.
Las dos reparaciones del CSV se escriben solo en modo real.

Las filas de antes (2026-2) no tienen `correccion`: corregir registraba una
`evaluacion` con la nota del modelo al corregir, saliera o no el correo, y
feedback.py anotaba un `feedback` al mandarlo. Para esas, feedback_pendiente
sigue decidiendo, salvo que el log ya tenga el `feedback`.

Uso:
    python -m modulos.tareas.feedback T2
    python -m modulos.tareas.feedback T2 --dry-run          # muestra los correos, no los manda
    python -m modulos.tareas.feedback T2 --solo a@x.cl,b@x.cl
    python -m modulos.tareas.feedback T2 --por profe@x.cl   # quién lo revisó, para el log
"""

import json
import sys

from modulos import datos as _datos
from modulos.datos import candidatos as _candidatos
from modulos.mail.vista import mostrar_correo
from modulos.progreso import avanzar

from . import config, storage
from .corregir import _cargar_template_feedback, armar_correo, mandar_feedback
from .escala import validar_nota

POR_MANDAR, ENVIADA, ANTERIOR = "por mandar", "enviada", "anterior"


def _historia(tarea: str) -> dict:
    """Por correo, qué dice el log de su corrección, en orden.

    `estado`: "por mandar" (hay una `correccion` sin `evaluacion` después),
    "enviada" (lo último es una `evaluacion` con Message-ID o un `feedback`) o
    "anterior" (lo último es una `evaluacion` sin Message-ID, del flujo de antes:
    no se sabe si salió). `correccion` y `anterior` guardan esos eventos.
    """
    por = {}
    eventos = sorted(_datos.log.leer(flujo=_datos.TAREAS, item=tarea),
                     key=lambda e: _datos.log._instante(e.get("Timestamp")))
    for e in eventos:
        d = por.setdefault((e.get("Correo") or "").strip().lower(),
                           {"estado": None, "correccion": None, "anterior": None})
        ev = e.get("Evento")
        if ev == "correccion":
            d.update(estado=POR_MANDAR, correccion=e)
        elif ev == "feedback" or (ev == "evaluacion" and (e.get("MessageId") or "").strip()):
            d["estado"] = ENVIADA
        elif ev == "evaluacion":
            d.update(estado=ANTERIOR, anterior=e)
    return por


def _json(texto: str) -> dict:
    try:
        valor = json.loads(texto or "")
    except ValueError:
        return {}
    return valor if isinstance(valor, dict) else {}


def _desde_correccion(correccion: dict) -> dict:
    """Las columnas del CSV que deja corregir, sacadas de su evento `correccion`."""
    j = _json(correccion.get("EvaluacionIA"))
    senales = j.get("señales_copia_ia") or j.get("senales_copia_ia")
    return {"nota": (correccion.get("Nota") or "").strip(), "comentario": j.get("comentario", ""),
            "senales_ia": "sí" if senales else "", "justificacion": j.get("justificacion_interna", ""),
            "feedback_pendiente": "sí"}


def _misma_nota(a, b) -> bool:
    a, b = str(a or "").strip().replace(",", "."), str(b or "").strip().replace(",", ".")
    try:
        return float(a) == float(b)
    except ValueError:
        return a == b


def _detalle(por: str | None, nota_antes: str, nota, comentario_antes: str | None, comentario: str) -> str:
    """«revisado por X; nota 5.0 → 5.5; comentario editado»: quién lo mandó y qué cambió."""
    partes = [f"revisado por {por}" if por else "revisado"]
    if nota_antes and not _misma_nota(nota_antes, nota):
        partes.append(f"nota {nota_antes} → {nota}")
    if comentario_antes is not None and comentario.strip() != comentario_antes.strip():
        partes.append("comentario editado")
    return "; ".join(partes)


def _respuestas(tarea: str) -> dict:
    return {e["Correo"]: e["Respuesta"]
            for e in _datos.log.leer(flujo=_datos.TAREAS, item=tarea, evento="respuesta")
            if e.get("Respuesta", "").strip()}


def _al_dia_con_el_log(tarea: str, filas: list[dict], historia: dict, dry_run: bool) -> list[dict]:
    """Pone el CSV de acuerdo con el log y devuelve las filas que esperan su correo.

    Con `dry_run` los cambios quedan solo en memoria: una simulación no escribe.
    """
    cambio = False
    pendientes = []
    for fila in filas:
        correo = (fila.get("alumno_correo") or "").strip().lower()
        if not correo:
            continue
        h = historia.get(correo, {})
        en_csv = bool((fila.get("feedback_pendiente") or "").strip())
        if h.get("estado") == POR_MANDAR:
            if not en_csv:
                fila.update(_desde_correccion(h["correccion"]))
                cambio = True
                print(f"  → {fila['alumno_nombre']:30s}: su corrección estaba en el registro y no en "
                      f"feedback_{tarea}.csv; " + ("al mandar de verdad se copia." if dry_run else "se copió."))
            pendientes.append(fila)
        elif h.get("estado") == ENVIADA:
            if en_csv:
                fila["feedback_pendiente"] = ""
                cambio = True
                print(f"  ⊘ {fila['alumno_nombre']:30s}: según el registro su corrección ya salió; no se reenvía"
                      + ("." if dry_run else f" y deja de figurar como pendiente en feedback_{tarea}.csv."))
        elif en_csv:
            # Sin `correccion` en el log: una fila de antes (2026-2). Decide el CSV.
            pendientes.append(fila)
    if cambio and not dry_run:
        storage.escribir_csv(tarea, filas)
    return pendientes


def main(tarea: str, dry_run: bool = False, solo: set[str] | None = None,
         por: str | None = None) -> None:
    """`por`: quién revisó y pidió el envío; queda en el Detalle de cada `evaluacion`."""
    todas = storage.leer_csv(tarea)
    historia = _historia(tarea)
    filas = _al_dia_con_el_log(tarea, todas, historia, dry_run)
    if solo is not None:
        filas = [f for f in filas if f["alumno_correo"].strip().lower() in solo]
    if not filas:
        print(f"No hay correcciones de {tarea} esperando para salir.")
        return

    template = _cargar_template_feedback()
    respuestas = _respuestas(tarea)
    print(f"{len(filas)} corrección(es) de {tarea} por mandar.")
    print("--- DRY RUN (no se envía nada) ---\n" if dry_run else "--- ENVIANDO ---\n")

    for fila in avanzar(filas, "correos"):
        correo = fila["alumno_correo"].strip().lower()
        nombre = fila["alumno_nombre"]
        try:
            nota = validar_nota(fila["nota"].replace(",", "."))
        except (ValueError, AttributeError) as e:
            print(f"  ✗ {nombre:30s}: {e}. Corrígela en la revisión antes de mandar.")
            continue
        comentario = fila.get("comentario", "").strip()
        if not comentario:
            print(f"  ✗ {nombre:30s}: el comentario quedó vacío. No se manda.")
            continue

        if dry_run:
            asunto, _, cuerpo = armar_correo(template, fila, nota, comentario, respuestas.get(correo, ""))
            mostrar_correo(correo, asunto, cuerpo, nombre=nombre)
            continue

        # Contra qué se compara lo que sale: la propuesta del modelo, o en una
        # fila de antes, la nota y el comentario que registró corregir.
        h = historia.get(correo, {})
        origen = h.get("correccion") or h.get("anterior") or {}
        if h.get("correccion"):
            comentario_antes = _json(origen.get("EvaluacionIA")).get("comentario")
        else:
            comentario_antes = origen.get("EvaluacionIA") if origen else None
        nota_antes = ((origen.get("Nota") or "").strip()
                      or ((_datos.notas.estado(correo, _datos.TAREAS, tarea) or {}).get("Nota") or "").strip())
        detalle = _detalle(por, nota_antes, nota, comentario_antes, comentario)
        try:
            mandar_feedback(tarea, fila, nota, comentario, template,
                            respuesta=respuestas.get(correo, ""), modelo=origen.get("Modelo") or config.MODELO,
                            versiones_base=origen.get("Versiones") or "", detalle=detalle)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {nombre:30s}: no se pudo enviar ({e}). Sigue pendiente.")
            continue
        marca = f" ({detalle.split('; ', 1)[1]})" if "; " in detalle else ""
        print(f"  ✉ {nombre:30s}: nota {nota}{marca} → {correo}")


def _por_de_argv(argv: list[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--por" and i + 1 < len(argv):
            return argv[i + 1].strip() or None
        if a.startswith("--por="):
            return a[len("--por="):].strip() or None
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = config.TAREA_DEFAULT
    dry_run = False
    for a in args:
        if a.lower() == "--dry-run":
            dry_run = True
        elif a.upper().startswith("T") and a[1:].isdigit():
            tarea = a.upper()
    main(tarea, dry_run=dry_run, solo=_candidatos.solo_de_argv(), por=_por_de_argv(args))
