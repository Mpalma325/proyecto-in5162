"""
Qué pasaría al generar las preguntas de una tarea, sin llamar al modelo.

Recorre las entregas y dice, para cada grupo: si se pudieron recortar las cuatro
preguntas, de dónde salen los integrantes, cuáles no resuelven a un correo y con
qué candidatos, y qué se va a saltar y por qué. Al final cruza contra el roster
para mostrar quién del curso queda sin pregunta.

    python -m modulos.tareas.chequeo T1

Solo lee: no llama a la API, no escribe archivos y no manda correos. Se puede
correr las veces que haga falta mientras se arreglan las entregas.
"""

import sys

from modulos import datos

from . import asignacion as _asignacion
from . import config
from .alumnos import cargar_alumnos, buscar_correo
from .generar import _leer_entrega, _asignar_preguntas
from .limpieza_html import (revisar_entrega, extraer_tabla_roles,
                            es_nombre_placeholder)


def _integrantes_de(secciones: dict, autores: list[str]) -> tuple[list[str], str]:
    """Los nombres del grupo y de dónde salieron."""
    filas = extraer_tabla_roles(secciones.get("roles_html", ""))
    nombres = [list(f.values())[0] for f in filas if list(f.values())]
    nombres = [n for n in nombres if not es_nombre_placeholder(n)]
    if nombres:
        return nombres, "tabla de roles"
    return autores, "campo author del documento"


def revisar(tarea: str) -> dict:
    """El chequeo completo de una tarea, como datos. La impresión va aparte."""
    alumnos = cargar_alumnos()
    elegido = _asignacion.leer(tarea)
    entregas_dir = config.ENTREGAS / tarea
    archivos = sorted(entregas_dir.glob("*.html"))

    grupos = []
    for path in archivos:
        secciones, autores, fuente = _leer_entrega(path)
        motivos = revisar_entrega(secciones)
        sin_roles = [m for m in motivos if "roles" in m]
        nombres, origen = _integrantes_de(secciones, autores)

        bloqueo = [m for m in motivos if m not in sin_roles]
        if sin_roles and not nombres:
            bloqueo.append("tampoco se pudo saber quiénes son los integrantes")

        integrantes = []
        for nombre in nombres:
            correo, candidatos = buscar_correo(nombre, alumnos)
            integrantes.append({
                "nombre": nombre,
                "correo": correo or "",
                "candidatos": [(a["nombre"], a["correo"], round(s, 2))
                               for a, s in candidatos[:3]] if not correo else [],
            })

        asignacion = {}
        if sin_roles and nombres and not bloqueo:
            asignacion = _asignacion.aplicar(
                _asignar_preguntas(nombres, path.name), elegido, path.name)

        grupos.append({
            "archivo": path.name,
            "fuente": fuente,
            "secciones": {n: len(secciones.get(f"p{n}", "")) for n in (1, 2, 3, 4)},
            "origen_integrantes": origen,
            "integrantes": integrantes,
            "asignacion": asignacion,
            "a_mano": [n for n in asignacion if (path.name, n) in elegido],
            "bloqueo": bloqueo,
            "sin_roles": bool(sin_roles) and not bloqueo,
        })

    con_correo = {i["correo"].lower()
                  for g in grupos if not g["bloqueo"]
                  for i in g["integrantes"] if i["correo"]}
    roster = [(a["Nombre"], a["Correo"]) for a in datos.alumnos.leer()]
    sin_entrega = [n for n, c in roster if c.lower() not in con_correo]

    return {
        "tarea": tarea,
        "carpeta": entregas_dir,
        "grupos": grupos,
        "sin_entrega": sin_entrega,
        "total_roster": len(roster),
    }


def imprimir(informe: dict) -> int:
    """Deja el chequeo en pantalla. Devuelve cuántas cosas piden intervención."""
    from modulos import semestre as _sem

    print(f"=== Chequeo previo — {informe['tarea']} ===")
    print(f"[CHEQUEO] semestre {_sem.activo_o_error()}")
    print(f"Entregas en {informe['carpeta']}\n")

    if not informe["grupos"]:
        print("No hay HTMLs en esa carpeta. Súbelos desde la app, en "
              "Datos y Configuración → Entregas (Tareas).")
        return 1

    pendientes = 0
    a_generar = 0

    for g in informe["grupos"]:
        print(f"[{g['archivo']}]")
        if g["fuente"] != g["archivo"]:
            print(f"  el HTML viene sin código: se lee {g['fuente']}")
        cortes = "  ".join(f"p{n}={c}" for n, c in g["secciones"].items())
        print(f"  secciones: {cortes}")

        if g["bloqueo"]:
            print("  ✗ SE VA A SALTAR — no se llama al modelo:")
            for m in g["bloqueo"]:
                print(f"      - {m}")
            pendientes += 1
            print()
            continue

        print(f"  integrantes según: {g['origen_integrantes']}")
        if g["sin_roles"]:
            print("  ⚠  Sin tabla de roles: se reparten las preguntas. "
                  "Revisa la asignación antes de generar.")

        for i in g["integrantes"]:
            asignada = g["asignacion"].get(i["nombre"], "")
            marca = "*" if i["nombre"] in g["a_mano"] else ""
            etiqueta = f" [{asignada}{marca}]" if asignada else ""
            if i["correo"]:
                print(f"    ✓ {i['nombre']:28s}{etiqueta:6s} → {i['correo']}")
                a_generar += 1
            else:
                print(f"    ⚠ {i['nombre']:28s}{etiqueta:6s} → SIN CORREO, hay que elegirlo a mano")
                for nombre, correo, sim in i["candidatos"]:
                    print(f"        candidato: {nombre:30s} {correo:34s} (parecido {sim})")
                if not i["candidatos"]:
                    print("        (ningún candidato razonable en el roster)")
                pendientes += 1
        print()

    print("-" * 60)
    print(f"Preguntas que se generarían ahora: {a_generar}")
    print(f"Grupos que se saltarían: {sum(1 for g in informe['grupos'] if g['bloqueo'])}")
    print(f"Cosas que piden intervención: {pendientes}")

    print(f"\nDel roster ({informe['total_roster']} personas), quedan sin pregunta "
          f"{len(informe['sin_entrega'])}:")
    for nombre in informe["sin_entrega"]:
        print(f"   - {nombre}")
    print("\n(Incluye al equipo docente si está en el roster: revisa la lista, "
          "no todos son alumnos que no entregaron.)")

    return pendientes


def main(tarea: str) -> int:
    return imprimir(revisar(tarea))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    tarea = args[0].upper() if args else config.TAREA_DEFAULT
    sys.exit(0 if main(tarea) == 0 else 0)
