"""
Dice si la carpeta de un semestre y la de acá tienen lo mismo.

    python -m modulos.datos.comparar ruta/al/semestre-de-ella
    python -m modulos.datos.comparar ruta/al/2026-2 --semestre 2026-2

Compara por contenido, no por orden ni por fecha de archivo: el orden de las
filas no significa nada, porque todo se cruza por (Correo, Flujo, Item) y el
log se ordena por timestamp al fusionar. Dos carpetas con las mismas filas en
distinto orden son idénticas para el sistema.

Solo lee. No escribe ni corrige nada; para juntar lo que falte está
`modulos.datos.fusionar`.
"""

import csv
import sys
from pathlib import Path

from modulos import semestre as _semestre
from modulos.datos import _csv as _tablas
from modulos.datos.esquema import ALUMNOS, LOG, NOTAS


# Lo que se compara de una casilla presente en las dos tablas.
_CAMPOS_CASILLA = ("Enviado", "Respondio", "Nota", "Originalidad",
                   "Corregido", "Logro", "Descartada")


def _leer(ruta: Path) -> list[dict]:
    if not ruta.is_file():
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _clave_log(f: dict) -> tuple:
    return ((f.get("Timestamp") or "").strip(), (f.get("Flujo") or "").strip(),
            str(f.get("Item") or "").strip(), (f.get("Correo") or "").strip().lower(),
            (f.get("Evento") or "").strip())


def _clave_casilla(f: dict) -> tuple:
    return ((f.get("Correo") or "").strip().lower(), (f.get("Flujo") or "").strip(),
            str(f.get("Item") or "").strip())


def _comparar_conjuntos(mias: list[dict], suyas: list[dict], clave) -> dict:
    a = {clave(f): f for f in mias}
    b = {clave(f): f for f in suyas}
    return {"aca": len(a), "alla": len(b),
            "solo_aca": sorted(set(a) - set(b)), "solo_alla": sorted(set(b) - set(a)),
            "comunes": sorted(set(a) & set(b)), "_a": a, "_b": b}


def _linea(nombre: str, r: dict, distintos: int = 0) -> bool:
    """Imprime el veredicto de una tabla. Devuelve si coinciden."""
    igual = not r["solo_aca"] and not r["solo_alla"] and not distintos
    marca = "=" if igual else "!"
    cola = f"   con otro valor {distintos:4d}" if distintos else ""
    print(f"  [{marca}] {nombre:12s} acá {r['aca']:5d}   allá {r['alla']:5d}"
          f"   solo acá {len(r['solo_aca']):4d}   solo allá {len(r['solo_alla']):4d}"
          f"{cola}")
    return igual


def _muestra(titulo: str, claves: list, cuantas: int = 5) -> None:
    if not claves:
        return
    print(f"\n  {titulo} ({len(claves)}):")
    for k in claves[:cuantas]:
        print(f"      {' | '.join(str(x) for x in k)}")
    if len(claves) > cuantas:
        print(f"      ... y {len(claves) - cuantas} más")


