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

import sys
from datetime import datetime, timedelta

from modulos import datos as _datos

from . import asignacion as _asignacion
from . import config, storage
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


def _construir_cuerpo(template: str, fila: dict, plazo: datetime | None = None,
                      minutos: int = MINUTOS_POR_DEFECTO) -> str:
    plazo = plazo or calcular_plazo(datetime.now().astimezone(), minutos)
    return template.format(
        nombre=fila["alumno_nombre"].split()[0] if fila["alumno_nombre"] else "estudiante",
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
         desde: str | None = None) -> None:
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

    main(tarea, dry_run, minutos, desde)
