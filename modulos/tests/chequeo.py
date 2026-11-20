"""
Verifica que todo esté listo para evaluar una semana, sin enviar nada.

Correr esto antes de `evaluar_respuestas` da el panorama completo: si las
credenciales sirven, cuántas respuestas hay esperando, a quiénes ya se les
puso nota y cuánto va a costar la corrida.

    python -m modulos.tests.chequeo 4

Solo lee: abre el buzón en modo lectura y no toca ningún correo.
"""

import sys

from modulos import datos

from . import config
from modulos.mail import buscar_respuestas_semana
from .evaluar import _mapa_correos
from .preguntas import cargar_semana
from .respuestas import criterio as _criterio_respuestas


def _anunciar_semestre() -> str:
    """Deja en pantalla sobre qué semestre se está trabajando.

    El semestre activo se toma de un archivo, no del comando, así que sin
    esto no hay forma de notar que se está operando el equivocado.
    """
    from modulos import semestre as _sem
    sid = _sem.activo_o_error()
    print(f"[CHEQUEO] semestre {sid}")
    return sid


def main(semana: int) -> int:
    print(f"=== Chequeo previo — semana {semana} ===\n")
    _anunciar_semestre()
    problemas = []

    # 1. credenciales y modelo
    try:
        creds = config.cargar_correo_config()
        print(f"  cuenta de correo   {creds['remitente']}")
        print(f"  modelo             {config.MODELO}")
    except Exception as e:
        print(f"  ✗ credenciales: {e}")
        return 1

    try:
        config.cargar_api_key()
        print("  API key de OpenAI  presente")
    except Exception as e:
        problemas.append(f"falta la API key: {e}")

    # 2. la semana existe y tiene preguntas
    try:
        info = cargar_semana(semana)
        print(f"  tema               {info.tema}")
        print(f"  preguntas          control={len(info.control.preguntas)} "
              f"tratamiento={len(info.tratamiento.preguntas)}")
        if not info.control.pautas or not any(info.control.pautas):
            problemas.append(f"la semana {semana} no tiene pautas de corrección")
    except Exception as e:
        print(f"  ✗ preguntas: {e}")
        return 1

    # 3. el curso
    con_correo = [a for a in datos.alumnos.leer() if a.get("Correo", "").strip()]
    con_nota = {e["Correo"] for e in datos.notas.leer(flujo=datos.TESTS, item=semana)
                if e.get("Nota", "").strip()}
    ya_con_nota = [f for f in con_correo if f["Correo"].strip().lower() in con_nota]
    print(f"  alumnos             {len(con_correo)}")
    print(f"  ya tienen nota      {len(ya_con_nota)}")

    # 4. el buzón (solo lectura)
    print("\n  revisando el buzón...")
    try:
        correos = buscar_respuestas_semana(semana, **_criterio_respuestas(info))
    except Exception as e:
        print(f"  ✗ no pude leer el buzón: {e}")
        return 1

    conocidos = set(_mapa_correos(con_correo))
    de_alumnos = [c for c in correos if c["remitente"] in conocidos]
    ajenos = [c for c in correos if c["remitente"] not in conocidos]
    ya_evaluados = [c for c in de_alumnos
                    if c["remitente"] in {f["Correo"].strip().lower() for f in ya_con_nota}]
    a_evaluar = [c for c in de_alumnos if c not in ya_evaluados]

    print(f"  sin leer {f'del módulo {semana}' if info.legado else f'de {info.nombre}'}: {len(correos)}")
    print(f"     de alumnos del curso   {len(de_alumnos)}")
    print(f"     ya tienen nota         {len(ya_evaluados)}  (se les avisa, no se re-evalúan)")
    print(f"     SE VAN A EVALUAR       {len(a_evaluar)}")
    if ajenos:
        print(f"     ⚠ de remitentes desconocidos: {len(ajenos)}")
        for c in ajenos[:5]:
            print(f"        {c['remitente']}")

    vacias = [c for c in a_evaluar if not c.get("texto", "").strip()]
    if vacias:
        problemas.append(f"{len(vacias)} respuesta(s) quedaron vacías al limpiarlas; "
                         f"se van a saltar")

    # 5. veredicto
    print()
    if problemas:
        print("  Revisar antes de correr:")
        for p in problemas:
            print(f"    - {p}")
    if not a_evaluar:
        print("  Nada que evaluar: o no llegaron respuestas nuevas, o ya están todas con nota.")
    else:
        print(f"  Listo para evaluar {len(a_evaluar)} respuesta(s).")
        print(f"  Eso manda {len(a_evaluar)} correo(s) de feedback y "
              f"{len(ya_evaluados)} aviso(s) de 'ya tenías nota'.")
        print(f"\n  Para correrlo:  python -m modulos.tests.evaluar {semana}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        print("Uso: python -m modulos.tests.chequeo <semana>")
        sys.exit(1)
    sys.exit(main(int(sys.argv[1])))
