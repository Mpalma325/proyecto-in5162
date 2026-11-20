"""
Cambiar la escala de notas de Tests y recalcular las notas que ya están.

    python -m modulos.datos.escala_trabajo --escala '{"tipo": "lineal", "minima": 1.0, "maxima": 7.0,
        "decimales": 1, "aprobacion": null, "exigencia": null, "puntaje_maximo_pregunta": 3}' --por profe@x.cl

Lo pide Configuración › Semestre (trabajo `datos.escala`). Con `--dry-run`
(«Ver qué cambia») no escribe nada: dice cuántas notas cambian, cuántas ya le
llegaron al alumno con número, la media antes y después, el mayor cambio y las
notas que quedan fijas. En real escribe `escala_notas.json`, recalcula
`notas.csv` y deja un evento `recalculo` por nota que cambió. No llama al
modelo ni manda correos.

De dónde sale el logro de cada nota, en este orden:

1. Los puntajes de la última evaluación (`Puntajes` en el log), si con la
   escala actual dan la nota que está. Es el logro exacto: "0.5;0" en la escala
   4–7 con dos decimales es 4,25, y pasado a un decimal da 4,3. Desde el
   `Logro` guardado (0.0833) daría 4,2.
2. El `Logro` de notas.csv, si con la escala actual da la nota que está y no
   es solo la inversa redondeada a cuatro decimales.
3. La inversa de la escala actual sobre la nota, que es exacta.

Quedan fijas, y se listan, las notas de un ajuste sin logro (el ajuste lo deja
vacío cuando la nota cae fuera de la escala, como un 3,0 en una de 4 a 7), las
que están fuera de la escala actual y las que no son un número. Las
correcciones por revisar no tienen nota guardada: la toman con la escala nueva
cuando salen.
"""

import argparse
import json
import os
import sys
from fractions import Fraction

from modulos import escala as _escala
from modulos import semestre as _semestre

from . import TESTS, _csv
from . import log as _log
from . import migracion as _migracion
from .esquema import COLUMNAS_NOTAS, NOTAS

# La línea que lee la página para la confirmación de «Guardar y recalcular»
# (web/public/escala.js, resumenSimulacion). La salida visible no la muestra.
MARCA = "@@escala"


def _clave(fila: dict) -> tuple[str, str]:
    return (fila.get("Correo") or "").strip().lower(), str(fila.get("Item", "")).strip()


def _numero(texto: str) -> Fraction | None:
    try:
        return Fraction((texto or "").strip().replace(",", "."))
    except (ValueError, ZeroDivisionError):
        return None


def _decimal(x: Fraction) -> str:
    """Una media o una diferencia para leer: dos decimales, con coma."""
    return f"{float(x):.2f}".replace(".", ",")


def _nombres(semestre_id: str | None) -> dict[str, str]:
    """El nombre de cada test para la salida: «Control 2», o «semana 3» en un semestre de antes."""
    nombres = {}
    for fila in _csv.leer("tests_semanales/preguntas.csv", semestre_id):
        if (fila.get("Instancia") or "").strip():
            i = fila["Instancia"].strip()
            tipo = (fila.get("Tipo") or "").strip() or "Instancia"
            nombres[i] = f"{tipo} {(fila.get('Numero') or '').strip() or i}"
        elif (fila.get("Semana") or "").strip():
            nombres[fila["Semana"].strip()] = f"semana {fila['Semana'].strip()}"
    return nombres


def _historia(semestre_id: str | None) -> dict[tuple, dict]:
    """Por casilla de test: la última evaluación o ajuste (lo que fijó la nota) y si el alumno vio un número."""
    casillas: dict[tuple, dict] = {}
    for e in _log.leer(semestre_id, flujo=TESTS):
        ev = e.get("Evento")
        if ev not in ("evaluacion", "ajuste"):
            continue
        c = casillas.setdefault(_clave(e), {"base": None, "comunicada": False})
        c["base"] = e
        # El número le llegó en el bloque NOTA FINAL de la corrección o en el
        # aviso de un ajuste («tu nota quedó en 6,5»), que es el que trae MessageId.
        if (ev == "evaluacion" and "NOTA FINAL" in (e.get("EvaluacionIA") or "")) or \
                (ev == "ajuste" and (e.get("MessageId") or "").strip()):
            c["comunicada"] = True
    return casillas


