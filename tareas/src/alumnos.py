"""
Gestión del CSV de alumnos y matching nombre ↔ correo.

El CSV canónico se llama data/alumnos.csv con columnas:
    nombre, correo
"""

import csv
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from . import config


def _normalizar(s: str) -> str:
    """Normaliza un nombre: sin tildes, minúsculas, sin espacios extra."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # saca tildes
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s


def _similitud(a: str, b: str) -> float:
    """Similitud entre dos nombres normalizados, 0 a 1."""
    return SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio()


def cargar_alumnos() -> list[dict]:
    """
    Carga data/alumnos.csv como lista de dicts con keys 'nombre' y 'correo'.
    """
    path = config.DATA / "alumnos.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. "
            f"Genera primero con: python -m src.alumnos <csv_crudo_de_DataCamp>"
        )

    alumnos = []
    with path.open(encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            nombre = (row.get('nombre') or '').strip()
            correo = (row.get('correo') or '').strip()
            if nombre and correo:
                alumnos.append({'nombre': nombre, 'correo': correo})
    return alumnos


def preparar_desde_csv_datacamp(path_crudo: Path) -> Path:
    """
    Toma el CSV crudo 
    """
    alumnos = []
    with path_crudo.open(encoding='utf-8-sig') as f:

        primera = f.readline()
      
        if 'Email' not in primera:
            pass  # headers vienen en la siguiente línea
        else:
            
            f.seek(0)

        reader = csv.DictReader(f)
        for row in reader:
            nombre = (row.get('Nombre') or row.get('nombre') or '').strip()
            email = (row.get('Email') or row.get('correo') or '').strip()
            if nombre and email and '@' in email:
                alumnos.append({'nombre': nombre, 'correo': email})

    destino = config.DATA / "alumnos.csv"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['nombre', 'correo'])
        writer.writeheader()
        writer.writerows(alumnos)

    print(f"✓ Generado {destino} con {len(alumnos)} alumnos")
    return destino


def buscar_correo(nombre_html: str, alumnos: list[dict],
                  umbral_auto: float = 0.82,
                  umbral_candidato: float = 0.55) -> tuple[str | None, list[tuple[dict, float]]]:
    """
    Intenta matchear un nombre del HTML con un alumno del CSV.

    Devuelve (correo, candidatos):
    - Si no, devuelve None y una lista de candidatos ordenados por similitud.
    """
    puntuados = [(a, _similitud(nombre_html, a['nombre'])) for a in alumnos]
    puntuados.sort(key=lambda x: x[1], reverse=True)

    if puntuados and puntuados[0][1] >= umbral_auto:
        return puntuados[0][0]['correo'], puntuados

    candidatos = [(a, s) for a, s in puntuados if s >= umbral_candidato][:5]
    return None, candidatos


def resolver_interactivo(nombre_html: str, alumnos: list[dict],
                         interactivo: bool = True) -> str | None:
    correo, candidatos = buscar_correo(nombre_html, alumnos)
    if correo:
        return correo

    if not interactivo:
        print(f"  ⚠️  Sin match automático: '{nombre_html}' — correo quedará vacío, edítalo en el CSV")
        return None

    print(f"\n⚠️  No encontré automáticamente a: '{nombre_html}'")
    if candidatos:
        print("   Candidatos del CSV (ordenados por parecido):")
        for i, (a, sim) in enumerate(candidatos, start=1):
            print(f"   [{i}] {a['nombre']:35s} → {a['correo']:40s} (similitud {sim:.2f})")
    else:
        print("   (No hay candidatos razonables en el CSV)")

    print("   [m] escribir correo manualmente")
    print("   [s] saltar este integrante (no se le envía correo)")

    while True:
        eleccion = input("   → Tu elección: ").strip().lower()
        if eleccion == 's':
            return None
        if eleccion == 'm':
            correo_manual = input("   → Correo: ").strip()
            if correo_manual and '@' in correo_manual:
                return correo_manual
            print("   Correo inválido, intenta de nuevo.")
            continue
        if eleccion.isdigit():
            idx = int(eleccion) - 1
            if 0 <= idx < len(candidatos):
                return candidatos[idx][0]['correo']
        print("   Opción inválida. Usa número, 'm' o 's'.")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Uso: python -m src.alumnos <csv_crudo_de_DataCamp>")
        sys.exit(1)
    preparar_desde_csv_datacamp(Path(sys.argv[1]))
