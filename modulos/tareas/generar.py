"""
Paso 1 del flujo: generar preguntas + pautas + resolver correos.

Por cada HTML en data/entregas/<TAREA>/:
  1. Limpia el HTML y extrae las 4 preguntas + tabla de roles
  2. Llama a OpenAI para generar (pregunta, pauta) por integrante
  3. Resuelve el correo de cada integrante matcheando contra alumnos.csv
     (interactivo si no encuentra match automático)
  4. Agrega todo al CSV data/salidas/feedback_<TAREA>.csv

Uso:
    python -m modulos.tareas.generar              # procesa data/entregas/<TAREA_DEFAULT>/
    python -m modulos.tareas.generar T1 archivo.html   # tarea específica + archivo específico
"""

import random
import sys
from pathlib import Path

from . import asignacion as _asignacion
from . import contexto as _contexto
from . import config, storage
from .alumnos import cargar_alumnos, resolver_interactivo
from .limpieza_html import (limpiar_html, extraer_secciones, extraer_autores,
                            secciones_desde_rmd, revisar_entrega,
                            es_nombre_placeholder)
from .ia_prompts import generar_preguntas


def _rescatar_sin_pregunta(integrantes: list[dict], secciones: dict,
                           path_html: Path, elegido: dict | None = None) -> list[dict]:
    """
    Segunda pasada para quien quedó sin pregunta por no aportar código.

    Pasa cuando alguien declaró solo "interpretación" o "redacción" en las cuatro
    preguntas. Igual tiene que rendir cuenta del trabajo, así que se le asigna una
    pregunta como a los grupos sin roles, en vez de dejarlo sin nada.
    """
    huerfanos = [i for i in integrantes
                 if not (i.get("pregunta") or "").strip()
                 and not es_nombre_placeholder(i.get("nombre", ""))]
    if not huerfanos:
        return integrantes

    nombres = [i["nombre"].strip() for i in huerfanos]
    asignacion = _asignacion.aplicar(
        _asignar_preguntas(nombres, path_html.name + "-rescate"),
        elegido or {}, path_html.name)
    print(f"    → Sin pregunta por roles: {', '.join(nombres)}. Se les asigna una: "
          + ", ".join(f"{n} ({p})" for n, p in asignacion.items()))

    rescatado = generar_preguntas(secciones, "", asignacion)
    por_nombre = {(i.get("nombre") or "").strip(): i
                  for i in rescatado.get("integrantes", [])}

    salida = []
    for integrante in integrantes:
        es_huerfano = any(h is integrante for h in huerfanos)
        nuevo = por_nombre.get((integrante.get("nombre") or "").strip())
        if es_huerfano and nuevo and (nuevo.get("pregunta") or "").strip():
            salida.append(nuevo)
        else:
            salida.append(integrante)
    return salida


def _contenido(secciones: dict) -> int:
    return sum(len(secciones.get(f"p{n}", "")) for n in (1, 2, 3, 4))


def _leer_entrega(path_html: Path) -> tuple[dict, list[str], str]:
    """
    Las secciones, los integrantes y de qué archivo salieron.

    Normalmente sale del HTML. Cuando el grupo renderizó el HTML antes de
    escribir el código —queda el template con los comentarios y el trabajo vive
    en el .Rmd de al lado— se usa el .Rmd, que trae más contenido. No imprime:
    devuelve la fuente y decide quien llama, porque generar y chequeo la muestran
    en lugares distintos.
    """
    html = path_html.read_text(encoding="utf-8", errors="replace")
    secciones = extraer_secciones(limpiar_html(html))
    autores = extraer_autores(html)
    fuente = path_html.name

    path_rmd = path_html.with_suffix(".Rmd")
    if path_rmd.exists():
        rmd = path_rmd.read_text(encoding="utf-8", errors="replace")
        desde_rmd = secciones_desde_rmd(rmd)
        if _contenido(desde_rmd) > _contenido(secciones):
            desde_rmd["roles_html"] = secciones["roles_html"]
            secciones = desde_rmd
            autores = extraer_autores(rmd) or autores
            fuente = path_rmd.name

    return secciones, [a for a in autores if not es_nombre_placeholder(a)], fuente


