"""
Agregaciones para la reportería del curso.

Todo sale de `panel()`: una fila por (alumno, ítem) con lo que se sabe de esa
casilla. El resto de las funciones son cortes de esa misma tabla, así que una
métrica se calcula en un solo lugar y no puede discrepar entre dos vistas.

Sin pandas a propósito. El resto de `modulos/` usa el `csv` de la stdlib, y la
reportería no es razón para meterle una dependencia pesada a la capa de datos:
quien quiera un DataFrame hace `pd.DataFrame(reportes.panel())` en la app, que
es donde pandas ya vive. Así estas agregaciones sirven igual desde la app, desde
un script o desde un servidor, sin arrastrar nada.
"""

from __future__ import annotations

from . import alumnos as _alumnos
from . import log as _log
from . import notas as _notas
from .esquema import TESTS

# Cómo se ordenan las categorías de originalidad al graficar. El modelo las
# escribe en texto libre, así que se comparan en minúscula y sin depender de
# que estén todas presentes.
ORDEN_ORIGINALIDAD = ["muy baja", "baja", "media", "alta", "muy alta"]


def nota_a_float(texto: str | float | None) -> float | None:
    """Convierte la nota a número.

    Las notas se guardan en formato chileno con coma ("6,5"). Pasarlas a
    `float()` o a `pd.to_numeric` sin esto devuelve NaN y las métricas quedan
    todas vacías sin avisar.
    """
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    limpio = str(texto).strip().replace(",", ".")
    if not limpio:
        return None
    try:
        return float(limpio)
    except ValueError:
        return None


def _hay(valor: str | None) -> bool:
    """Si una marca de estado tiene contenido.

    `Enviado` y `Respondio` mezclan dos formatos: fecha ISO cuando lo escribió
    el flujo, y el literal "SI" cuando lo escribió la migración, que prefirió
    eso antes que inventar una fecha. Para saber si ocurrió basta con que no
    esté vacío.
    """
    return bool((valor or "").strip())


def _orden_item(item: str):
    """Ordena ítems: las semanas por número, las tareas alfabéticamente."""
    texto = str(item).strip()
    return (0, int(texto), "") if texto.isdigit() else (1, 0, texto)


def panel(semestre_id: str | None = None, flujo: str = TESTS) -> list[dict]:
    """Una fila por (alumno, ítem), con todo lo que se sabe de esa casilla.

    Es la tabla base de la reportería. Cruza las tres fuentes: la identidad del
    alumno, su estado en `notas.csv` y los textos del log. Solo aparecen los
    ítems que existen en `notas.csv`, así que un semestre a medio andar no
    inventa semanas futuras.
    """
    gente = {a["Correo"].strip().lower(): a
             for a in _alumnos.leer(semestre_id) if a.get("Correo", "").strip()}

    textos = {}
    for fila in _log.como_interacciones(semestre_id):
        if fila.get("Flujo") == flujo:
            textos[(fila["Correo"].strip().lower(), str(fila["Item"]))] = fila

    filas = []
    for estado in _notas.leer(semestre_id, flujo=flujo):
        correo = estado.get("Correo", "").strip().lower()
        item = str(estado.get("Item", "")).strip()
        alumno = gente.get(correo, {})
        extra = textos.get((correo, item), {})
        nota = nota_a_float(estado.get("Nota"))

        # Tener nota implica haber respondido. En los semestres migrados la
        # columna `Respondio` quedó vacía aunque haya nota, y sin esto los
        # "pendientes de evaluar" salen negativos.
        respondio = (_hay(estado.get("Respondio"))
                     or _hay(extra.get("Respuesta"))
                     or nota is not None)
        enviado_registrado = _hay(estado.get("Enviado"))
        # Si respondió o tiene nota, es que se le envió: el registro del envío
        # falta porque se hizo desde otro equipo. Sin esta inferencia la tasa de
        # respuesta pasa de 100% y "sin responder" queda negativo. Es el mismo
        # criterio que aplica la migración al reconstruir el estado.
        enviado = enviado_registrado or respondio or nota is not None

        filas.append({
            "Correo": correo,
            "Nombre": alumno.get("Nombre", "") or correo,
            "Grupo": (alumno.get("Grupo", "") or "").strip().lower(),
            "EnRoster": correo in gente,
            "Item": item,
            "Enviado": enviado,
            "EnvioRegistrado": enviado_registrado,
            "Respondio": respondio,
            "Nota": nota,
            "NotaTexto": (estado.get("Nota") or "").strip(),
            "Originalidad": (estado.get("Originalidad") or "").strip(),
            "Modelo": (extra.get("Modelo") or "").strip(),
            "FechaEnvio": (extra.get("FechaEnvio") or "").strip(),
            "FechaRespuesta": (extra.get("FechaRespuesta") or "").strip(),
            "Respuesta": extra.get("Respuesta", ""),
            "EvaluacionIA": extra.get("EvaluacionIA", ""),
        })

    filas.sort(key=lambda f: (_orden_item(f["Item"]), f["Nombre"].lower()))
    return filas


