"""
Prueba un prompt de evaluación distinto sobre respuestas ya corregidas.

Toma N respuestas al azar de las que el curso ya evaluó, las vuelve a pasar por
el modelo con un prompt candidato, y compara casilla por casilla contra la nota
y la originalidad que se les puso en su momento. Sirve para saber si un cambio
de prompt corre la distribución de originalidad antes de aplicarlo al curso.

    python -m modulos.tests.experimento --prompt nuevo.md
    python -m modulos.tests.experimento --prompt nuevo.md -n 30 --semana 4
    python -m modulos.tests.experimento --prompt nuevo.md -n 10 --dry-run

**No manda un solo correo, no toca `notas.csv` y no escribe en el log.** La nota
del alumno es la que se le comunicó; esto es un ensayo aparte y su resultado
vive en un CSV propio. Lo único que gasta es API.

El muestreo es aleatorio con semilla (`--semilla`, 19 por defecto), así que dos
corridas con la misma semilla eligen las mismas respuestas: es lo que permite
comparar dos prompts candidatos sobre la misma muestra en vez de sobre dos
muestras distintas.
"""

import csv
import random
import sys
from datetime import datetime
from pathlib import Path

from modulos import datos as _datos
from modulos.datos import reportes as _reportes

from . import config
from .evaluar import extraer_nota_y_originalidad
from .ia_prompts import evaluar_respuesta
from .preguntas import cargar_semana

SEMILLA_DEFAULT = 19
N_DEFAULT = 20

COLUMNAS = [
    "Correo", "Nombre", "Semana", "Grupo",
    "NotaAntes", "NotaDespues", "DeltaNota",
    "OriginalidadAntes", "OriginalidadDespues", "DeltaNivel",
    "ModeloAntes", "ModeloDespues", "TokensEntrada", "TokensSalida",
    "Respuesta", "EvaluacionNueva",
]


def _anunciar_semestre() -> str:
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[EXPERIMENTO] semestre {sid}")
    return sid


def candidatas(semana: int | None = None, semestre_id: str | None = None) -> list[dict]:
    """Las casillas reevaluables: tienen el texto del alumno y una nota puesta.

    Sale del mismo `panel()` que alimenta la reportería, así que "lo que se
    evaluó" significa exactamente lo mismo acá que en los gráficos.
    """
    filas = _reportes.filtrar(_reportes.panel(semestre_id, _datos.TESTS))
    elegibles = [f for f in filas
                 if f["Respuesta"].strip() and f["Nota"] is not None]
    if semana is not None:
        elegibles = [f for f in elegibles if f["Item"] == str(semana)]
    return elegibles


def muestrear(filas: list[dict], n: int, semilla: int) -> list[dict]:
    """N casillas al azar, reproducible. Si se piden más de las que hay, van todas."""
    if n >= len(filas):
        return list(filas)
    return random.Random(semilla).sample(filas, n)


def _comparar(fila: dict, nota_nueva: str, originalidad_nueva: str) -> dict:
    """Las diferencias de una casilla entre la evaluación original y la nueva."""
    antes = fila["Nota"]
    despues = _reportes.nota_a_float(nota_nueva)
    nivel_antes = _reportes.nivel_originalidad(fila["Originalidad"])
    nivel_despues = _reportes.nivel_originalidad(originalidad_nueva)
    return {
        "NotaDespues": despues,
        "DeltaNota": (round(despues - antes, 2)
                      if despues is not None and antes is not None else None),
        "DeltaNivel": (nivel_despues - nivel_antes
                       if nivel_despues is not None and nivel_antes is not None else None),
    }


def _signos(valores: list) -> tuple[int, int, int]:
    """Cuántos subieron, bajaron y quedaron igual, ignorando los que no se pudo comparar."""
    limpios = [v for v in valores if v is not None]
    return (sum(1 for v in limpios if v > 0),
            sum(1 for v in limpios if v < 0),
            sum(1 for v in limpios if v == 0))


