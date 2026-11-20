import sys

from modulos import datos as _datos
from modulos.datos import esquema as _esquema

from . import config
from modulos.mail import enviar_correo, buscar_respuestas_semana, marcar_leido
from modulos.mail.vista import mostrar_correo
from modulos.datos import candidatos as _candidatos
from modulos.ia import versiones
from .ia_prompts import evaluar_respuesta
from .preguntas import asunto as _asunto, cargar_semana, SemanaInfo
from .respuestas import criterio as _criterio_respuestas
from modulos.progreso import avanzar
from modulos.semestre import configuracion as _configuracion
from . import decisiones as _decisiones


# La lectura de la corrección vive en correccion.py (JSON nuevo o HTML viejo);
# el extractor del HTML viejo se reexporta para quien lo importaba de aquí.
from . import correccion as _correccion  # noqa: E402
from .correccion import _normalizar_html_gpt, extraer_nota_y_originalidad  # noqa: E402,F401
from modulos import escala as _escala  # noqa: E402


def _cargar_template_duplicado() -> str:
    return (config.PROMPTS / "correo_duplicado.md").read_text(encoding="utf-8")


def _construir_cuerpo_duplicado(template: str, nombre: str) -> str:
    nombre_corto = nombre.split()[0] if nombre else "estudiante"
    return template.replace("{NOMBRE}", nombre_corto)


# El armado del correo de corrección se mudó a feedback.py (fase 3): el envío
# ya no es parte de corregir. Se reexportan para quien los importaba de aquí.
from . import feedback as _feedback  # noqa: E402
from .feedback import (  # noqa: E402,F401
    _cargar_template_correccion, _construir_cuerpo_correccion, _construir_asunto_respuesta,
)


def _mapa_correos(filas_alumnos: list[dict]) -> dict:
    """Correo -> alumno, incluyendo los alternativos.

    Algunos alumnos responden desde una cuenta distinta a la que tienen
    registrada. Para esos casos se puede agregar una columna
    "CorreosAlternativos" en alumnos.csv, con los correos separados por ";".
    Sin esa columna todo funciona igual que antes.
    """
    mapa = {}
    for f in filas_alumnos:
        principal = f.get("Correo", "").strip().lower()
        if principal:
            mapa[principal] = f
        for alt in (f.get("CorreosAlternativos") or "").split(";"):
            alt = alt.strip().lower()
            if alt:
                mapa[alt] = f
    return mapa


def _identificar_alumno(corr_recibido: dict, semana: int, filas_alumnos: list[dict]) -> dict | None:
    correos_a_alumno = _mapa_correos(filas_alumnos)

    irt = corr_recibido.get("in_reply_to", "").strip()
    if irt:
        correo_match = _datos.log.correo_de_message_id(irt, _datos.TESTS, semana)
        if correo_match and correo_match.lower() in correos_a_alumno:
            return correos_a_alumno[correo_match.lower()]

    remitente = corr_recibido.get("remitente", "").lower()
    if remitente in correos_a_alumno:
        return correos_a_alumno[remitente]

    return None


def _anunciar_semestre() -> str:
    """Deja en pantalla sobre qué semestre se está trabajando.

    El semestre activo se toma de un archivo, no del comando, así que sin
    esto no hay forma de notar que se está operando el equivocado.
    """
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[EVALUAR] semestre {sid}")
    return sid


def _es_repregunta(corr: dict) -> bool:
    """Si el correo contesta a un feedback nuestro en vez de a la pregunta.

    Se decide por el In-Reply-To: si apunta al Message-ID de una evaluación o de
    una tutoría que ya mandamos, el alumno está preguntando sobre su corrección.
    Solo funciona para feedback enviado después de que se empezó a guardar ese
    id; lo anterior no es distinguible y sigue tratándose como respuesta.
    """
    irt = (corr.get("in_reply_to") or "").strip()
    if not irt:
        return False
    origen = _datos.log.fila_por_message_id(irt, eventos=_esquema.DEL_AGENTE, flujo=_datos.TESTS)
    return origen is not None


def _sin_angulos(message_id: str | None) -> str:
    return (message_id or "").strip().strip("<>")


