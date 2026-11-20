"""
Las decisiones de la revisión docente de una instancia de Tests.

Viven en `tests_semanales/revision/<id>.json` y las escribe solo la página
(Tests › Revisar). Los trabajos solo las leen: `tests.feedback` manda las que
dicen `enviar` y registra las `descartada`.

    {
      "alumno@x.cl": {
        "estado": "enviar",                       # aprobada | enviar | descartada
        "base": "2026-11-02T09:41:07-03:00",      # Timestamp de la correccion
        "nota_legado": "6,5",                     # solo si el docente la cambió
        "html_legado": "<p>…</p>",                # ídem
        "manual": false,                          # true: la corrige el docente
        "retroalimentacion": "…",                 # en un descarte, el motivo
        "por": "profe@x.cl", "cuando": "…"
      }
    }

«Por revisar» es no tener entrada. «Enviada» y «descarte registrado» no se
escriben aquí: se deducen de notas.csv y del log.

`base` es el `Timestamp` de la fila `correccion` sobre la que se decidió,
copiado tal cual del log. Si después aparece una corrección más nueva, la
decisión queda vieja: el trabajo la ignora y la página pide revisar otra vez.
La página compara la misma cadena (web/public/revision.js, baseDe).
"""

import json
import re
from pathlib import Path

from modulos import semestre as _semestre
from modulos import datos as _datos

APROBADA = "aprobada"
ENVIAR = "enviar"
DESCARTADA = "descartada"
ESTADOS = (APROBADA, ENVIAR, DESCARTADA)

DOCENTE = "docente:"


def ruta(item: int | str, semestre_id: str | None = None) -> Path:
    return _semestre.raiz(semestre_id) / "tests_semanales" / "revision" / f"{item}.json"


def leer(item: int | str, semestre_id: str | None = None) -> dict[str, dict]:
    """{correo: decisión} de la instancia. Sin archivo, o ilegible, no hay decisiones."""
    p = ruta(item, semestre_id)
    if not p.exists():
        return {}
    try:
        datos = json.loads(p.read_text(encoding="utf-8-sig") or "{}")
    except json.JSONDecodeError as e:
        print(f"⚠ {p.name} de la revisión no es JSON válido ({e}): no se toma ninguna decisión.")
        return {}
    if not isinstance(datos, dict):
        return {}
    return {c.strip().lower(): d for c, d in datos.items()
            if isinstance(d, dict) and d.get("estado") in ESTADOS}


def es_del_docente(correccion: dict | None) -> bool:
    return (correccion or {}).get("Modelo", "").startswith(DOCENTE)


def modo_de(correccion: dict | None) -> str:
    """`auto` o `revisar`, el modo con que se corrigió (Detalle `modo=…`)."""
    m = re.search(r"modo=(\w+)", (correccion or {}).get("Detalle", ""))
    return m.group(1) if m else ""


def estado_por_correo(item: int | str, semestre_id: str | None = None,
                      filas: list[dict] | None = None) -> dict[str, dict]:
    """Por alumno: su última `correccion` y si después de ella hubo feedback o descarte.

    {correo: {"correccion": fila, "cerrada": bool, "respuesta": fila | None}}.
    El log es append-only: la última fila de un tipo es la más nueva.
    """
    if filas is None:
        filas = _datos.log.leer(semestre_id, flujo=_datos.TESTS, item=str(item))
    salida: dict[str, dict] = {}
    for fila in filas:
        correo = (fila.get("Correo") or "").strip().lower()
        ev = fila.get("Evento")
        if not correo:
            continue
        if ev == "correccion":
            previo = salida.get(correo, {})
            salida[correo] = {"correccion": fila, "cerrada": False,
                              "respuesta": previo.get("respuesta")}
        elif ev in ("evaluacion", "descarte") and correo in salida:
            salida[correo]["cerrada"] = True
        elif ev == "respuesta" and not _datos.log.es_duplicado(fila):
            # La primera respuesta no duplicada es la que se corrigió.
            entrada = salida.setdefault(correo, {"correccion": None, "cerrada": False, "respuesta": None})
            if entrada.get("respuesta") is None:
                entrada["respuesta"] = fila
    return {c: e for c, e in salida.items() if e.get("correccion")}


def vigente(decision: dict | None, correccion: dict | None) -> bool:
    """Si la decisión se tomó sobre esa corrección (y no sobre una anterior)."""
    return bool(decision and correccion
                and (decision.get("base") or "") == (correccion.get("Timestamp") or ""))


_NOTA_FINAL = re.compile(r"(NOTA\s*FINAL\s*:?\s*(?:</?\w+[^>]*>\s*)*)([0-9]+(?:[.,][0-9]+)?)", re.IGNORECASE)


def reescribir_nota_final(html: str, nota: str) -> str:
    """Pone `nota` en la línea NOTA FINAL del HTML viejo, para que el correo diga la nota que sale.

    La misma regla está en web/public/revision.js (reescribirNotaFinal).
    """
    return _NOTA_FINAL.sub(lambda m: m.group(1) + nota, html, count=1)


def juntar(correccion: dict, decision: dict | None) -> dict:
    """Lo que sale en el correo: la corrección con lo que el docente cambió encima.

    Devuelve {"nota", "originalidad", "html", "cambios"}; `cambios` es la lista
    de lo editado («nota 5,0 → 6,0», «texto»), vacía si se manda tal cual.
    Sin decisión, el HTML es el de la corrección sin tocar: el correo es el
    mismo que salía antes de la revisión, byte a byte.
    """
    html = correccion.get("EvaluacionIA") or ""
    nota = (correccion.get("Nota") or "").strip()
    originalidad = (correccion.get("Originalidad") or "").strip()
    cambios = []
    decision = decision or {}

    html_nuevo = decision.get("html_legado")
    if isinstance(html_nuevo, str) and html_nuevo.strip() and html_nuevo != html:
        html = html_nuevo
        cambios.append("texto")
    nota_nueva = decision.get("nota_legado")
    if nota_nueva not in (None, ""):
        nota_nueva = str(nota_nueva).strip().replace(".", ",")
        if nota_nueva != nota:
            cambios.insert(0, f"nota {nota or '—'} → {nota_nueva}")
            nota = nota_nueva
        html = reescribir_nota_final(html, nota)
    if "texto" in cambios or nota_nueva not in (None, ""):
        # La originalidad sale del texto que se manda, si el docente la cambió ahí.
        from .evaluar import extraer_nota_y_originalidad
        _, orig = extraer_nota_y_originalidad(html)
        originalidad = orig or originalidad
    return {"nota": nota, "originalidad": originalidad, "html": html, "cambios": cambios}


def faltante_manual(decision: dict | None) -> str:
    """Qué le falta a una corrección hecha a mano para poder salir; vacío si está completa."""
    d = decision or {}
    if d.get("estado") != ENVIAR:
        return "falta que el docente la apruebe"
    if not re.fullmatch(r"\d{1,2}([.,]\d)?", str(d.get("nota_legado") or "").strip()):
        return "falta la nota"
    if not str(d.get("html_legado") or "").strip():
        return "falta el texto de la corrección"
    return ""