def _distribuciones(resultados: list[dict]) -> list[dict]:
    """Distribución de originalidad antes y después, sobre la misma muestra.

    Se arma con `distribucion_originalidad` en vez de contar acá: es la misma
    función que usa la reportería, así que los porcentajes se calculan igual.
    """
    antes = {d["Originalidad"].lower(): d for d in _reportes.distribucion_originalidad(
        [{"Originalidad": r["OriginalidadAntes"]} for r in resultados])}
    despues = {d["Originalidad"].lower(): d for d in _reportes.distribucion_originalidad(
        [{"Originalidad": r["OriginalidadDespues"]} for r in resultados])}

    etiquetas = sorted(
        set(antes) | set(despues),
        key=lambda e: (_reportes.nivel_originalidad(e) or 99, e),
    )
    return [{
        "Originalidad": e.title(),
        "Antes": antes.get(e, {}).get("Evaluaciones", 0),
        "AntesPct": antes.get(e, {}).get("Porcentaje", 0.0) or 0.0,
        "Despues": despues.get(e, {}).get("Evaluaciones", 0),
        "DespuesPct": despues.get(e, {}).get("Porcentaje", 0.0) or 0.0,
    } for e in etiquetas]


def _imprimir_comparacion(resultados: list[dict]) -> None:
    notas_antes = [r["NotaAntes"] for r in resultados if r["NotaAntes"] is not None]
    notas_despues = [r["NotaDespues"] for r in resultados if r["NotaDespues"] is not None]
    deltas = [r["DeltaNota"] for r in resultados]
    niveles = [r["DeltaNivel"] for r in resultados]

    print("\n=== NOTAS ===")
    if notas_antes:
        print(f"  media antes:   {sum(notas_antes) / len(notas_antes):.2f}")
    if notas_despues:
        print(f"  media después: {sum(notas_despues) / len(notas_despues):.2f}")
    sube, baja, igual = _signos(deltas)
    print(f"  subieron {sube}, bajaron {baja}, iguales {igual}")

    print("\n=== ORIGINALIDAD ===")
    sube, baja, igual = _signos(niveles)
    print(f"  subieron {sube}, bajaron {baja}, iguales {igual}")
    print(f"  {'categoría':12s} {'antes':>14s} {'después':>14s}")
    for d in _distribuciones(resultados):
        print(f"  {d['Originalidad']:12s} "
              f"{d['Antes']:5d} ({d['AntesPct']:4.1f}%) "
              f"{d['Despues']:5d} ({d['DespuesPct']:4.1f}%)")

    # La correlación se recalcula sobre la muestra reevaluada con las dos
    # etiquetas, para ver si el prompt nuevo separa mejor o peor la
    # originalidad de la nota.
    for cuando, orig, nota in (("antes", "OriginalidadAntes", "NotaAntes"),
                               ("después", "OriginalidadDespues", "NotaDespues")):
        c = _reportes.correlacion_originalidad_nota(
            [{"Originalidad": r[orig], "Nota": r[nota]} for r in resultados])
        print(f"  correlación originalidad–nota ({cuando}): "
              f"{'—' if c['R'] is None else c['R']}  (n={c['N']})")


