"""
Sacar las entregas de los comprimidos: los .html de cada grupo y su .Rmd.

Lo usan la app de Streamlit (al subir el .zip de U-Cursos) y los pasos de
Tareas: la página sube los .rar sin abrir, porque el navegador no los lee, y el
chequeo o generar los abren acá antes de leer las entregas.

Reglas, las mismas que sigue la página en web/public/datos.js:
  - Se ignora la metadata de macOS (__MACOSX/, ._*, .DS_Store) y la carpeta .git
    de los grupos que suben su repositorio.
  - El enunciado que algunos grupos incluyen no es una entrega: se reporta y se omite.
  - Un comprimido con un solo HTML le da su nombre (Grupo1.zip -> Grupo1.html);
    con varios, cada uno queda como Grupo1__archivo.html. Vale también para el
    zip subido si trae una sola entrega y nada anidado: es el zip individual de
    U-Cursos, y la entrega queda con su nombre como si viniera en el general.
  - El .Rmd viaja con el nombre base de su HTML.
  - Lo que no se pudo abrir se reporta en `omitidos`, no se descarta en silencio.
"""

import os
import shutil
import subprocess
from pathlib import Path


def _miembro_valido(member: str) -> bool:
    return not (".." in member or member.startswith("/") or member.startswith("\\"))


def _es_basura_mac(member: str) -> bool:
    """Metadata que macOS agrega al comprimir (AppleDouble, __MACOSX/, .DS_Store)
    y la carpeta .git de los grupos que suben su repositorio."""
    partes = Path(member).parts
    nombre = Path(member).name
    return ("__MACOSX" in partes or ".git" in partes
            or nombre.startswith("._") or nombre == ".DS_Store")


def _es_enunciado(member: str) -> bool:
    """Algunos grupos incluyen el enunciado renderizado junto a su entrega (T2 de 2026-2)."""
    return "enunciado" in member.lower()


def _rmd_de(html: str, rmds: list, multiple: bool):
    """El .Rmd que acompaña a un HTML: el de igual nombre base, o con un solo
    HTML en la entrega, el primero que haya."""
    base = str(html).lower().rsplit(".", 1)[0]
    for r in rmds:
        if str(r).lower().rsplit(".", 1)[0] == base:
            return r
    return None if multiple or not rmds else rmds[0]


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
    instalar nada. En Linux, bsdtar es ese mismo tar (el motor lo instala con
    libarchive-tools); si no está, unar o unrar. El tar de Linux es GNU tar y no
    lee rar, así que no sirve.
    """
    # El tar de Windows va explícito por ruta: si el PATH trae primero el de Git
    # Bash o MSYS, ese es GNU tar y no lee rar.
    tar_windows = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
    if tar_windows.exists():
        return str(tar_windows)
    for candidato in ("bsdtar", "unar", "unrar"):
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
        lector = Path(herramienta).stem.lower()
        if lector in ("tar", "bsdtar"):
            cmd = [herramienta, "-xf", str(path_rar)]
        elif lector == "unar":
            cmd = [herramienta, "-q", "-o", str(salida), str(path_rar)]
        else:  # unrar
            cmd = [herramienta, "x", "-y", str(path_rar), str(salida) + os.sep]
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
    for p in archivos:
        if p.suffix.lower() in (".html", ".rmd") and _es_enunciado(p.as_posix()):
            omitidos.append(f"{prefijo}/{p.name} (es el enunciado)")
    htmls = [p for p in archivos if p.suffix.lower() == ".html" and not _es_enunciado(p.as_posix())]
    rmds = [p for p in archivos if p.suffix.lower() == ".rmd" and not _es_enunciado(p.as_posix())]

    multiple = len(htmls) > 1
    for p in htmls:
        nombre = f"{prefijo}__{p.name}" if multiple else f"{prefijo}.html"
        _guardar_html(destino, nombre, p.read_bytes(), agregados, omitidos)
        # El .Rmd viaja con el mismo nombre base que su HTML: generar lo busca así
        # cuando el HTML viene renderizado sin código.
        rmd = _rmd_de(p.as_posix(), rmds, multiple)
        if rmd is not None:
            _guardar_html(destino, nombre.rsplit(".", 1)[0] + ".Rmd", rmd.read_bytes(),
                          agregados, omitidos)

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
                  prefijo: str | None = None, profundidad: int = 0,
                  nombre_subido: str | None = None) -> None:
    """Extrae *.html de un zip, entrando recursivamente a zips anidados
    (ej. un zip por grupo dentro del zip general de la tarea).

    `nombre_subido`: el nombre del zip subido, sin .zip. Si trae una sola
    entrega, la entrega toma ese nombre.
    """
    if profundidad > 3:
        return

    nombres = [m for m in zf.namelist() if not _es_basura_mac(m)]
    enunciados = [m for m in nombres
                  if m.lower().endswith((".html", ".rmd")) and _es_enunciado(m)]
    for m in enunciados:
        omitidos.append(f"{prefijo}/{m} (es el enunciado)" if prefijo else f"{m} (es el enunciado)")
    nombres = [m for m in nombres if m not in enunciados]
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
    if not prefijo and nombre_subido and len(htmls) == 1 and not zips_anidados and not rars:
        prefijo = nombre_subido

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
        # generar cuando el HTML viene renderizado sin código. Con varios HTML
        # solo se aparea el de igual nombre.
        rmd = _rmd_de(member, rmds, multiple) if prefijo else None
        if rmd is not None and _miembro_valido(rmd):
            _guardar_html(destino, safe_name.rsplit(".", 1)[0] + ".Rmd", zf.read(rmd),
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
                    _extraer_zip(zf, destino, agregados, omitidos,
                                 nombre_subido=Path(nombre).stem)
            except zipfile.BadZipFile:
                omitidos.append(nombre)
        elif nombre.lower().endswith(".rar"):
            _extraer_rar(archivo.getvalue(), destino, agregados, omitidos, nombre)

    return agregados, omitidos


def _ya_desempacado(carpeta: Path, prefijo: str) -> bool:
    """Si ese .rar ya se abrió antes: está su HTML (o los HTML que salieron de él)."""
    return (carpeta / f"{prefijo}.html").exists() or any(carpeta.glob(f"{prefijo}__*.html"))


def desempacar_rars(carpeta: Path) -> tuple[list[str], list[str]]:
    """
    Abre los .rar de una carpeta de entregas y deja sus HTML al lado.

    La página no puede abrir un .rar, así que lo sube tal cual, con el nombre que
    tendría su HTML (Grupo1.rar -> Grupo1.html). Un .rar que ya se abrió no se
    vuelve a abrir. Devuelve (agregados, omitidos).
    """
    agregados: list[str] = []
    omitidos: list[str] = []
    if not carpeta.is_dir():
        return agregados, omitidos
    for rar in sorted(carpeta.glob("*.rar")) + sorted(carpeta.glob("*.RAR")):
        if _ya_desempacado(carpeta, rar.stem):
            continue
        _extraer_rar(rar.read_bytes(), carpeta, agregados, omitidos, rar.name, rar.stem)
        if not any(a.startswith(rar.stem) for a in agregados) and not any(
                o.startswith(rar.name) for o in omitidos):
            omitidos.append(f"{rar.name} (no traía ningún .html)")
    return agregados, omitidos
