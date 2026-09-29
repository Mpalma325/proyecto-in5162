"""
Junta el log de otro equipo con el de acá.

    python -m modulos.datos.fusionar <log_del_otro.csv>
    python -m modulos.datos.fusionar <log.csv> --simular   # dice qué entraría
    python -m modulos.datos.fusionar <log.csv> --semestre 2026-2

Cuando el curso se opera desde dos computadores, cada uno acumula solo lo que
hizo: los envíos quedan donde se mandaron y las evaluaciones donde se
corrigieron. Reemplazar una carpeta por la del otro borra esa mitad; esto la
suma. Se pueden pasar los dos logs uno contra el otro y ambos equipos quedan
con la historia completa.

Al terminar deja el estado al día, que es lo que mira la reportería.
"""

import sys

from modulos import semestre as _semestre
from modulos.datos import log as _log, notas as _notas


def main(archivo: str, semestre_id: str | None = None, simular: bool = False) -> int:
    sid = semestre_id or _semestre.activo_o_error()
    print(f"[FUSIONAR] semestre {sid}")

    try:
        r = _log.fusionar(archivo, sid, simular=simular)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n{e}")
        return 2

    print(f"\nEventos en el log traído: {r['Entrantes']}")
    print(f"  ya estaban acá: {r['YaEstaban']}")
    print(f"  faltaban:       {r['Nuevas']}")
    for evento, n in sorted(r["PorEvento"].items()):
        print(f"      {evento:12s} {n}")

    if not r["Nuevas"]:
        print("\nNada que agregar: este log ya tiene todo lo del otro.")
        return 0

    if simular:
        print("\nSimulación: no se escribió nada.")
        return 0

    print(f"\nLog actualizado. Copia del anterior en {r['Respaldo']}")

    e = _notas.sincronizar_desde_log(sid)
    print(f"Estado al día: {e['FilasNuevas']} filas nuevas, "
          f"{e['Enviado']} envíos, {e['Respondio']} respuestas, {e['Nota']} notas.")
    return 0


def _parsear_args(argv: list[str]) -> dict:
    args = {"archivo": None, "semestre_id": None, "simular": False}
    resto = list(argv)
    while resto:
        a = resto.pop(0)
        if a in ("--simular", "--dry-run", "-n"):
            args["simular"] = True
        elif a in ("--semestre", "-s"):
            args["semestre_id"] = resto.pop(0) if resto else None
        elif a in ("-h", "--help"):
            print(__doc__)
            raise SystemExit(0)
        elif args["archivo"] is None:
            args["archivo"] = a
        else:
            print(f"Argumento no reconocido: {a}")
            raise SystemExit(2)
    if not args["archivo"]:
        print(__doc__)
        raise SystemExit(2)
    return args


if __name__ == "__main__":
    sys.exit(main(**_parsear_args(sys.argv[1:])))
