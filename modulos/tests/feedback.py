"""
Mandar el feedback de Tests: la corrección que quedó en el log, al alumno.

    python -m modulos.tests.feedback 4 [--dry-run] [--por profe@x.cl]

Corregir y mandar son dos pasos desde la revisión docente. `tests.evaluar`
deja cada corrección como evento `correccion` (y `Corregido` en notas.csv);
este trabajo elige cuáles salen y las manda. En modo automático,
`tests.evaluar` llama a `enviar_una` en la misma iteración, así que para el
alumno nada cambia.

Elige, entre los alumnos con `correccion` sin `evaluacion` ni `descarte`
posteriores, y sin Nota ni Descartada:

- decisión `enviar` sobre esa corrección: se manda;
- decisión `descartada` sobre esa corrección: se registra el descarte;
- sin decisión, corregida en `modo=auto` por el modelo, y el semestre sigue en
  automático: se manda (es un envío que falló en una corrida anterior);
- una corrección del docente («Las corrijo yo») sale solo con `enviar` y la
  nota y el texto completos.

La nota cuenta cuando sale el correo: `enviar_una` agrega `evaluacion` al log
y recién después escribe la Nota en notas.csv. Si el proceso muere entre las
dos, la corrida siguiente ve la `evaluacion` y no reenvía, y
`sincronizar_desde_log` completa la nota.

Con `--dry-run` (todo trabajo de la página es prueba salvo `prueba: false`)
elige igual, muestra cada correo y no envía ni registra nada.
"""

import sys

from modulos import datos as _datos
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo
from modulos.ia import versiones
from modulos.progreso import avanzar
from modulos import escala as _escala
from modulos.escala import leer as _leer_escala, texto_logro as _texto_logro
from modulos.semestre import configuracion as _configuracion

from . import config
from . import decisiones as _decisiones
from .correccion import _normalizar_html_gpt  # noqa: F401  (resumen y tutoría lo importaban de aquí)
from .preguntas import asunto as _asunto, cargar_semana, SemanaInfo


# --------------------------------------------------------------- armado

def _cargar_template_correccion() -> str | None:
    """El correo que envuelve la corrección, si el semestre lo tiene.

    Lo fijo del correo (el cierre con las dudas y la nota a la corrección) va
    en correo_correccion.md y no en el prompt: así la IA solo corrige y no
    tiene que copiar párrafos al pie de la letra. Un semestre sin ese archivo
    manda la corrección sola, como antes.
    """
    ruta = config.PROMPTS / "correo_correccion.md"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else None


def _construir_cuerpo_correccion(template: str | None, evaluacion_html: str, nombre: str) -> str:
    evaluacion = _normalizar_html_gpt(evaluacion_html)
    if not template:
        return evaluacion
    nombre_corto = nombre.split()[0] if nombre else "estudiante"
    # La corrección entra al final: si trajera "{NOMBRE}" escrito, no se toca.
    return template.replace("{NOMBRE}", nombre_corto).replace("{EVALUACION}", evaluacion)


def _construir_asunto_respuesta(info: SemanaInfo) -> str:
    return f"Re: {_asunto(info)}"


class Plantilla:
    """El correo de corrección del semestre y su huella para el log."""

    def __init__(self, prueba: bool):
        self.texto = _cargar_template_correccion()
        # Una simulación no guarda versiones.
        if prueba:
            self.version = ""
        elif self.texto is None:
            self.version = "sin correo_correccion.md"
        else:
            self.version = versiones.anotar(config.PROMPTS / "correo_correccion.md", self.texto)


# --------------------------------------------------------------- un alumno

def _logro_de(nota: str) -> str:
    try:
        logro = _leer_escala().logro(nota) if nota else None
    except ValueError:
        logro = None
    return _texto_logro(logro) if logro is not None else ""


