"""
Llamada a la API de OpenAI para generar preguntas de comprensión.
"""

import json
from pathlib import Path
from openai import OpenAI

from . import config
from .limpieza_html import extraer_codigo_r_de_clase


def _cargar_contexto_clases() -> str:
    """
    Si INCLUIR_CONTEXTO_CLASES está activo, carga los .R del cache.
    Si no hay cache, los genera a partir de los HTMLs de data/clases/.
    """
    if not config.INCLUIR_CONTEXTO_CLASES:
        return ""

    config.CACHE.mkdir(parents=True, exist_ok=True)
    partes = []
    for html_clase in sorted(config.CLASES.glob("*.html")):
        r_cache = config.CACHE / (html_clase.stem + ".R")
        if not r_cache.exists():
            codigo = extraer_codigo_r_de_clase(html_clase)
            r_cache.write_text(codigo, encoding="utf-8")
        partes.append(f"# === {html_clase.stem} ===\n{r_cache.read_text(encoding='utf-8')}")

    if not partes:
        return ""
    return "\n\n".join(partes)


def generar_preguntas(secciones: dict, roles_html: str) -> dict:
    """
    Llama a la API de OpenAI con el system prompt + los insumos del grupo.
    Devuelve el dict parseado con las preguntas por integrante.
    """
    client = OpenAI(api_key=config.cargar_api_key())

    system_prompt = (config.PROMPTS / "generar_preguntas.md").read_text(encoding="utf-8")

    partes_user = []

    contexto_clases = _cargar_contexto_clases()
    if contexto_clases:
        partes_user.append(
            "=== CONTEXTO: CÓDIGO R DE CLASES DEL PROFESOR ===\n"
            "(Úsalo solo como referencia del estilo y librerías esperadas. "
            "Si el grupo usa algo muy fuera de esto, puede ser señal de copia externa.)\n\n"
            + contexto_clases
        )

    partes_user.append(f"=== TABLA DE ROLES (HTML) ===\n{roles_html}")
    partes_user.append(f"=== PREGUNTA 1 ===\n{secciones['p1']}")
    partes_user.append(f"=== PREGUNTA 2 ===\n{secciones['p2']}")
    partes_user.append(f"=== PREGUNTA 3 ===\n{secciones['p3']}")
    partes_user.append(f"=== PREGUNTA 4 ===\n{secciones['p4']}")

    user_msg = "\n\n".join(partes_user)

    resp = client.chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=config.TEMPERATURA,
        max_completion_tokens=config.MAX_TOKENS,
        response_format={"type": "json_object"},
    )

    contenido = resp.choices[0].message.content
    uso = resp.usage

    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"OpenAI devolvió algo que no es JSON válido:\n{contenido[:500]}..."
        ) from e

    datos["_meta"] = {
        "modelo": config.MODELO,
        "prompt_tokens": uso.prompt_tokens,
        "completion_tokens": uso.completion_tokens,
        "total_tokens": uso.total_tokens,
    }
    return datos