def _respuestas_registradas() -> set[str]:
    """Los Message-ID de los correos de alumnos que ya se procesaron.

    Son los de cada 'respuesta' de tests del log, también las que llegaron
    duplicadas. Se lee el log una sola vez por corrida, no una por correo.
    """
    return {_sin_angulos(f.get("MessageId"))
            for f in _datos.log.leer(flujo=_datos.TESTS, evento="respuesta")
            if _sin_angulos(f.get("MessageId"))}


def _ya_corregido_texto(estado: dict) -> str:
    nota = (estado.get("Nota") or "").strip()
    if nota:
        return f"ya tenía nota ({nota})"
    if (estado.get("Descartada") or "").strip():
        return "su corrección se descartó"
    return "ya estaba corregido, por revisar"


def _estado_candidato(fila: dict | None) -> str:
    """Para la lista de elegidos: «con nota 6,0», «por revisar», «descartada» o vacío."""
    fila = fila or {}
    nota = (fila.get("Nota") or "").strip()
    if nota:
        return f"con nota {nota}"
    if (fila.get("Descartada") or "").strip():
        return "descartada"
    if (fila.get("Corregido") or "").strip():
        return "por revisar"
    return ""


def _n_preguntas(grupo_info) -> int:
    """Cuántas preguntas no vacías tiene el grupo: con eso se avisa si el modelo juntó dos."""
    return len([p for p in grupo_info.preguntas if str(p).strip()])


def _modo_de_la_corrida(info: SemanaInfo, sin_modelo: bool) -> str:
    """El modo de esta corrida: el de la instancia (columna Revision; vacía,
    configuracion.json), salvo «Las corrijo yo», que siempre revisa."""
    modo = _configuracion.modo_de(info.revision)
    # Una corrección a mano está vacía: en automático se le mandaría eso al alumno.
    return _configuracion.REVISAR if sin_modelo else modo


