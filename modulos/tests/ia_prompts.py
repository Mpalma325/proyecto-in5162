"""
Llamadas al modelo para Tests Semanales.

La conexión con OpenAI vive en modulos/ia; acá quedan solo los prompts y el
armado de los mensajes, que es lo propio de este flujo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modulos import ia  # noqa: E402
from modulos.ia import versiones  # noqa: E402

from . import config  # noqa: E402

ia.configurar(config.cargar_api_key, config.MODELO, config.TEMPERATURA, config.MAX_TOKENS)


def _bloque(items: list[str]) -> str:
    return "\n".join(f"P{i+1}. {p}" for i, p in enumerate(items))


def evaluar_respuesta(preguntas: list[str], pautas: list[str],
                      respuesta_alumno: str,
                      plantilla: str | None = None) -> ia.Texto:
    """Corrige una respuesta con el prompt de evaluación del semestre.

    `plantilla` deja pasar otro prompt en vez del que está en disco, sin tocar
    el archivo del semestre. Lo usa `experimento.py` para reevaluar respuestas
    viejas con un prompt candidato; el flujo del curso nunca la pasa.
    """
    if plantilla is None:
        ruta = config.PROMPTS / "evaluar_respuesta.md"
        plantilla = ruta.read_text(encoding="utf-8")
        version = versiones.anotar(ruta, plantilla)
    else:
        version = f"candidato@{versiones.huella(plantilla)}"
    system_prompt = (
        plantilla
        .replace("{{PREGUNTAS}}", _bloque(preguntas))
        .replace("{{PAUTAS}}", _bloque(pautas))
    )

    user_msg = (
        "[RESPUESTA ESTUDIANTE]\n"
        "<<<INICIO_RESPUESTA>>>\n"
        f"{respuesta_alumno}\n"
        "<<<FIN_RESPUESTA>>>"
    )

    resp = ia.completar(system_prompt, user_msg)
    resp.meta["prompt"] = version
    return resp.con_meta()


def responder_duda(preguntas: list[str], pautas: list[str], respuesta_alumno: str,
                   evaluacion_html: str, consulta: str, nombre: str,
                   historial: list[dict] | None = None) -> ia.Texto:
    """Contesta la duda de un alumno sobre su corrección. No toca la nota.

    Recibe todo el contexto —la pregunta, la pauta, lo que respondió y lo que se
    le corrigió— porque sin eso el modelo no puede explicar por qué le faltó
    puntaje. El `historial` son las vueltas anteriores, si las hubo.
    """
    ruta = config.PROMPTS / "tutoria.md"
    plantilla = ruta.read_text(encoding="utf-8")
    version = versiones.anotar(ruta, plantilla)
    system_prompt = plantilla.replace("{NOMBRE}", (nombre or "").split()[0] if nombre else "")

    partes = [
        f"=== PREGUNTA DE LA SEMANA ===\n{_bloque(preguntas)}",
        f"=== PAUTA ESPERADA ===\n{_bloque(pautas)}",
        f"=== LO QUE RESPONDIÓ EL ESTUDIANTE ===\n{respuesta_alumno}",
        f"=== LA CORRECCIÓN QUE SE LE ENVIÓ ===\n{evaluacion_html}",
    ]
    for turno in historial or []:
        quien = "ESTUDIANTE" if turno.get("Evento") == "repregunta" else "AYUDANTE"
        texto = turno.get("Respuesta") or turno.get("EvaluacionIA") or ""
        if texto.strip():
            partes.append(f"=== {quien} (ronda {turno.get('Ronda', '?')}) ===\n{texto}")

    partes.append(
        "=== CONSULTA ACTUAL DEL ESTUDIANTE ===\n"
        "<<<INICIO_MENSAJE>>>\n"
        f"{consulta}\n"
        "<<<FIN_MENSAJE>>>"
    )
    resp = ia.completar(system_prompt, "\n\n".join(partes))
    resp.meta["prompt"] = version
    return resp.con_meta()


def generar_resumen(preguntas: list[str], pautas: list[str],
                    evaluaciones_html: list[str]) -> str:
    system_prompt = (config.PROMPTS / "resumen_respuestas.md").read_text(encoding="utf-8")

    user_msg = (
        f"=== PREGUNTAS DE LA SEMANA ===\n{_bloque(preguntas)}\n\n"
        f"=== PAUTAS ===\n{_bloque(pautas)}\n\n"
        f"=== EVALUACIONES DE TODOS LOS ESTUDIANTES ===\n"
        + "\n\n---\n\n".join(evaluaciones_html)
    )

    # el resumen usa valores propios, distintos a los de la evaluación
    return ia.completar(system_prompt, user_msg, temperatura=0.3, max_tokens=2000).texto
