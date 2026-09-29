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
# Los flujos viven en modulos/ y se invocan desde la raíz del proyecto.
ENV_FILE = PROJECT_ROOT / ".env"

sys.path.insert(0, str(PROJECT_ROOT))
from modulos import semestre as _semestre  # noqa: E402

# La app conserva estos nombres; la logica vive en modulos/semestre.
semestre_activo = _semestre.activo
listar_semestres = _semestre.listar
set_semestre_activo = _semestre.activar
crear_semestre = _semestre.crear

SEMESTRES_DIR = PROJECT_ROOT / "semestres"
_TEMPLATE_DIR = SEMESTRES_DIR / "_template"
ACTIVO_FILE = SEMESTRES_DIR / "activo.txt"
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


# Las rutas las resuelve modulos/semestre: acá solo se les pone el nombre que
# usa la app. Antes estaban calculadas a mano y había que cambiarlas en dos
# lugares cada vez.
def tests_data_dir(semestre: str | None = None) -> Path:
    return _semestre.datos("tests_semanales", semestre)


def tests_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre.prompts("tests_semanales", semestre)


def tareas_data_dir(semestre: str | None = None) -> Path:
    return _semestre.datos("tareas", semestre)


def tareas_prompts_dir(semestre: str | None = None) -> Path:
    return _semestre.prompts("tareas", semestre)


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


def _hay_lector_rar() -> str | None:
    """
    Con qué desempaquetar un .rar, si es que hay algo.

    No existe lector de rar en la biblioteca estándar. El `tar` de Windows trae
    libarchive y lee RAR4 y RAR5, así que en la práctica está disponible sin
    instalar nada; fuera de Windows se usa unar o unrar si están.
    """
    # El tar de Windows va explícito por ruta: si el PATH trae primero el de Git
    # Bash o MSYS, ese es GNU tar y no lee rar.
    tar_windows = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    if tar_windows.exists():
        return str(tar_windows)
    for candidato in ("unar", "unrar", "tar"):
        ruta = shutil.which(candidato)
        if ruta:
            return ruta
    return None


