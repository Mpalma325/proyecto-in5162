import sys

from modulos import datos

from . import config
from .ia_prompts import evaluar_respuesta, generar_resumen
from .preguntas import cargar_semana
from modulos.progreso import avanzar


def main(semana: int) -> None:
    info = cargar_semana(semana)
    filas = [a for a in datos.alumnos.leer() if a.get("Correo", "").strip()]

    # el texto de cada respuesta vive en el log, no en la tabla de estado
    textos = {
        e["Correo"]: e["Respuesta"]
        for e in datos.log.leer(flujo=datos.TESTS, item=semana, evento="respuesta")
        if e.get("Respuesta", "").strip()
    }
    con_nota = {
        e["Correo"] for e in datos.notas.leer(flujo=datos.TESTS, item=semana)
        if e.get("Nota", "").strip()
    }

    con_respuesta = [
        f for f in filas
        if f["Correo"].strip().lower() in con_nota
        and textos.get(f["Correo"].strip().lower())
    ]

    if not con_respuesta:
        print(f"No hay respuestas evaluadas para la semana {semana}.")
        if not textos:
            print("(el log no tiene respuestas de esa semana; se puede "
                  "reconstruir con: python -m herramientas.reconstruir_interacciones)")
        return

    print(f"Procesando {len(con_respuesta)} respuesta(s)...")

    evaluaciones_html = []
    for fila in avanzar(con_respuesta, "respuestas"):
        nombre = fila.get("Nombre", "?")
        respuesta = textos[fila["Correo"].strip().lower()]
        try:
            html = evaluar_respuesta(info.preguntas, info.pautas, respuesta)
            evaluaciones_html.append(f"<!-- {nombre} -->\n{html}")
        except Exception as e:
            print(f"⚠ Error evaluando a {nombre}: {e}")
            continue

    if not evaluaciones_html:
        print("No se pudo procesar ninguna evaluación.")
        return

    resumen = generar_resumen(info.preguntas, info.pautas, evaluaciones_html)

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
