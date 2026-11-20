"""
Cambiar una nota a mano, dejando constancia de quién, cuándo y por qué.

El modelo se equivoca a veces: en 2026-2, por ejemplo, varias respuestas
llegaron con la línea "El vie… escribió:" pegada y el modelo las castigó por
"contenido ajeno". Esto corrige la nota sin volver a evaluar:

    python -m modulos.datos.ajustar --flujo test --item 3 --correo alumno@x.cl \\
        --nota 6,5 --motivo "la respuesta estaba correcta; el modelo castigó la firma" --por profe@x.cl

Queda en `notas.csv` (lo que ve la reportería) y como evento `ajuste` en el
log, con la nota anterior y el motivo, así que se puede reconstruir y auditar.

En Tests la nota se valida con la escala del semestre (`escala_notas.json`):
va de min(1, mínima) a la máxima, con los decimales de la escala, y guarda su
logro. Una nota bajo la mínima (un 3,0 en 4–7) se acepta sin logro y queda
fija si la escala cambia. Tareas sigue con 1,0–7,0 y un decimal.

Sin `--avisar` no manda correos. Con `--avisar` (solo Tests) le escribe al
alumno «tu nota quedó en 6,5», con `tests_semanales/prompts/correo_ajuste.md`
o, si el semestre no lo tiene, con un texto fijo. El aviso responde en el hilo
del último feedback y su Message-ID queda en el evento `ajuste`, así que si el
alumno contesta, la tutoría lo recoge. Ni la plantilla ni el texto fijo usan la
etiqueta NOTA FINAL: `reconstruir` no tiene que confundir un aviso con la
corrección.

Una casilla «por revisar» no se ajusta: esa nota se cambia en Tests › Revisar.
"""

import argparse
import re
import sys
from fractions import Fraction

from modulos import escala as _escala
from modulos import semestre as _semestre

from . import TAREAS, TESTS
from . import log as _log
from . import notas as _notas

AVISO_POR_DEFECTO = (
    "<p>Hola {NOMBRE}:</p>"
    "<p>Revisamos otra vez tu corrección y tu nota quedó en {NOTA}.</p>"
    "<p>Si tienes dudas, responde este correo.</p>"
)


def _plantilla_aviso() -> str:
    from modulos.tests import config as _config_tests
    ruta = _config_tests.PROMPTS / "correo_ajuste.md"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else AVISO_POR_DEFECTO


def cuerpo_aviso(plantilla: str, nombre: str, nota: str, motivo: str = "") -> str:
    nombre_corto = nombre.split()[0] if nombre else "estudiante"
    return (plantilla.replace("{NOMBRE}", nombre_corto).replace("{NOTA}", nota)
            .replace("{MOTIVO}", motivo))


def _ultimo_feedback(correo: str, item: str, semestre_id: str | None) -> str:
    """El Message-ID del último correo con nota que recibió (feedback o aviso anterior)."""
    ultimo = ""
    for e in _log.leer(semestre_id, flujo=TESTS, item=str(item)):
        if (e.get("Correo") or "").strip().lower() == correo and e.get("Evento") in ("evaluacion", "ajuste"):
            if (e.get("MessageId") or "").strip():
                ultimo = e["MessageId"].strip()
    return ultimo


def _avisar(correo: str, item: str, nota: str, motivo: str, semestre_id: str | None) -> str:
    """Manda el aviso y devuelve su Message-ID. Si falla, levanta ValueError: no se ajusta."""
    # Importar el flujo de tests configura el correo con las credenciales del curso.
    from modulos.tests.preguntas import asunto, cargar_semana
    from modulos import mail
    from modulos.datos import alumnos as _alumnos

    nombre = next((a.get("Nombre", "") for a in _alumnos.leer(semestre_id)
                   if (a.get("Correo") or "").strip().lower() == correo), "")
    try:
        asunto_aviso = f"Re: {asunto(cargar_semana(int(item)))}"
    except ValueError as e:
        raise ValueError(f"No pude armar el asunto del aviso: {e}") from e
    hilo = _ultimo_feedback(correo, item, semestre_id)
    cuerpo = cuerpo_aviso(_plantilla_aviso(), nombre, nota, motivo)
    try:
        return mail.enviar_correo(correo, asunto_aviso, cuerpo, html=True, in_reply_to=hilo or None) or ""
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"No pude mandar el aviso ({e}): la nota no se cambió.") from e


