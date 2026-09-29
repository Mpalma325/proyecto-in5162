"""
Llamada a la API de OpenAI para generar preguntas de comprensión.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modulos import ia

from . import config
from .limpieza_html import extraer_codigo_r_de_clase

ia.configurar(config.cargar_api_key, config.MODELO, config.TEMPERATURA, config.MAX_TOKENS)


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


def _bloque_sin_roles(asignacion: dict) -> str:
    """
    Instrucciones para el grupo que no declaró quién hizo qué.

    Sin tabla de roles no hay cómo saber qué le tocó a cada uno, así que se le
    asigna a cada integrante una de las cuatro preguntas y se pregunta sobre esa.
    El reparto lo decide el flujo, no el modelo, para que sea reproducible.
    """
    lineas = "\n".join(f"- {nombre}: {pregunta}"
                       for nombre, pregunta in asignacion.items())
    return (
        "=== ESTE GRUPO NO DECLARÓ ROLES ===\n"
        "No hay tabla de roles utilizable, así que no se sabe qué parte hizo cada "
        "integrante. En vez de la tabla, se te indica abajo sobre qué pregunta "
        "interrogar a cada uno. Para cada integrante, toma el fragmento de código "
        "técnicamente más interesante de la pregunta que le fue asignada y formula "
        "ahí su pregunta de comprensión, con los mismos criterios de siempre.\n"
        "Como no hay información de roles, no marques a nadie con \"pregunta\": null "
        "por no haber contribuido: se asume que todos participaron del trabajo.\n\n"
        "Integrantes y pregunta asignada:\n" + lineas
    )


def generar_preguntas(secciones: dict, roles_html: str,
                      asignacion: dict | None = None) -> dict:
    """
    Llama a la API de OpenAI con el system prompt + los insumos del grupo.
    Devuelve el dict parseado con las preguntas por integrante.

    `asignacion` es {nombre: "P1".."P4"} y reemplaza a la tabla de roles cuando
    el grupo no la llenó.
    """
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

    if asignacion:
        partes_user.append(_bloque_sin_roles(asignacion))
    else:
        partes_user.append(f"=== TABLA DE ROLES (HTML) ===\n{roles_html}")
    partes_user.append(f"=== PREGUNTA 1 ===\n{secciones['p1']}")
    partes_user.append(f"=== PREGUNTA 2 ===\n{secciones['p2']}")
    partes_user.append(f"=== PREGUNTA 3 ===\n{secciones['p3']}")
    partes_user.append(f"=== PREGUNTA 4 ===\n{secciones['p4']}")

    user_msg = "\n\n".join(partes_user)

    resp = ia.completar(system_prompt, user_msg, json_mode=True)

    datos = resp.datos
    datos["_meta"] = resp.meta
    return datos