def filtrar(filas: list[dict], items=None, grupos=None, solo_roster=True) -> list[dict]:
    """Recorta el panel. Se usa para que los filtros de la app no se repitan."""
    salida = filas
    if solo_roster:
        salida = [f for f in salida if f["EnRoster"]]
    if items:
        elegidos = {str(i) for i in items}
        salida = [f for f in salida if f["Item"] in elegidos]
    if grupos:
        elegidos = {str(g).lower() for g in grupos}
        salida = [f for f in salida if f["Grupo"] in elegidos]
    return salida


def items(filas: list[dict]) -> list[str]:
    """Los ítems presentes, en orden natural."""
    return sorted({f["Item"] for f in filas}, key=_orden_item)


def grupos(filas: list[dict]) -> list[str]:
    return sorted({f["Grupo"] for f in filas if f["Grupo"]})


def _agregar(filas: list[dict]) -> dict:
    """Las métricas de un conjunto de casillas. Único lugar donde se calculan."""
    enviados = [f for f in filas if f["Enviado"]]
    respondieron = [f for f in filas if f["Respondio"]]
    notas = [f["Nota"] for f in filas if f["Nota"] is not None]
    sin_registro = [f for f in filas if f["Enviado"] and not f["EnvioRegistrado"]]

    return {
        "Casillas": len(filas),
        "Enviados": len(enviados),
        "EnviosSinRegistro": len(sin_registro),
        "Respondieron": len(respondieron),
        "SinResponder": len(enviados) - len(respondieron),
        "Evaluados": len(notas),
        "PendientesEvaluar": len(respondieron) - len(notas),
        "TasaRespuesta": round(len(respondieron) / len(enviados) * 100, 1) if enviados else None,
        "NotaMedia": round(sum(notas) / len(notas), 2) if notas else None,
        "NotaMin": min(notas) if notas else None,
        "NotaMax": max(notas) if notas else None,
    }


def resumen(filas: list[dict]) -> dict:
    """KPIs del conjunto completo, más cuántas personas distintas hay."""
    base = _agregar(filas)
    base["Alumnos"] = len({f["Correo"] for f in filas})
    base["Items"] = len({f["Item"] for f in filas})
    modelos = {f["Modelo"] for f in filas if f["Modelo"]}
    base["Modelos"] = sorted(modelos)
    return base


def por_item(filas: list[dict]) -> list[dict]:
    """Una fila por ítem: la evolución del curso semana a semana."""
    grupos_item: dict[str, list] = {}
    for f in filas:
        grupos_item.setdefault(f["Item"], []).append(f)
    return [{"Item": item, **_agregar(sub)}
            for item, sub in sorted(grupos_item.items(), key=lambda kv: _orden_item(kv[0]))]


def por_grupo(filas: list[dict]) -> list[dict]:
    """Una fila por (ítem, grupo): la comparación del estudio de impacto."""
    celdas: dict[tuple, list] = {}
    for f in filas:
        celdas.setdefault((f["Item"], f["Grupo"] or "sin grupo"), []).append(f)
    return [{"Item": item, "Grupo": grupo, **_agregar(sub)}
            for (item, grupo), sub in sorted(
                celdas.items(), key=lambda kv: (_orden_item(kv[0][0]), kv[0][1]))]


