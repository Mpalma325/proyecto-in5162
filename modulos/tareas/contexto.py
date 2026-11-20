"""
El contexto del curso que se le da al modelo al generar las preguntas de tareas.

Se sube desde la página (Configuración › Tareas › Contexto) y vive en
`tareas/data/clases/`. Sirve para cualquier curso, no solo para uno con R:

- `.html` de una clase renderizada con RMarkdown: se toma solo el código R, que
  es lo que dice qué estilo y qué librerías espera el curso. Si el HTML no trae
  código R, se toma su texto.
- `.md`, `.txt`, `.R`, `.py`: tal cual.

Lo extraído queda en `tareas/cache/` con la huella del archivo de origen. Si se
reemplaza una clase por otra versión con el mismo nombre, se vuelve a extraer;
antes se seguía usando la versión vieja sin avisar.

    python -m modulos.tareas.contexto      # qué contexto se está usando
"""

import hashlib
from pathlib import Path

from . import config

EXTENSIONES = (".html", ".md", ".txt", ".r", ".py")
# Tope por archivo: un apunte enorme no puede llevarse todo el contexto del modelo.
MAX_CARACTERES = 40_000

_memo: dict[tuple, str] = {}


def archivos() -> list[Path]:
    if not config.CLASES.exists():
        return []
    return sorted(p for p in config.CLASES.iterdir()
                  if p.is_file() and p.suffix.lower() in EXTENSIONES)


def _extraer(path: Path) -> str:
    if path.suffix.lower() != ".html":
        return path.read_text(encoding="utf-8", errors="replace")
    from .limpieza_html import extraer_codigo_r_de_clase
    codigo = extraer_codigo_r_de_clase(path)
    if codigo.strip():
        return codigo
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return soup.get_text("\n", strip=True)


def texto_de(path: Path) -> str:
    """Lo que el modelo ve de un archivo, usando el cache si el archivo no cambió."""
    huella = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    cache = config.CACHE / f"{path.stem}.contexto.txt"
    marca = f"# fuente {path.name} sha256:{huella}\n"
    if cache.exists():
        guardado = cache.read_text(encoding="utf-8")
        if guardado.startswith(marca):
            return guardado[len(marca):]
    texto = _extraer(path)[:MAX_CARACTERES]
    config.CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(marca + texto, encoding="utf-8")
    return texto


def cargar() -> str:
    """Todo el contexto, listo para el mensaje al modelo ("" si no hay o está apagado)."""
    if not config.INCLUIR_CONTEXTO_CLASES:
        return ""
    lista = archivos()
    clave = tuple((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in lista)
    if clave not in _memo:
        # Se arma una vez por corrida: generar lo pide para cada grupo.
        _memo.clear()
        _memo[clave] = "\n\n".join(f"# === {p.stem} ===\n{texto_de(p)}" for p in lista)
    return _memo[clave]


def resumen() -> dict:
    """Qué contexto se está usando, para mostrarlo en la página y en la salida."""
    if not config.INCLUIR_CONTEXTO_CLASES:
        return {"activo": False, "archivos": [], "caracteres": 0}
    detalle = [{"nombre": p.name, "caracteres": len(texto_de(p))} for p in archivos()]
    return {"activo": True, "archivos": detalle, "caracteres": sum(d["caracteres"] for d in detalle)}


def describir(r: dict | None = None) -> str:
    r = resumen() if r is None else r
    if not r["activo"]:
        return "Contexto del curso: apagado (INCLUIR_CONTEXTO_CLASES=false)"
    if not r["archivos"]:
        return ("⚠ Contexto del curso: no hay ninguno. El modelo genera las preguntas sin ver el "
                "material del curso; súbelo en Configuración › Tareas › Contexto.")
    vacios = [a["nombre"] for a in r["archivos"] if not a["caracteres"]]
    texto = (f"Contexto del curso: {len(r['archivos'])} archivo(s), "
             f"{r['caracteres'] / 1000:.0f} mil caracteres")
    return texto + (f"\n⚠ Sin contenido utilizable: {', '.join(vacios)}" if vacios else "")


if __name__ == "__main__":
    r = resumen()
    print(describir(r))
    for a in r["archivos"]:
        print(f"  {a['nombre']:60s} {a['caracteres']:>7d} caracteres")

