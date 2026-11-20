"""
La configuración de un semestre: `configuracion.json`, en su raíz.

    {"revision": "revisar", "correo_muestra": "nota"}

- `revision`: el modo de respaldo de Tests, para las instancias que no dicen
  el suyo. Cada instancia lo elige en la columna `Revision` de preguntas.csv
  (`auto`: corregir y mandar el feedback en el mismo trabajo; `revisar`:
  corregir y dejar la corrección para que el docente la revise). Ver
  `modo_instancia`.
- `correo_muestra`: qué números ve el alumno en el correo de Tests: `nota`
  (el puntaje de cada pregunta, el total y la NOTA FINAL), `puntajes` (sin el
  total ni la nota) o `nada` (solo los comentarios). La nota se calcula y se
  registra igual; esto decide solo el correo (modulos/tests/correccion.py).

La escribe solo la página (Configuración › Semestre, que ya no muestra el
modo: se elige en cada instancia). Un semestre sin el archivo (2026-2 y
anteriores) sigue como siempre: `auto` y `nota`. Los semestres nuevos lo
traen de la plantilla, con `revisar` de respaldo.
"""

import json

ARCHIVO = "configuracion.json"

AUTO = "auto"
REVISAR = "revisar"
MODOS = (AUTO, REVISAR)
MUESTRAS = ("nota", "puntajes", "nada")


def leer(semestre_id: str | None = None) -> dict | None:
    """El contenido del archivo, o None si el semestre no lo tiene.

    Un archivo que no se puede leer cuenta como {"revision": "revisar"}: ante
    la duda, nada sale sin que el docente lo vea.
    """
    from modulos import semestre as _semestre

    ruta = _semestre.raiz(semestre_id) / ARCHIVO
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig") or "{}")
    except json.JSONDecodeError as e:
        print(f"⚠ {ARCHIVO} no es JSON válido ({e}): se trabaja en modo revisión.")
        return {"revision": REVISAR}
    if not isinstance(datos, dict):
        print(f"⚠ {ARCHIVO} no es un objeto JSON: se trabaja en modo revisión.")
        return {"revision": REVISAR}
    return datos


def modo_revision(semestre_id: str | None = None) -> str:
    """El modo de respaldo del semestre: `auto` o `revisar`.

    Sin archivo, `auto` (como siempre, así 2026-2 no cambia). Con archivo pero
    sin la clave, `revisar`: ante la duda, nada sale sin que el docente lo vea.
    """
    datos = leer(semestre_id)
    if datos is None:
        return AUTO
    valor = str(datos.get("revision") or REVISAR).strip().lower()
    if valor not in MODOS:
        print(f"⚠ {ARCHIVO}: revision «{valor}» no se entiende (auto o revisar): se trabaja en modo revisión.")
        return REVISAR
    return valor


def modo_instancia(valor: str | None, respaldo: str) -> str:
    """El modo de una instancia de Tests a partir de su columna `Revision`.

    Orden: la columna (`auto` o `revisar`, sin importar mayúsculas ni espacios)
    y, si está vacía, `respaldo` (el de configuracion.json; sin archivo,
    `auto`). Un valor que no se entiende cuenta como `revisar`: ante la duda,
    nada sale sin que el docente lo vea.

    Gemela: `modoInstancia` en web/public/configuracion.js; pruebas/web.py
    compara las dos.
    """
    texto = " ".join(str(valor or "").split()).lower()
    if not texto:
        return respaldo
    if texto in MODOS:
        return texto
    print(f"⚠ preguntas.csv: Revision «{texto}» no se entiende (auto o revisar): se trabaja en modo revisión.")
    return REVISAR


def modo_de(revision: str | None, semestre_id: str | None = None) -> str:
    """El modo con que se corrige una instancia, leído al correr.

    `revision` es la columna `Revision` de su fila (SemanaInfo.revision).
    configuracion.json se lee solo si hace falta el respaldo.
    """
    respaldo = REVISAR if str(revision or "").strip() else modo_revision(semestre_id)
    return modo_instancia(revision, respaldo)


def correo_muestra(semestre_id: str | None = None) -> str:
    datos = leer(semestre_id) or {}
    valor = str(datos.get("correo_muestra") or "nota").strip().lower()
    return valor if valor in MUESTRAS else "nota"


def describir(modo: str) -> str:
    """Una línea para la salida de un trabajo."""
    if modo == AUTO:
        return "Modo automático: cada corrección se envía al alumno apenas queda lista."
    return ("Modo revisión: las correcciones quedan esperando en Tests › Revisar; "
            "el alumno no recibe nada hasta que se aprueben.")
