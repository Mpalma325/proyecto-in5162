"""
Responde las dudas que los alumnos mandan sobre su corrección.

Un alumno recibe su nota y escribe de vuelta: por qué un 6 y no un 7, qué
tendría que haber puesto, qué efecto tienen los X en esa medición, o algún
concepto que le quedó dando vueltas. Esto lee esas dudas y las contesta.

Es opcional y va aparte del ciclo del curso: se corre cuando uno quiera, no
tiene fecha, y si nunca se corre no pasa nada. `evaluar` deja estos correos sin
leer justamente para que los recoja este comando.

**La nota nunca se modifica.** Acá se explica y se enseña; corregir de nuevo
sería otra cosa y no es lo que hace.

    python -m modulos.tests.tutoria            # todas las semanas
    python -m modulos.tests.tutoria 4          # solo la semana 4
    python -m modulos.tests.tutoria --dry-run  # muestra qué contestaría
"""

import sys

from modulos import datos as _datos
from modulos.datos import esquema as _esquema
from modulos.mail import buscar_no_leidos, enviar_correo, marcar_leidos

from . import config
from .ia_prompts import responder_duda
from .preguntas import cargar_semana
from modulos.progreso import avanzar

# Tope de vueltas por alumno y semana. La conversación es para resolver una
# duda, no para negociar la nota indefinidamente; pasado esto conviene que
# intervenga una persona.
MAX_RONDAS = 4


def _anunciar_semestre() -> str:
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[TUTORIA] semestre {sid}")
    return sid


def _pendientes(semana: int | None = None) -> list[tuple[dict, dict]]:
    """Correos sin leer que contestan a un feedback nuestro.

    Devuelve pares (correo entrante, evento que lo originó). El emparejamiento
    es por In-Reply-To contra el MessageId de una 'evaluacion' o una 'tutoria';
    por eso solo se reconocen los feedback enviados desde que ese id se guarda.
    """
    salida = []
    for corr in buscar_no_leidos():
        irt = (corr.get("in_reply_to") or "").strip()
        if not irt:
            continue
        origen = _datos.log.fila_por_message_id(irt, eventos=_esquema.DEL_AGENTE)
        if not origen:
            continue
        if semana is not None and str(origen.get("Item")) != str(semana):
            continue
        salida.append((corr, origen))
    return salida


def main(semana: int | None = None, dry_run: bool = False) -> None:
    _anunciar_semestre()

    pendientes = _pendientes(semana)
    ambito = f"semana {semana}" if semana is not None else "todas las semanas"
    print(f"Dudas sobre el feedback ({ambito}): {len(pendientes)}")
    if not pendientes:
        print("Nada que responder.")
        return

    gente = {a["Correo"].strip().lower(): a
             for a in _datos.alumnos.leer() if a.get("Correo", "").strip()}

    procesados, respondidas, fallidas = [], 0, 0

    for corr, origen in avanzar(pendientes, "dudas"):
        correo = (origen.get("Correo") or "").strip().lower()
        item = str(origen.get("Item"))
        alumno = gente.get(correo, {})
        nombre = alumno.get("Nombre") or correo
        consulta = (corr.get("texto") or "").strip()

        if not consulta:
            print(f"  ⊘ {nombre}: mensaje vacío, lo salto")
            continue

        ronda = _datos.log.ultima_ronda(correo, _datos.TESTS, item) + 1
        if ronda > MAX_RONDAS:
            print(f"  ⊘ {nombre} (semana {item}): ya lleva {MAX_RONDAS} vueltas, "
                  f"lo dejo para revisión humana")
            continue

        historial = _datos.log.conversacion(correo, _datos.TESTS, item)
        evaluacion = next(
            (h.get("EvaluacionIA", "") for h in reversed(historial)
             if h.get("Evento") == "evaluacion"), "")
        respuesta_original = next(
            (h.get("Respuesta", "") for h in historial
             if h.get("Evento") == "respuesta"), "")

        if dry_run:
            print(f"  → {nombre} (semana {item}, ronda {ronda}): "
                  f"respondería a {len(consulta)} chars")
            continue

        try:
            info = cargar_semana(int(item))
            grupo = (alumno.get("Grupo") or "control").strip().lower()
            gi = info.para_grupo(grupo)
            html = responder_duda(
                gi.preguntas, gi.pautas, respuesta_original, evaluacion,
                consulta, nombre, historial=historial,
            )
        except Exception as e:  # noqa: BLE001
            fallidas += 1
            print(f"  ✗ {nombre} (semana {item}): error del modelo: {e}")
            _datos.log.registrar("error", _datos.TESTS, item, correo,
                                 Ronda=ronda, Detalle=f"tutoria: {e}")
            continue

        meta = getattr(html, "meta", {}) or {}
        asunto = corr.get("asunto") or f"Re: Módulo {item}"
        if not asunto.lower().startswith("re:"):
            asunto = f"Re: {asunto}"

        try:
            id_respuesta = enviar_correo(
                correo, asunto, html, html=True,
                in_reply_to=corr.get("message_id") or None,
            )
        except Exception as e:  # noqa: BLE001
            fallidas += 1
            print(f"  ✗ {nombre} (semana {item}): modelo OK pero falló el envío: {e}")
            continue

        # Se registran los dos lados de la vuelta. La nota no se toca: acá no
        # se llama a notas.registrar_nota a propósito.
        _datos.log.registrar("repregunta", _datos.TESTS, item, correo,
                             Ronda=ronda, RespondeA=corr.get("in_reply_to", ""),
                             MessageId=corr.get("message_id", ""),
                             Respuesta=consulta)
        _datos.log.registrar("tutoria", _datos.TESTS, item, correo,
                             Ronda=ronda, RespondeA=corr.get("message_id", ""),
                             MessageId=id_respuesta or "",
                             Modelo=meta.get("modelo") or config.MODELO,
                             TokensEntrada=meta.get("prompt_tokens") or "",
                             TokensSalida=meta.get("completion_tokens") or "",
                             EvaluacionIA=html)

        respondidas += 1
        procesados.append(corr["uid"])
        print(f"  ✓ {nombre} (semana {item}, ronda {ronda}): respondida")

    if procesados:
        try:
            marcar_leidos(procesados)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ no pude marcar como leídos (el trabajo ya está guardado): {e}")

    print(f"\nRespondidas: {respondidas}  Fallidas: {fallidas}")


def _parsear_args(argv: list[str]) -> tuple[int | None, bool]:
    semana, dry_run = None, False
    for a in argv:
        if a in ("--dry-run", "--dry", "-n"):
            dry_run = True
        elif a.isdigit():
            semana = int(a)
        else:
            print(f"Argumento desconocido: {a}")
            print(__doc__)
            raise SystemExit(2)
    return semana, dry_run


if __name__ == "__main__":
    _semana, _dry = _parsear_args(sys.argv[1:])
    main(_semana, _dry)
