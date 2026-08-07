import html as _html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

APP_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = APP_DIR.parent
TESTS_DIR = PROJECT_ROOT / "tests_semanales"
TAREAS_DIR = PROJECT_ROOT / "tareas"

SEMESTRES_DIR = PROJECT_ROOT / "semestres"
_TEMPLATE_DIR = SEMESTRES_DIR / "_template"
ACTIVO_FILE = SEMESTRES_DIR / "activo.txt"
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


# mantener sincronizado con: tests_semanales/src/config.py, tareas/src/config.py
def semestre_activo() -> str | None:
    if not ACTIVO_FILE.exists():
        return None
    valor = ACTIVO_FILE.read_text(encoding="utf-8").strip()
    return valor or None


def listar_semestres() -> list[str]:
    if not SEMESTRES_DIR.exists():
        return []
    return sorted(
        p.name for p in SEMESTRES_DIR.iterdir()
        if p.is_dir() and p.name != "_template"
    )


def set_semestre_activo(semestre_id: str) -> None:
    if not (SEMESTRES_DIR / semestre_id).is_dir():
        raise ValueError(f"El semestre '{semestre_id}' no existe.")
    ACTIVO_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVO_FILE.write_text(semestre_id, encoding="utf-8")


def crear_semestre(semestre_id: str) -> None:
    semestre_id = semestre_id.strip()
    if not semestre_id or not _ID_VALIDO.match(semestre_id):
        raise ValueError(
            "El identificador del semestre solo puede contener letras, "
            "números, puntos, guiones y guiones bajos."
        )
    destino = SEMESTRES_DIR / semestre_id
    if destino.exists():
        raise ValueError(f"El semestre '{semestre_id}' ya existe.")
    if not _TEMPLATE_DIR.exists():
        raise RuntimeError(f"No encontré la plantilla en {_TEMPLATE_DIR}.")
    shutil.copytree(_TEMPLATE_DIR, destino)


def _semestre_dir(semestre: str | None) -> Path:
    s = semestre or semestre_activo()
    if not s:
        raise RuntimeError("No hay un semestre activo. Créalo en Datos y Configuración.")
    return SEMESTRES_DIR / s


def tests_data_dir(semestre: str | None = None) -> Path:
    return _semestre_dir(semestre) / "tests_semanales" / "data"


def tests_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre_dir(semestre) / "tests_semanales" / "prompts"


def tareas_data_dir(semestre: str | None = None) -> Path:
    return _semestre_dir(semestre) / "tareas" / "data"


def tareas_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre_dir(semestre) / "tareas" / "prompts"


def tareas_entregas_dir(semestre: str | None = None, tarea: str | None = None) -> Path:
    base = tareas_data_dir(semestre) / "entregas"
    return base / tarea if tarea else base


def tareas_clases_dir(semestre: str | None = None) -> Path:
    return tareas_data_dir(semestre) / "clases"


def tareas_salidas_dir(semestre: str | None = None) -> Path:
    return tareas_data_dir(semestre) / "salidas"


def tareas_conocidas(semestre: str | None = None) -> list[str]:
    """Nombres de tarea (T1, T2, ...) con feedback ya generado o con entregas subidas."""
    conocidas: set[str] = set()

    salidas_dir = tareas_salidas_dir(semestre)
    if salidas_dir.exists():
        conocidas |= {
            p.stem.replace("feedback_", "").upper()
            for p in salidas_dir.glob("feedback_*.csv")
        }

    entregas_base = tareas_entregas_dir(semestre)
    if entregas_base.exists():
        conocidas |= {p.name.upper() for p in entregas_base.iterdir() if p.is_dir()}

    return sorted(conocidas)


def tarea_selector(key: str, semestre: str | None = None) -> str:
    """Selector de tarea (T1, T2, ...) compartido entre Entregas y el flujo de Tareas."""
    import streamlit as st

    opciones = tareas_conocidas(semestre)
    if not opciones:
        return st.text_input("Tarea (ej. T1)", value="T1", key=key + "_text")

    seleccion = st.selectbox("Tarea", opciones + ["Nueva..."], key=key + "_sel")
    if seleccion == "Nueva...":
        return st.text_input("Nombre de tarea (ej. T2)", value="T2", key=key + "_new")
    return seleccion


