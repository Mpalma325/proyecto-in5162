"""
Paso 5 del flujo: mandar las correcciones que se guardaron para revisarlas.

`corregir --no-enviar` deja en feedback_<TAREA>.csv la nota, el comentario, la
marca de IA y la justificación del modelo, con feedback_pendiente = "sí". En la
página se leen y se pueden editar la nota y el comentario. Esto manda el correo
con lo que quedó escrito.

Si alguien cambió la nota o el comentario, la nota nueva se registra en datos y
el log anota un 'ajuste' con lo que había antes. Cada correo que sale queda como
evento 'feedback'.

Uso:
    python -m modulos.tareas.feedback T2
    python -m modulos.tareas.feedback T2 --dry-run          # muestra los correos, no los manda
    python -m modulos.tareas.feedback T2 --solo a@x.cl,b@x.cl
"""

import sys

from modulos import datos as _datos
from modulos.datos import candidatos as _candidatos
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo
from modulos.progreso import avanzar

from . import config, storage
from .corregir import _cargar_template_feedback, _construir_cuerpo_feedback, encabezado_feedback
from .escala import validar_nota


def _ultima_evaluacion(tarea: str) -> dict:
    """Lo que dejó corregir en el log, por correo: la nota y el comentario del modelo."""
    ultima = {}
    for e in _datos.log.leer(flujo=_datos.TAREAS, item=tarea, evento="evaluacion"):
        ultima[e["Correo"]] = e
    return ultima


def _respuestas(tarea: str) -> dict:
    return {e["Correo"]: e["Respuesta"]
            for e in _datos.log.leer(flujo=_datos.TAREAS, item=tarea, evento="respuesta")
            if e.get("Respuesta", "").strip()}


def main(tarea: str, dry_run: bool = False, solo: set[str] | None = None) -> None:
    filas = [f for f in storage.leer_csv(tarea)
             if f.get("feedback_pendiente", "").strip() and f.get("alumno_correo", "").strip()]
    if solo is not None:
        filas = [f for f in filas if f["alumno_correo"].strip().lower() in solo]
    if not filas:
        print(f"No hay correcciones de {tarea} esperando para salir.")
        return

    template = _cargar_template_feedback()
    respuestas = _respuestas(tarea)
    del_modelo = _ultima_evaluacion(tarea)
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

        cuerpo = _construir_cuerpo_feedback(template, {
            **fila, "respuesta": respuestas.get(correo, ""), "nota": nota, "comentario": comentario})
        asunto, en_hilo = encabezado_feedback(fila)
        if dry_run:
            mostrar_correo(correo, asunto, cuerpo, nombre=nombre)
            continue

        try:
            enviar_correo(correo, asunto, cuerpo, in_reply_to=en_hilo)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {nombre:30s}: no se pudo enviar ({e}). Sigue pendiente.")
            continue

        modelo = del_modelo.get(correo, {})
        editada = False
        try:
            nota_antes = (_datos.notas.estado(correo, _datos.TAREAS, tarea) or {}).get("Nota", "").strip()
            editada = (str(nota) != nota_antes
                       or comentario != (modelo.get("EvaluacionIA") or "").strip())
            if editada:
                _datos.notas.registrar_nota(correo, _datos.TAREAS, tarea, str(nota))
                _datos.log.registrar("ajuste", _datos.TAREAS, tarea, correo, Nota=str(nota),
                                     EvaluacionIA=comentario,
                                     Detalle=f"editada en la revisión antes de mandar "
                                             f"(el modelo había puesto {nota_antes or 'sin nota'})")
            _datos.log.registrar("feedback", _datos.TAREAS, tarea, correo, Nota=str(nota),
                                 EvaluacionIA=comentario)
        except Exception as _e:  # noqa: BLE001
            print(f"     ⚠ no pude registrar en el log: {_e}")
        storage.actualizar_fila(tarea, fila["grupo_archivo"], fila["alumno_nombre"],
                                {"feedback_pendiente": "", "nota": str(nota), "comentario": comentario})
        marca = " (editada)" if editada else ""
        print(f"  ✉ {nombre:30s}: nota {nota}{marca} → {correo}")


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = config.TAREA_DEFAULT
    dry_run = False
    for a in args:
        if a.lower() == "--dry-run":
            dry_run = True
        elif a.upper().startswith("T") and a[1:].isdigit():
            tarea = a.upper()
    main(tarea, dry_run=dry_run, solo=_candidatos.solo_de_argv())
