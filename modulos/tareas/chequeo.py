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
from . import contexto as _contexto
from . import config, storage
from .desempacar import desempacar_rars
from .alumnos import cargar_alumnos, buscar_correo
from .generar import _leer_entrega, _asignar_preguntas, identicos
from .limpieza_html import revisar_entrega, extraer_tabla_roles, nombres_de_tabla


def _integrantes_de(secciones: dict, autores: list[str]) -> tuple[list[str], str]:
    """Los nombres del grupo y de dónde salieron."""
    nombres = nombres_de_tabla(extraer_tabla_roles(secciones.get("roles_html", "")))
    if nombres:
        return nombres, "tabla de roles"
    return autores, "campo author del documento"


def revisar(tarea: str) -> dict:
    """El chequeo completo de una tarea, como datos. La impresión va aparte."""
    alumnos = cargar_alumnos()
    elegido = _asignacion.leer(tarea)
    correos = _asignacion.leer_correos(tarea)
    entregas_dir = config.ENTREGAS / tarea
    # La página sube los .rar sin abrir: se abren acá, y sus HTML quedan como
    # una entrega más (el motor los guarda en la nube).
    desempacados, rar_omitidos = desempacar_rars(entregas_dir)
    archivos = sorted(entregas_dir.glob("*.html"))
    ya_guardados = {(f["grupo_archivo"], " ".join(f["alumno_nombre"].lower().split())): f["alumno_correo"].strip()
                    for f in storage.leer_csv(tarea) if f.get("alumno_correo", "").strip()}

    repetidos = identicos(archivos)
    grupos = []
    for path in archivos:
        secciones, autores, fuente = _leer_entrega(path)
        if path.name in repetidos:
            # Mismo contenido que otra entrega: generar la salta, así que sus
            # integrantes no cuentan como si aparecieran en dos entregas.
            grupos.append({"archivo": path.name, "fuente": fuente,
                           "secciones": {n: len(secciones.get(f"p{n}", "")) for n in (1, 2, 3, 4)},
                           "origen_integrantes": "", "integrantes": [], "asignacion": {}, "a_mano": [],
                           "bloqueo": [], "sin_roles": False, "identico_a": repetidos[path.name]})
            continue
        motivos = revisar_entrega(secciones)
        sin_roles = [m for m in motivos if "roles" in m]
        nombres, origen = _integrantes_de(secciones, autores)

        bloqueo = [m for m in motivos if m not in sin_roles]
        if sin_roles and not nombres:
            bloqueo.append("tampoco se pudo saber quiénes son los integrantes")

        integrantes = []
        for nombre in nombres:
            # También vale el correo que ya quedó en feedback_<T>.csv: en T2 de
            # 2026-2 uno se emparejó a mano ahí antes de que existiera
            # correos_<T>.csv, y el chequeo lo seguía marcando sin correo.
            a_mano = (_asignacion.correo_elegido(correos, path.name, nombre)
                      or ya_guardados.get((path.name, " ".join(nombre.lower().split()))))
            correo, candidatos = (a_mano, []) if a_mano else buscar_correo(nombre, alumnos)
            integrantes.append({
                "nombre": nombre,
                "correo": correo or "",
                "correo_a_mano": bool(a_mano),
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

    # Alguien que aparece en dos entregas recibiría dos preguntas. Pasó en T2 de
    # 2026-2: un alumno subió una versión propia además de la de su grupo.
    donde: dict[str, list[str]] = {}
    for g in grupos:
        if g["bloqueo"]:
            continue
        for i in g["integrantes"]:
            if i["correo"]:
                donde.setdefault(i["correo"].lower(), []).append(g["archivo"])
    nombre_de = {a["correo"].lower(): a["nombre"] for a in alumnos}
    duplicados = [{"correo": c, "nombre": nombre_de.get(c, c), "archivos": archivos_}
                  for c, archivos_ in sorted(donde.items()) if len(archivos_) > 1]
    roster = [(a["Nombre"], a["Correo"]) for a in datos.alumnos.leer()]
    sin_entrega = [n for n, c in roster if c.lower() not in con_correo]

    return {
        "tarea": tarea,
        "carpeta": entregas_dir,
        "grupos": grupos,
        "sin_entrega": sin_entrega,
        "duplicados": duplicados,
        "identicos": [{"archivo": r, "igual_a": q} for r, q in repetidos.items()],
        "desempacados": desempacados,
        "rar_omitidos": rar_omitidos,
        "total_roster": len(roster),
        "contexto": _contexto.resumen(),
    }


def imprimir(informe: dict) -> int:
    """Deja el chequeo en pantalla. Devuelve cuántas cosas piden intervención."""
    from modulos import semestre as _sem

    print(f"=== Chequeo previo — {informe['tarea']} ===")
    print(f"[CHEQUEO] semestre {_sem.activo_o_error()}")
    print(f"Entregas en {informe['carpeta']}")
    print(_contexto.describir(informe["contexto"]) + "\n")

    if informe.get("desempacados"):
        print(f"Abrí los .rar: {', '.join(informe['desempacados'])}\n")
    for o in informe.get("rar_omitidos", []):
        print(f"⚠ {o}")

    if not informe["grupos"]:
        print("No hay HTMLs en esa carpeta. Súbelos desde la app, en "
              "Configuración › Tareas › Entregas.")
        return 1

    pendientes = 0
    a_generar = 0

    for g in informe["grupos"]:
        print(f"[{g['archivo']}]")
        if g["fuente"] != g["archivo"]:
            print(f"  el HTML viene sin código: se lee {g['fuente']}")
        cortes = "  ".join(f"p{n}={c}" for n, c in g["secciones"].items())
        print(f"  secciones: {cortes}")

        if g.get("identico_a"):
            print(f"  ⊘ mismo contenido que {g['identico_a']}: se genera una sola vez, con ese archivo\n")
            continue

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
                elegido = " (elegido a mano)" if i.get("correo_a_mano") else ""
                print(f"    ✓ {i['nombre']:28s}{etiqueta:6s} → {i['correo']}{elegido}")
                a_generar += 1
            else:
                print(f"    ⚠ {i['nombre']:28s}{etiqueta:6s} → SIN CORREO, hay que elegirlo a mano")
                for nombre, correo, sim in i["candidatos"]:
                    print(f"        candidato: {nombre:30s} {correo:34s} (parecido {sim})")
                if not i["candidatos"]:
                    print("        (ningún candidato razonable en el roster)")
                pendientes += 1
        print()

    for d in informe.get("duplicados", []):
        print(f"⚠ {d['nombre']} aparece en {len(d['archivos'])} entregas: "
              f"{', '.join(d['archivos'])}. Recibe una sola pregunta, la de la primera.")
        pendientes += 1

    print("-" * 60)
    print(f"Preguntas que se generarían ahora: {a_generar}")
    print(f"Grupos que se saltarían: {sum(1 for g in informe['grupos'] if g['bloqueo'])}")
    if informe.get("identicos"):
        print(f"Archivos repetidos (mismo contenido, no se pagan dos veces): {len(informe['identicos'])}")
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
