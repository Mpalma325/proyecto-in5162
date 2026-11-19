"""
Qué semestre está activo y cómo se crean los nuevos.

Esta lógica estaba escrita tres veces (los dos config.py y app/utils/runner.py),
las tres con un comentario "mantener sincronizado con...". Ahora vive acá.
"""

import html
import os
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEMESTRES_DIR = PROJECT_ROOT / "semestres"
TEMPLATE_DIR = SEMESTRES_DIR / "_template"
ACTIVO_FILE = SEMESTRES_DIR / "activo.txt"

_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


def activo() -> str | None:
    """Semestre en uso, o None si todavía no hay ninguno.

    La variable de entorno IN5162_SEMESTRE tiene prioridad sobre el archivo.
    Sirve para trabajar sobre otro semestre en un proceso puntual —las pruebas
    la usan— sin escribir el activo.txt, que es compartido: si un proceso que
    lo modifica muere antes de restaurarlo, deja al resto apuntando al semestre
    equivocado.
    """
    forzado = os.environ.get("IN5162_SEMESTRE", "").strip()
    if forzado:
        return forzado
    if not ACTIVO_FILE.exists():
        return None
    return ACTIVO_FILE.read_text(encoding="utf-8").strip() or None


def activo_o_error() -> str:
    """Igual que activo(), pero falla si no hay ninguno.

    Lo usan los scripts, que no tienen forma de mostrar un mensaje en pantalla
    y necesitan cortar de inmediato.
    """
    valor = activo()
    if not valor:
        raise RuntimeError(
            f"No hay un semestre activo en {ACTIVO_FILE}. Créalo desde la "
            f"página Datos y Configuración de la app antes de ejecutar scripts."
        )
    return valor


def listar() -> list[str]:
    if not SEMESTRES_DIR.exists():
        return []
    return sorted(
        p.name for p in SEMESTRES_DIR.iterdir()
        if p.is_dir() and p.name != "_template"
    )


def activar(semestre_id: str) -> None:
    if not (SEMESTRES_DIR / semestre_id).is_dir():
        raise ValueError(f"El semestre '{semestre_id}' no existe.")
    ACTIVO_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVO_FILE.write_text(semestre_id, encoding="utf-8")


# Los prompts y correos de la plantilla no nombran a ningún curso: donde va el
# nombre tienen una de estas marcas. Se llenan al copiar la plantilla, acá y en
# instalar.py (que la sube al sitio), con los datos del .env.
MARCA = re.compile(r"«([A-Z_]+)»")
MARCAS = ("CURSO", "NOMBRE_CURSO", "PROFESOR")
_CON_MARCAS = (".md", ".csv", ".txt", ".json")


# Los correos de tests_semanales son HTML, y sus prompts piden respuestas en
# HTML; los de tareas son texto.
_ES_HTML = re.compile(r"<(?:p|br|div|html|body)\b", re.I)


def llenar_marcas(texto: str, valores: dict[str, str]) -> str:
    """Reemplaza las marcas. Una marca desconocida o sin valor es un error.

    En un archivo HTML el valor va escapado: «Investigación & Desarrollo» se ve
    tal cual en el correo. Las llaves se rechazan: los correos de tareas se
    llenan después con str.format, y una llave suelta lo rompería.
    """
    es_html = bool(_ES_HTML.search(texto))

    def poner(m: re.Match) -> str:
        valor = (valores.get(m.group(1)) or "").strip()
        if m.group(1) not in MARCAS or not valor:
            raise ValueError(f"La plantilla usa «{m.group(1)}» y no tengo ese dato.")
        if "{" in valor or "}" in valor:
            raise ValueError(f"{m.group(1)} no puede tener llaves {{ }}: los correos las usan "
                             "para sus campos.")
        return html.escape(valor, quote=False) if es_html else valor
    return MARCA.sub(poner, texto)


def datos_del_curso() -> dict[str, str]:
    """CURSO, NOMBRE_CURSO y PROFESOR, del entorno o del .env de la raíz."""
    valores: dict[str, str] = {}
    env = PROJECT_ROOT / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            clave, igual, valor = linea.partition("=")
            if igual and clave.strip() in MARCAS:
                valores[clave.strip()] = valor.strip().strip('"').strip("'")
    valores.update({k: os.environ[k] for k in MARCAS if os.environ.get(k, "").strip()})
    # Como en config.py: sin CURSO, el curso es IN5162.
    valores["CURSO"] = valores.get("CURSO", "").strip() or "IN5162"
    return valores


def crear(semestre_id: str) -> None:
    """Crea un semestre nuevo copiando la plantilla, con los datos del curso. No lo activa."""
    semestre_id = semestre_id.strip()
    if not semestre_id or not _ID_VALIDO.match(semestre_id):
        raise ValueError(
            "El identificador del semestre solo puede contener letras, "
            "números, puntos, guiones y guiones bajos."
        )
    destino = SEMESTRES_DIR / semestre_id
    if destino.exists():
        raise ValueError(f"El semestre '{semestre_id}' ya existe.")
    if not TEMPLATE_DIR.exists():
        raise RuntimeError(f"No encontré la plantilla en {TEMPLATE_DIR}.")
    valores = datos_del_curso()
    llenos = {}
    for p in TEMPLATE_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in _CON_MARCAS:
            texto = p.read_text(encoding="utf-8")
            if MARCA.search(texto):
                faltan = sorted({m for m in MARCA.findall(texto) if not valores.get(m, "").strip()})
                if faltan:
                    # Antes de copiar: un semestre a medio llenar mandaría
                    # «PROFESOR» en la firma de los correos.
                    raise ValueError(
                        f"Falta {', '.join(faltan)} en el .env: la plantilla lo usa en "
                        f"{p.relative_to(TEMPLATE_DIR).as_posix()} (prompts y firma de los correos)."
                    )
                llenos[p.relative_to(TEMPLATE_DIR)] = llenar_marcas(texto, valores)
    shutil.copytree(TEMPLATE_DIR, destino)
    for ruta, texto in llenos.items():
        (destino / ruta).write_text(texto, encoding="utf-8")


def raiz(semestre_id: str | None = None) -> Path:
    """Carpeta de un semestre (el activo si no se indica cuál)."""
    return SEMESTRES_DIR / (semestre_id or activo_o_error())


def datos(flujo: str, semestre_id: str | None = None) -> Path:
    """Carpeta de datos de un flujo: 'tests_semanales' o 'tareas'."""
    return raiz(semestre_id) / flujo / "data"


def prompts(flujo: str, semestre_id: str | None = None) -> Path:
    return raiz(semestre_id) / flujo / "prompts"
