"""
La corrección de un test: leerla, calcular la nota y armar el bloque del correo.

Hay dos formatos y se distinguen por el contenido:

- Nuevo (semestres que estrenan el prompt JSON). El modelo devuelve puntajes
  por pregunta y no escribe nota:

      {"preguntas": [{"rotulo": "P1", "respuesta": "…", "puntaje": 2, "justificacion": "…"}],
       "originalidad": "Media", "justificacion_originalidad": "…", "retroalimentacion": "…"}

  El código valida cada puntaje contra la rúbrica (0; 0,5; 1; 2; 3, hasta el
  `puntaje_maximo_pregunta` de la escala), calcula el logro (suma sobre
  máximo × bloques) y la nota con la escala del semestre (modulos/escala.py).
  Si el modelo devolvió menos bloques que preguntas, lo dice en `avisos`.
- Viejo (2026-2 y anteriores): el HTML con `NOTA FINAL`, leído con el
  extractor de siempre. El logro es la inversa de la nota en la escala.

`armar_html` arma el bloque que va en {EVALUACION} según `correo_muestra`
(configuracion.json): `nota` (puntaje por pregunta y NOTA FINAL), `puntajes`
(solo el puntaje por pregunta) o `nada` (solo comentarios y originalidad).
Con `nota` el bloque conserva las etiquetas de siempre, así que reconstruir y
la página siguen leyendo la nota del correo enviado. El HTML viejo sale tal
cual con `nota`; con lo demás se le quitan las líneas con números.

`texto_docente` es la corrección para el equipo docente: siempre con
puntajes y NOTA FINAL. Lo usan el resumen y Probar criterio.

La gemela para la página es web/public/correccion.js; pruebas/correccion.py
compara las dos sobre los mismos casos.
"""

from __future__ import annotations

import json
import math
import re
from fractions import Fraction

from modulos import escala as _escala

JSON = "json"
HTML = "html"

NOTA = "nota"
PUNTAJES = "puntajes"
NADA = "nada"
MUESTRAS = (NOTA, PUNTAJES, NADA)


# --------------------------------------------------------------- formato viejo

def _normalizar_html_gpt(html: str) -> str:
    html = html.strip()
    if html.startswith("```"):
        html = re.sub(r'^```(?:html)?\s*', '', html)
        html = re.sub(r'\s*```$', '', html)
    return html.strip()


def extraer_nota_y_originalidad(html: str) -> tuple[str, str]:
    """La nota y la originalidad del HTML viejo (las líneas NOTA FINAL y ORIGINALIDAD)."""
    from bs4 import BeautifulSoup

    html = _normalizar_html_gpt(html)
    texto = BeautifulSoup(html, "html.parser").get_text("\n")

    nota = ""
    m = re.search(r'NOTA\s*FINAL\s*:?\s*([0-9]+(?:[.,][0-9]+)?)', texto, re.IGNORECASE)
    if m:
        nota = m.group(1).replace(".", ",")

    originalidad = ""
    # El ":" es obligatorio y debe ir al inicio de línea: si no, cualquier mención
    # de "originalidad" en el texto de retroalimentación se captura por error.
    m = re.search(r'^\s*ORIGINALIDAD\s*:\s*([^\n]+)', texto, re.IGNORECASE | re.MULTILINE)
    if m:
        valor = m.group(1).strip()
        for sep in ('.', '\n', '|', '<'):
            if sep in valor:
                valor = valor.split(sep)[0].strip()
        originalidad = valor

    return nota, originalidad


# Una línea con un número en el HTML viejo: la etiqueta (en negrita o no), su
# valor y el <br> que la cierra. Igual en correccion.js.
_LINEA_TOTALES = re.compile(
    r"(?:<(?:b|strong)>\s*)?(?:NOTA\s*FINAL|PUNTAJE\s*TOTAL)\s*:?\s*(?:</(?:b|strong)>)?[^<\n]*(?:<br\s*/?>)?\n?",
    re.IGNORECASE)
