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

from modulos import datos

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


def _tokens(s: str) -> set[str]:
    """Los tokens de un nombre normalizado, sin puntos ni guiones."""
    limpio = _normalizar(s).replace('.', ' ').replace('-', ' ')
    return {t for t in limpio.split() if t}


def _por_nombre_incompleto(nombre_html: str, alumnos: list[dict]) -> str | None:
    """
    El caso frecuente: el alumno firma con su nombre y un apellido, y el roster
    trae los dos. La similitud de texto lo deja en 0.72-0.81, bajo el umbral.

    Se acepta solo si todos los tokens del HTML están en el nombre del roster, hay
    al menos dos, y ningún otro alumno cumple lo mismo. Pedir dos tokens deja
    fuera el apellido suelto, que es justo donde el emparejamiento se equivoca, y
    exigir unicidad evita elegir entre dos alumnos que comparten el primer nombre.

    También al revés: la tabla trae nombre y dos apellidos y el roster nombre y
    uno (T2 de 2026-2, similitud 0.81 con umbral 0.82). Ahí se pide además que
    el primer nombre sea el mismo, para no tomar "Rojo Soto" por "Ana Rojo".
    """
    tokens = _tokens(nombre_html)
    if len(tokens) < 2:
        return None
    primero = _normalizar(nombre_html).replace('.', ' ').replace('-', ' ').split()[0]

    def del_roster_en_la_tabla(a: dict) -> bool:
        suyos = _tokens(a['nombre'])
        return (len(suyos) >= 2 and suyos < tokens
                and _normalizar(a['nombre']).replace('.', ' ').replace('-', ' ').split()[0] == primero)

    contenidos = [a for a in alumnos
                  if tokens <= _tokens(a['nombre']) or del_roster_en_la_tabla(a)]
    if len(contenidos) == 1:
        return contenidos[0]['correo']
    return None


def nombre_de_pila(correo: str, nombre_tabla: str = "") -> str:
    """
    El nombre con que se saluda al alumno: el primero de la nómina.

    Antes salía de la tabla de roles, y quien firmó solo con el apellido
    recibía "Hola Rojo," (T1 de la prueba del 19/11/2026). Si el correo no está
    en la nómina, queda la primera palabra de la tabla.
    """
    fila = datos.alumnos.por_correo().get((correo or "").strip().lower()) or {}
    nombre = (fila.get('Nombre') or '').strip()
    if ',' in nombre:  # "Apellido Apellido, Nombre"
        nombre = nombre.split(',', 1)[1].strip()
    palabras = (nombre or nombre_tabla or '').split()
    return palabras[0] if palabras else "estudiante"


def cargar_alumnos() -> list[dict]:
    """
    El roster del semestre activo, como lista de dicts con 'nombre' y 'correo'.

    Sale de datos.alumnos, que es el único roster del curso; este flujo tenía el
    suyo aparte, con los mismos alumnos escritos en otras columnas.
    """
    alumnos = []
    for fila in datos.alumnos.leer():
        nombre = (fila.get('Nombre') or '').strip()
        correo = (fila.get('Correo') or '').strip()
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

    correo = _por_nombre_incompleto(nombre_html, alumnos)
    if correo:
        return correo, puntuados

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
        print("Uso: python -m modulos.tareas.alumnos <csv_crudo_de_DataCamp>")
        sys.exit(1)
    preparar_desde_csv_datacamp(Path(sys.argv[1]))
