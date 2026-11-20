"""
Envío de la pregunta de una instancia de test (una semana, en el formato antiguo).

A cada alumno le llega la versión que le corresponde según su grupo. Quién
falta por recibirla lo dice `datos.notas`; el envío queda registrado ahí y en
el log.
"""

import sys

from modulos import datos
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo

from . import config
from .preguntas import SemanaInfo, asunto as _asunto, cargar_semana
from modulos.progreso import avanzar

SEMILLA_GRUPOS = config.GRUPO_SEED


def _cargar_template_correo() -> str:
    return (config.PROMPTS / "correo_pregunta.md").read_text(encoding="utf-8")


def _construir_bloque_preguntas(preguntas: list[str], legado: bool = True) -> str:
    estilo = ('border-left: 3px solid #ccc; margin: 10px 0; '
              'padding-left: 12px; color: #555;')
    # «de la semana» solo en el formato antiguo: una instancia nueva no es una semana.
    de = " de la semana" if legado else ""
    if len(preguntas) == 1:
        return (f'<p>La pregunta{de} es:</p>\n'
                f'<blockquote style="{estilo}">\n  {preguntas[0]}\n</blockquote>')
    bloques = [f'<p>Las preguntas{de} son:</p>']
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
        .replace("{BLOQUE_PREGUNTAS}", _construir_bloque_preguntas(grupo_info.preguntas, info.legado))
        # El id no se muestra: {SEMANA} es el número visible («2» en «Control 2»),
        # que en el formato antiguo es la semana misma.
        .replace("{SEMANA}", str(info.numero))
        .replace("{TITULO}", info.nombre)
    )


def _construir_asunto(info: SemanaInfo) -> str:
    return _asunto(info)


def _anunciar_semestre() -> str:
    """Deja en pantalla sobre qué semestre se está trabajando.

    El semestre activo se toma de un archivo, no del comando, así que sin
    esto no hay forma de notar que se está operando el equivocado.
    """
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[ENVIAR] semestre {sid}")
    return sid


def main(semana: int, dry_run: bool = False) -> int:
    """Devuelve 0, o 1 si se pidió mandar de verdad una instancia en borrador."""
    _anunciar_semestre()
    info = cargar_semana(semana)
    if info.borrador:
        if not dry_run:
            # El motor también lo frena aquí: un envío programado que llega a su
            # hora después de que alguien volvió la instancia a borrador.
            print(f"✗ {info.nombre} está en borrador: confírmala en Configuración › Preguntas "
                  "antes de enviarla. No se mandó nada.")
            return 1
        print(f"({info.nombre} está en borrador: se puede simular, pero no enviar hasta confirmarla.)")

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
        return 0

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
        return 0

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
    return 0


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
    sys.exit(main(*_parsear_args()))
