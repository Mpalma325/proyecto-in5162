"""
Paso 2 del flujo: enviar correos con la pregunta a cada integrante.

Lee el CSV de la tarea, y para cada integrante con correo y pregunta al que
todavía no se le envió
compone un correo personalizado y lo envía. Guarda el Message-ID para matcheo
posterior de respuestas.

Uso:
    python -m modulos.tareas.enviar                # tarea = config.TAREA_DEFAULT
    python -m modulos.tareas.enviar T1
    python -m modulos.tareas.enviar T1 --dry-run   # NO envía, solo muestra qué se enviaría
    python -m modulos.tareas.enviar T1 --minutos 25  # plazo para responder (por defecto 20)
    python -m modulos.tareas.enviar T1 --desde 2026-11-13T10:00-03:00
                                   # el plazo se cuenta desde esa hora (envío programado)

El plazo se calcula al empezar a enviar, no se escribe en la plantilla: la
plantilla dice "Plazo de respuesta: {plazo} hrs. Tienes {minutos} minutos..." y
queda "hoy viernes 13 de noviembre de 2026, hasta las 10:25". El plazo de cada
alumno se guarda en el CSV, para que recolectar y corregir sepan quién respondió
tarde.

Cuando el envío se programa desde la página, la recolección y la corrección
quedan agendadas para ese plazo. Por eso el plazo se cuenta desde la hora
programada (--desde), y no desde que la cola lo despachó.
"""

import re
import sys
from datetime import datetime, timedelta

from modulos import datos as _datos

from . import asignacion as _asignacion
from . import config, storage
from .alumnos import nombre_de_pila
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo
from modulos.progreso import avanzar


def _cargar_template() -> str:
    return (config.PROMPTS / "correo_pregunta.md").read_text(encoding="utf-8")


MINUTOS_POR_DEFECTO = 20
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


# Cuánto puede atrasarse un envío programado y seguir contando el plazo desde la
# hora programada. Más que eso, los alumnos tendrían muy poco tiempo.
ATRASO_TOLERADO = timedelta(minutes=5)