def _logro(fila: dict, base: dict | None, vieja: _escala.Escala) -> tuple[Fraction | None, str]:
    """El logro de la nota de esa fila, o (None, por qué queda fija). Ver el docstring del módulo."""
    actual = _numero(fila.get("Nota", ""))
    if actual is None:
        return None, "no es un número"
    if base and base.get("Evento") == "ajuste" and not (base.get("Logro") or "").strip():
        # Un ajuste sin logro quedó fuera de la escala de su momento (o es de
        # antes de que el ajuste lo anotara): se respeta tal cual.
        return None, "ajuste fuera de la escala"

    def explica(logro) -> bool:
        try:
            return 0 <= logro <= 1 and Fraction(vieja.nota(logro)) == actual
        except ValueError:
            return False

    if base and base.get("Evento") == "evaluacion" and (base.get("Puntajes") or "").strip():
        try:
            logro = vieja.logro_de([p for p in base["Puntajes"].split(";") if p.strip()])
        except (ValueError, ZeroDivisionError):
            logro = None
        if logro is not None and explica(logro):
            return logro, ""
    inversa = vieja.logro(actual)
    guardado = _numero(fila.get("Logro", ""))
    # El Logro guardado tiene cuatro decimales. Si es el de la inversa, la
    # inversa es la exacta (0.8333 es 5/6); si es otro y da la nota, sabe algo
    # que la nota redondeada no dice.
    if guardado is not None and explica(guardado) and (
            inversa is None or _escala.texto_logro(inversa) != _escala.texto_logro(guardado)):
        return guardado, ""
    if inversa is None:
        return None, f"fuera de la escala {vieja.describir()}"
    return inversa, ""


def calcular(nueva: _escala.Escala, semestre_id: str | None = None) -> dict:
    """Qué pasaría con las notas de Tests si la escala fuera `nueva`. No escribe nada."""
    vieja = _escala.leer(semestre_id)
    filas = _csv.leer(NOTAS, semestre_id)
    historia = _historia(semestre_id)
    cambios, fijas, iguales, antes, despues = [], [], 0, [], []
    for fila in filas:
        nota = (fila.get("Nota") or "").strip()
        if fila.get("Flujo") != TESTS or not nota:
            continue
        h = historia.get(_clave(fila), {"base": None, "comunicada": False})
        logro, motivo = _logro(fila, h["base"], vieja)
        valor = _numero(nota)
        if valor is not None:
            antes.append(valor)
        if logro is None:
            fijas.append({"fila": fila, "motivo": motivo})
            if valor is not None:
                despues.append(valor)
            continue
        texto = nueva.texto(nueva.nota(logro))
        despues.append(Fraction(nueva.nota(logro)))
        if texto == nota:
            iguales += 1
            continue
        cambios.append({"fila": fila, "antes": nota, "despues": texto, "logro": logro,
                        "diferencia": Fraction(nueva.nota(logro)) - valor,
                        "comunicada": h["comunicada"]})
    mayor = max(cambios, key=lambda c: abs(c["diferencia"]), default=None)
    return {
        "vieja": vieja, "nueva": nueva, "cambios": cambios, "fijas": fijas, "iguales": iguales,
        "comunicadas": sum(1 for c in cambios if c["comunicada"] and c["diferencia"] != 0),
        "media_antes": sum(antes) / len(antes) if antes else None,
        "media_despues": sum(despues) / len(despues) if despues else None,
        "mayor": mayor,
    }


def _escribir_escala(nueva: _escala.Escala, semestre_id: str | None) -> None:
    """escala_notas.json, de una vez: un corte a la mitad deja el archivo anterior entero."""
    ruta = _semestre.raiz(semestre_id) / _escala.ARCHIVO
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(nueva.como_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ruta)


