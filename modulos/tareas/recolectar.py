"""
Paso 3 del flujo: recolectar respuestas de los alumnos desde el inbox.

Lee el CSV de la tarea, identifica las filas con correo enviado pero sin
respuesta, busca en el inbox los correos que sean Reply a esos Message-IDs,
y guarda el texto de la respuesta + timestamp en el CSV.

Uso:
    python -m modulos.tareas.recolectar               # tarea = config.TAREA_DEFAULT
    python -m modulos.tareas.recolectar T1
    python -m modulos.tareas.recolectar T1 --solo a@x.cl,b@y.cl   # solo esos correos

Con --solo se busca la respuesta solo de esos alumnos; los demás pendientes
siguen igual. Lo usa el envío programado a un grupo chico, para que una
respuesta tardía de otro envío no entre en esta tanda.

Si el alumno mandó más de un correo, los que llegaron dentro del plazo se
juntan en una sola respuesta, en orden y con una línea que los separa, y el
plazo se mide con el primero. Los que llegaron después del plazo no entran en
lo que se corrige: quedan anotados en la columna `aviso` de feedback_<T>.csv,
igual que una respuesta desde otra dirección o con adjuntos (que no se leen).
Un correo que trae solo la cita de la pregunta, sin una línea del alumno,
cuenta como vacío: igual que antes un correo vacío, el alumno sigue sin
respuesta.
"""

import sys
from datetime import datetime

from modulos import datos as _datos
from modulos.datos import candidatos as _candidatos
from modulos.mail.limpieza import es_solo_eco

from . import config, storage
from modulos.mail import buscar_respuestas
from modulos.progreso import avanzar

# Las plantillas de los correos que se le mandan al alumno con una pregunta.
_PLANTILLAS_PREGUNTA = ("correo_pregunta.md", "correo_segunda_oportunidad.md")


def _solo_cita(texto: str, fila: dict) -> bool:
    """¿El correo trae solo lo que le mandamos, sin una línea del alumno?"""
    from .enviar import texto_plazo
    try:
        plazo_txt = texto_plazo(datetime.fromisoformat((fila.get("plazo") or "").strip()))
    except ValueError:
        plazo_txt = None
    valores = {"tarea": fila.get("tarea"), "pregunta_tarea": fila.get("pregunta_tarea") or "pregunta",
               "pregunta": fila.get("pregunta"), "plazo": plazo_txt,
               # El saludo pudo salir con otro nombre (antes era el de la tabla
               # de roles): calza con cualquiera.
               "nombre": None}
    for nombre in _PLANTILLAS_PREGUNTA:
        ruta = config.PROMPTS / nombre
        if ruta.exists() and es_solo_eco(texto, ruta.read_text(encoding="utf-8"), valores):
            return True
    return False


def _momento(fecha: str) -> float:
    try:
        return datetime.fromisoformat(fecha).timestamp()
    except (ValueError, TypeError):
        return float("inf")


def juntar(fila: dict, correos) -> tuple[dict | None, list[str]]:
    """
    La respuesta que cuenta, a partir de todos los correos del alumno en el hilo.

    Devuelve ({'texto', 'fecha'}, avisos), o (None, avisos) si ningún correo
    trae texto propio. `correos` es la lista de buscar_respuestas; se acepta
    también un solo dict.
    """
    correos = correos if isinstance(correos, list) else [correos]
    vistos, ordenados = set(), []
    for c in sorted(correos, key=lambda c: _momento(c.get("fecha", ""))):
        clave = (c.get("fecha", ""), (c.get("texto") or "").strip())
        if clave not in vistos:
            vistos.add(clave)
            ordenados.append(c)

    avisos = []
    con_texto = []
    for c in ordenados:
        texto = (c.get("texto") or "").strip()
        if texto and _solo_cita(texto, fila):
            texto = ""
        if c.get("adjuntos"):
            avisos.append(f"respondió con adjuntos que no se leen ({', '.join(c['adjuntos'])})"
                          + ("" if texto else ", sin texto en el correo"))
        elif not texto:
            avisos.append("llegó un correo con solo la cita de la pregunta, que cuenta como sin respuesta")
        if texto:
            con_texto.append({**c, "texto": texto})

    correo_alumno = (fila.get("alumno_correo") or "").strip().lower()
    otras = sorted({(c.get("remitente") or "").strip().lower() for c in ordenados} - {correo_alumno, ""})
    if otras and correo_alumno:
        avisos.append(f"respondió desde otra dirección ({', '.join(otras)})")
    if not con_texto:
        return None, avisos

    a_tiempo = [c for c in con_texto if not storage.respondio_tarde(fila, c["fecha"])]
    # Si el primero ya llegó tarde, la respuesta entera es tardía, como antes.
    cuentan = a_tiempo or con_texto
    for c in con_texto:
        if not any(c is x for x in cuentan):
            avisos.append(f"mandó otro correo a las {storage.hora(c['fecha'])}, después del plazo; "
                          "no entra en la corrección")
    texto = cuentan[0]["texto"]
    for i, c in enumerate(cuentan[1:], start=2):
        texto += f"\n\n--- correo {i} de {len(cuentan)}, {storage.hora(c['fecha'])} ---\n\n{c['texto']}"
    if len(cuentan) > 1:
        donde = "dentro del plazo" if a_tiempo else "fuera del plazo"
        avisos.append(f"mandó {len(cuentan)} correos {donde}; se corrigen juntos")
    return {"texto": texto, "fecha": cuentan[0]["fecha"]}, avisos