def por_alumno(filas: list[dict]) -> list[dict]:
    """Una fila por alumno, para ver quién se está descolgando."""
    gente: dict[str, list] = {}
    for f in filas:
        gente.setdefault(f["Correo"], []).append(f)

    salida = []
    for correo, sub in gente.items():
        agg = _agregar(sub)
        salida.append({
            "Correo": correo,
            "Nombre": sub[0]["Nombre"],
            "Grupo": sub[0]["Grupo"],
            **agg,
        })
    salida.sort(key=lambda f: (f["NotaMedia"] is not None, f["NotaMedia"] or 0))
    return salida


def ficha(correo: str, filas: list[dict]) -> dict:
    """El detalle de un alumno: sus casillas en orden, con textos completos."""
    correo = correo.strip().lower()
    suyas = [f for f in filas if f["Correo"] == correo]
    if not suyas:
        return {}
    return {
        "Correo": correo,
        "Nombre": suyas[0]["Nombre"],
        "Grupo": suyas[0]["Grupo"],
        "Resumen": _agregar(suyas),
        "Casillas": sorted(suyas, key=lambda f: _orden_item(f["Item"])),
    }


def distribucion_notas(filas: list[dict], ancho: float = 0.5) -> list[dict]:
    """Histograma de notas, en tramos de `ancho`."""
    notas = [f["Nota"] for f in filas if f["Nota"] is not None]
    if not notas:
        return []
    cubos: dict[float, int] = {}
    for n in notas:
        piso = round((n // ancho) * ancho, 2)
        cubos[piso] = cubos.get(piso, 0) + 1
    return [{"Tramo": piso, "Etiqueta": f"{piso:.1f}–{piso + ancho:.1f}", "Alumnos": n}
            for piso, n in sorted(cubos.items())]


def nivel_originalidad(texto: str | None) -> int | None:
    """La categoría de originalidad como número de 1 a 5, o None si no se reconoce.

    El modelo la escribe en texto libre ("Muy Baja", "media", "ALTA"), así que
    se compara en minúscula y sin acentos de más. Tener un número es lo que
    permite promediarla y correlacionarla con la nota; el texto se conserva
    igual para mostrarlo tal como vino.
    """
    clave = (texto or "").strip().lower()
    if clave in ORDEN_ORIGINALIDAD:
        return ORDEN_ORIGINALIDAD.index(clave) + 1
    return None


def _pares_originalidad_nota(filas: list[dict]) -> list[tuple[int, float]]:
    """Las casillas que tienen las dos cosas: nivel de originalidad y nota."""
    pares = []
    for f in filas:
        nivel = nivel_originalidad(f.get("Originalidad"))
        nota = f.get("Nota")
        if nivel is not None and nota is not None:
            pares.append((nivel, float(nota)))
    return pares


def distribucion_originalidad(filas: list[dict]) -> list[dict]:
    """Cuántas evaluaciones cayeron en cada categoría de originalidad.

    `Porcentaje` es sobre el total de evaluaciones que tienen categoría, no
    sobre todas las casillas: comparar dos semanas con distinta cantidad de
    respuestas usando cuentas absolutas no dice nada.
    """
    cuenta: dict[str, int] = {}
    for f in filas:
        etiqueta = (f.get("Originalidad") or "").strip()
        if etiqueta:
            cuenta[etiqueta] = cuenta.get(etiqueta, 0) + 1

    total = sum(cuenta.values())

    def orden(etiqueta: str):
        clave = etiqueta.lower()
        return (ORDEN_ORIGINALIDAD.index(clave)
                if clave in ORDEN_ORIGINALIDAD else len(ORDEN_ORIGINALIDAD), clave)

    return [{"Originalidad": k,
             "Nivel": nivel_originalidad(k),
             "Evaluaciones": v,
             "Porcentaje": round(v / total * 100, 1) if total else None}
            for k, v in sorted(cuenta.items(), key=lambda kv: orden(kv[0]))]


def originalidad_por_item(filas: list[dict]) -> list[dict]:
    """Cómo se reparte la originalidad en cada semana.

    Una fila por (ítem, categoría) con su porcentaje **dentro de esa semana**,
    que es lo que hace comparable una semana con otra. `NivelMedio` es el
    promedio de la escala 1–5 de esa semana: sirve para ver de un vistazo si la
    distribución se está corriendo hacia arriba o hacia abajo.
    """
    por_item: dict[str, list] = {}
    for f in filas:
        por_item.setdefault(f["Item"], []).append(f)

    salida = []
    for item, sub in sorted(por_item.items(), key=lambda kv: _orden_item(kv[0])):
        niveles = [nivel_originalidad(f.get("Originalidad")) for f in sub]
        niveles = [n for n in niveles if n is not None]
        medio = round(sum(niveles) / len(niveles), 2) if niveles else None
        for fila in distribucion_originalidad(sub):
            salida.append({"Item": item, "NivelMedio": medio, **fila})
    return salida


def originalidad_vs_nota(filas: list[dict]) -> list[dict]:
    """La nota que sacó cada categoría de originalidad.

    Es la tabla que responde "¿a quien el modelo le ve menos originalidad, le
    pone además peor nota?". Son dos juicios distintos del mismo prompt, así
    que verlos juntos es lo que permite saber si están midiendo lo mismo.
    """
    celdas: dict[str, list] = {}
    for f in filas:
        etiqueta = (f.get("Originalidad") or "").strip()
        if etiqueta and f.get("Nota") is not None:
            celdas.setdefault(etiqueta, []).append(float(f["Nota"]))

    def orden(etiqueta: str):
        nivel = nivel_originalidad(etiqueta)
        return (nivel if nivel is not None else 99, etiqueta.lower())

    return [{"Originalidad": etiqueta,
             "Nivel": nivel_originalidad(etiqueta),
             "Evaluaciones": len(notas),
             "NotaMedia": round(sum(notas) / len(notas), 2),
             "NotaMin": min(notas),
             "NotaMax": max(notas)}
            for etiqueta, notas in sorted(celdas.items(), key=lambda kv: orden(kv[0]))]


def correlacion_originalidad_nota(filas: list[dict]) -> dict:
    """Cuánto se mueven juntas la originalidad y la nota.

    Pearson entre el nivel 1–5 y la nota. Como la originalidad es ordinal y
    solo toma cinco valores, esto equivale a una correlación de rangos por ese
    lado: sirve para ver la dirección y la fuerza, no para leerlo como una
    regresión. Con menos de tres pares devuelve `R` en None en vez de un número
    que no significaría nada.
    """
    pares = _pares_originalidad_nota(filas)
    n = len(pares)
    base = {"N": n, "R": None, "NivelMedio": None, "NotaMedia": None}
    if n < 3:
        return base

    niveles = [p[0] for p in pares]
    notas = [p[1] for p in pares]
    mx = sum(niveles) / n
    my = sum(notas) / n
    base["NivelMedio"] = round(mx, 2)
    base["NotaMedia"] = round(my, 2)

    cov = sum((x - mx) * (y - my) for x, y in pares)
    varx = sum((x - mx) ** 2 for x in niveles)
    vary = sum((y - my) ** 2 for y in notas)
    if varx == 0 or vary == 0:
        # Todas las respuestas cayeron en la misma categoría, o todas sacaron
        # la misma nota: no hay variación que correlacionar.
        return base

    base["R"] = round(cov / (varx ** 0.5 * vary ** 0.5), 3)
    return base


def sin_responder(filas: list[dict]) -> list[dict]:
    """A quiénes se les envió y no han contestado. Ordenado por ítem."""
    return sorted(
        [f for f in filas if f["Enviado"] and not f["Respondio"]],
        key=lambda f: (_orden_item(f["Item"]), f["Nombre"].lower()),
    )


def pendientes_de_evaluar(filas: list[dict]) -> list[dict]:
    """Respondieron pero todavía no tienen nota."""
    return sorted(
        [f for f in filas if f["Respondio"] and f["Nota"] is None],
        key=lambda f: (_orden_item(f["Item"]), f["Nombre"].lower()),
    )
