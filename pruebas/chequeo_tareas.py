"""
El chequeo previo de las entregas y la asignación que se elige a mano.

Dos cosas: que lo elegido a mano pise al reparto por sorteo sin tocar al resto
del grupo, y que la pantalla del chequeo ofrezca un selector por integrante
justo cuando el grupo no declaró roles.

No hay red ni API acá: el chequeo no llama al modelo, que es su razón de ser.
"""

import sys

sys.path.insert(0, ".")

from pruebas.comun import check, resultado  # noqa: E402
from modulos.tareas import asignacion  # noqa: E402
from modulos.tareas.generar import _asignar_preguntas  # noqa: E402
# "app" solo, sin importarlo como paquete: si hay otro paquete "app" instalado
# en el Python (pasa con proyectos en modo editable), le ganaría a esta carpeta.
sys.path.insert(0, "app")
from utils import runner  # noqa: E402


class _StFalso:
    """Un streamlit que anota lo que le piden dibujar en vez de dibujarlo."""

    def __init__(self):
        self.selectores = {}
        self.metricas = {}
        self.errores = []
        self.avisos = []

    # los contenedores devuelven el mismo objeto, así que todo cae en las listas
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def columns(self, pesos, **k): return [self for _ in range(
        pesos if isinstance(pesos, int) else len(pesos))]

    def expander(self, *a, **k): return self

    def selectbox(self, label, opciones, index=0, key=None, **k):
        self.selectores[key] = list(opciones)[index]
        return list(opciones)[index]

    def metric(self, label, valor, **k): self.metricas[label] = valor
    def error(self, texto, **k): self.errores.append(texto)
    def warning(self, texto, **k): self.avisos.append(texto)

    def button(self, *a, **k): return False
    def markdown(self, *a, **k): pass
    def caption(self, *a, **k): pass
    def info(self, *a, **k): pass
    def success(self, *a, **k): pass
    def divider(self, *a, **k): pass
    def subheader(self, *a, **k): pass


def _informe_de_prueba() -> dict:
    """Un chequeo con los tres casos que importan: normal, sin roles y saltado."""
    sin_roles = ["Ana Mora", "Bruno Soto"]
    return {
        "tarea": "TX",
        "carpeta": "entregas/TX",
        "total_roster": 4,
        "sin_entrega": ["Alguien Que No Entregó"],
        "grupos": [
            {
                "archivo": "Normal.html", "fuente": "Normal.html",
                "secciones": {1: 900, 2: 900, 3: 900, 4: 900},
                "origen_integrantes": "tabla de roles",
                "integrantes": [{"nombre": "Ana Pérez", "correo": "ana@x.cl", "candidatos": []}],
                "asignacion": {}, "a_mano": [], "bloqueo": [], "sin_roles": False,
            },
            {
                "archivo": "SinRoles.html", "fuente": "SinRoles.Rmd",
                "secciones": {1: 900, 2: 900, 3: 900, 4: 900},
                "origen_integrantes": "campo author del documento",
                "integrantes": [{"nombre": n, "correo": f"{n[0].lower()}@x.cl",
                                 "candidatos": []} for n in sin_roles],
                "asignacion": _asignar_preguntas(sin_roles, "SinRoles.html"),
                "a_mano": [], "bloqueo": [], "sin_roles": True,
            },
            {
                "archivo": "Vacia.html", "fuente": "Vacia.html",
                "secciones": {1: 0, 2: 0, 3: 0, 4: 0},
                "origen_integrantes": "tabla de roles",
                "integrantes": [],
                "asignacion": {}, "a_mano": [],
                "bloqueo": ["no se pudo recortar ninguna de las cuatro preguntas"],
                "sin_roles": False,
            },
        ],
    }


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

    # --- la pantalla del chequeo ---
    st = _StFalso()
    runner.pintar_chequeo(st, _informe_de_prueba(), "TX")

    check("el resumen cuenta las preguntas que se generarían",
          st.metricas.get("Preguntas que se generarían") == 3, st.metricas)
    check("el resumen cuenta los grupos que se saltarían",
          st.metricas.get("Grupos que se saltarían") == 1, st.metricas)

    claves = list(st.selectores)
    check("hay un selector por integrante del grupo sin roles",
          len(claves) == 2, claves)
    check("el grupo con roles no ofrece selector",
          not any("Normal.html" in c for c in claves), claves)
    check("el selector parte en lo que salió por sorteo",
          set(st.selectores.values()) <= {"P1", "P2", "P3", "P4"}, st.selectores)
    check("el grupo que se salta explica por qué", len(st.errores) == 1, st.errores)

    return resultado()


if __name__ == "__main__":
    raise SystemExit(main())