def _asignar_preguntas(nombres: list[str], semilla: str) -> dict:
    """
    Reparte P1..P4 entre los integrantes de un grupo que no declaró roles.

    Con semilla fija —el nombre del archivo— para que dos corridas sobre la
    misma entrega asignen lo mismo, igual que el reparto de grupos en tests.
    """
    orden = ["P1", "P2", "P3", "P4"]
    random.Random(semilla).shuffle(orden)
    return {nombre: orden[i % len(orden)] for i, nombre in enumerate(nombres)}


def procesar_entrega(path_html: Path, tarea: str, alumnos: list[dict],
                     interactivo: bool = True, elegido: dict | None = None) -> list[dict]:
    """Procesa una entrega y devuelve la lista de filas a agregar al CSV."""
    print(f"\n[{path_html.name}]")
    print(f"  → Limpiando HTML...")
    secciones, autores, fuente = _leer_entrega(path_html)
    if fuente != path_html.name:
        print(f"    → El HTML viene sin código; se usa {fuente}")

    for k in ("p1", "p2", "p3", "p4"):
        if not secciones[k]:
            print(f"    ⚠️  Sección {k} vacía")

    motivos = revisar_entrega(secciones)
    # Que no declaren roles no impide preguntarles: se les asigna una pregunta
    # cada uno. Lo que sí impide es no saber quiénes son.
    sin_roles = [m for m in motivos if "roles" in m]
    if sin_roles and not autores:
        motivos.append("tampoco se pudo saber quiénes son los integrantes")
    elif sin_roles:
        motivos = [m for m in motivos if m not in sin_roles]

    if motivos:
        print(f"    ✗ Saltando este archivo (no se llama al modelo):")
        for motivo in motivos:
            print(f"      - {motivo}")
        return []

    elegido = elegido or {}
    asignacion = None
    if sin_roles:
        asignacion = _asignacion.aplicar(
            _asignar_preguntas(autores, path_html.name), elegido, path_html.name)
        a_mano = [n for n in asignacion if (path_html.name, n) in elegido]
        print(f"    → Sin tabla de roles; se asigna una pregunta a cada integrante: "
              + ", ".join(f"{n} ({p})" for n, p in asignacion.items()))
        if a_mano:
            print(f"      (elegidas a mano: {', '.join(a_mano)})")

    print(f"  → Llamando a {config.MODELO}...")
    resultado = generar_preguntas(secciones, secciones["roles_html"], asignacion)
    tokens = resultado.get("_meta", {}).get("total_tokens", "?")
    print(f"  ✓ {tokens} tokens")

    integrantes = resultado.get("integrantes", [])
    integrantes = _rescatar_sin_pregunta(integrantes, secciones, path_html, elegido)

    print(f"  → Resolviendo correos...")
    filas = []
    for integrante in integrantes:
        nombre = integrante.get("nombre", "").strip()
        if es_nombre_placeholder(nombre):
            print(f"    ⚠  Fila ignorada: '{nombre}' no es el nombre de una persona")
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
    elegido = _asignacion.leer(tarea)
    print(f"Tarea: {tarea} | {len(alumnos)} alumnos en CSV | {len(archivos)} HTMLs a procesar")
    print(_contexto.describir())
    if elegido:
        print(f"  {len(elegido)} asignación(es) elegidas a mano en asignacion_{tarea}.csv")

    todas_las_filas = []
    for archivo in archivos:
        try:
            filas = procesar_entrega(archivo, tarea, alumnos,
                                     interactivo=interactivo, elegido=elegido)
            todas_las_filas.extend(filas)
        except Exception as e:
            print(f"  ✗ Error procesando {archivo.name}: {e}")
            continue

    if todas_las_filas:
        path_csv = storage.agregar_filas(tarea, todas_las_filas)
        print(f"\n✓ Guardado en {path_csv.relative_to(config.PROJECT_ROOT)}")
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
        entregas_tarea = config.ENTREGAS / tarea
        archivos_arg = sorted(entregas_tarea.glob("*.html"))
        if not archivos_arg:
            print(f"No hay HTMLs en {entregas_tarea}")
            sys.exit(1)

    main(tarea, archivos_arg, interactivo=interactivo)
