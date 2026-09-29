import re
import sys

from bs4 import BeautifulSoup


from modulos import datos as _datos
from modulos.datos import esquema as _esquema

from . import config
from modulos.mail import enviar_correo, buscar_respuestas_semana, marcar_leido
from modulos.datos import candidatos as _candidatos
from .ia_prompts import evaluar_respuesta
from .preguntas import cargar_semana, SemanaInfo


def _normalizar_html_gpt(html: str) -> str:
    html = html.strip()
    if html.startswith("```"):
        html = re.sub(r'^```(?:html)?\s*', '', html)
        html = re.sub(r'\s*```$', '', html)
    return html.strip()


def extraer_nota_y_originalidad(html: str) -> tuple[str, str]:
    html = _normalizar_html_gpt(html)
    texto = BeautifulSoup(html, "html.parser").get_text("\n")

    nota = ""
    m = re.search(r'NOTA\s*FINAL\s*:?\s*([0-9]+(?:[.,][0-9]+)?)', texto, re.IGNORECASE)
    if m:
        nota = m.group(1).replace(".", ",")

    originalidad = ""
    # El ":" es obligatorio y debe ir al inicio de línea: si no, cualquier mención
    # de "originalidad" en el texto de retroalimentación se captura por error.
    m = re.search(r'^\s*ORIGINALIDAD\s*:\s*([^\n]+)', texto, re.IGNORECASE | re.MULTILINE)
    if m:
        valor = m.group(1).strip()
        for sep in ('.', '\n', '|', '<'):
            if sep in valor:
                valor = valor.split(sep)[0].strip()
        originalidad = valor

    return nota, originalidad


def _cargar_template_duplicado() -> str:
    return (config.PROMPTS / "correo_duplicado.md").read_text(encoding="utf-8")


def _construir_cuerpo_duplicado(template: str, nombre: str) -> str:
    nombre_corto = nombre.split()[0] if nombre else "estudiante"
    return template.replace("{NOMBRE}", nombre_corto)


def _construir_asunto_respuesta(info: SemanaInfo) -> str:
    return f"Re: Evaluación de Progreso Individual Módulo {info.semana}: {info.tema}"


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
    origen = _datos.log.fila_por_message_id(irt, eventos=_esquema.DEL_AGENTE)
    return origen is not None


