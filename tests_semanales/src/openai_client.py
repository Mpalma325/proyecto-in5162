from openai import OpenAI

from . import config


def _client() -> OpenAI:
    return OpenAI(api_key=config.cargar_api_key())


def evaluar_respuesta(preguntas: list[str], pautas: list[str],
                      respuesta_alumno: str) -> str:
    system_prompt_template = (config.PROMPTS / "evaluar_respuesta.md").read_text(encoding="utf-8")

    # Inyectar preguntas y pautas en el system prompt
    bloque_preguntas = "\n".join(f"P{i+1}. {p}" for i, p in enumerate(preguntas))
    bloque_pautas = "\n".join(f"P{i+1}. {p}" for i, p in enumerate(pautas))

    system_prompt = (
        system_prompt_template
        .replace("{{PREGUNTAS}}", bloque_preguntas)
        .replace("{{PAUTAS}}", bloque_pautas)
    )

    user_msg = (
        "[RESPUESTA ESTUDIANTE]\n"
        "<<<INICIO_RESPUESTA>>>\n"
        f"{respuesta_alumno}\n"
        "<<<FIN_RESPUESTA>>>"
    )

    resp = _client().chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=config.TEMPERATURA,
        max_completion_tokens=config.MAX_TOKENS,
    )
    return resp.choices[0].message.content or ""


def generar_resumen(preguntas: list[str], pautas: list[str],
                    evaluaciones_html: list[str]) -> str:
    system_prompt = (config.PROMPTS / "resumen_respuestas.md").read_text(encoding="utf-8")

    bloque_preguntas = "\n".join(f"P{i+1}. {p}" for i, p in enumerate(preguntas))
    bloque_pautas = "\n".join(f"P{i+1}. {p}" for i, p in enumerate(pautas))
    bloque_evaluaciones = "\n\n---\n\n".join(evaluaciones_html)

    user_msg = (
        f"=== PREGUNTAS DE LA SEMANA ===\n{bloque_preguntas}\n\n"
        f"=== PAUTAS ===\n{bloque_pautas}\n\n"
        f"=== EVALUACIONES DE TODOS LOS ESTUDIANTES ===\n{bloque_evaluaciones}"
    )

    resp = _client().chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_completion_tokens=2000,
    )
    return resp.choices[0].message.content or ""
