"""
Deja esta copia del curso igual a la que te pasaron, sin perder lo tuyo.

    python -m modulos.datos.poner_al_dia ruta/al/2026-2.zip
    python -m modulos.datos.poner_al_dia ruta/a/la/carpeta/2026-2
    python -m modulos.datos.poner_al_dia ruta/al/2026-2.zip --simular

Acepta el .zip tal como llega o una carpeta ya descomprimida. Hace lo mismo en
los dos casos:

  - Si el semestre no existe acá, lo instala entero. Es el caso de la primera
    vez, y no hay nada que decidir.
  - Si ya existe, NO lo reemplaza: junta el log del otro equipo con el de acá y
    reconstruye el estado. Así no se pierde lo que se corrió de este lado, que
    es lo que pasa al descomprimir encima.

Al terminar dice si las dos copias quedaron con lo mismo y qué falta si no.
"""

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from modulos import semestre as _semestre
from modulos.datos import comparar as _comparar, log as _log, notas as _notas
from modulos.datos.esquema import ALUMNOS, LOG, NOTAS


def _raiz_del_semestre(carpeta: Path) -> Path | None:
    """La carpeta que contiene el log, esté al tope o un nivel más adentro.

    Un zip a veces trae la carpeta del semestre adentro y a veces su contenido
    suelto; buscar el archivo evita que el usuario tenga que saber cuál es.
    """
    if (carpeta / LOG).is_file() or (carpeta / ALUMNOS).is_file():
        return carpeta
    hijas = [h for h in carpeta.iterdir() if h.is_dir()]
    for h in hijas:
        if (h / LOG).is_file() or (h / ALUMNOS).is_file():
            return h
    return hijas[0] if len(hijas) == 1 else None


def _preparar(origen: Path, temporal: Path) -> tuple[Path, str]:
    """Deja el contenido accesible como carpeta y devuelve su id de semestre."""
    if origen.is_file() and origen.suffix.lower() == ".zip":
        with zipfile.ZipFile(origen) as z:
            z.extractall(temporal)
        base = _raiz_del_semestre(temporal)
    elif origen.is_dir():
        base = _raiz_del_semestre(origen)
    else:
        raise FileNotFoundError(f"No es un .zip ni una carpeta: {origen}")

    if base is None:
        raise ValueError(
            f"No encuentro {LOG} ni {ALUMNOS} dentro de {origen}. "
            f"¿Es la carpeta de un semestre?")
    return base, base.name


def main(origen: str, semestre_id: str | None = None, simular: bool = False) -> int:
    ruta = Path(origen)
    temporal = Path(tempfile.mkdtemp(prefix="in5162_"))
    try:
        base, detectado = _preparar(ruta, temporal)
        sid = semestre_id or detectado
        destino = _semestre.raiz(sid)
        print(f"[PONER AL DIA] semestre {sid}")
        print(f"  lo que te pasaron: {base}")
        print(f"  lo que tienes acá: {destino}\n")

        if not destino.exists():
            print("Acá no existe ese semestre todavía, así que se instala entero.")
            if simular:
                print("Simulación: no se copió nada.")
                return 0
            shutil.copytree(base, destino)
            print(f"Instalado en {destino}")
            print("\nListo. No había nada que fusionar: era la primera copia.")
            return 0

        # Existe de los dos lados. Fusionar en vez de reemplazar: lo que se
        # corrió acá no está en la copia que llegó, y descomprimir encima lo
        # borraría sin avisar.
        print("Ya existe acá, así que NO se reemplaza: se junta lo de los dos.\n")
        r = _log.fusionar(base / LOG, sid, simular=simular)
        print(f"Eventos en el log que te pasaron: {r['Entrantes']}")
        print(f"  ya estaban acá: {r['YaEstaban']}")
        print(f"  faltaban:       {r['Nuevas']}")
        for evento, n in sorted(r["PorEvento"].items()):
            print(f"      {evento:12s} {n}")

        if simular:
            print("\nSimulación: no se escribió nada.")
            return 0

        if r["Nuevas"]:
            print(f"\nLog actualizado. Copia del anterior en {r['Respaldo']}")
        e = _notas.sincronizar_desde_log(sid)
        print(f"Estado al día: {e['FilasNuevas']} filas nuevas, {e['Enviado']} "
              f"envíos, {e['Respondio']} respuestas, {e['Nota']} notas"
              + (f", {e['NotaAlDia']} notas atrasadas puestas al día." if e["NotaAlDia"] else "."))

        print("\n" + "-" * 60)
        print("Cómo quedaron las dos copias:\n")
        rc = _comparar.main(str(base), sid, sugerir=False)
        if rc == 0:
            print("\nListo: tu copia tiene todo lo de la que te pasaron.")
        else:
            print("\nQueda algo distinto. Si el log de acá tiene eventos que allá "
                  "no están, mándale tu log_envios.csv para que corra esto mismo "
                  "de su lado; ahí quedan iguales los dos.")
        return 0
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _parsear_args(argv: list[str]) -> dict:
    args = {"origen": None, "semestre_id": None, "simular": False}
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
        elif args["origen"] is None:
            args["origen"] = a
        else:
            print(f"Argumento no reconocido: {a}")
            raise SystemExit(2)
    if not args["origen"]:
        print(__doc__)
        raise SystemExit(2)
    return args


if __name__ == "__main__":
    try:
        sys.exit(main(**_parsear_args(sys.argv[1:])))
    except (FileNotFoundError, ValueError) as e:
        print(f"\n{e}")
        sys.exit(2)