def main(carpeta: str, semestre_id: str | None = None, detalle: bool = False,
         sugerir: bool = True) -> int:
    alla = Path(carpeta)
    if not alla.is_dir():
        print(f"No existe la carpeta: {alla}")
        return 2

    sid = semestre_id or _semestre.activo_o_error()
    aca = _semestre.raiz(sid)
    if aca.resolve() == alla.resolve():
        print("Es la misma carpeta.")
        return 2

    print(f"[COMPARAR] acá {aca}\n           allá {alla}\n")

    log = _comparar_conjuntos(_tablas.leer(LOG, sid), _leer(alla / LOG), _clave_log)
    notas = _comparar_conjuntos(_tablas.leer(NOTAS, sid), _leer(alla / NOTAS),
                                _clave_casilla)
    gente = _comparar_conjuntos(
        _tablas.leer(ALUMNOS, sid), _leer(alla / ALUMNOS),
        lambda f: (f.get("Correo") or "").strip().lower())

    # En las casillas que los dos tienen, el valor puede diferir: una nota
    # corregida a mano de un lado y no del otro. Eso no lo arregla fusionar, y
    # por eso se cuenta antes de imprimir: una tabla con las mismas casillas
    # pero distinto contenido no puede salir marcada como igual.
    discrepan = sorted({k for k in notas["comunes"]
                        for c in _CAMPOS_CASILLA
                        if (notas["_a"][k].get(c) or "").strip()
                        and (notas["_b"][k].get(c) or "").strip()
                        and notas["_a"][k][c].strip() != notas["_b"][k][c].strip()})

    iguales = [_linea("log_envios", log),
               _linea("notas", notas, distintos=len(discrepan)),
               _linea("alumnos", gente)]

    if detalle:
        _muestra("eventos que solo están acá", log["solo_aca"])
        _muestra("eventos que solo están allá", log["solo_alla"])
        _muestra("casillas que solo están acá", notas["solo_aca"])
        _muestra("casillas que solo están allá", notas["solo_alla"])
        _muestra("alumnos que solo están acá", gente["solo_aca"])
        _muestra("alumnos que solo están allá", gente["solo_alla"])

    print()
    if all(iguales) and not discrepan:
        print("Las dos carpetas tienen lo mismo. El orden de las filas no importa.")
        return 0

    if log["solo_aca"] or log["solo_alla"]:
        print(f"Al log le faltan eventos: {len(log['solo_alla'])} que están solo allá "
              f"y {len(log['solo_aca'])} solo acá.")
        # Quien llama desde `poner_al_dia` ya fusionó, y ahí la carpeta de
        # origen era temporal: mandarlo a correr un comando sobre una ruta que
        # ya no existe es peor que no decir nada.
        if sugerir:
            print("Se juntan con:")
            print(f"    python -m modulos.datos.fusionar {alla / LOG}")
            print("  y del otro lado, con el log de acá. Después quedan iguales.")

    if discrepan:
        print(f"\n[!] {len(discrepan)} casillas tienen distinto valor en las dos "
              f"tablas: alguien editó una nota a mano. Fusionar no las toca, "
              f"porque no sabe cuál es la buena. Hay que mirarlas:")
        for k in discrepan[:5]:
            campos = [f"{c}: {notas['_a'][k].get(c)!r} vs {notas['_b'][k].get(c)!r}"
                      for c in _CAMPOS_CASILLA
                      if (notas["_a"][k].get(c) or "").strip()
                      != (notas["_b"][k].get(c) or "").strip()]
            print(f"      {k[0]} {k[1]} {k[2]}: {'; '.join(campos)}")
        if len(discrepan) > 5:
            print(f"      ... y {len(discrepan) - 5} más (--detalle las lista)")

    if gente["solo_aca"] or gente["solo_alla"]:
        print(f"\nEl roster no coincide: {len(gente['solo_alla'])} alumnos solo allá, "
              f"{len(gente['solo_aca'])} solo acá. alumnos.csv no se fusiona; hay "
              f"que dejar una sola versión.")
    return 1


def _parsear_args(argv: list[str]) -> dict:
    args = {"carpeta": None, "semestre_id": None, "detalle": False}
    resto = list(argv)
    while resto:
        a = resto.pop(0)
        if a in ("--detalle", "-v"):
            args["detalle"] = True
        elif a in ("--semestre", "-s"):
            args["semestre_id"] = resto.pop(0) if resto else None
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        elif args["carpeta"] is None:
            args["carpeta"] = a
        else:
            print(f"Argumento no reconocido: {a}")
            raise SystemExit(2)
    if not args["carpeta"]:
        print(__doc__)
        raise SystemExit(2)
    return args


if __name__ == "__main__":
    sys.exit(main(**_parsear_args(sys.argv[1:])))