_LINEA_EVALUACION = re.compile(
    r"(?:<(?:b|strong)>\s*)?EVALUACI[OÓ]N\s*:\s*(?:</(?:b|strong)>)?[^<\n]*(?:<br\s*/?>)?\n?",
    re.IGNORECASE)
_PARRAFO_VACIO = re.compile(r"<p>\s*(?:<br\s*/?>\s*)*</p>\n?", re.IGNORECASE)


def quitar_numeros(html: str, muestra: str) -> str:
    """El HTML viejo sin los números que el semestre no muestra.

    `puntajes` quita PUNTAJE TOTAL y NOTA FINAL; `nada` quita además cada
    «EVALUACIÓN: x / 3». Con `nota` sale tal cual.
    """
    if muestra not in (PUNTAJES, NADA):
        return html
    salida = _LINEA_TOTALES.sub("", html)
    if muestra == NADA:
        salida = _LINEA_EVALUACION.sub("", salida)
    # Un <br> que quedó justo antes del cierre del párrafo, y los párrafos vacíos.
    salida = re.sub(r"<br\s*/?>\s*</p>", "</p>", salida, flags=re.IGNORECASE)
    return _PARRAFO_VACIO.sub("", salida)


# --------------------------------------------------------------- formato nuevo

def datos_json(texto) -> dict | None:
    """El objeto de una corrección del formato nuevo, o None si no lo es."""
    t = str(texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    if not t.startswith("{"):
        return None
    try:
        datos = json.loads(t)
    except ValueError:
        return None
    if isinstance(datos, dict) and isinstance(datos.get("preguntas"), list):
        return datos
    return None


def _coma(f: Fraction) -> str:
    """2 → "2"; 1/2 → "0,5". Para escribirle un puntaje a una persona."""
    return _punto(f).replace(".", ",")


def _punto(f: Fraction) -> str:
    """2 → "2"; 1/2 → "0.5". Como se guardan los puntajes en el log (Puntajes)."""
    if f.denominator == 1:
        return str(f.numerator)
    return repr(float(f))


def rubrica(escala: _escala.Escala) -> list[Fraction]:
    """Los puntajes que puede tener una pregunta: 0; 0,5; y los enteros hasta el máximo."""
    maximo = _escala._fraccion(escala.puntaje_maximo_pregunta)
    valores = [Fraction(0), Fraction(1, 2)] + [Fraction(i) for i in range(1, math.floor(maximo) + 1)]
    if maximo not in valores:
        valores.append(maximo)
    return [v for v in valores if v <= maximo]


def texto_rubrica(escala: _escala.Escala) -> str:
    return "; ".join(_coma(v) for v in rubrica(escala))


_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


def leer_puntaje(valor, escala: _escala.Escala) -> Fraction | None:
    """El puntaje como fracción, o None si no es uno de la rúbrica."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
        return None
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    texto = valor.strip() if isinstance(valor, str) else repr(valor)
    if not _NUMERO.fullmatch(texto):
        return None
    f = Fraction(texto.replace(",", "."))
    return f if f in rubrica(escala) else None

def _texto_valor(valor) -> str:
    """Cómo se muestra un puntaje que no se entiende, en el aviso."""
    if isinstance(valor, str):
        return valor.strip() or "vacío"
    if valor is None:
        return "vacío"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def _texto(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def leer(texto, escala: _escala.Escala | None = None, n_preguntas: int | None = None) -> dict:
    """La corrección del modelo (JSON o HTML) como diccionario, con la nota calculada.

    {"formato", "preguntas", "originalidad", "justificacion_originalidad",
     "retroalimentacion", "html", "puntajes", "logro", "nota", "problemas", "avisos"}

    `puntajes` ("3;2;0.5"), `logro` ("0.8333") y `nota` ("6,5") quedan vacíos
    si algún puntaje no se entiende; `problemas` dice cuál. `avisos` trae lo
    que conviene mirar sin impedir la nota (menos bloques que preguntas).
    `html` es el texto viejo tal cual (vacío en el formato nuevo).
    """
    escala = escala or _escala.POR_DEFECTO
    datos = datos_json(texto)
    if datos is None:
        crudo = str(texto or "")
        nota, originalidad = extraer_nota_y_originalidad(crudo) if crudo.strip() else ("", "")
        try:
            logro = escala.logro(nota) if nota else None
        except ValueError:
            logro = None
        return {
            "formato": HTML, "preguntas": [], "originalidad": originalidad,
            "justificacion_originalidad": "", "retroalimentacion": "", "html": crudo,
            "puntajes": "", "logro": _escala.texto_logro(logro) if logro is not None else "",
            "nota": nota, "problemas": [], "avisos": [],
        }

    preguntas = []
    for i, p in enumerate(datos.get("preguntas") or [], 1):
        p = p if isinstance(p, dict) else {}
        puntaje = p.get("puntaje")
        preguntas.append({
            "rotulo": _texto(p.get("rotulo")) or f"P{i}",
            "respuesta": _texto(p.get("respuesta")),
            "puntaje": puntaje if isinstance(puntaje, (int, float, str)) and not isinstance(puntaje, bool) else "",
            "justificacion": _texto(p.get("justificacion")),
        })
    c = {
        "formato": JSON, "preguntas": preguntas,
        "originalidad": _texto(datos.get("originalidad")),
        "justificacion_originalidad": _texto(datos.get("justificacion_originalidad")),
        "retroalimentacion": _texto(datos.get("retroalimentacion")),
        "html": "", "puntajes": "", "logro": "", "nota": "", "problemas": [], "avisos": [],
    }
    return calcular(c, escala, n_preguntas)


def calcular(c: dict, escala: _escala.Escala | None = None, n_preguntas: int | None = None) -> dict:
    """Valida los puntajes de una corrección nueva y calcula logro y nota. Devuelve otra."""
    escala = escala or _escala.POR_DEFECTO
    c = {**c, "preguntas": [dict(p) for p in c["preguntas"]], "problemas": [], "avisos": []}
    if c["formato"] != JSON:
        return c
    puntajes = []
    for p in c["preguntas"]:
        f = leer_puntaje(p["puntaje"], escala)
        if f is None:
            c["problemas"].append(f"{p['rotulo']}: el puntaje «{_texto_valor(p['puntaje'])}» no está en la "
                                  f"rúbrica ({texto_rubrica(escala)}).")
        else:
            p["puntaje"] = _punto(f)
        puntajes.append(f)
    if not c["preguntas"]:
        c["problemas"].append("La corrección no trae preguntas.")
    if n_preguntas and len(c["preguntas"]) and len(c["preguntas"]) != n_preguntas:
        n = len(c["preguntas"])
        if n < n_preguntas:
            c["avisos"].append(f"La IA devolvió {_plural(n, 'bloque', 'bloques')} para {n_preguntas} preguntas: "
                               f"puede haber juntado preguntas. La nota se calculó sobre {_plural(n, 'bloque', 'bloques')}.")
        else:
            c["avisos"].append(f"La IA devolvió {n} bloques para {_plural(n_preguntas, 'pregunta', 'preguntas')}.")
    if c["problemas"]:
        c.update(puntajes="", logro="", nota="")
        return c
    logro = escala.logro_de(puntajes)
    c.update(puntajes=";".join(_punto(f) for f in puntajes), logro=_escala.texto_logro(logro),
             nota=escala.texto(escala.nota(logro)))
    return c


def logro_exacto(puntajes: str, escala: _escala.Escala | None = None) -> Fraction | None:
    """El logro exacto de una lista de puntajes como la guarda el log ("3;2;0.5"), o None."""
    escala = escala or _escala.POR_DEFECTO
    partes = [p for p in str(puntajes or "").split(";") if p.strip()]
    if not partes:
        return None
    try:
        return escala.logro_de(partes)
    except (ValueError, ZeroDivisionError):
        return None


# --------------------------------------------------------------- decisiones del docente

def aplicar(c: dict, decision: dict | None, escala: _escala.Escala | None = None) -> tuple[dict, list[str]]:
    """La corrección nueva con lo que el docente cambió en Revisar, y la lista de cambios.

    La decisión trae solo lo que cambió: `puntajes` y `justificaciones` (listas
    por pregunta), `originalidad`, `retroalimentacion`.
    """
    d = decision or {}
    nueva = {**c, "preguntas": [dict(p) for p in c["preguntas"]]}
    cambios = []
    antes = ";".join(_texto_valor(p["puntaje"]) for p in c["preguntas"])
    puntajes = d.get("puntajes")
    if isinstance(puntajes, list):
        for p, valor in zip(nueva["preguntas"], puntajes):
            if valor is not None and valor != "":
                p["puntaje"] = valor
    justificaciones = d.get("justificaciones")
    if isinstance(justificaciones, list):
        if any(isinstance(j, str) and j.strip() != p["justificacion"]
               for p, j in zip(nueva["preguntas"], justificaciones)):
            cambios.append("justificaciones")
        for p, j in zip(nueva["preguntas"], justificaciones):
            if isinstance(j, str):
                p["justificacion"] = j.strip()
    for campo, nombre in (("originalidad", "originalidad"), ("retroalimentacion", "retroalimentación")):
        valor = d.get(campo)
        if isinstance(valor, str) and valor.strip() and valor.strip() != c.get(campo, ""):
            if campo == "originalidad":
                cambios.append(f"originalidad {c.get(campo) or '—'} → {valor.strip()}")
            else:
                cambios.append(nombre)
            nueva[campo] = valor.strip()
    nueva = calcular(nueva, escala)
    despues = ";".join(_texto_valor(p["puntaje"]) for p in nueva["preguntas"])
    if despues != antes:
        cambios.insert(0, f"puntajes {antes} → {despues}")
    return nueva, cambios


def desde_decision(decision: dict | None, n_preguntas: int, escala: _escala.Escala | None = None) -> dict:
    """La corrección que escribe el docente a mano en el formato nuevo («Las corrijo yo»)."""
    d = decision or {}
    puntajes = d.get("puntajes") if isinstance(d.get("puntajes"), list) else []
    justificaciones = d.get("justificaciones") if isinstance(d.get("justificaciones"), list) else []
    n = max(len(puntajes), n_preguntas or 0)
    c = {
        "formato": JSON,
        "preguntas": [{"rotulo": f"P{i + 1}", "respuesta": "",
                       "puntaje": puntajes[i] if i < len(puntajes) and puntajes[i] is not None else "",
                       "justificacion": _texto(justificaciones[i]) if i < len(justificaciones) else ""}
                      for i in range(n)],
        "originalidad": _texto(d.get("originalidad")), "justificacion_originalidad": "",
        "retroalimentacion": _texto(d.get("retroalimentacion")),
        "html": "", "puntajes": "", "logro": "", "nota": "", "problemas": [], "avisos": [],
    }
    return calcular(c, escala)


# --------------------------------------------------------------- armado

def _esc(texto: str) -> str:
    """Como `escapar` de la página: &, <, > y comillas dobles."""
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _con_saltos(texto: str) -> str:
    return "<br>\n".join(_esc(linea) for linea in str(texto).replace("\r\n", "\n").split("\n"))


def _rotulo(p: dict) -> str:
    r = p["rotulo"]
    return r if r.endswith(".") else f"{r}."


def _puntaje_coma(valor) -> str:
    t = _texto_valor(valor)
    return t.replace(".", ",") if _NUMERO.fullmatch(t) else t


def _maximo(escala: _escala.Escala) -> str:
    return _coma(_escala._fraccion(escala.puntaje_maximo_pregunta))


def _total(c: dict, escala: _escala.Escala) -> str:
    suma = sum(_escala._fraccion(p) for p in c["puntajes"].split(";"))
    maximo = _escala._fraccion(escala.puntaje_maximo_pregunta) * len(c["preguntas"])
    return f"{_coma(suma)} de {_coma(maximo)} puntos"


def armar_html(c: dict, muestra: str = NOTA, escala: _escala.Escala | None = None) -> str:
    """El bloque que va en {EVALUACION} del correo, con los números que el semestre muestra."""
    if c["formato"] != JSON:
        return c["html"] if muestra == NOTA else quitar_numeros(c["html"], muestra)
    escala = escala or _escala.POR_DEFECTO
    varias = len(c["preguntas"]) > 1
    partes = ["<p><strong>EVALUACIÓN SEGÚN PAUTA</strong></p>"]
    for p in c["preguntas"]:
        lineas = [f"<u>{_esc(_rotulo(p))}</u>"] if varias else []
        if p["respuesta"]:
            lineas.append(f"<b>RESPUESTA:</b> {_con_saltos(p['respuesta'])}")
        if muestra != NADA:
            lineas.append(f"<b>EVALUACIÓN:</b> {_puntaje_coma(p['puntaje'])} / {_maximo(escala)} puntos")
        if p["justificacion"]:
            lineas.append(f"<b>JUSTIFICACIÓN:</b> {_con_saltos(p['justificacion'])}")
        if lineas:
            partes.append("<p>" + "<br>\n".join(lineas) + "</p>")
    partes.append("<hr>")
    if muestra == NOTA and c["nota"]:
        lineas = [f"<b>PUNTAJE TOTAL:</b> {_total(c, escala)}"] if varias else []
        lineas.append(f"<b>NOTA FINAL:</b> {c['nota']}")
        partes.append("<p>" + "<br>\n".join(lineas) + "</p>")
    if c["originalidad"]:
        partes.append(f"<p><b>ORIGINALIDAD:</b> {_esc(c['originalidad'])}</p>")
    if c["justificacion_originalidad"]:
        partes.append(f"<p><b>JUSTIFICACIÓN ORIGINALIDAD:</b> {_con_saltos(c['justificacion_originalidad'])}</p>")
    if c["retroalimentacion"]:
        partes.append(f"<p><b>RETROALIMENTACIÓN:</b><br>\n{_con_saltos(c['retroalimentacion'])}</p>")
    return "\n".join(partes)


def texto_docente(c: dict, escala: _escala.Escala | None = None) -> str:
    """La corrección para el equipo docente: puntajes, NOTA FINAL y originalidad, siempre.

    En el formato viejo es el HTML tal como lo dejó el modelo (sin ```html).
    """
    if c["formato"] != JSON:
        return _normalizar_html_gpt(c["html"])
    escala = escala or _escala.POR_DEFECTO
    lineas = ["EVALUACIÓN SEGÚN PAUTA"]
    for p in c["preguntas"]:
        lineas.append("")
        lineas.append(_rotulo(p))
        if p["respuesta"]:
            lineas.append(f"RESPUESTA: {p['respuesta']}")
        lineas.append(f"EVALUACIÓN: {_puntaje_coma(p['puntaje'])} / {_maximo(escala)} puntos")
        if p["justificacion"]:
            lineas.append(f"JUSTIFICACIÓN: {p['justificacion']}")
    lineas.append("")
    if c["nota"] and len(c["preguntas"]) > 1:
        lineas.append(f"PUNTAJE TOTAL: {_total(c, escala)}")
    lineas.append(f"NOTA FINAL: {c['nota'] or 'sin nota'}")
    if c["originalidad"]:
        lineas.append(f"ORIGINALIDAD: {c['originalidad']}")
    if c["justificacion_originalidad"]:
        lineas.append(f"JUSTIFICACIÓN ORIGINALIDAD: {c['justificacion_originalidad']}")
    if c["retroalimentacion"]:
        lineas.append(f"RETROALIMENTACIÓN: {c['retroalimentacion']}")
    for aviso in c["problemas"] + c["avisos"]:
        lineas.append(f"AVISO: {aviso}")
    return "\n".join(lineas)


# --------------------------------------------------------------- el prompt

_PIDE_JSON = re.compile(r"\bJSON\b")


def pide_json(prompt: str | None) -> bool:
    """Si el prompt de corrección pide la salida en JSON (el formato nuevo).

    El prompt viejo pide HTML con NOTA FINAL; el nuevo declara la salida JSON
    con «"puntaje"». Se mira el texto: cada semestre conserva su prompt.
    """
    t = str(prompt or "")
    return bool(_PIDE_JSON.search(t)) and '"puntaje"' in t
