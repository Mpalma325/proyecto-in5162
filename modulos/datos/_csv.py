"""Lectura y escritura de los CSV del semestre. Detalle interno del módulo.

Lo que se escribe acá va siempre en UTF-8 y separado por coma. Lo que se lee
puede venir de una planilla: Excel con configuración regional en español
guarda los CSV separados por punto y coma, a veces con BOM y a veces en
cp1252. `lector` acepta todo eso, y es por donde pasa cada lectura de un CSV
que arma una persona (alumnos.csv, preguntas.csv).
"""

import csv
import io
from pathlib import Path

from modulos import semestre as _semestre


def ruta(nombre: str, semestre_id: str | None = None) -> Path:
    """Ubicación de una de las tablas, en la raíz del semestre."""
    return _semestre.raiz(semestre_id) / nombre


def _decodificar(datos: bytes) -> str:
    """UTF-8 (con o sin BOM) o, si no lo es, cp1252: lo que guarda Excel en Windows."""
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def separador(primera_linea: str) -> str:
    """Coma o punto y coma: el que más aparece en la cabecera, fuera de comillas.
    Si empatan (una sola columna), coma."""
    fuera, entre_comillas = [], False
    for c in primera_linea:
        if c == '"':
            entre_comillas = not entre_comillas
        elif not entre_comillas:
            fuera.append(c)
    return ";" if fuera.count(";") > fuera.count(",") else ","


def lector(p: Path) -> csv.DictReader:
    """Un DictReader sobre el archivo, con separador y codificación detectados."""
    texto = _decodificar(Path(p).read_bytes())
    # splitlines corta también en "\r" solo (Excel para Mac antiguo).
    return csv.DictReader(io.StringIO(texto, newline=""),
                          delimiter=separador((texto.splitlines() or [""])[0]))


def leer(nombre: str, semestre_id: str | None = None) -> list[dict]:
    p = ruta(nombre, semestre_id)
    if not p.exists():
        return []
    return list(lector(p))


def escribir(nombre: str, filas: list[dict], columnas: list[str],
             semestre_id: str | None = None) -> Path:
    """Reescribe la tabla completa. No usar para el log.

    Conserva las columnas que el archivo ya tenga y el llamador no conozca: van
    después de las suyas, como en `log.fusionar`. Sin eso, un código más viejo
    que el archivo borraría al escribir las columnas que agregó uno más nuevo,
    y una columna puesta a mano en alumnos.csv se perdía al asignar grupos.

    Escribe a un `.tmp` y lo pone en su lugar al final: si el proceso muere a
    mitad, queda el archivo anterior entero y no uno truncado.
    """
    p = ruta(nombre, semestre_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    campos = list(columnas) + [c for c in cabecera(p) if c and c not in columnas]
    tmp = p.with_suffix(p.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            for fila in filas:
                w.writerow({c: fila.get(c, "") for c in campos})
        tmp.replace(p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return p


def cabecera(p: Path) -> list[str]:
    """Los nombres de columna del archivo, sin leerlo entero."""
    if not p.exists():
        return []
    with p.open("rb") as f:
        primera = (_decodificar(f.readline()).splitlines() or [""])[0]
    return next(csv.reader([primera], delimiter=separador(primera)), [])


def _ampliar_columnas(p: Path, columnas: list[str]) -> None:
    """Agrega al archivo las columnas que le falten, conservando las filas.

    Cuando el esquema crece, los archivos que ya existen siguen con la cabecera
    vieja. Escribir filas nuevas contra esa cabecera correría los valores de
    columna sin avisar, así que el archivo se reescribe una vez con las
    columnas nuevas vacías. Es idempotente: si no falta ninguna, no toca nada.
    """
    actuales = cabecera(p)
    if not actuales:
        return
    faltan = [c for c in columnas if c not in actuales]
    if not faltan:
        return

    filas = list(lector(p))
    nuevas = actuales + faltan
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=nuevas, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({c: (fila.get(c) or "") for c in nuevas})
    tmp.replace(p)


def agregar(nombre: str, fila: dict, columnas: list[str],
            semestre_id: str | None = None) -> Path:
    """Agrega una fila al final, sin leer ni reescribir lo que ya está.

    Es lo que hace seguro el log: dos procesos escribiendo a la vez pueden
    intercalar filas, pero ninguno pisa lo del otro.
    """
    p = ruta(nombre, semestre_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not p.exists()
    if not nuevo:
        _ampliar_columnas(p, columnas)
    # Se escribe contra la cabecera real del archivo, no contra la lista que
    # pide el llamador: si alguien agregó una columna a mano, respetarla evita
    # correr todos los valores una posición.
    campos = columnas if nuevo else (cabecera(p) or columnas)
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in campos})
    return p