def nota_de_test(nota: str, escala: _escala.Escala) -> tuple[str, str]:
    """La nota de un ajuste en Tests, validada con la escala: (como se escribe, logro).

    Va de min(1, mínima) a la máxima, con a lo más los decimales de la escala.
    Bajo la mínima (un 3,0 en una escala de 4 a 7) se acepta sin logro: queda
    fija aunque la escala cambie (modulos/datos/escala_trabajo.py).
    """
    texto = (nota or "").strip()
    decimales = f"([.,]\\d{{1,{escala.decimales}}})?" if escala.decimales else ""
    if not re.fullmatch(r"\d{1,4}" + decimales, texto):
        ejemplo = escala.texto(escala.maxima)
        raise ValueError(f"Nota inválida: {nota!r} (se escribe como {ejemplo})")
    valor = Fraction(texto.replace(",", "."))
    if not min(Fraction(1), Fraction(repr(float(escala.minima)))) <= valor <= Fraction(repr(float(escala.maxima))):
        raise ValueError(f"Nota fuera de la escala: {nota} (va de {escala.texto(min(1, escala.minima))} "
                         f"a {escala.texto(escala.maxima)})")
    logro = escala.logro(valor)
    return escala.texto(valor), (_escala.texto_logro(logro) if logro is not None else "")


def ajustar(flujo: str, item: str, correo: str, nota: str, motivo: str, por: str,
            semestre_id: str | None = None, avisar: bool = False) -> dict:
    """Cambia la nota. Devuelve {"antes", "despues", "aviso"}. Levanta ValueError si no corresponde."""
    if flujo not in (TESTS, TAREAS):
        raise ValueError(f"Flujo inválido: {flujo!r}")
    if avisar and flujo != TESTS:
        raise ValueError("El aviso de ajuste solo existe para Tests.")
    logro = ""
    if flujo == TESTS:
        nueva, logro = nota_de_test(nota, _escala.leer(semestre_id))
    else:
        # Tareas tiene su propia escala (modulos/tareas/escala.py) y sigue con la de siempre.
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
    if _notas.esta_por_revisar(antes):
        raise ValueError(f"{correo} tiene la corrección de {flujo} {item} por revisar: "
                         "esa nota se cambia en Tests › Revisar, no con un ajuste.")
    nota_antes = (antes.get("Nota") or "").strip()
    if flujo == TAREAS:
        # Con el separador que ya usa ese registro.
        separador = "," if "," in nota_antes else "."
        nueva = f"{float(nota.replace(',', '.')):.1f}".replace(".", separador)

    aviso = _avisar(correo, str(item), nueva, motivo, semestre_id) if avisar else None

    _notas.registrar_nota(correo, flujo, str(item), nueva, antes.get("Originalidad", ""), semestre_id,
                          logro=logro)
    _log.registrar("ajuste", flujo, str(item), correo, semestre_id,
                   Nota=nueva, Originalidad=antes.get("Originalidad", ""), Logro=logro,
                   MessageId=aviso or "",
                   Detalle=f"{motivo} (antes: {nota_antes or 'sin nota'}; por {por}"
                           + ("; avisado por correo" if avisar else "") + ")")
    return {"antes": nota_antes, "despues": nueva, "aviso": aviso}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cambiar una nota a mano, con motivo.")
    p.add_argument("--flujo", required=True, choices=(TESTS, TAREAS))
    p.add_argument("--item", required=True, help="instancia (tests) o tarea, p. ej. T1")
    p.add_argument("--correo", required=True)
    p.add_argument("--nota", required=True)
    p.add_argument("--motivo", default="")
    p.add_argument("--por", required=True, help="quién hace el ajuste")
    p.add_argument("--avisar", action="store_true", help="avisarle al alumno por correo (solo tests)")
    a = p.parse_args(argv)
    print(f"[AJUSTAR] semestre {_semestre.activo_o_error()}")
    try:
        r = ajustar(a.flujo, a.item, a.correo, a.nota, a.motivo, a.por, avisar=a.avisar)
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ {a.correo} · {a.flujo} {a.item}: nota {r['antes'] or 'sin nota'} → {r['despues']}")
    print(f"  motivo: {a.motivo}")
    if a.avisar:
        print("  Se le avisó por correo.")
    else:
        print("  No se envió ningún correo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