def main(semana: int, dry_run: bool = False, solo: set[str] | None = None,
         sin_modelo: bool = False, por: str = "") -> None:
    """Corrige las respuestas de una instancia.

    `solo`: si se pasa, corrige solo a esos correos; el resto queda sin leer.
    `sin_modelo`: no llama al modelo; deja una corrección vacía a nombre del
    docente (`por`) para que la complete en Tests › Revisar.

    El modo es el de la instancia, leído de preguntas.csv al momento de correr
    (columna Revision; vacía, configuracion.json; sin archivo, automático): en
    `auto` cada corrección se manda apenas queda (feedback.enviar_una); en
    `revisar` queda esperando la revisión. Cambiarlo vale para lo que se
    corrija desde ese momento. La primera línea de la salida dice cuál es.
    """
    avisos_preguntas: list[str] = []
    info = cargar_semana(semana, avisos=avisos_preguntas)
    modo = _modo_de_la_corrida(info, sin_modelo)
    print(_configuracion.describir(modo)
          + (" Corrección a mano: no se llama al modelo." if sin_modelo else ""))
    _anunciar_semestre()
    for aviso in avisos_preguntas:
        print(aviso)
    if info.borrador and not dry_run:
        print(f"✗ {info.nombre} está en borrador: no se envió, no hay nada que evaluar.")
        return
    filas = [a for a in _datos.alumnos.leer() if a.get("Correo", "").strip()]
    if not dry_run:
        # Si un corte dejó una evaluacion en el log sin su Nota en la tabla, se
        # completa antes de decidir a quién corregir o reenviar.
        _datos.notas.sincronizar_desde_log()

    correos = buscar_respuestas_semana(semana, **_criterio_respuestas(info))
    print(f"{f'Módulo {semana}' if info.legado else info.nombre} — {len(correos)} respuesta(s) encontrada(s)")

    template_duplicado = _cargar_template_duplicado()
    automatico = modo == _configuracion.AUTO
    escala = _escala.leer()
    muestra = _configuracion.correo_muestra()
    plantilla = _feedback.Plantilla(dry_run) if automatico else None
    if automatico and plantilla.texto is None:
        print("Sin correo_correccion.md: el correo lleva solo la corrección de la IA.")
    asunto_respuesta = _construir_asunto_respuesta(info)

    # En automático, primero lo que quedó corregido y sin mandar en una corrida
    # anterior (falló el envío): el alumno ya esperó una vez.
    if automatico:
        if dry_run:
            pendientes = _feedback.seleccionar(semana, modo, solo_automaticas=True)["enviar"]
            if pendientes:
                print(f"{len(pendientes)} corrección(es) de una corrida anterior quedaron sin enviar: "
                      f"se enviarían ahora.")
        else:
            previas = _feedback.enviar_pendientes(info, modo, solo_automaticas=True, plantilla=plantilla,
                                                  escala=escala, muestra=muestra)
            if previas["enviados"] or previas["fallidos"]:
                print(f"Reenvío de correcciones anteriores: {previas['enviados']} enviada(s), "
                      f"{previas['fallidos']} fallida(s).")

    procesados = []
    evaluados = 0
    duplicados = 0
    sin_alumno = 0
    fallidos = 0
    ya_evaluados_en_esta_corrida = set()
    repreguntas = 0
    candidatos = []  # lo que se evaluaría, para elegir en la página
    no_elegidos = 0
    ya_procesados = 0
    registradas = _respuestas_registradas()

    for corr in avanzar(correos, "respuestas"):
        # Un correo que ya está en el log se procesó en una corrida anterior
        # que no alcanzó a marcarlo como leído (falló el buzón o se cortó el
        # trabajo). Solo falta marcarlo: volver a tratarlo le mandaba al alumno
        # el correo de "ya respondiste" por su propia respuesta.
        if _sin_angulos(corr.get("message_id")) in registradas:
            ya_procesados += 1
            quien = (_identificar_alumno(corr, semana, filas) or {}).get("Nombre") or corr.get("remitente", "?")
            print(f"  ✓ {quien:30s} ya procesado en una corrida anterior; solo se marca leído")
            procesados.append(corr["uid"])
            continue

        # Si contesta a un feedback que ya le mandamos, no es una respuesta
        # atrasada: es una duda sobre su corrección. Se deja sin leer para que
        # la recoja `python -m modulos.tests.tutoria`. Sin esto el alumno
        # recibía un "ya respondiste, no se te puede evaluar de nuevo".
        if _es_repregunta(corr):
            repreguntas += 1
            continue

        alumno = _identificar_alumno(corr, semana, filas)

        if not alumno:
            sin_alumno += 1
            print(f"  ⚠ No identifiqué al alumno: remitente={corr['remitente']}, asunto={corr['asunto'][:60]}")
            continue

        nombre = alumno.get("Nombre", "?")
        correo_alumno = alumno.get("Correo", "").strip()
        estado_previo = _datos.notas.estado(correo_alumno, _datos.TESTS, semana) or {}
        candidatos.append({
            "correo": correo_alumno.lower(), "nombre": nombre,
            "grupo": alumno.get("Grupo", ""), "llegada": corr.get("fecha"),
            "estado": _estado_candidato(estado_previo),
            "respuesta": corr.get("texto", "").strip()[:3000],
        })

        if solo is not None and correo_alumno.lower() not in solo:
            no_elegidos += 1
            print(f"  ⋯ {nombre:30s} no elegido: su correo queda sin leer")
            continue

        # No se re-corrige a quien ya está corregido (con nota, por revisar o
        # descartado): gasta API y le manda un correo repetido al alumno.
        if _datos.notas.esta_corregida(estado_previo) or correo_alumno.lower() in ya_evaluados_en_esta_corrida:
            duplicados += 1
            motivo = (_ya_corregido_texto(estado_previo) if _datos.notas.esta_corregida(estado_previo)
                      else "ya estaba corregido (en esta corrida)")
            print(f"  ⊘ {nombre:30s} {motivo}")

            if not dry_run:
                try:
                    cuerpo = _construir_cuerpo_duplicado(template_duplicado, nombre)
                    enviar_correo(
                        correo_alumno,
                        asunto_respuesta,
                        cuerpo,
                        html=True,
                        in_reply_to=corr.get("in_reply_to") or None,
                    )
                except Exception as e:
                    print(f"     ✗ Error mandando correo de duplicado: {e}")
                # Queda en el log como respuesta duplicada: no cuenta como su
                # respuesta, pero el equipo docente puede ver qué mandó, y si el
                # correo vuelve a aparecer sin leer se reconoce por su Message-ID.
                _datos.log.registrar("respuesta", _datos.TESTS, semana, correo_alumno.lower(),
                                     Ronda=0, MessageId=corr.get("message_id") or "",
                                     RespondeA=corr.get("in_reply_to") or "",
                                     Respuesta=corr.get("texto", "").strip(),
                                     Detalle=_datos.log.DUPLICADO)
                if _sin_angulos(corr.get("message_id")):
                    registradas.add(_sin_angulos(corr.get("message_id")))
            else:
                mostrar_correo(correo_alumno, asunto_respuesta,
                               _construir_cuerpo_duplicado(template_duplicado, nombre),
                               html=True, nombre=nombre)

            procesados.append(corr["uid"])
            continue

        respuesta_alumno = corr.get("texto", "").strip()

        if not respuesta_alumno:
            print(f"⚠ {nombre}: respuesta vacía, salto")
            continue

        grupo = alumno.get("Grupo", "control").strip().lower()
        grupo_info = info.para_grupo(grupo)

        if dry_run:
            verbo = "dejaría para corregir a mano" if sin_modelo else "evaluaría"
            print(f"→ {nombre}: {verbo} ({len(respuesta_alumno)} chars) [{grupo}]")
            # Como en la corrida real: una segunda respuesta suya recibe el
            # correo de duplicado, y la simulación tiene que mostrarlo.
            ya_evaluados_en_esta_corrida.add(correo_alumno.lower())
            continue

        leida = None
        if sin_modelo:
            html_eval, nota, originalidad, meta = "", "", "", {}
            modelo = f"{_decisiones.DOCENTE}{por or 'desconocido'}"
        else:
            try:
                html_eval = evaluar_respuesta(grupo_info.preguntas, grupo_info.pautas, respuesta_alumno)
            except Exception as e:
                fallidos += 1
                print(f"✗ {nombre}: error GPT: {e}")
                continue
            # JSON con puntajes (la nota la calcula la escala) o el HTML de
            # siempre con NOTA FINAL (la nota la escribió el modelo).
            leida = _correccion.leer(html_eval, escala, _n_preguntas(grupo_info))
            nota, originalidad = leida["nota"], leida["originalidad"]
            # El texto del modelo trae encima lo que costó producirlo. Puede venir
            # un str pelado (una prueba con mocks), así que se pide con getattr.
            meta = getattr(html_eval, "meta", {}) or {}
            modelo = meta.get("modelo") or config.MODELO

        # Un puntaje fuera de la rúbrica deja la corrección sin nota: no sale
        # sola aunque la instancia esté en automático, espera la revisión.
        problemas = (leida or {}).get("problemas") or []
        avisos = problemas + ((leida or {}).get("avisos") or [])
        modo_alumno = _configuracion.REVISAR if problemas else modo

        # La corrección queda registrada antes de mandar nada: la API ya se
        # gastó, y si el envío falla la corrida siguiente la manda sin volver
        # a corregir.
        _c = correo_alumno.lower()
        correccion = {
            "Modelo": modelo,
            "Versiones": versiones.juntar(meta.get("versiones")),
            "Nota": nota, "Originalidad": originalidad,
            "Puntajes": (leida or {}).get("puntajes", ""),
            "EvaluacionIA": html_eval,
            "Detalle": "; ".join([f"modo={modo_alumno}", *avisos]),
        }
        logro = (leida or {}).get("logro", "")
        try:
            _fecha = corr.get("fecha").isoformat() if corr.get("fecha") else None
            _datos.notas.marcar_respondio(_c, _datos.TESTS, semana, _fecha)
            # Con su Message-ID se reconoce después si el correo vuelve a
            # aparecer sin leer; RespondeA dice a qué envío contestó, y es el
            # hilo en que sale el feedback.
            _datos.log.registrar("respuesta", _datos.TESTS, semana, _c,
                                 Ronda=0, MessageId=corr.get("message_id") or "",
                                 RespondeA=corr.get("in_reply_to") or "",
                                 Respuesta=respuesta_alumno)
            _datos.log.registrar("correccion", _datos.TESTS, semana, _c,
                                 Ronda=0,
                                 TokensEntrada=meta.get("prompt_tokens") or "",
                                 TokensSalida=meta.get("completion_tokens") or "",
                                 Logro=logro, **correccion)
            _datos.notas.marcar_corregido(_c, _datos.TESTS, semana, logro=logro)
        except Exception as _e:  # noqa: BLE001
            print(f"     ⚠ no pude registrar la corrección: {_e}")

        ya_evaluados_en_esta_corrida.add(_c)
        evaluados += 1
        procesados.append(corr["uid"])

        for aviso in avisos:
            print(f"  ⚠ {nombre}: {aviso}")
        if automatico and problemas:
            print(f"⋯ {nombre}: corregido sin nota; queda por revisar en Tests › Revisar")
        elif automatico:
            id_feedback = _feedback.enviar_una(info, _c, nombre, correccion, None, plantilla,
                                               in_reply_to=corr.get("in_reply_to") or None,
                                               escala=escala, muestra=muestra)
            if id_feedback is None:
                fallidos += 1
                print(f"✗ {nombre}: corregido (nota {nota or '?'}), pero el feedback no salió")
                continue
            print(f"✓ {nombre}: nota {nota or '?'}, originalidad {originalidad or '?'}")
        elif sin_modelo:
            print(f"✓ {nombre}: queda para corregir a mano en Tests › Revisar")
        else:
            print(f"✓ {nombre}: corregido, espera revisión (nota propuesta {nota or '?'}, "
                  f"originalidad {originalidad or '?'})")

    if not dry_run and procesados:
        # Marcar como leídos es lo último y lo menos importante: si falla, todo
        # el trabajo ya está guardado y los correos ya salieron. Antes esto
        # reventaba con un traceback que hacía parecer que se perdió la corrida.
        from modulos.mail import marcar_leidos
        try:
            marcar_leidos(procesados)
        except Exception as e:
            print(f"⚠ No pude marcar los correos como leídos: {e}")
            print(f"  Las {evaluados} correcciones SÍ quedaron guardadas"
                  + (" y los correos ya se enviaron." if automatico else ".") + " No hay que repetir nada.")
            print(f"  Quedan {len(procesados)} correos sin marcar en el buzón. "
                  f"Volver a correr este paso es seguro: los que ya se procesaron "
                  f"se reconocen y solo se marcan, sin mandar nada.")

    if dry_run:
        _candidatos.guardar("tests_semanales", semana, candidatos)
        if candidatos:
            print(f"\n{len(candidatos)} respuesta(s) para elegir cuáles evaluar.")

    if correos:
        print(f"\nEvaluados: {evaluados}  Duplicados: {duplicados}  Sin identificar: {sin_alumno}  Fallidos: {fallidos}"
              + (f"  No elegidos: {no_elegidos}" if no_elegidos else "")
              + (f"  Ya procesados antes: {ya_procesados}" if ya_procesados else ""))
        if repreguntas:
            print(f"Repreguntas sobre el feedback: {repreguntas} (sin leer; las atiende: python -m modulos.tests.tutoria {semana})")
        if not automatico and evaluados and not dry_run:
            print(f"Las {evaluados} corrección(es) esperan en Tests › Revisar: el alumno no recibe nada todavía.")

    estados = {e["Correo"]: e for e in _datos.notas.leer(flujo=_datos.TESTS, item=semana)}
    # Quien tiene nota (o corrección) entregó, aunque "Respondio" esté vacío
    # (pasa con datos migrados). Sin esto salía a la vez evaluado y "no entregó".
    sin_entregar = [
        f for f in filas
        if (est := estados.get(f["Correo"].strip().lower()))
        and est.get("Enviado", "").strip()
        and not est.get("Respondio", "").strip()
        and not _datos.notas.esta_corregida(est)
    ]
    if sin_entregar:
        print()
        for f in sin_entregar:
            print(f"→ {f.get('Nombre', '?'):30s}: no entregó")


def _parsear_args(argv: list[str] | None = None) -> tuple[int, bool, bool, str]:
    args = sys.argv[1:] if argv is None else argv
    semana = None
    dry_run = False
    sin_modelo = False
    por = ""

    i = 0
    while i < len(args):
        a = args[i]
        al = a.lower()
        if al == "--dry-run":
            dry_run = True
        elif al == "--sin-modelo":
            sin_modelo = True
        elif al == "--por" and i + 1 < len(args):
            por = args[i + 1].strip()
            i += 1
        elif al.startswith("--por="):
            por = a[len("--por="):].strip()
        elif a.isdigit() and semana is None:
            semana = int(a)
        i += 1

    if semana is None:
        try:
            semana = int(input("¿Semana? → ").strip())
        except (ValueError, EOFError):
            print("Semana inválida.")
            sys.exit(1)

    return semana, dry_run, sin_modelo, por


if __name__ == "__main__":
    semana, dry_run, sin_modelo, por = _parsear_args()
    main(semana, dry_run, solo=_candidatos.solo_de_argv(), sin_modelo=sin_modelo, por=por)