def aplicar(r: dict, por: str, semestre_id: str | None = None) -> None:
    """Escribe la escala, las notas recalculadas y un `recalculo` por cada una que cambió."""
    _escribir_escala(r["nueva"], semestre_id)
    if not r["cambios"]:
        return
    nuevas = {_clave(c["fila"]): c for c in r["cambios"]}
    filas = _csv.leer(NOTAS, semestre_id)
    for fila in filas:
        c = nuevas.get(_clave(fila)) if fila.get("Flujo") == TESTS else None
        if c:
            fila["Nota"] = c["despues"]
            fila["Logro"] = _escala.texto_logro(c["logro"])
    _csv.escribir(NOTAS, filas, COLUMNAS_NOTAS, semestre_id)
    detalle = f"escala {r['vieja'].describir()} → {r['nueva'].describir()}; por {por}"
    for c in r["cambios"]:
        f = c["fila"]
        _log.registrar("recalculo", TESTS, str(f.get("Item", "")), f.get("Correo", ""), semestre_id,
                       Nota=c["despues"], Logro=_escala.texto_logro(c["logro"]), Detalle=detalle)


def _imprimir(r: dict, nombres: dict[str, str], simular: bool) -> None:
    def nombre(f: dict) -> str:
        item = str(f.get("Item", "")).strip()
        return f"{f.get('Correo', '')} · {nombres.get(item, 'test ' + item)}"

    total = len(r["cambios"]) + len(r["fijas"]) + r["iguales"]
    print(f"Escala actual: {r['vieja'].describir()} ({r['vieja'].rango()})")
    print(f"Escala nueva:  {r['nueva'].describir()} ({r['nueva'].rango()})")
    print(f"Notas de Tests: {total} · cambian {len(r['cambios'])} · quedan igual {r['iguales']}"
          f" · fijas {len(r['fijas'])}")
    print(f"Notas que el alumno ya vio con número y cambian: {r['comunicadas']}")
    if r["media_antes"] is not None:
        print(f"Media: {_decimal(r['media_antes'])} → {_decimal(r['media_despues'])}")
    if r["mayor"]:
        m = r["mayor"]
        signo = "+" if m["diferencia"] > 0 else "−"
        print(f"Mayor cambio: {nombre(m['fila'])}: {m['antes']} → {m['despues']} "
              f"({signo}{_decimal(abs(m['diferencia']))})")
    simbolo = "→" if simular else "✓"
    for c in r["cambios"]:
        visto = " (ya la vio)" if c["comunicada"] and c["diferencia"] != 0 else ""
        print(f"  {simbolo} {nombre(c['fila'])}: {c['antes']} → {c['despues']}{visto}")
    for f in r["fijas"]:
        print(f"  ⊘ {nombre(f['fila'])}: {f['fila'].get('Nota', '')} queda fija ({f['motivo']})")
    print(MARCA + " " + json.dumps({
        "escala": r["nueva"].como_dict(),
        "notas": total, "cambian": len(r["cambios"]), "fijas": len(r["fijas"]),
        "comunicadas": r["comunicadas"],
        "media_antes": _decimal(r["media_antes"]) if r["media_antes"] is not None else "",
        "media_despues": _decimal(r["media_despues"]) if r["media_despues"] is not None else "",
    }, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cambiar la escala de notas de Tests y recalcular.")
    p.add_argument("--escala", required=True, help="la escala nueva, en JSON (escala_notas.json)")
    p.add_argument("--por", required=True, help="quién la cambia")
    p.add_argument("--dry-run", action="store_true", help="solo decir qué cambiaría")
    a = p.parse_args(argv)
    semestre_id = _semestre.activo_o_error()
    print(f"[ESCALA] semestre {semestre_id}" + (" · simulación: no se escribe nada" if a.dry_run else ""))
    try:
        nueva = _escala.desde_dict(json.loads(a.escala))
    except (ValueError, TypeError) as e:
        print(f"✗ La escala no sirve: {e}")
        return 1
    if not a.dry_run:
        # Un semestre con el esquema viejo se migra antes de leer (en simulación no se escribe).
        _migracion.asegurar(semestre_id)
    try:
        r = calcular(nueva, semestre_id)
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    _imprimir(r, _nombres(semestre_id), a.dry_run)
    if a.dry_run:
        print("No se escribió nada. «Guardar y recalcular» hace estos cambios.")
        return 0
    aplicar(r, a.por, semestre_id)
    print(f"✓ Escala guardada en {_escala.ARCHIVO}; {len(r['cambios'])} nota(s) recalculada(s). "
          "No se envió ningún correo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
