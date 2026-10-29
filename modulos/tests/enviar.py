"""
Envío de la pregunta semanal.

A cada alumno le llega la versión que le corresponde según su grupo. Quién
falta por recibirla lo dice `datos.notas`; el envío queda registrado ahí y en
el log.
"""

import sys

from modulos import datos
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo

from . import config
from .preguntas import SemanaInfo, cargar_semana
from modulos.progreso import avanzar

SEMILLA_GRUPOS = config.GRUPO_SEED


def _cargar_template_correo() -> str:
    return (config.PROMPTS / "correo_pregunta.md").read_text(encoding="utf-8")


def _construir_bloque_preguntas(preguntas: list[str]) -> str:
    estilo = ('border-left: 3px solid #ccc; margin: 10px 0; '
              'padding-left: 12px; color: #555;')
    if len(preguntas) == 1:
        return (f'<p>La pregunta de la semana es:</p>\n'
                f'<blockquote style="{estilo}">\n  {preguntas[0]}\n</blockquote>')
    bloques = ['<p>Las preguntas de la semana son:</p>']
    for i, p in enumerate(preguntas, start=1):
        bloques.append(f'<blockquote style="{estilo}">\n  {i}. {p}\n</blockquote>')
    return "\n".join(bloques)


def _construir_cuerpo(template: str, alumno: dict, info: SemanaInfo) -> str:
    nombre_corto = alumno["Nombre"].split()[0] if alumno.get("Nombre") else "estudiante"
    grupo_info = info.para_grupo(alumno.get("Grupo", "control").strip().lower())
    return (
        template
        .replace("{NOMBRE}", nombre_corto)
        .replace("{TEMA}", info.tema)
        .replace("{FECHA_ENTREGA}", info.fecha_entrega)
        .replace("{BLOQUE_PREGUNTAS}", _construir_bloque_preguntas(grupo_info.preguntas))
        .replace("{SEMANA}", str(info.semana))
    )


def _construir_asunto(info: SemanaInfo) -> str:
    return f"Evaluación de Progreso Individual Módulo {info.semana}: {info.tema}"


def _anunciar_semestre() -> str:
    """Deja en pantalla sobre qué semestre se está trabajando.

    El semestre activo se toma de un archivo, no del comando, así que sin
    esto no hay forma de notar que se está operando el equivocado.
    """
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[ENVIAR] semestre {sid}")
    return sid


def main(semana: int, dry_run: bool = False) -> None:
    _anunciar_semestre()
    info = cargar_semana(semana)

    if config.GRUPO_CONTROL_TRATAMIENTO:
        nuevos = datos.alumnos.asignar_grupos_faltantes(SEMILLA_GRUPOS)
        if nuevos:
            print(f"Asigné grupo a {nuevos} alumno(s) nuevo(s).")

    alumnos = [a for a in datos.alumnos.leer() if a.get("Correo", "").strip()]
    faltan = set(datos.notas.pendientes_de_envio(
        [a["Correo"] for a in alumnos], datos.TESTS, semana))
    pendientes = [a for a in alumnos if a["Correo"].strip().lower() in faltan]

    if not pendientes:
        print("Nada por enviar.")
        return

    template = _cargar_template_correo()
    asunto = _construir_asunto(info)

    if dry_run:
        for grupo in ("control", "tratamiento"):
            gi = info.para_grupo(grupo)
            print(f"Preguntas {grupo.upper()}:")
            for i, p in enumerate(gi.preguntas, 1):
                print(f"  P{i}: {p[:200]}{'...' if len(p) > 200 else ''}")
        for grupo in ("control", "tratamiento"):
            ej = next((a for a in pendientes
                       if a.get("Grupo", "control").strip().lower() == grupo), None)
            if ej:
                print(f"\nEjemplo {grupo.upper()} — {ej.get('Nombre')} → {ej.get('Correo')}")
                mostrar_correo(ej["Correo"].strip(), asunto, _construir_cuerpo(template, ej, info),
                               html=True, nombre=ej.get("Nombre", ""))
        # Se recorre igual, sin mandar nada, para que la página muestre la barra.
        for _ in avanzar(pendientes, "correos"):
            pass
        print(f"\nSe enviaría a {len(pendientes)} alumno(s).")
        return

    enviados = fallidos = 0
    for alumno in avanzar(pendientes, "correos"):
        correo = alumno["Correo"].strip()
        grupo = alumno.get("Grupo", "control").strip().lower()
        try:
            cuerpo = _construir_cuerpo(template, alumno, info)
            message_id = enviar_correo(correo, asunto, cuerpo, html=True)

            # se registra apenas sale el correo: si el proceso muere en el
            # siguiente alumno, este no puede quedar sin constancia de envío
            datos.notas.marcar_enviado(correo, datos.TESTS, semana)
            datos.log.registrar("envio", datos.TESTS, semana, correo,
                                MessageId=message_id)
            enviados += 1
            print(f"✓ {alumno.get('Nombre', '?'):30s} [{grupo}] → {correo}")
        except Exception as e:
            fallidos += 1
            datos.log.registrar("error", datos.TESTS, semana, correo, Detalle=str(e))
            print(f"✗ {alumno.get('Nombre', '?'):30s} [{grupo}] → {correo}: {e}")

    print(f"\n{enviados} enviado(s), {fallidos} fallido(s)")


def _parsear_args() -> tuple[int, bool]:
    args = sys.argv[1:]
    semana, dry_run = None, False
    for a in args:
        if a.lower() == "--dry-run":
            dry_run = True
        elif a.isdigit():
            semana = int(a)
    if semana is None:
        try:
            semana = int(input("¿Semana? → ").strip())
        except (ValueError, EOFError):
            print("Semana inválida.")
            sys.exit(1)
    return semana, dry_run


if __name__ == "__main__":
    main(*_parsear_args())
