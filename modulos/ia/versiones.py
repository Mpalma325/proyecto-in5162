"""
Con qué se produjo cada respuesta del modelo: prompt, pauta y parámetros.

Los prompts y las pautas se editan a mitad de semestre: en 2026-2 el criterio
de originalidad cambió entre las semanas 6 y 7, y las notas de antes y después
no se comparan igual. Ese cambio se hizo en el PC y no quedó registrado en
ninguna parte; solo se nota en las notas. Cada llamada anota ahora en el log
una huella de cada cosa que la produjo, y la primera vez que aparece una huella
el texto se guarda aparte: cualquier corrección se puede leer junto al prompt y
la pauta exactos con que se hizo.

    evaluar_respuesta.md@73784193; pauta.md@1a2b3c4d; temperatura=0.2; max_tokens=3000
"""

import hashlib
from pathlib import Path

CARPETA = "prompts_usados"
SEPARADOR = "; "


def huella(texto: str) -> str:
    # Los fines de línea cambian entre Windows y la nube sin que cambie el prompt.
    normal = texto.replace("\r\n", "\n").strip()
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:8]


def guardar(flujo: Path, nombre: str, texto: str) -> str:
    """`nombre@1a2b3c4d`, y guarda esa versión si es nueva.

    Va en <flujo>/prompts_usados/: el motor sube los archivos nuevos del flujo
    al terminar. Si no se puede guardar, la huella igual queda en el log.
    """
    h = huella(texto)
    base, punto, ext = nombre.rpartition(".")
    destino = flujo / CARPETA / (f"{base}@{h}.{ext}" if punto else f"{nombre}@{h}")
    try:
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            # Tal cual: en Windows, write_text pasaría cada \r\n a \r\r\n y
            # el archivo ya no tendría la huella de su nombre.
            destino.write_text(texto, encoding="utf-8", newline="")
    except OSError as e:
        print(f"⚠ No pude guardar la versión de {nombre}: {e}")
    return f"{nombre}@{h}"


def anotar(ruta: Path, texto: str) -> str:
    """`evaluar_respuesta.md@1a2b3c4d` para un archivo de <flujo>/prompts/."""
    return guardar(ruta.parent.parent, ruta.name, texto)


def pauta(flujo: Path, preguntas: list[str], pautas: list[str]) -> str:
    """`pauta.md@1a2b3c4d`: las preguntas y la pauta con que se corrigió, guardadas como texto."""
    def bloque(items):
        return "\n".join(f"P{i}. {t}" for i, t in enumerate(items, 1))
    texto = f"=== PREGUNTAS ===\n{bloque(preguntas)}\n\n=== PAUTAS ===\n{bloque(pautas)}\n"
    return guardar(flujo, "pauta.md", texto)


def parametros(meta: dict) -> str:
    """Los parámetros con que se llamó al modelo, desde la metadata de la llamada."""
    return juntar(*(f"{k}={meta[k]}" for k in ("temperatura", "max_tokens", "razonamiento")
                    if meta.get(k) not in (None, "")))


def juntar(*partes: str | None) -> str:
    return SEPARADOR.join(p for p in partes if p)