def _extraer_rar(contenido: bytes, destino: Path, agregados: list[str],
                 omitidos: list[str], nombre_rar: str,
                 prefijo: str | None = None, profundidad: int = 0) -> None:
    """
    Extrae un .rar a un directorio temporal y recoge de ahí lo que sirve.

    Los alumnos entregan .rar cada tanto y perderlos significa perder al grupo
    entero. Si no hay con qué abrirlo se reporta, no se descarta en silencio.
    """
    import tempfile

    herramienta = _hay_lector_rar()
    if not herramienta:
        omitidos.append(f"{nombre_rar} (es .rar y no hay con qué abrirlo en este equipo)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        path_rar = tmp_dir / "entrega.rar"
        path_rar.write_bytes(contenido)
        salida = tmp_dir / "salida"
        salida.mkdir()
        if Path(herramienta).stem.lower() == "tar":
            cmd = [herramienta, "-xf", str(path_rar)]
        else:
            cmd = [herramienta, "x", "-o" + str(salida), str(path_rar)]
        try:
            subprocess.run(cmd, cwd=salida, capture_output=True, timeout=180, check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            omitidos.append(f"{nombre_rar} (no se pudo abrir el .rar)")
            return

        _recoger_de_directorio(salida, destino, agregados, omitidos,
                               prefijo or Path(nombre_rar).stem, profundidad)


def _recoger_de_directorio(raiz: Path, destino: Path, agregados: list[str],
                           omitidos: list[str], prefijo: str,
                           profundidad: int) -> None:
    """Toma los HTML (y su .Rmd) de un árbol ya extraído en disco."""
    archivos = [p for p in raiz.rglob("*")
                if p.is_file() and not _es_basura_mac(p.as_posix())]
    htmls = [p for p in archivos if p.suffix.lower() == ".html"]
    rmds = [p for p in archivos if p.suffix.lower() == ".rmd"]

    multiple = len(htmls) > 1
    for p in htmls:
        nombre = f"{prefijo}__{p.name}" if multiple else f"{prefijo}.html"
        _guardar_html(destino, nombre, p.read_bytes(), agregados, omitidos)
    # El .Rmd viaja con el mismo nombre base que su HTML: generar lo busca así
    # cuando el HTML viene renderizado sin código.
    if rmds and not multiple:
        _guardar_html(destino, f"{prefijo}.Rmd", rmds[0].read_bytes(), agregados, omitidos)

    for p in archivos:
        if p.suffix.lower() == ".zip" and profundidad <= 3:
            import zipfile
            try:
                with zipfile.ZipFile(p) as zf:
                    _extraer_zip(zf, destino, agregados, omitidos,
                                 prefijo, profundidad + 1)
            except zipfile.BadZipFile:
                omitidos.append(p.name)


def _extraer_zip(zf, destino: Path, agregados: list[str], omitidos: list[str],
                  prefijo: str | None = None, profundidad: int = 0) -> None:
    """Extrae *.html de un zip, entrando recursivamente a zips anidados
    (ej. un zip por grupo dentro del zip general de la tarea).
    """
    if profundidad > 3:
        return

    nombres = [m for m in zf.namelist() if not _es_basura_mac(m)]
    htmls = [m for m in nombres if m.lower().endswith(".html")]
    rmds = [m for m in nombres if m.lower().endswith(".rmd")]
    zips_anidados = [m for m in nombres if m.lower().endswith(".zip")]
    rars = [m for m in nombres if m.lower().endswith(".rar")]
    reconocidos = set(htmls) | set(rmds) | set(zips_anidados) | set(rars)
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

    # El .Rmd acompaña a su HTML con el mismo nombre base, que es como lo busca
    # generar cuando el HTML viene renderizado sin código. Solo tiene sentido
    # cuando el zip trae un HTML: con varios no hay forma segura de aparearlos.
    if rmds and prefijo and not multiple:
        for member in rmds[:1]:
            if _miembro_valido(member):
                _guardar_html(destino, f"{prefijo}.Rmd", zf.read(member),
                              agregados, omitidos)

    for member in rars:
        if not _miembro_valido(member):
            omitidos.append(member)
            continue
        nombre_rar = Path(member).with_suffix("").as_posix().replace("/", "_")
        nuevo_prefijo = f"{prefijo}__{nombre_rar}" if prefijo else nombre_rar
        _extraer_rar(zf.read(member), destino, agregados, omitidos,
                     Path(member).name, nuevo_prefijo, profundidad + 1)

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
        omitidos.append(f"{nombre_mostrado} (formato no soportado — no es .html, .Rmd, .zip ni .rar)")


def extraer_entregas(archivos: list, destino: Path) -> tuple[list[str], list[str]]:
    """Guarda HTMLs sueltos y extrae las entregas de .zip y .rar subidos.

    Entra recursivamente a los comprimidos anidados (uno por grupo dentro del
    comprimido general de la tarea), hasta 3 niveles de profundidad. Ignora
    metadata de macOS (__MACOSX/, archivos ._*). Se queda con los .html y con el
    .Rmd que los acompaña. Cualquier otro miembro se reporta en `omitidos` en
    vez de descartarse en silencio.

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
        elif nombre.lower().endswith(".rar"):
            _extraer_rar(archivo.getvalue(), destino, agregados, omitidos, nombre)

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


# --- Chequeo previo de las entregas -----------------------------------------
# El cálculo vive en modulos/tareas/chequeo.py; acá solo se dibuja, igual que
# con la reportería.

def chequeo_tareas(tarea: str) -> dict:
    """El estado de las entregas de una tarea. No llama al modelo."""
    from modulos.tareas import chequeo
    return chequeo.revisar(tarea)


def _pintar_grupo(st, grupo: dict, tarea: str, elegido: dict) -> None:
    """Un grupo dentro del chequeo. Deja en `elegido` lo que se elija a mano."""
    archivo = grupo["archivo"]

    if grupo["bloqueo"]:
        icono, resumen = "❌", "se va a saltar"
    elif grupo["sin_roles"] or any(not i["correo"] for i in grupo["integrantes"]):
        icono, resumen = "⚠️", "pide revisión"
    else:
        icono, resumen = "✅", f"{len(grupo['integrantes'])} integrantes"

    with st.expander(f"{icono} {archivo} — {resumen}",
                     expanded=bool(grupo["bloqueo"]) or grupo["sin_roles"]):
        if grupo["fuente"] != archivo:
            st.info(f"El HTML viene sin código: se lee `{grupo['fuente']}`.")

        cortes = " · ".join(f"P{n}: {c:,} car." for n, c in grupo["secciones"].items())
        st.caption(cortes.replace(",", "."))

        if grupo["bloqueo"]:
            st.error("No se llama al modelo por esto:\n\n"
                     + "\n".join(f"- {m}" for m in grupo["bloqueo"]))
            return

        st.caption(f"Integrantes según: {grupo['origen_integrantes']}")

        if grupo["sin_roles"]:
            st.warning(
                "Este grupo no declaró quién hizo qué. Cada integrante trae una "
                "pregunta repartida al azar (con semilla fija, así que no cambia "
                "sola entre corridas). Cámbiala acá si sabes cuál le corresponde."
            )

        for integrante in grupo["integrantes"]:
            nombre = integrante["nombre"]
            col_nombre, col_correo, col_pregunta = st.columns([3, 4, 2])

            with col_nombre:
                st.markdown(f"**{nombre}**")

            with col_correo:
                if integrante["correo"]:
                    st.markdown(f"`{integrante['correo']}`")
                else:
                    st.markdown(":red[Sin correo — elígelo en Datos → Feedback Tareas]")
                    for cand_nombre, cand_correo, sim in integrante["candidatos"]:
                        st.caption(f"¿{cand_nombre}? `{cand_correo}` (parecido {sim})")
                    if not integrante["candidatos"]:
                        st.caption("Ningún candidato razonable en el roster.")

            with col_pregunta:
                asignada = grupo["asignacion"].get(nombre)
                if asignada:
                    opciones = ["P1", "P2", "P3", "P4"]
                    elegida = st.selectbox(
                        "Pregunta", opciones, index=opciones.index(asignada),
                        key=f"asig_{tarea}_{archivo}_{nombre}",
                        label_visibility="collapsed",
                    )
                    elegido[(archivo, nombre)] = elegida


def pintar_chequeo(st, informe: dict, tarea: str) -> None:
    """Dibuja el chequeo previo y deja guardar la asignación que se elija."""
    from modulos.tareas import asignacion as _asignacion

    grupos = informe["grupos"]
    if not grupos:
        st.warning("No hay entregas que revisar.")
        return

    a_generar = sum(1 for g in grupos if not g["bloqueo"]
                    for i in g["integrantes"] if i["correo"])
    saltados = sum(1 for g in grupos if g["bloqueo"])
    sin_correo = sum(1 for g in grupos if not g["bloqueo"]
                     for i in g["integrantes"] if not i["correo"])

    col1, col2, col3 = st.columns(3)
    col1.metric("Preguntas que se generarían", a_generar)
    col2.metric("Sin correo, a resolver", sin_correo)
    col3.metric("Grupos que se saltarían", saltados)

    elegido = dict(_asignacion.leer(tarea))
    for grupo in grupos:
        _pintar_grupo(st, grupo, tarea, elegido)

    hay_reparto = any(g["asignacion"] for g in grupos)
    if hay_reparto and st.button("Guardar asignación", key=f"guardar_asig_{tarea}"):
        path = _asignacion.escribir(tarea, elegido)
        st.success(f"Guardado en `{path.name}`. Generar va a usar esto.")

    if informe["sin_entrega"]:
        with st.expander(
            f"Del roster ({informe['total_roster']}), quedan sin pregunta "
            f"{len(informe['sin_entrega'])}"
        ):
            st.caption(
                "Revisa la lista antes de sacar conclusiones: acá también cae el "
                "equipo docente, si está en el roster."
            )
            for nombre in informe["sin_entrega"]:
                st.markdown(f"- {nombre}")
