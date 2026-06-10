"""
Paso 1 del flujo: generar preguntas + pautas + resolver correos.

Por cada HTML en data/entregas/:
  1. Limpia el HTML y extrae las 4 preguntas + tabla de roles
  2. Llama a OpenAI para generar (pregunta, pauta) por integrante
  3. Resuelve el correo de cada integrante matcheando contra alumnos.csv
     (interactivo si no encuentra match automático)
  4. Agrega todo al CSV data/salidas/feedback_<TAREA>.csv

Uso:
    python -m src.paso1_generar              # procesa todo data/entregas/, tarea = config.TAREA_DEFAULT
    python -m src.paso1_generar T1 archivo.html   # tarea específica + archivo específico
"""

import sys
from pathlib import Path

from . import config, storage
from .alumnos import cargar_alumnos, resolver_interactivo
from .limpieza_html import limpiar_html, extraer_secciones
from .openai_client import generar_preguntas


def procesar_entrega(path_html: Path, tarea: str, alumnos: list[dict],
                     interactivo: bool = True) -> list[dict]:
    """Procesa una entrega y devuelve la lista de filas a agregar al CSV."""
    print(f"\n[{path_html.name}]")
    print(f"  → Limpiando HTML...")
    html = path_html.read_text(encoding="utf-8")
    limpio = limpiar_html(html)
    secciones = extraer_secciones(limpio)

    for k in ("p1", "p2", "p3", "p4"):
        if not secciones[k]:
            print(f"    ⚠️  Sección {k} vacía")
    if not secciones["roles_html"]:
        print(f"    ✗ Tabla de roles vacía — saltando este archivo")
        return []

    print(f"  → Llamando a {config.MODELO}...")
    resultado = generar_preguntas(secciones, secciones["roles_html"])
    tokens = resultado.get("_meta", {}).get("total_tokens", "?")
    print(f"  ✓ {tokens} tokens")

    print(f"  → Resolviendo correos...")
    filas = []
    integrantes = resultado.get("integrantes", [])
    for integrante in integrantes:
        nombre = integrante.get("nombre", "").strip()
        if not nombre:
            continue

        correo = resolver_interactivo(nombre, alumnos, interactivo=interactivo) or ""

        fila = {
            "tarea": tarea,
            "grupo_archivo": path_html.name,
            "alumno_nombre": nombre,
            "alumno_correo": correo,
            "pregunta_tarea": integrante.get("pregunta_tarea") or "",
            "pregunta": integrante.get("pregunta") or "",
            "pauta": integrante.get("pauta") or "",
            "motivo_sin_pregunta": integrante.get("motivo_sin_pregunta") or "",
        }
        filas.append(fila)

       
        marcador = "✓" if correo else "⚠"
        preg = fila["pregunta"] or f"({fila['motivo_sin_pregunta']})"
        print(f"    {marcador} {nombre:30s} → {correo or 'SIN CORREO':40s}")
        print(f"      Q: {preg[:100]}{'...' if len(preg) > 100 else ''}")

    return filas


def main(tarea: str, archivos: list[Path], interactivo: bool = True) -> None:
    alumnos = cargar_alumnos()
    print(f"Tarea: {tarea} | {len(alumnos)} alumnos en CSV | {len(archivos)} HTMLs a procesar")

    todas_las_filas = []
    for archivo in archivos:
        try:
            filas = procesar_entrega(archivo, tarea, alumnos, interactivo=interactivo)
            todas_las_filas.extend(filas)
        except Exception as e:
            print(f"  ✗ Error procesando {archivo.name}: {e}")
            continue

    if todas_las_filas:
        path_csv = storage.agregar_filas(tarea, todas_las_filas)
        print(f"\n✓ Guardado en {path_csv.relative_to(config.ROOT)}")
        print(f"  Total de filas agregadas: {len(todas_las_filas)}")

        sin_correo = [f for f in todas_las_filas if not f["alumno_correo"]]
        if sin_correo:
            print(f"\n⚠️  {len(sin_correo)} integrante(s) sin correo (edítalos manualmente en el CSV antes del paso 2):")
            for f in sin_correo:
                print(f"   - {f['alumno_nombre']} ({f['grupo_archivo']})")


if __name__ == "__main__":
    args = sys.argv[1:]

    interactivo = "--no-interactivo" not in args
    args = [a for a in args if a != "--no-interactivo"]

    tarea = config.TAREA_DEFAULT
    archivos_arg = []

    if args and args[0].upper().startswith('T') and args[0][1:].isdigit():
        tarea = args[0].upper()
        args = args[1:]

    if args:
        archivos_arg = [Path(a) for a in args]
    else:
        archivos_arg = sorted(config.ENTREGAS.glob("*.html"))
        if not archivos_arg:
            print(f"No hay HTMLs en {config.ENTREGAS}")
            sys.exit(1)

    main(tarea, archivos_arg, interactivo=interactivo)
