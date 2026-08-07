import re
import sys

from bs4 import BeautifulSoup

from . import config, storage
from .correo import enviar_correo, buscar_respuestas_semana, marcar_leido
from .openai_client import evaluar_respuesta
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
    m = re.search(r'ORIGINALIDAD\s*:?\s*([^\n]+)', texto, re.IGNORECASE)
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


def _identificar_alumno(corr_recibido: dict, semana: int, filas_alumnos: list[dict]) -> dict | None:
    correos_a_alumno = {f.get("Correo", "").strip().lower(): f for f in filas_alumnos}

    irt = corr_recibido.get("in_reply_to", "").strip()
    if irt:
        correo_match = storage.buscar_alumno_por_message_id(irt, semana)
        if correo_match and correo_match.lower() in correos_a_alumno:
            return correos_a_alumno[correo_match.lower()]

    remitente = corr_recibido.get("remitente", "").lower()
    if remitente in correos_a_alumno:
        return correos_a_alumno[remitente]

    return None


def main(semana: int, dry_run: bool = False) -> None:
    info = cargar_semana(semana)
    filas, headers = storage.leer_alumnos()
    headers = storage.asegurar_columnas_semana(headers, semana)

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

    for corr in correos:
        alumno = _identificar_alumno(corr, semana, filas)

        if not alumno:
            sin_alumno += 1
            print(f"  ⚠ No identifiqué al alumno: remitente={corr['remitente']}, asunto={corr['asunto'][:60]}")
            continue

        nombre = alumno.get("Nombre", "?")
        correo_alumno = alumno.get("Correo", "").strip()

        nota_existente = alumno.get(storage.col_nota(semana), "").strip()
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

        try:
            enviar_correo(
                correo_alumno,
                asunto_respuesta,
                html_eval,
                html=True,
                in_reply_to=corr.get("in_reply_to") or None,
            )
        except Exception as e:
            fallidos += 1
            print(f"✗ {nombre}: GPT OK pero falló envío: {e}")

        alumno[storage.col_nota(semana)] = nota
        alumno[storage.col_originalidad(semana)] = originalidad
        alumno[storage.col_respuesta(semana)] = respuesta_alumno

        ya_evaluados_en_esta_corrida.add(correo_alumno.lower())
        evaluados += 1
        print(f"✓ {nombre}: nota {nota or '?'}, originalidad {originalidad or '?'}")
        procesados.append(corr["uid"])

    if not dry_run and procesados:
        storage.escribir_alumnos(filas, headers)
        from .correo import marcar_leidos
        marcar_leidos(procesados)

    if correos:
        print(f"\nEvaluados: {evaluados}  Duplicados: {duplicados}  Sin identificar: {sin_alumno}  Fallidos: {fallidos}")

    sin_entregar = [
        f for f in filas
        if f.get(storage.col_envio(semana), "").strip().upper() == "SI"
        and f.get("Correo", "").strip()
        and not f.get(storage.col_respuesta(semana), "").strip()
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