def enviar_una(info: SemanaInfo, correo: str, nombre: str, correccion: dict,
               decision: dict | None, plantilla: Plantilla, *, in_reply_to: str | None,
               prueba: bool = False, por: str = "", escala: _escala.Escala | None = None,
               muestra: str | None = None) -> str | None:
    """Manda el feedback de un alumno y lo registra. Devuelve el Message-ID, o None si no salió.

    `correccion` es la fila `correccion` del log (o la misma, armada en
    memoria por evaluar en modo automático). Solo si el envío funciona se
    agrega `evaluacion` al log y, después, la Nota en notas.csv.

    En el formato nuevo la nota sale de los puntajes con `escala` (la del
    semestre si no se pasa), y el bloque muestra los números que diga
    `muestra` (correo_muestra de configuracion.json).
    """
    item = info.semana
    escala = escala or _leer_escala()
    muestra = muestra or _configuracion.correo_muestra()
    final = _decisiones.juntar(correccion, decision, escala=escala, muestra=muestra)
    if final["problemas"]:
        print(f"⋯ {nombre or correo}: no sale, la corrección no tiene nota ({' '.join(final['problemas'])})")
        return None
    asunto = _construir_asunto_respuesta(info)
    cuerpo = _construir_cuerpo_correccion(plantilla.texto, final["html"], nombre)

    if prueba:
        mostrar_correo(correo, asunto, cuerpo, html=True, nombre=nombre)
        return None

    try:
        message_id = enviar_correo(correo, asunto, cuerpo, html=True, in_reply_to=in_reply_to or None)
    except Exception as e:  # noqa: BLE001
        print(f"✗ {nombre}: falló el envío del feedback: {e}")
        print("     La corrección queda guardada; volver a correr este paso la manda.")
        return None

    if decision:
        quien = decision.get("por") or por or "docente"
        detalle = "; ".join([f"revisado por {quien}", *final["cambios"]])
    else:
        detalle = "auto"
    # Primero el log (una línea) y después la tabla: si el proceso muere entre
    # los dos, la corrida siguiente ve la evaluacion y no lo vuelve a mandar.
    try:
        _datos.log.registrar("evaluacion", _datos.TESTS, item, correo,
                             Ronda=0, MessageId=message_id or "",
                             Modelo=correccion.get("Modelo", ""),
                             Versiones=versiones.juntar(correccion.get("Versiones"), plantilla.version,
                                                        f"escala={escala.describir()}"),
                             Nota=final["nota"], Originalidad=final["originalidad"],
                             Puntajes=final["puntajes"], Logro=final["logro"],
                             EvaluacionIA=final["html"], Detalle=detalle)
    except Exception as e:  # noqa: BLE001
        # El correo ya salió: no se corta el lote. La Nota de abajo es lo que
        # evita que la corrida siguiente lo reenvíe.
        print(f"     ⚠ el correo a {nombre or correo} salió, pero no pude anotarlo en el log: {e}")
    try:
        _datos.notas.registrar_nota(correo, _datos.TESTS, item, final["nota"], final["originalidad"],
                                    logro=final["logro"])
    except Exception as e:  # noqa: BLE001
        print(f"     ⚠ el correo salió y quedó en el log, pero no pude escribir notas.csv: {e}")
    return message_id or ""


def registrar_descarte(item: int, correo: str, decision: dict, por: str = "") -> None:
    motivo = " ".join(str(decision.get("retroalimentacion") or "").split()) or "sin motivo indicado"
    quien = decision.get("por") or por or "docente"
    _datos.log.registrar("descarte", _datos.TESTS, item, correo, Detalle=f"{motivo}; por {quien}")
    _datos.notas.marcar_descartada(correo, _datos.TESTS, item)


# --------------------------------------------------------------- selección

