"""
Ejecuta cada página de la app con Streamlit simulado.

Compilar no alcanza: los errores de esta clase —una ruta que ya no existe, una
clave de diccionario renombrada— solo aparecen al ejecutar el código. Acá los
widgets devuelven valores por defecto y los botones siempre dicen que nadie los
apretó, así que nada sale a la red ni toca datos.
"""

import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")
sys.path.insert(0, "app")
sys.path.insert(0, "pruebas")
from comun import check, resultado


class _Detenida(Exception):
    """Lo que hace st.stop(): corta la página sin que sea un error.

    El streamlit real levanta su propia excepción para esto. Sin imitarlo, una
    página que se detiene a propósito seguiría ejecutando el resto del archivo
    y la prueba mediría algo que en pantalla nunca pasa.
    """


class _Estado(dict):
    """streamlit permite session_state["x"] y session_state.x indistintamente."""

    def __getattr__(self, nombre):
        try:
            return self[nombre]
        except KeyError as e:
            raise AttributeError(nombre) from e

    def __setattr__(self, nombre, valor):
        self[nombre] = valor


class _Pagina:
    """Lo que devuelve st.Page: recuerda la función para poder ejecutarla."""

    def __init__(self, destino, **k):
        self.destino = destino

    def correr(self):
        if callable(self.destino):
            self.destino()


class _Navegacion:
    """st.navigation(...).run() ejecuta de verdad las páginas que son función.

    Sin esto la prueba solo comprobaba que el archivo importara: el cuerpo del
    dashboard vive dentro de una función registrada con st.Page, así que nunca
    llegaba a correr y cualquier error ahí pasaba inadvertido.
    """

    def __init__(self, paginas):
        self.paginas = paginas

    def run(self):
        for p in self.paginas:
            if isinstance(p, _Pagina):
                p.correr()


def falso_streamlit():
    st = MagicMock()
    st.button.return_value = False
    st.form_submit_button.return_value = False
    st.checkbox.return_value = False
    st.text_input.return_value = ""
    st.text_area.return_value = ""
    st.number_input.return_value = 1
    def _selectbox(label, opciones, *a, index=0, **k):
        # Respetar index= no es un detalle: la página de configuración compara la
        # selección contra el semestre activo y, si difieren, lo cambia.
        opciones = list(opciones)
        return opciones[index or 0] if opciones else None

    st.selectbox.side_effect = _selectbox
    # multiselect devuelve su default, como el de verdad cuando nadie lo toca
    st.multiselect.side_effect = lambda label, opciones, *a, default=None, **k: (
        list(default) if default is not None else list(opciones))
    st.file_uploader.return_value = None
    st.stop.side_effect = _Detenida
    st.Page.side_effect = _Pagina
    st.navigation.side_effect = _Navegacion
    st.session_state = _Estado()
    # Las columnas y las pestañas devuelven el propio st. En Streamlit real
    # `col.metric(...)` es equivalente a `st.metric(...)` dentro de esa columna;
    # si acá se devolvieran MagicMocks pelados, los widgets escritos como
    # `col.multiselect(...)` no pasarían por la lógica de arriba y devolverían
    # basura, dejando sin ejercitar la mitad del dashboard.
    st.columns.side_effect = lambda n, **k: [
        st for _ in range(n if isinstance(n, int) else len(n))]
    st.tabs.side_effect = lambda nombres: [st for _ in nombres]
    for ctx in ("spinner", "expander", "container", "form", "status", "sidebar", "empty"):
        getattr(st, ctx).return_value.__enter__ = lambda *a: MagicMock()
        getattr(st, ctx).return_value.__exit__ = lambda *a: False
    st.cache_data.side_effect = lambda *a, **k: (lambda f: f)
    return st


