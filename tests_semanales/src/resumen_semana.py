import sys

from . import config, storage
from .openai_client import evaluar_respuesta, generar_resumen
from .preguntas import cargar_semana


def main(semana: int) -> None:
    info = cargar_semana(semana)
    filas, _ = storage.leer_alumnos()

    con_respuesta = [
        f for f in filas
        if f.get(storage.col_respuesta(semana), "").strip()
        and f.get(storage.col_nota(semana), "").strip()
    ]

    if not con_respuesta:
        print(f"No hay respuestas evaluadas para la semana {semana}.")
        return

    print(f"Procesando {len(con_respuesta)} respuesta(s)...")

    evaluaciones_html = []
    for fila in con_respuesta:
        nombre = fila.get("Nombre", "?")
        respuesta = fila[storage.col_respuesta(semana)]
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