def _anotar(tarea: str, fila: dict, avisos: list[str]) -> None:
    """Suma los avisos a la columna `aviso`, sin repetir los que ya estaban."""
    actual = (fila.get("aviso") or "").strip()
    nuevos = [a for a in dict.fromkeys(avisos) if a not in actual]
    for a in nuevos:
        print(f"     ⚠ {a}")
    if nuevos:
        fila["aviso"] = "; ".join(([actual] if actual else []) + nuevos)
        storage.actualizar_fila(tarea, fila["grupo_archivo"], fila["alumno_nombre"], {"aviso": fila["aviso"]})


def main(tarea: str, solo: set[str] | None = None) -> None:
    """`solo`: si se pasa, busca solo las respuestas de esos correos."""
    filas = storage.leer_csv(tarea)
    if not filas:
        print(f"No hay CSV para tarea {tarea}.")
        return

    # Pendientes: ya se les envió (tienen message_id) pero aún no respondieron
    def _respondio(correo: str) -> bool:
        e = _datos.notas.estado(correo, _datos.TAREAS, tarea)
        return bool(e and e.get("Respondio", "").strip())

    pendientes = [
        f for f in filas
        if f.get("message_id") and not _respondio(f.get("alumno_correo", ""))
    ]
    if solo is not None:
        fuera = [f for f in pendientes if f.get("alumno_correo", "").strip().lower() not in solo]
        if fuera:
            print(f"{len(fuera)} pendiente(s) de otro envío quedan para después.")
        pendientes = [f for f in pendientes if f.get("alumno_correo", "").strip().lower() in solo]
    if not pendientes:
        print(f"No hay respuestas pendientes por buscar para {tarea}.")
        return

    message_ids = [f["message_id"] for f in pendientes]
    print(f"Buscando respuestas en inbox para {len(message_ids)} correo(s) pendiente(s)...")

    encontradas = buscar_respuestas(message_ids)
    print(f"Encontradas {len(encontradas)} respuesta(s) nuevas.\n")

    for fila in avanzar(pendientes, "alumnos"):
        mid = fila["message_id"]
        respuesta, avisos = juntar(fila, encontradas[mid]) if mid in encontradas else (None, [])
        if respuesta is None:
            print(f"  ⋯ {fila['alumno_nombre']:30s}: sin respuesta aún")
            _anotar(tarea, fila, avisos)
            continue

        try:
            _datos.notas.marcar_respondio(fila["alumno_correo"], _datos.TAREAS,
                                          tarea, respuesta["fecha"])
            _datos.log.registrar("respuesta", _datos.TAREAS, tarea,
                                 fila["alumno_correo"], Respuesta=respuesta["texto"])
        except Exception as _e:  # noqa: BLE001
            print(f"     ⚠ no pude registrar en el esquema nuevo: {_e}")

        vista_previa = respuesta["texto"][:80].replace("\n", " ")
        print(f"  ✓ {fila['alumno_nombre']:30s}: '{vista_previa}...'")
        if storage.respondio_tarde(fila, respuesta["fecha"]):
            # Se recolecta igual: corregir la deja fuera salvo que se elija a mano.
            print(f"     ⏰ fuera de plazo: respondió a las {storage.hora(respuesta['fecha'])}, "
                  f"el plazo era hasta las {storage.hora(fila['plazo'])}")
        _anotar(tarea, fila, avisos)


if __name__ == "__main__":
    args = sys.argv[1:]
    tarea = args[0].upper() if args and args[0].upper().startswith('T') else config.TAREA_DEFAULT
    main(tarea, solo=_candidatos.solo_de_argv())
