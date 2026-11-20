"""
El resumen de una instancia para el equipo docente: qué entendió el curso.

Toma a quien tiene la respuesta corregida (con Corregido o Nota, y no
descartada) y le pasa al modelo las correcciones que ya están en el log: la
última `correccion` de cada alumno o, en filas anteriores a la revisión, su
`evaluacion`. No vuelve a corregir a nadie: es una sola llamada al modelo.
Así también hay resumen de una instancia que todavía espera revisión.
"""

import sys

from modulos import datos
from modulos.escala import leer as leer_escala

from . import config
from . import correccion as _correccion
from .ia_prompts import generar_resumen
from .preguntas import cargar_semana


def _correcciones(semana: int) -> dict[str, str]:
    """Por alumno, el texto de su corrección más nueva: `correccion` si hay, si no `evaluacion`."""
    ultima: dict[str, tuple[str, str]] = {}
    for e in datos.log.leer(flujo=datos.TESTS, item=semana):
        ev = e.get("Evento")
        texto = (e.get("EvaluacionIA") or "").strip()
        if ev not in ("correccion", "evaluacion") or not texto:
            continue
        correo = (e.get("Correo") or "").strip().lower()
        previo = ultima.get(correo)
        # Una evaluacion no reemplaza a una correccion: el resumen mira lo que
        # dijo quien corrigió, y la corrección hecha a mano (vacía en el log)
        # cae a lo que salió en el correo.
        if ev == "correccion" or previo is None or previo[0] == "evaluacion":
            ultima[correo] = (ev, texto)
    # El JSON del formato nuevo pasa a texto con puntajes y NOTA FINAL; el HTML
    # viejo queda tal cual (sin el ```html).
    escala = leer_escala()
    return {c: _correccion.texto_docente(_correccion.leer(t, escala), escala) for c, (_, t) in ultima.items()}


def main(semana: int) -> None:
    info = cargar_semana(semana)
    filas = [a for a in datos.alumnos.leer() if a.get("Correo", "").strip()]

    estados = {e["Correo"].strip().lower(): e for e in datos.notas.leer(flujo=datos.TESTS, item=semana)}
    corregidos = {
        c for c, e in estados.items()
        if ((e.get("Corregido") or "").strip() or (e.get("Nota") or "").strip())
        and not (e.get("Descartada") or "").strip()
    }
    textos = _correcciones(semana)

    elegidos = [f for f in filas
                if f["Correo"].strip().lower() in corregidos and textos.get(f["Correo"].strip().lower())]

    if not elegidos:
        print(f"No hay respuestas corregidas para {f'la semana {semana}' if info.legado else info.nombre}.")
        if not textos:
            print("(el log no tiene correcciones de esa instancia)")
        return

    print(f"Resumiendo {len(elegidos)} corrección(es) guardadas (sin volver a corregir).")

    evaluaciones = []
    for fila in elegidos:
        grupo = (fila.get("Grupo") or "control").strip().lower() or "control"
        evaluaciones.append(f"<!-- {fila.get('Nombre', '?')} · grupo {grupo} -->\n"
                            f"{textos[fila['Correo'].strip().lower()]}")

    resumen = generar_resumen(info.control, info.tratamiento, evaluaciones)

    salida = config.DATA / f"resumen_semana_{semana}.txt"
    salida.write_text(resumen, encoding="utf-8")
    print(f"✓ Guardado en {salida.relative_to(config.PROJECT_ROOT)}")


def _parsear_semana() -> int:
    args = sys.argv[1:]
    for a in args:
        if a.isdigit():
            return int(a)
    try:
        return int(input("¿Semana? → ").strip())
    except (ValueError, EOFError):
        print("Semana inválida.")
        sys.exit(1)


if __name__ == "__main__":
    semana = _parsear_semana()
    main(semana)
