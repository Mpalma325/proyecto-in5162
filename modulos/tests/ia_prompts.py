"""
Llamadas al modelo para Tests Semanales.

La conexión con OpenAI vive en modulos/ia; acá quedan solo los prompts y el
armado de los mensajes, que es lo propio de este flujo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modulos import ia  # noqa: E402

from . import config  # noqa: E402

ia.configurar(config.cargar_api_key, config.MODELO, config.TEMPERATURA, config.MAX_TOKENS)


def _bloque(items: list[str]) -> str:
    return "\n".join(f"P{i+1}. {p}" for i, p in enumerate(items))


def evaluar_respuesta(preguntas: list[str], pautas: list[str],
                      respuesta_alumno: str) -> str:
    plantilla = (config.PROMPTS / "evaluar_respuesta.md").read_text(encoding="utf-8")
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

    return ia.completar(system_prompt, user_msg).texto


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