def inicio_del_plazo(desde: str | None, ahora: datetime) -> tuple[datetime, str]:
    """Desde cuándo corre el plazo, y un aviso si no se pudo usar la hora programada."""
    if not desde:
        return ahora, ""
    try:
        programado = datetime.fromisoformat(desde.replace("Z", "+00:00")).astimezone(ahora.tzinfo)
    except ValueError:
        return ahora, f"⚠ No entendí la hora programada ({desde}); el plazo se cuenta desde ahora."
    if ahora - programado > ATRASO_TOLERADO:
        atraso = int((ahora - programado).total_seconds() // 60)
        return ahora, (f"⚠ El envío salió {atraso} minutos después de lo programado; el plazo se "
                       "cuenta desde ahora. La recolección agendada puede llegar antes de que "
                       "venza: recolecta de nuevo después del plazo.")
    return min(programado, ahora), ""


def calcular_plazo(inicio: datetime, minutos: int) -> datetime:
    """Hasta cuándo se puede responder: el minuto en que se empezó a enviar, más los minutos."""
    return inicio.replace(second=0, microsecond=0) + timedelta(minutes=minutos)


def texto_plazo(plazo: datetime) -> str:
    """Como iba escrito a mano en T1 y T2: "hoy viernes 13 de noviembre de 2026, hasta las 10:25"."""
    return (f"hoy {_DIAS[plazo.weekday()]} {plazo.day} de {_MESES[plazo.month - 1]} de {plazo.year}, "
            f"hasta las {plazo:%H:%M}")


# Una fecha u hora escrita a mano en la plantilla: "viernes 11 de septiembre",
# "11/09", "10:20".
_RE_FECHA_ESCRITA = re.compile(
    r"\b\d{1,2}\s+de\s+(?:" + "|".join(_MESES) + r")\b"
    r"|\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+\d{1,2}\b"
    # Con barra y un mes posible (11/9, 11/09/2026), o con guion y año completo
    # (11-09-2026). «2-3 líneas» o «Preguntas 1-2» no son fechas.
    r"|\b(?:[0-2]?\d|3[01])/(?:0?[1-9]|1[0-2])(?:/\d{2,4})?\b"
    r"|\b\d{1,2}-\d{1,2}-\d{4}\b"
    r"|\b\d{1,2}:\d{2}\b",
    re.IGNORECASE)


def revisar_plazo_plantilla(template: str, plazo: datetime) -> tuple[str, bool]:
    """
    Si la plantilla dice el plazo de verdad: (aviso, si hay que detener el envío).

    El plazo se calcula al enviar y entra al correo por {plazo}. La plantilla de
    2026-2 lo traía escrito a mano ("hoy viernes 11 de septiembre de 2026, hasta
    las 10:20"), y en la prueba del 19/11 salieron 155 correos con esa fecha
    mientras el CSV guardaba la real. Sin {plazo}:
    - con una fecha u hora escrita que no es el plazo de este envío, no se envía;
    - sin fecha ni hora ("tienes 20 minutos"), se envía con un aviso.
    """
    if "{plazo}" in template:
        return "", False
    if texto_plazo(plazo) in template:
        return ("⚠ correo_pregunta.md no usa {plazo}, pero la fecha escrita calza con la de este "
                f"envío ({texto_plazo(plazo)}). Cámbiala por {{plazo}} para la próxima."), False
    fecha = _RE_FECHA_ESCRITA.search(template)
    if fecha:
        return (f"✗ correo_pregunta.md no usa {{plazo}} y trae una fecha u hora escrita a mano "
                f"(«{fecha.group()}») que no es el plazo de este envío ({texto_plazo(plazo)}). "
                "No se envía nada: reemplaza esa fecha por {plazo} (y los minutos por {minutos}) "
                "en la plantilla."), True
    return ("⚠ correo_pregunta.md no usa {plazo}: el correo no dice hasta cuándo se puede "
            f"responder. El plazo que cuenta para recolectar y corregir es {texto_plazo(plazo)}."), False


def _construir_cuerpo(template: str, fila: dict, plazo: datetime | None = None,
                      minutos: int = MINUTOS_POR_DEFECTO) -> str:
    plazo = plazo or calcular_plazo(datetime.now().astimezone(), minutos)
    return template.format(
        nombre=nombre_de_pila(fila.get("alumno_correo", ""), fila.get("alumno_nombre", "")),
        tarea=fila["tarea"],
        pregunta_tarea=fila["pregunta_tarea"] or "pregunta",
        pregunta=fila["pregunta"],
        plazo=texto_plazo(plazo),
        minutos=minutos,
    )


def _construir_asunto(fila: dict) -> str:
    """Asunto limpio y humano. El tracking va por Message-ID (header oculto)."""
    return f"Pregunta de comprensión — {config.CURSO} {fila['tarea']}"


def _completar_correos(tarea: str, filas: list[dict], guardar: bool) -> None:
    """Los correos elegidos a mano en el chequeo, para quien quedó sin correo al generar."""
    correos = _asignacion.leer_correos(tarea)
    for f in filas:
        if f.get("alumno_correo", "").strip():
            continue
        correo = _asignacion.correo_elegido(correos, f.get("grupo_archivo", ""), f.get("alumno_nombre", ""))
        if correo:
            f["alumno_correo"] = correo
            if guardar:
                storage.actualizar_fila(tarea, f["grupo_archivo"], f["alumno_nombre"],
                                        {"alumno_correo": correo})
            print(f"  {f['alumno_nombre']}: correo elegido a mano, {correo}")


def main(tarea: str, dry_run: bool = False, minutos: int = MINUTOS_POR_DEFECTO,
         desde: str | None = None) -> bool:
    """Devuelve False si no se envió por un problema que hay que arreglar antes."""
    filas = storage.leer_csv(tarea)
    if not filas:
        print(f"No hay CSV para tarea {tarea}. Corre primero el paso 1.")
        return

    template = _cargar_template()
    _completar_correos(tarea, filas, guardar=not dry_run)

    pendientes = []
    for f in filas:
        if not (f.get("alumno_correo") and f.get("pregunta")):
            continue
        if _datos.notas.ya_enviado(f["alumno_correo"], _datos.TAREAS, tarea):
            continue
        # Una sola pregunta por alumno, aunque haya quedado en dos filas.
        correo = f["alumno_correo"].strip().lower()
        if any(p["alumno_correo"].strip().lower() == correo for p in pendientes):
            print(f"  ⚠ {f['alumno_nombre']} tiene más de una pregunta; se envía solo la primera.")
            continue
        pendientes.append(f)

    sin_correo = [f for f in filas if f.get("pregunta") and not f.get("alumno_correo")]
    sin_pregunta = [f for f in filas if not f.get("pregunta")]
    ya_enviados = [f for f in filas if f.get("alumno_correo", "").strip()
                   and _datos.notas.ya_enviado(f["alumno_correo"], _datos.TAREAS, tarea)]

    print(f"Tarea {tarea}:")
    print(f"  Total filas: {len(filas)}")
    print(f"  A enviar: {len(pendientes)}")
    print(f"  Sin correo (arreglar en CSV antes de continuar): {len(sin_correo)}")
    print(f"  Sin pregunta (no contribuyeron con código): {len(sin_pregunta)}")
    print(f"  Ya enviados antes: {len(ya_enviados)}")

    if sin_correo:
        print("\n⚠️  Integrantes sin correo:")
        for f in sin_correo:
            print(f"   - {f['alumno_nombre']} ({f['grupo_archivo']})")

    if not pendientes:
        print("\nNada por enviar.")
        return

    inicio, aviso = inicio_del_plazo(desde, datetime.now().astimezone())
    if aviso:
        print(f"\n{aviso}")
    plazo = calcular_plazo(inicio, minutos)
    print(f"\nPlazo para responder: {texto_plazo(plazo)} ({minutos} minutos).")
    aviso_plantilla, detener = revisar_plazo_plantilla(template, plazo)
    if aviso_plantilla:
        print(f"\n{aviso_plantilla}")
    if detener and not dry_run:
        return False
    if dry_run:
        print("\n--- DRY RUN (no se envía nada) ---")
    else:
        print("\n--- ENVIANDO ---")

    for fila in avanzar(pendientes, "correos"):
        asunto = _construir_asunto(fila)
        cuerpo = _construir_cuerpo(template, fila, plazo, minutos)

        if dry_run:
            print(f"\n→ A: {fila['alumno_correo']}")
            mostrar_correo(fila["alumno_correo"], asunto, cuerpo, nombre=fila.get("alumno_nombre", ""))
            continue

        try:
            message_id = enviar_correo(fila["alumno_correo"], asunto, cuerpo)
            storage.actualizar_fila(
                tarea,
                fila["grupo_archivo"],
                fila["alumno_nombre"],
                {"message_id": message_id, "plazo": plazo.isoformat(timespec="minutes")},
            )
            try:
                _datos.notas.marcar_enviado(fila["alumno_correo"], _datos.TAREAS, tarea)
                _datos.log.registrar("envio", _datos.TAREAS, tarea,
                                     fila["alumno_correo"], MessageId=message_id)
            except Exception as _e:  # noqa: BLE001
                print(f"     ⚠ no pude registrar en el esquema nuevo: {_e}")

            print(f"  ✓ {fila['alumno_nombre']:30s} → {fila['alumno_correo']}")
        except Exception as e:
            print(f"  ✗ {fila['alumno_nombre']:30s} → {fila['alumno_correo']}: {e}")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = config.TAREA_DEFAULT
    dry_run = False
    minutos = MINUTOS_POR_DEFECTO
    desde = None

    for i, a in enumerate(args):
        if a.lower() == "--dry-run":
            dry_run = True
        elif a == "--minutos" and i + 1 < len(args):
            minutos = int(args[i + 1])
        elif a == "--desde" and i + 1 < len(args):
            desde = args[i + 1]
        elif a.upper().startswith('T') and a[1:].isdigit():
            tarea = a.upper()

    if main(tarea, dry_run, minutos, desde) is False:
        sys.exit(1)
