"""
Paso 2 del flujo: enviar correos con la pregunta a cada integrante.

Lee el CSV de la tarea, y para cada fila con correo y pregunta (y sin fecha_envio)
compone un correo personalizado y lo envía. Guarda el Message-ID para matcheo
posterior de respuestas.

Uso:
    python -m src.paso2_enviar                # tarea = config.TAREA_DEFAULT
    python -m src.paso2_enviar T1
    python -m src.paso2_enviar T1 --dry-run   # NO envía, solo muestra qué se enviaría
"""

import sys
from datetime import datetime

from . import config, storage
from .correo import enviar_correo


def _cargar_template() -> str:
    return (config.PROMPTS / "correo_pregunta.md").read_text(encoding="utf-8")


def _construir_cuerpo(template: str, fila: dict) -> str:
    return template.format(
        nombre=fila["alumno_nombre"].split()[0] if fila["alumno_nombre"] else "estudiante",
        tarea=fila["tarea"],
        pregunta_tarea=fila["pregunta_tarea"] or "pregunta",
        pregunta=fila["pregunta"],
    )


def _construir_asunto(fila: dict) -> str:
    """Asunto limpio y humano. El tracking va por Message-ID (header oculto)."""
    return f"Pregunta de comprensión — IN5162 {fila['tarea']}"


def main(tarea: str, dry_run: bool = False) -> None:
    filas = storage.leer_csv(tarea)
    if not filas:
        print(f"No hay CSV para tarea {tarea}. Corre primero el paso 1.")
        return

    template = _cargar_template()

    pendientes = [
        f for f in filas
        if f.get("alumno_correo")
        and f.get("pregunta")
        and not f.get("fecha_envio")
    ]

    sin_correo = [f for f in filas if f.get("pregunta") and not f.get("alumno_correo")]
    sin_pregunta = [f for f in filas if not f.get("pregunta")]
    ya_enviados = [f for f in filas if f.get("fecha_envio")]

    print(f"Tarea {tarea}:")
    print(f"  Total filas: {len(filas)}")
    print(f"  A enviar: {len(pendientes)}")
    print(f"  Sin correo (arreglar en CSV antes de continuar): {len(sin_correo)}")
    print(f"  Sin pregunta (no contribuyeron con código): {len(sin_pregunta)}")
    print(f"  Ya enviados antes: {len(ya_enviados)}")

    if sin_correo:
        print("\n⚠️  Integrantes sin correo:")
        for f in sin_correo:
            print(f"   - {f['alumno_nombre']} ({f['grupo_archivo']})")

    if not pendientes:
        print("\nNada por enviar.")
        return

    if dry_run:
        print("\n--- DRY RUN (no se envía nada) ---")
    else:
        print("\n--- ENVIANDO ---")

    for fila in pendientes:
        asunto = _construir_asunto(fila)
        cuerpo = _construir_cuerpo(template, fila)

        if dry_run:
            print(f"\n→ A: {fila['alumno_correo']}")
            print(f"  Asunto: {asunto}")
            print(f"  Cuerpo: {cuerpo[:200]}...")
            continue

        try:
            message_id = enviar_correo(fila["alumno_correo"], asunto, cuerpo)
            storage.actualizar_fila(
                tarea,
                fila["grupo_archivo"],
                fila["alumno_nombre"],
                {
                    "fecha_envio": datetime.now().isoformat(timespec='seconds'),
                    "message_id": message_id,
                },
            )
            print(f"  ✓ {fila['alumno_nombre']:30s} → {fila['alumno_correo']}")
        except Exception as e:
            print(f"  ✗ {fila['alumno_nombre']:30s} → {fila['alumno_correo']}: {e}")


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = config.TAREA_DEFAULT
    dry_run = False

    for a in args:
        if a.lower() == "--dry-run":
            dry_run = True
        elif a.upper().startswith('T') and a[1:].isdigit():
            tarea = a.upper()

    main(tarea, dry_run)