def _escribir_csv(resultados: list[dict], destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
        w.writeheader()
        w.writerows(resultados)
    return destino


def main(prompt: Path, n: int = N_DEFAULT, semana: int | None = None,
         semilla: int = SEMILLA_DEFAULT, dry_run: bool = False,
         salida: Path | None = None) -> list[dict]:
    _anunciar_semestre()

    plantilla = Path(prompt).read_text(encoding="utf-8")
    if "{{PREGUNTAS}}" not in plantilla or "{{PAUTAS}}" not in plantilla:
        print("⚠ El prompt no tiene {{PREGUNTAS}} ni {{PAUTAS}}: el modelo va a "
              "evaluar sin ver la pregunta ni la pauta.")
    if "NOTA FINAL" not in plantilla or "ORIGINALIDAD" not in plantilla:
        print("⚠ El prompt no menciona 'NOTA FINAL:' ni 'ORIGINALIDAD:'. Sin esas "
              "etiquetas no se puede leer el resultado y la comparación sale vacía.")

    disponibles = candidatas(semana)
    ambito = f"semana {semana}" if semana is not None else "todas las semanas"
    print(f"Respuestas ya evaluadas ({ambito}): {len(disponibles)}")
    if not disponibles:
        print("No hay nada que reevaluar.")
        return []

    muestra = muestrear(disponibles, n, semilla)
    print(f"Muestra: {len(muestra)} (semilla {semilla})\n")

    if dry_run:
        for f in muestra:
            print(f"→ {f['Nombre']:30s} semana {f['Item']:>3s}  nota actual "
                  f"{f['NotaTexto'] or '?'}, originalidad {f['Originalidad'] or '?'}")
        print(f"\nNo se llamó al modelo. Serían {len(muestra)} llamadas.")
        return []

    semanas: dict[int, object] = {}
    resultados = []
    fallidas = 0

    for i, fila in enumerate(muestra, start=1):
        etiqueta = f"{fila['Nombre'][:28]:28s} sem {fila['Item']:>3s}"
        try:
            num = int(fila["Item"])
        except ValueError:
            fallidas += 1
            print(f"✗ {etiqueta}: ítem no numérico, no puedo cargar sus preguntas")
            continue

        if num not in semanas:
            try:
                semanas[num] = cargar_semana(num)
            except Exception as e:  # noqa: BLE001
                semanas[num] = None
                print(f"⚠ semana {num}: {e}")
        info = semanas[num]
        if info is None:
            fallidas += 1
            continue

        grupo_info = info.para_grupo(fila["Grupo"] or "control")

        try:
            html = evaluar_respuesta(grupo_info.preguntas, grupo_info.pautas,
                                     fila["Respuesta"], plantilla=plantilla)
        except Exception as e:  # noqa: BLE001
            fallidas += 1
            print(f"✗ {etiqueta}: error del modelo: {e}")
            continue

        nota_nueva, orig_nueva = extraer_nota_y_originalidad(html)
        meta = getattr(html, "meta", {}) or {}
        comparacion = _comparar(fila, nota_nueva, orig_nueva)

        resultados.append({
            "Correo": fila["Correo"],
            "Nombre": fila["Nombre"],
            "Semana": fila["Item"],
            "Grupo": fila["Grupo"],
            "NotaAntes": fila["Nota"],
            "OriginalidadAntes": fila["Originalidad"],
            "OriginalidadDespues": orig_nueva,
            "ModeloAntes": fila["Modelo"],
            "ModeloDespues": meta.get("modelo") or config.MODELO,
            "TokensEntrada": meta.get("prompt_tokens") or "",
            "TokensSalida": meta.get("completion_tokens") or "",
            "Respuesta": fila["Respuesta"],
            "EvaluacionNueva": str(html),
            **comparacion,
        })

        flecha = ("=" if comparacion["DeltaNivel"] in (0, None)
                  else "↑" if comparacion["DeltaNivel"] > 0 else "↓")
        print(f"✓ [{i}/{len(muestra)}] {etiqueta}: "
              f"nota {fila['NotaTexto'] or '?'} → {nota_nueva or '?'}, "
              f"originalidad {fila['Originalidad'] or '?'} → {orig_nueva or '?'} {flecha}")

    if not resultados:
        print("\nNo se pudo reevaluar ninguna respuesta.")
        return []

    _imprimir_comparacion(resultados)

    if salida is None:
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        salida = config.DATA / f"experimento_{marca}.csv"
    destino = _escribir_csv(resultados, Path(salida))
    print(f"\nReevaluadas: {len(resultados)}  Fallidas: {fallidas}")
    print(f"Detalle: {destino}")
    return resultados


def _parsear_args(argv: list[str]) -> dict:
    opciones = {"prompt": None, "n": N_DEFAULT, "semana": None,
                "semilla": SEMILLA_DEFAULT, "dry_run": False, "salida": None}
    esperando = None

    for a in argv:
        if esperando:
            opciones[esperando] = a
            esperando = None
        elif a in ("--prompt", "-p"):
            esperando = "prompt"
        elif a in ("-n", "--n", "--cantidad"):
            esperando = "n"
        elif a in ("--semana", "-s"):
            esperando = "semana"
        elif a == "--semilla":
            esperando = "semilla"
        elif a in ("--salida", "-o"):
            esperando = "salida"
        elif a in ("--dry-run", "--dry"):
            opciones["dry_run"] = True
        else:
            print(f"Argumento desconocido: {a}")
            print(__doc__)
            raise SystemExit(2)

    if esperando:
        print(f"Falta el valor de --{esperando}")
        raise SystemExit(2)

    if not opciones["prompt"]:
        print("Falta --prompt con el archivo del prompt candidato.")
        print(__doc__)
        raise SystemExit(2)

    opciones["prompt"] = Path(opciones["prompt"])
    if not opciones["prompt"].exists():
        print(f"No existe el archivo de prompt: {opciones['prompt']}")
        raise SystemExit(2)

    for campo in ("n", "semilla"):
        opciones[campo] = int(opciones[campo])
    if opciones["semana"] is not None:
        opciones["semana"] = int(opciones["semana"])
    if opciones["salida"] is not None:
        opciones["salida"] = Path(opciones["salida"])

    return opciones


if __name__ == "__main__":
    main(**_parsear_args(sys.argv[1:]))
