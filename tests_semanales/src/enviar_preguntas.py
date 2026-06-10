import sys

from . import config, storage
from .correo import enviar_correo
from .preguntas import cargar_semana, SemanaInfo


def _cargar_template_correo() -> str:
    return (config.PROMPTS / "correo_pregunta.md").read_text(encoding="utf-8")


def _construir_bloque_preguntas(preguntas: list[str]) -> str:
    if len(preguntas) == 1:
        return (
            '<p>La pregunta de la semana es:</p>\n'
            '<blockquote style="border-left: 3px solid #ccc; margin: 10px 0; '
            'padding-left: 12px; color: #555;">\n'
            f'  {preguntas[0]}\n'
            '</blockquote>'
        )
    bloques = []
    bloques.append('<p>Las preguntas de la semana son:</p>')
    for i, p in enumerate(preguntas, start=1):
        bloques.append(
            f'<blockquote style="border-left: 3px solid #ccc; margin: 10px 0; '
            f'padding-left: 12px; color: #555;">\n  {i}. {p}\n</blockquote>'
        )
    return "\n".join(bloques)


def _construir_cuerpo(template: str, alumno: dict, info: SemanaInfo) -> str:
    nombre_corto = alumno["Nombre"].split()[0] if alumno.get("Nombre") else "estudiante"

    grupo = alumno.get("Grupo", "control").strip().lower()
    grupo_info = info.para_grupo(grupo)

    bloque_preguntas = _construir_bloque_preguntas(grupo_info.preguntas)
    return (
        template
        .replace("{NOMBRE}", nombre_corto)
        .replace("{TEMA}", info.tema)
        .replace("{FECHA_ENTREGA}", info.fecha_entrega)
        .replace("{BLOQUE_PREGUNTAS}", bloque_preguntas)
        .replace("{SEMANA}", str(info.semana))
    )


def _construir_asunto(info: SemanaInfo) -> str:
    return f"Evaluación de Progreso Individual Módulo {info.semana}: {info.tema}"


def main(semana: int, dry_run: bool = False) -> None:
    info = cargar_semana(semana)
    filas, headers = storage.leer_alumnos()
    headers = storage.asegurar_columnas_semana(headers, semana)
    headers = storage.asignar_grupos_si_falta(filas, headers)

    template = _cargar_template_correo()
    asunto = _construir_asunto(info)

    pendientes = [
        f for f in filas
        if f.get("Correo", "").strip()
        and f.get(storage.col_envio(semana), "").strip().upper() != "SI"
    ]

    if not pendientes:
        print("Nada por enviar.")
        return

    if dry_run:
        for grupo_nombre in ["control", "tratamiento"]:
            grupo_info = info.para_grupo(grupo_nombre)
            print(f"Preguntas {grupo_nombre.upper()}:")
            for i, p in enumerate(grupo_info.preguntas, 1):
                print(f"  P{i}: {p[:200]}{'...' if len(p) > 200 else ''}")

        for grupo_nombre in ["control", "tratamiento"]:
            ejemplos = [f for f in pendientes if f.get("Grupo", "control").strip().lower() == grupo_nombre]
            if ejemplos:
                ej = ejemplos[0]
                cuerpo = _construir_cuerpo(template, ej, info)
                print(f"\nEjemplo {grupo_nombre.upper()} — {ej.get('Nombre')} → {ej.get('Correo')}")
                print(f"Asunto: {asunto}")
                print(cuerpo)
        return

    enviados = 0
    fallidos = 0
    for fila in pendientes:
        correo = fila["Correo"].strip()
        grupo = fila.get("Grupo", "control").strip().lower()
        try:
            cuerpo = _construir_cuerpo(template, fila, info)
            message_id = enviar_correo(correo, asunto, cuerpo, html=True)
            storage.registrar_message_id(correo, semana, message_id)
            fila[storage.col_envio(semana)] = "SI"
            enviados += 1
            print(f"✓ {fila.get('Nombre', '?'):30s} [{grupo}] → {correo}")
        except Exception as e:
            fallidos += 1
            print(f"✗ {fila.get('Nombre', '?'):30s} [{grupo}] → {correo}: {e}")

    storage.escribir_alumnos(filas, headers)
    print(f"\n{enviados} enviado(s), {fallidos} fallido(s)")


def _parsear_args() -> tuple[int, bool]:
    args = sys.argv[1:]
    semana = None
    dry_run = False

    for a in args:
        al = a.lower()
        if al == "--dry-run":
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
    semana, dry_run = _parsear_args()
    main(semana, dry_run)