def _sin_escrituras():
    """Neutraliza todo lo que modificaría datos reales.

    El selectbox arreglado ya evita el caso conocido, pero una página futura
    puede escribir por otro camino. Ejecutar código de la app no puede ser capaz
    de tocar el semestre activo ni de mandar un correo.
    """
    from modulos import semestre as _sem
    from utils import runner as _runner

    return [
        patch.object(_sem.gestion, "activar", lambda *a, **k: None),
        patch.object(_runner, "set_semestre_activo", lambda *a, **k: None),
        patch("smtplib.SMTP", MagicMock()),
        patch("imaplib.IMAP4_SSL", MagicMock()),
    ]


_ANTES = pathlib.Path("semestres/activo.txt")
_activo_previo = _ANTES.read_text(encoding="utf-8") if _ANTES.exists() else None

paginas = ["app/main.py"] + sorted(str(p) for p in pathlib.Path("app/pages").glob("*.py"))

falsos = {}

for ruta in paginas:
    modulo = types.ModuleType("pagina")
    modulo.__file__ = ruta
    guardas = _sin_escrituras()
    st = falso_streamlit()
    falsos[ruta] = st
    try:
        for g in guardas:
            g.__enter__()
        with patch.dict(sys.modules, {"streamlit": st}):
            exec(compile(pathlib.Path(ruta).read_text(encoding="utf-8"), ruta, "exec"),
                 modulo.__dict__)
        check(ruta, True)
    except _Detenida:
        check(ruta, True)
    except Exception as e:
        check(ruta, False, f"{type(e).__name__}: {e}")
    finally:
        for g in reversed(guardas):
            g.__exit__(None, None, None)

# La reportería tiene que haber dibujado algo. Comprobar solo que el archivo
# corra no sirve: si un filtro deja la tabla vacía o una métrica se cae, la
# página termina sin error y en pantalla no queda nada.
st = falsos.get("app/main.py")
if st is not None:
    from modulos import semestre as _sem

    errores = [str(a) for a in st.error.call_args_list]
    check("la reportería no reportó errores", not errores, errores[:2])
    if _sem.activo():
        check("la reportería dibujó KPIs", st.metric.call_count >= 5, st.metric.call_count)
        check("la reportería dibujó gráficos", st.altair_chart.call_count >= 3,
              st.altair_chart.call_count)
        check("la reportería armó sus pestañas", st.tabs.call_count >= 1, st.tabs.call_count)
    else:
        # Recién clonado no hay semestre elegido y no hay nada que dibujar. Lo
        # que sí tiene que pasar es que avise, en vez de quedar en blanco.
        check("sin semestre activo, la reportería lo avisa",
              st.warning.call_count >= 1, st.warning.call_count)

# Y tienen que abrir también cuando todavía no hay semestre elegido, que es
# como se ve el sistema recién clonado: el semestre se elige desde la app, así
# que una página que revienta antes de eso deja sin salida a quien recién llega.
def _sin_semestre_activo():
    from modulos.semestre import gestion as _gestion
    return [
        patch.object(_gestion, "ACTIVO_FILE", pathlib.Path("semestres/_no_existe.txt")),
        patch.dict("os.environ", {"IN5162_SEMESTRE": ""}),
    ]


for ruta in paginas:
    modulo = types.ModuleType("pagina")
    modulo.__file__ = ruta
    guardas = _sin_escrituras() + _sin_semestre_activo()
    st = falso_streamlit()
    try:
        for g in guardas:
            g.__enter__()
        with patch.dict(sys.modules, {"streamlit": st}):
            exec(compile(pathlib.Path(ruta).read_text(encoding="utf-8"), ruta, "exec"),
                 modulo.__dict__)
        check(f"{ruta} abre sin semestre activo", True)
    except _Detenida:
        check(f"{ruta} abre sin semestre activo", True)
    except Exception as e:
        check(f"{ruta} abre sin semestre activo", False, f"{type(e).__name__}: {e}")
    finally:
        for g in reversed(guardas):
            g.__exit__(None, None, None)

_activo_ahora = _ANTES.read_text(encoding="utf-8") if _ANTES.exists() else None
check("las páginas no cambiaron el semestre activo",
      _activo_ahora == _activo_previo, f"{_activo_previo!r} -> {_activo_ahora!r}")

sys.exit(resultado())