def seleccionar(item: int, modo: str, *, solo_automaticas: bool = False,
                semestre_id: str | None = None, escala: _escala.Escala | None = None) -> dict:
    """Qué hacer con cada corrección pendiente de la instancia.

    Devuelve {"enviar": [...], "descartar": [...], "saltadas": [(correo, motivo)],
    "esperando": n}. Cada elemento de enviar/descartar es
    {"correo", "correccion", "decision", "respuesta"}. Una corrección del
    formato nuevo con un puntaje fuera de la rúbrica no tiene nota: se salta.
    """
    escala = escala or _leer_escala(semestre_id)
    # Las decisiones se leen siempre: con solo_automaticas (el reintento que hace
    # evaluar) una corrección que el docente ya tocó en Revisar no sale sola.
    decisiones = _decisiones.leer(item, semestre_id)
    estados = {f["Correo"].strip().lower(): f
               for f in _datos.notas.leer(semestre_id, flujo=_datos.TESTS, item=str(item))}
    salida = {"enviar": [], "descartar": [], "saltadas": [], "esperando": 0}

    for correo, e in _decisiones.estado_por_correo(item, semestre_id).items():
        fila = estados.get(correo) or {}
        if e["cerrada"] or (fila.get("Nota") or "").strip() or (fila.get("Descartada") or "").strip():
            continue
        correccion = e["correccion"]
        decision = decisiones.get(correo)
        caso = {"correo": correo, "correccion": correccion, "decision": None, "respuesta": e.get("respuesta")}

        if solo_automaticas and decision:
            # Aprobada, descartada o lo que sea: la decide el docente y la registra
            # o la manda tests.feedback, nunca el reintento automático.
            salida["esperando"] += 1
            continue

        if decision and decision.get("estado") in (_decisiones.ENVIAR, _decisiones.DESCARTADA):
            if not _decisiones.vigente(decision, correccion):
                salida["saltadas"].append((correo, "la decisión es sobre una corrección anterior; "
                                                   "hay que revisarla otra vez"))
                continue
            caso["decision"] = decision
            if decision["estado"] == _decisiones.DESCARTADA:
                salida["descartar"].append(caso)
            elif _decisiones.es_del_docente(correccion) and _decisiones.faltante_manual(decision, escala):
                salida["saltadas"].append((correo, f"corrección a mano: "
                                                   f"{_decisiones.faltante_manual(decision, escala)}"))
            elif _sin_nota(correccion, decision, escala):
                salida["saltadas"].append((correo, _sin_nota(correccion, decision, escala)))
            else:
                salida["enviar"].append(caso)
            continue

        automatica = (_decisiones.modo_de(correccion) == _configuracion.AUTO
                      and not _decisiones.es_del_docente(correccion))
        if automatica and modo == _configuracion.AUTO and not _sin_nota(correccion, None, escala):
            salida["enviar"].append(caso)
        else:
            salida["esperando"] += 1
    return salida


def _sin_nota(correccion: dict, decision: dict | None, escala) -> str:
    """Por qué una corrección del formato nuevo no tiene nota (un puntaje fuera de la rúbrica); vacío si la tiene."""
    if not _decisiones.es_formato_nuevo(correccion, decision):
        return ""
    problemas = _decisiones.juntar(correccion, decision, escala=escala)["problemas"]
    return f"sin nota: {' '.join(problemas)}" if problemas else ""


def _nombres() -> dict[str, str]:
    return {a.get("Correo", "").strip().lower(): a.get("Nombre", "") for a in _datos.alumnos.leer()}