def main(semana: int, dry_run: bool = False, solo: set[str] | None = None) -> None:
    """`solo`: si se pasa, evalúa solo a esos correos; el resto queda sin leer."""
    _anunciar_semestre()
    info = cargar_semana(semana)
    filas = [a for a in _datos.alumnos.leer() if a.get("Correo", "").strip()]

    correos = buscar_respuestas_semana(semana)
    print(f"Módulo {semana} — {len(correos)} respuesta(s) encontrada(s)")

    template_duplicado = _cargar_template_duplicado()
    asunto_respuesta = _construir_asunto_respuesta(info)

    procesados = []
    evaluados = 0
    duplicados = 0
    sin_alumno = 0
    fallidos = 0
    ya_evaluados_en_esta_corrida = set()
    repreguntas = 0
    candidatos = []  # lo que se evaluaría, para elegir en la página
    no_elegidos = 0

    for corr in correos:
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
        candidatos.append({
            "correo": correo_alumno.lower(), "nombre": nombre,
            "grupo": alumno.get("Grupo", ""), "llegada": corr.get("fecha"),
            "ya_tiene_nota": (_datos.notas.estado(correo_alumno, _datos.TESTS, semana) or {})
            .get("Nota", "").strip(),
            "respuesta": corr.get("texto", "").strip()[:3000],
        })

        if solo is not None and correo_alumno.lower() not in solo:
            no_elegidos += 1
            print(f"  ⋯ {nombre:30s} no elegido: su correo queda sin leer")
            continue

        # No se re-evalúa a quien ya tiene nota: gasta API y le manda un
        # correo repetido al alumno.
        nota_existente = (_datos.notas.estado(correo_alumno, _datos.TESTS, semana) or {}).get("Nota", "").strip()
        if nota_existente or correo_alumno.lower() in ya_evaluados_en_esta_corrida:
            duplicados += 1
            print(f"  ⊘ {nombre:30s} ya tenía nota ({nota_existente or 'evaluado en esta corrida'})")

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

            procesados.append(corr["uid"])
            continue

        respuesta_alumno = corr.get("texto", "").strip()

        if not respuesta_alumno:
            print(f"⚠ {nombre}: respuesta vacía, salto")
            continue

        grupo = alumno.get("Grupo", "control").strip().lower()
        grupo_info = info.para_grupo(grupo)

        if dry_run:
            print(f"→ {nombre}: evaluaría ({len(respuesta_alumno)} chars) [{grupo}]")
            continue

        try:
            html_eval = evaluar_respuesta(grupo_info.preguntas, grupo_info.pautas, respuesta_alumno)
        except Exception as e:
            fallidos += 1
            print(f"✗ {nombre}: error GPT: {e}")
            continue

        nota, originalidad = extraer_nota_y_originalidad(html_eval)
        # El texto del modelo trae encima lo que costó producirlo. Puede venir
        # un str pelado (una prueba con mocks), así que se pide con getattr.
        meta = getattr(html_eval, "meta", {}) or {}

        id_feedback = None
        try:
            id_feedback = enviar_correo(
                correo_alumno,
                asunto_respuesta,
                html_eval,
                html=True,
                in_reply_to=corr.get("in_reply_to") or None,
            )
        except Exception as e:
            fallidos += 1
            print(f"✗ {nombre}: GPT OK pero falló envío: {e}")

        # Se registra apenas se corrige: el correo ya salió y la API ya se
        # gastó, así que perder esto obligaría a repetir todo.
        try:
            _c = correo_alumno.lower()
            _fecha = corr.get("fecha").isoformat() if corr.get("fecha") else None
            _datos.notas.marcar_respondio(_c, _datos.TESTS, semana, _fecha)
            _datos.notas.registrar_nota(_c, _datos.TESTS, semana, nota, originalidad)
            _datos.log.registrar("respuesta", _datos.TESTS, semana, _c,
                                 Ronda=0, Respuesta=respuesta_alumno)
            # El MessageId del feedback es lo que después permite reconocer una
            # repregunta del alumno sobre esta corrección. Antes se generaba y
            # se descartaba, y por eso una repregunta era indistinguible de una
            # respuesta atrasada.
            _datos.log.registrar("evaluacion", _datos.TESTS, semana, _c,
                                 Ronda=0,
                                 MessageId=id_feedback or "",
                                 Modelo=meta.get("modelo") or config.MODELO,
                                 TokensEntrada=meta.get("prompt_tokens") or "",
                                 TokensSalida=meta.get("completion_tokens") or "",
                                 Nota=nota, Originalidad=originalidad,
                                 EvaluacionIA=html_eval)
        except Exception as _e:  # noqa: BLE001
            print(f"     ⚠ no pude registrar en el esquema nuevo: {_e}")

        ya_evaluados_en_esta_corrida.add(correo_alumno.lower())
        evaluados += 1

        print(f"✓ {nombre}: nota {nota or '?'}, originalidad {originalidad or '?'}")
        procesados.append(corr["uid"])

    if not dry_run and procesados:
        # Marcar como leídos es lo último y lo menos importante: si falla, todo
        # el trabajo ya está guardado y los correos ya salieron. Antes esto
        # reventaba con un traceback que hacía parecer que se perdió la corrida.
        from modulos.mail import marcar_leidos
        try:
            marcar_leidos(procesados)
        except Exception as e:
            print(f"⚠ No pude marcar los correos como leídos: {e}")
            print(f"  Las {evaluados} evaluaciones SÍ quedaron guardadas y los "
                  f"correos ya se enviaron. No hay que repetir nada.")
            print(f"  Quedan {len(procesados)} correos sin marcar en el buzón. "
                  f"Volver a correr este paso es seguro: los que ya tienen nota "
                  f"no se re-evalúan, solo se marcan.")

    if dry_run:
        _candidatos.guardar("tests_semanales", semana, candidatos)
        if candidatos:
            print(f"\n{len(candidatos)} respuesta(s) para elegir cuáles evaluar.")

    if correos:
        print(f"\nEvaluados: {evaluados}  Duplicados: {duplicados}  Sin identificar: {sin_alumno}  Fallidos: {fallidos}"
              + (f"  No elegidos: {no_elegidos}" if no_elegidos else ""))
        if repreguntas:
            print(f"Repreguntas sobre el feedback: {repreguntas} (sin leer; las atiende: python -m modulos.tests.tutoria {semana})")

    estados = {e["Correo"]: e for e in _datos.notas.leer(flujo=_datos.TESTS, item=semana)}
    # Quien tiene nota entregó, aunque "Respondio" esté vacío (pasa con datos
    # migrados). Sin esto salía a la vez evaluado y "no entregó".
    sin_entregar = [
        f for f in filas
        if (est := estados.get(f["Correo"].strip().lower()))
        and est.get("Enviado", "").strip()
        and not est.get("Respondio", "").strip()
        and not est.get("Nota", "").strip()
    ]
    if sin_entregar:
        print()
        for f in sin_entregar:
            print(f"→ {f.get('Nombre', '?'):30s}: no entregó")


def _parsear_args() -> tuple[int, bool]:
    args = sys.argv[1:]
    semana = None
    dry_run = False

    for a in args:
        al = a.lower()
        if al == "--dry-run":
            dry_run = True
        elif a.isdigit() and semana is None:
            semana = int(a)

    if semana is None:
        try:
            semana = int(input("¿Semana? → ").strip())
        except (ValueError, EOFError):
            print("Semana inválida.")
            sys.exit(1)

    return semana, dry_run


if __name__ == "__main__":
    semana, dry_run = _parsear_args()
    main(semana, dry_run, solo=_candidatos.solo_de_argv())
