"""
Cambiar una nota a mano, dejando constancia de quién, cuándo y por qué.

El modelo se equivoca a veces: en 2026-2, por ejemplo, varias respuestas
llegaron con la línea "El vie… escribió:" pegada y el modelo las castigó por
"contenido ajeno". Esto corrige la nota sin volver a evaluar ni escribirle al
alumno:

    python -m modulos.datos.ajustar --flujo test --item 3 --correo alumno@x.cl \\
        --nota 6,5 --motivo "la respuesta estaba correcta; el modelo castigó la firma" --por profe@x.cl

Queda en `notas.csv` (lo que ve la reportería) y como evento `ajuste` en el
log, con la nota anterior y el motivo, así que se puede reconstruir y auditar.
**No manda correos.**
"""

import argparse
import re
import sys

from modulos import semestre as _semestre

from . import TAREAS, TESTS
from . import log as _log
from . import notas as _notas


def ajustar(flujo: str, item: str, correo: str, nota: str, motivo: str, por: str,
            semestre_id: str | None = None) -> dict:
    """Cambia la nota. Devuelve {"antes", "despues"}. Levanta ValueError si no corresponde."""
    if flujo not in (TESTS, TAREAS):
        raise ValueError(f"Flujo inválido: {flujo!r}")
    if not re.fullmatch(r"\d{1,2}([.,]\d)?", nota.strip()):
        raise ValueError(f"Nota inválida: {nota!r} (se escribe como 6,5)")
    if not 1.0 <= float(nota.replace(",", ".")) <= 7.0:
        raise ValueError(f"Nota fuera de la escala: {nota}")
    # El motivo es opcional: si no se da, el log igual guarda la nota anterior y quién.
    motivo = " ".join((motivo or "").split()) or "sin motivo indicado"

    correo = correo.strip().lower()
    antes = _notas.estado(correo, flujo, str(item), semestre_id)
    if antes is None:
        raise ValueError(f"{correo} no tiene registro en {flujo} {item}: no hay nota que ajustar.")
    nota_antes = (antes.get("Nota") or "").strip()
    # Con el separador que ya usa ese registro: coma en tests (6,5); en tareas, el que tenga.
    separador = "," if flujo == TESTS or "," in nota_antes else "."
    nueva = f"{float(nota.replace(',', '.')):.1f}".replace(".", separador)

    _notas.registrar_nota(correo, flujo, str(item), nueva, antes.get("Originalidad", ""), semestre_id)
    _log.registrar("ajuste", flujo, str(item), correo, semestre_id,
                   Nota=nueva, Originalidad=antes.get("Originalidad", ""),
                   Detalle=f"{motivo} (antes: {nota_antes or 'sin nota'}; por {por})")
    return {"antes": nota_antes, "despues": nueva}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cambiar una nota a mano, con motivo.")
    p.add_argument("--flujo", required=True, choices=(TESTS, TAREAS))
    p.add_argument("--item", required=True, help="semana (tests) o tarea, p. ej. T1")
    p.add_argument("--correo", required=True)
    p.add_argument("--nota", required=True)
    p.add_argument("--motivo", default="")
    p.add_argument("--por", required=True, help="quién hace el ajuste")
    a = p.parse_args(argv)
    print(f"[AJUSTAR] semestre {_semestre.activo_o_error()}")
    try:
        r = ajustar(a.flujo, a.item, a.correo, a.nota, a.motivo, a.por)
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ {a.correo} · {a.flujo} {a.item}: nota {r['antes'] or 'sin nota'} → {r['despues']}")
    print(f"  motivo: {a.motivo}")
    print("  No se envió ningún correo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
