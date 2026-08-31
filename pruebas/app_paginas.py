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


class _Estado(dict):
    """streamlit permite session_state["x"] y session_state.x indistintamente."""

    def __getattr__(self, nombre):
        try:
            return self[nombre]
        except KeyError as e:
            raise AttributeError(nombre) from e

    def __setattr__(self, nombre, valor):
        self[nombre] = valor


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
    st.file_uploader.return_value = None
    st.session_state = _Estado()
    st.columns.side_effect = lambda n, **k: [
        MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
    st.tabs.side_effect = lambda nombres: [MagicMock() for _ in nombres]
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

for ruta in paginas:
    modulo = types.ModuleType("pagina")
    modulo.__file__ = ruta
    guardas = _sin_escrituras()
    try:
        for g in guardas:
            g.__enter__()
        with patch.dict(sys.modules, {"streamlit": falso_streamlit()}):
            exec(compile(pathlib.Path(ruta).read_text(encoding="utf-8"), ruta, "exec"),
                 modulo.__dict__)
        check(ruta, True)
    except Exception as e:
        check(ruta, False, f"{type(e).__name__}: {e}")
    finally:
        for g in reversed(guardas):
            g.__exit__(None, None, None)

_activo_ahora = _ANTES.read_text(encoding="utf-8") if _ANTES.exists() else None
check("las páginas no cambiaron el semestre activo",
      _activo_ahora == _activo_previo, f"{_activo_previo!r} -> {_activo_ahora!r}")

sys.exit(resultado())
