"""
Llamada a la API de OpenAI para generar preguntas de comprensión.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from modulos import ia

from . import config, contexto

ia.configurar(config.cargar_api_key, config.MODELO, config.TEMPERATURA, config.MAX_TOKENS)


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


def _bloque_rehacer(asignacion: dict) -> str:
    """Instrucciones para rehacer la pregunta de algunos integrantes, sobre la parte que ya tenían."""
    lineas = "\n".join(f"- {nombre}: {pregunta}" for nombre, pregunta in asignacion.items())
    return (
        "=== REHACER UNA PREGUNTA ===\n"
        "Formula una pregunta nueva solo para estos integrantes, sobre la pregunta de la "
        "tarea indicada, con los mismos criterios de siempre. No marques a nadie con "
        "\"pregunta\": null.\n\n"
        "Integrantes y pregunta de la tarea:\n" + lineas
    )


def generar_preguntas(secciones: dict, roles_html: str,
                      asignacion: dict | None = None, nota: str = "",
                      rehacer: bool = False) -> dict:
    """
    Llama a la API de OpenAI con el system prompt + los insumos del grupo.
    Devuelve el dict parseado con las preguntas por integrante.

    `asignacion` es {nombre: "P1".."P4"} y reemplaza a la tabla de roles cuando
    el grupo no la llenó.
    """
    system_prompt = (config.PROMPTS / "generar_preguntas.md").read_text(encoding="utf-8")

    partes_user = []

    contexto_curso = contexto.cargar()
    if contexto_curso:
        partes_user.append(
            "=== CONTEXTO DEL CURSO (material de clases) ===\n"
            "(Úsalo solo para entender la entrega: el estilo, los métodos y las librerías "
            "esperadas. Si el grupo usa algo muy fuera de esto, puede ser señal de copia "
            "externa. Nunca saques de aquí la pregunta: todo nombre de variable, función u "
            "objeto que cites tiene que aparecer en el código del grupo.)\n\n"
            + contexto_curso
        )

    if asignacion and rehacer:
        partes_user.append(_bloque_rehacer(asignacion))
    elif asignacion:
        partes_user.append(_bloque_sin_roles(asignacion))
    else:
        partes_user.append(f"=== TABLA DE ROLES (HTML) ===\n{roles_html}")
    partes_user.append(f"=== PREGUNTA 1 ===\n{secciones['p1']}")
    partes_user.append(f"=== PREGUNTA 2 ===\n{secciones['p2']}")
    partes_user.append(f"=== PREGUNTA 3 ===\n{secciones['p3']}")
    partes_user.append(f"=== PREGUNTA 4 ===\n{secciones['p4']}")
    if nota:
        partes_user.append(f"=== IMPORTANTE ===\n{nota}")

    user_msg = "\n\n".join(partes_user)

    resp = ia.completar(system_prompt, user_msg, json_mode=True)

    datos = resp.datos
    datos["_meta"] = resp.meta
    return datos