def run_command(
    cmd: list[str],
    cwd: Path,
    output_callback: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    lines: list[str] = []
    for line in process.stdout:
        lines.append(line)
        if output_callback:
            output_callback("".join(lines))

    process.wait()
    return process.returncode, "".join(lines)


def python() -> str:
    return sys.executable


def _miembro_valido(member: str) -> bool:
    return not (".." in member or member.startswith("/") or member.startswith("\\"))


def _es_basura_mac(member: str) -> bool:
    """Archivos de metadata que macOS agrega solo al comprimir (AppleDouble, __MACOSX/)."""
    partes = Path(member).parts
    return "__MACOSX" in partes or Path(member).name.startswith("._")


def _guardar_html(destino: Path, safe_name: str, contenido: bytes,
                   agregados: list[str], omitidos: list[str]) -> None:
    if not safe_name:
        return
    destino_path = destino / safe_name
    if destino_path.exists():
        omitidos.append(safe_name)
        return
    destino_path.write_bytes(contenido)
    agregados.append(safe_name)


def _extraer_zip(zf, destino: Path, agregados: list[str], omitidos: list[str],
                  prefijo: str | None = None, profundidad: int = 0) -> None:
    """Extrae *.html de un zip, entrando recursivamente a zips anidados
    (ej. un zip por grupo dentro del zip general de la tarea).
    """
    if profundidad > 3:
        return

    nombres = [m for m in zf.namelist() if not _es_basura_mac(m)]
    htmls = [m for m in nombres if m.lower().endswith(".html")]
    zips_anidados = [m for m in nombres if m.lower().endswith(".zip")]
    reconocidos = set(htmls) | set(zips_anidados)
    no_reconocidos = [
        m for m in nombres
        if m not in reconocidos and not m.endswith("/") and Path(m).name
    ]
    multiple = len(htmls) > 1

    for member in htmls:
        if not _miembro_valido(member):
            omitidos.append(member)
            continue
        base = Path(member).name
        if prefijo and not multiple:
            # un solo HTML en el zip anidado: usar el nombre del zip (ej. Grupo1.zip -> Grupo1.html)
            safe_name = f"{prefijo}.html"
        elif prefijo:
            safe_name = f"{prefijo}__{base}"
        else:
            safe_name = base
        _guardar_html(destino, safe_name, zf.read(member), agregados, omitidos)

    for member in zips_anidados:
        if not _miembro_valido(member):
            omitidos.append(member)
            continue
        import zipfile
        from io import BytesIO
        nombre_zip = Path(member).with_suffix("").as_posix().replace("/", "_")
        nuevo_prefijo = f"{prefijo}__{nombre_zip}" if prefijo else nombre_zip
        try:
            with zipfile.ZipFile(BytesIO(zf.read(member))) as nested:
                _extraer_zip(nested, destino, agregados, omitidos, nuevo_prefijo, profundidad + 1)
        except zipfile.BadZipFile:
            omitidos.append(member)

    for member in no_reconocidos:
        nombre_mostrado = f"{prefijo}/{member}" if prefijo else member
        omitidos.append(f"{nombre_mostrado} (formato no soportado — no es .html ni .zip)")


def extraer_entregas(archivos: list, destino: Path) -> tuple[list[str], list[str]]:
    """Guarda HTMLs sueltos y extrae *.html de .zip subidos en Streamlit.

    Entra recursivamente a zips anidados (un .zip por grupo dentro del .zip
    general de la tarea), hasta 3 niveles de profundidad. Ignora metadata de
    macOS (__MACOSX/, archivos ._*). Cualquier miembro que no sea .html ni
    .zip se reporta en `omitidos` en vez de descartarse en silencio.

    `archivos` son objetos UploadedFile (con .name y .getvalue()).
    Devuelve (agregados, omitidos) con los nombres de archivo.
    """
    import zipfile
    from io import BytesIO

    destino.mkdir(parents=True, exist_ok=True)
    agregados: list[str] = []
    omitidos: list[str] = []

    for archivo in archivos:
        nombre = archivo.name
        if _es_basura_mac(nombre):
            continue
        if nombre.lower().endswith(".html"):
            _guardar_html(destino, Path(nombre).name, archivo.getvalue(), agregados, omitidos)
        elif nombre.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(BytesIO(archivo.getvalue())) as zf:
                    _extraer_zip(zf, destino, agregados, omitidos)
            except zipfile.BadZipFile:
                omitidos.append(nombre)

    return agregados, omitidos


def render_output(output: str) -> str:
    """Convert script output to a styled HTML log for Streamlit (unsafe_allow_html=True)."""
    parts: list[str] = []
    for line in output.split("\n"):
        text = line.rstrip()
        if not text:
            parts.append("")
            continue
        stripped = text.lstrip()
        if stripped.startswith("✓"):
            style = "color:#2e7d32;font-weight:bold"
        elif stripped.startswith("✗"):
            style = "color:#c62828;font-weight:bold"
        elif stripped.startswith("⚠"):
            style = "color:#e65100;font-weight:bold"
        elif stripped.startswith("⊘"):
            style = "color:#616161"
        elif stripped.startswith("⋯"):
            style = "color:#616161"
        elif stripped.startswith("→"):
            style = "color:#1565c0"
        elif any(stripped.startswith(w) for w in ("Evaluados:", "enviado", "Módulo", "Nada")):
            style = "font-weight:bold;color:#212121"
        else:
            style = "color:#37474f"
        escaped = _html.escape(text)
        parts.append(
            f'<span style="font-family:monospace;font-size:13px;line-height:1.7;{style}">'
            f"{escaped}</span>"
        )
    body = "<br>".join(parts)
    return (
        '<div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:6px;'
        'padding:14px 16px;max-height:440px;overflow-y:auto">'
        f"{body}</div>"
    )
