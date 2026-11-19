"""
El chequeo previo de las entregas y la asignación que se elige a mano.

Que lo elegido a mano pise al reparto por sorteo sin tocar al resto del grupo,
y que una sección sin su título se recorte igual. La pantalla del chequeo es la
de Tareas en el sitio (web/public/tareas.js); la de Streamlit, que se probaba
aquí, ya no existe.

No hay red ni API acá: el chequeo no llama al modelo, que es su razón de ser.
"""

import sys

sys.path.insert(0, ".")

from pruebas.comun import check, resultado  # noqa: E402
from modulos.tareas import asignacion  # noqa: E402
from modulos.tareas.generar import _asignar_preguntas  # noqa: E402
from modulos.tareas.limpieza_html import extraer_secciones  # noqa: E402


def main() -> int:
    # --- lo elegido a mano manda sobre el sorteo ---
    nombres = ["Ana Mora", "Bruno Soto"]
    automatica = _asignar_preguntas(nombres, "Mora.html")
    check("el reparto por sorteo es reproducible",
          automatica == _asignar_preguntas(nombres, "Mora.html"), automatica)

    elegido = {("Mora.html", "Ana Mora"): "P4"}
    final = asignacion.aplicar(automatica, elegido, "Mora.html")
    check("lo elegido a mano pisa al sorteo", final["Ana Mora"] == "P4", final)
    check("el resto del grupo conserva lo sorteado",
          final["Bruno Soto"] == automatica["Bruno Soto"], final)

    otro_grupo = asignacion.aplicar(automatica, elegido, "Otro.html")
    check("la elección no se filtra a otro grupo con el mismo nombre",
          otro_grupo == automatica, otro_grupo)

    check("una pregunta inválida en el archivo se ignora",
          asignacion.aplicar(automatica, {("Mora.html", "Ana Mora"): "P9"},
                             "Mora.html")["Ana Mora"] != "P9")

    # --- un encabezado que no se renderizó (T2 de 2026-2) ---
    html = ('<div id="desarrollo"><div id="pregunta-1"><h3>Pregunta 1</h3><p>uno</p>'
            '<p>fin de la uno. ### Pregunta 2</p><p>dos</p>'
            '<p>fin de la dos. ### Pregunta 3</p><p>tres</p>'
            '<p>fin de la tres. ### Pregunta 4</p><p>cuatro</p></div>'
            '<div id="resumen">resumen</div>')
    sec = extraer_secciones(html)
    check("el texto '### Pregunta N' corta la sección cuando falta el título",
          all(sec[k] for k in ("p1", "p2", "p3", "p4")) and "dos" not in sec["p1"]
          and "cuatro" in sec["p4"] and "resumen" not in sec["p4"], sec)

    return resultado()


if __name__ == "__main__":
    raise SystemExit(main())