def enviar_pendientes(info: SemanaInfo, modo: str, *, prueba: bool = False, por: str = "",
                      solo_automaticas: bool = False, plantilla: Plantilla | None = None,
                      escala: _escala.Escala | None = None, muestra: str | None = None) -> dict:
    """Manda lo que `seleccionar` elige y registra los descartes. Devuelve los conteos."""
    escala = escala or _leer_escala()
    muestra = muestra or _configuracion.correo_muestra()
    seleccion = seleccionar(info.semana, modo, solo_automaticas=solo_automaticas, escala=escala)
    plantilla = plantilla or Plantilla(prueba)
    nombres = _nombres()
    cuenta = {"enviados": 0, "fallidos": 0, "descartes": 0,
              "saltadas": len(seleccion["saltadas"]), "esperando": seleccion["esperando"]}

    for correo, motivo in seleccion["saltadas"]:
        print(f"  ⋯ {nombres.get(correo) or correo:30s} no sale: {motivo}")

    for caso in seleccion["descartar"]:
        correo = caso["correo"]
        motivo = str(caso["decision"].get("retroalimentacion") or "").strip() or "sin motivo"
        if prueba:
            print(f"  ⊘ {nombres.get(correo) or correo:30s} se registraría como descartada ({motivo})")
        else:
            registrar_descarte(info.semana, correo, caso["decision"], por)
            print(f"  ⊘ {nombres.get(correo) or correo:30s} descartada ({motivo}): no se le manda nada")
        cuenta["descartes"] += 1

    for caso in avanzar(seleccion["enviar"], "correos"):
        correo = caso["correo"]
        nombre = nombres.get(correo) or ""
        respuesta = caso.get("respuesta") or {}
        message_id = enviar_una(info, correo, nombre, caso["correccion"], caso["decision"], plantilla,
                                in_reply_to=respuesta.get("RespondeA") or None, prueba=prueba, por=por,
                                escala=escala, muestra=muestra)
        if prueba:
            cuenta["enviados"] += 1
            continue
        if message_id is None:
            cuenta["fallidos"] += 1
        else:
            cuenta["enviados"] += 1
            nota = _decisiones.juntar(caso["correccion"], caso["decision"], escala=escala)["nota"]
            print(f"✓ {nombre or correo}: feedback enviado, nota {nota or '?'}")
    return cuenta


# --------------------------------------------------------------- trabajo

def main(item: int, prueba: bool = False, por: str = "") -> int:
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    modo = _configuracion.modo_revision()
    print(_configuracion.describir(modo))
    print(f"[FEEDBACK] semestre {sid}")
    info = cargar_semana(item)
    print(f"{f'Módulo {item}' if info.legado else info.nombre} — feedback{' (simulación)' if prueba else ''}")

    if not prueba:
        # Completa la Nota de quien quedó con evaluacion en el log y sin nota en
        # la tabla (un corte entre las dos escrituras de enviar_una).
        cambios = _datos.notas.sincronizar_desde_log()
        if cambios.get("Nota"):
            print(f"  notas.csv se puso al día con el log: {cambios['Nota']} nota(s).")

    cuenta = enviar_pendientes(info, modo, prueba=prueba, por=por)
    verbo = "se enviarían" if prueba else "enviados"
    print(f"\nFeedback {verbo}: {cuenta['enviados']}  Descartes: {cuenta['descartes']}"
          f"  Fallidos: {cuenta['fallidos']}  Saltados: {cuenta['saltadas']}"
          f"  Esperando revisión: {cuenta['esperando']}")
    if prueba and (cuenta["enviados"] or cuenta["descartes"]):
        print("Es una simulación: no se envió ni registró nada.")
    return 1 if cuenta["fallidos"] else 0


def _parsear_args(argv: list[str]) -> tuple[int, bool, str]:
    item, prueba, por = None, False, ""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            prueba = True
        elif a == "--por" and i + 1 < len(argv):
            por = argv[i + 1].strip()
            i += 1
        elif a.startswith("--por="):
            por = a[len("--por="):].strip()
        elif a.isdigit() and item is None:
            item = int(a)
        i += 1
    if item is None:
        print("Falta la instancia: python -m modulos.tests.feedback <id> [--dry-run] [--por correo]")
        sys.exit(2)
    return item, prueba, por


if __name__ == "__main__":
    item, prueba, por = _parsear_args(sys.argv[1:])
    sys.exit(main(item, prueba, por))
