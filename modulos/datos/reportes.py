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

Acá solo queda `panel()`, que lee los CSV. Los cálculos viven en
`agregaciones.py`, que no depende de nada del proyecto y corre también en el
navegador; se reexportan para que todo siga llamándose `datos.reportes.X`.
"""

from __future__ import annotations

from . import alumnos as _alumnos
from . import log as _log
from . import notas as _notas
from .esquema import TESTS
from .agregaciones import (  # noqa: F401  (se reexportan)
    ORDEN_ORIGINALIDAD,
    _agregar,
    _hay,
    _orden_item,
    _pares_originalidad_nota,
    _tramo,
    casillas,
    correlacion_originalidad_nota,
    correlaciones_por_alumno,
    correlaciones_por_respuesta,
    distribucion_notas,
    distribucion_originalidad,
    ficha,
    filtrar,
    horas_en_responder,
    intervalo_r,
    grupos,
    items,
    nivel_originalidad,
    nota_a_float,
    originalidad_por_item,
    originalidad_vs_nota,
    palabras,
    pendientes_de_evaluar,
    por_alumno,
    por_grupo,
    por_item,
    resumen,
    sin_responder,
    variables_por_alumno,
    variables_por_respuesta,
)


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
