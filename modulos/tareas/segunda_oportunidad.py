"""
Segunda oportunidad: una pregunta nueva para quien no respondió la primera.

    python -m modulos.tareas.segunda_oportunidad preparar T1
    python -m modulos.tareas.segunda_oportunidad borradores T1
    python -m modulos.tareas.segunda_oportunidad enviar T1 --confirmar

`preparar` elige a quienes se les envió y no respondieron, y les genera una
pregunta nueva sobre la misma parte de la tarea (una llamada al modelo por
alumno). Queda todo en `salidas/segunda_oportunidad_<TAREA>.csv`, que se puede
revisar y editar a mano antes de enviar.

`borradores` escribe los correos tal como saldrían, para leerlos.

`enviar` los manda y deja la pregunta nueva en `feedback_<TAREA>.csv`. Desde
ahí no hay nada especial: `recolectar` y `corregir` funcionan como siempre y
corrigen contra la pregunta nueva. La original queda en el CSV de este paso.

El plazo va escrito en la plantilla `prompts/correo_segunda_oportunidad.md`.
"""

import csv
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher

from modulos import datos, ia
from modulos.mail import enviar_correo
from modulos.mail.vista import mostrar_correo
from modulos.progreso import avanzar

from . import config, storage
from . import ia_prompts  # noqa: F401  (configura el modelo al importarse)
from .generar import _leer_entrega

COLUMNAS = ["correo", "nombre", "grupo_archivo", "alumno_nombre", "pregunta_tarea",
            "pregunta_original", "pregunta", "pauta", "message_id", "enviado"]


def _ruta(tarea: str):
    return config.SALIDAS / f"segunda_oportunidad_{tarea}.csv"


def leer(tarea: str) -> list[dict]:
    ruta = _ruta(tarea)
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _guardar(tarea: str, filas: list[dict]) -> None:
    ruta = _ruta(tarea)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)


def _sin_respuesta(tarea: str) -> list[dict]:
    """Las filas de la tarea a las que se les envió y no respondieron."""
    nombres = datos.alumnos.por_correo()
    salida = []
    for f in storage.leer_csv(tarea):
        correo = f.get("alumno_correo", "").strip().lower()
        estado = (datos.notas.estado(correo, datos.TAREAS, tarea) or {}) if correo else {}
        if not estado.get("Enviado") or estado.get("Respondio") or estado.get("Nota"):
            continue
        salida.append({
            "correo": correo,
            "nombre": nombres.get(correo, {}).get("Nombre") or f["alumno_nombre"],
            "grupo_archivo": f["grupo_archivo"], "alumno_nombre": f["alumno_nombre"],
            "pregunta_tarea": f["pregunta_tarea"], "pregunta_original": f["pregunta"],
            "pregunta": "", "pauta": "", "message_id": "", "enviado": "",
        })
    return sorted(salida, key=lambda a: a["nombre"].casefold())


# Nombres que aparecen en cualquier código: compartirlos no dice que sea el mismo fragmento.
_GENERICOS = {"data", "newdata", "by", "x", "y", "c", "n", "na.rm", "mean", "sum",
              "group_by", "mutate", "summarise", "summarize", "filter", "select",
              "ggplot", "aes", "lm", "factor", "as.factor"}


def _codigo(texto: str) -> set[str]:
    """Las funciones y objetos citados entre `comillas`, sin los que no distinguen.

    Fuera quedan las columnas de la base, que van en mayúsculas (ASISTENCIA, RBD)
    y aparecen en casi todas las preguntas, y los nombres genéricos de R.
    """
    nombres = {n for cita in re.findall(r"`([^`]+)`", texto)
               for n in re.findall(r"[A-Za-z_][\w.]*", cita)}
    return {n for n in nombres if not n.isupper() and n not in _GENERICOS}


def _repetida(pregunta: str, otras: list[str]) -> bool:
    """La misma pregunta con otras palabras: se parece mucho o cita el mismo código."""
    return any(SequenceMatcher(None, pregunta, o).ratio() > 0.5
               or _codigo(pregunta) & _codigo(o) for o in otras)


def _pregunta_nueva(tarea: str, alumno: dict, ya_preguntadas: list[str]) -> tuple[str, str]:
    """Una pregunta y su pauta, sobre la misma parte y distinta de las del grupo.

    El modelo tiende a volver al fragmento más obvio, que suele ser el de la
    pregunta original. Si lo hace, se le pide otra, hasta tres veces.
    """
    secciones, _, _ = _leer_entrega(config.ENTREGAS / tarea / alumno["grupo_archivo"])
    n = alumno["pregunta_tarea"].upper().lstrip("P") or "1"
    system = (config.PROMPTS / "generar_preguntas.md").read_text(encoding="utf-8")
    evitar = list(ya_preguntadas)
    for _ in range(3):
        user = (
            "=== SEGUNDA OPORTUNIDAD ===\n"
            f"El integrante {alumno['nombre']} no respondió su primera pregunta. Genera "
            f"UNA pregunta nueva para él sobre la Pregunta {n} de la tarea, con los "
            "mismos criterios de siempre. Tiene que ser sobre OTRO fragmento de código: "
            "no puede usar el mismo bloque, gráfico, modelo ni las mismas funciones u "
            "objetos que estas preguntas, que ya se hicieron a su grupo:\n- "
            + "\n- ".join(evitar)
            + f"\n\nDevuelve el JSON con un solo integrante, \"{alumno['nombre']}\", "
            f"y \"pregunta_tarea\": \"P{n}\".\n\n"
            f"=== PREGUNTA {n} ===\n{secciones.get(f'p{n}', '')}"
        )
        datos_ia = ia.completar(system, user, json_mode=True).datos
        integrante = next((i for i in datos_ia.get("integrantes", []) if i.get("pregunta")), {})
        pregunta = (integrante.get("pregunta") or "").strip()
        pauta = (integrante.get("pauta") or "").strip()
        if pregunta and pauta and not _repetida(pregunta, ya_preguntadas):
            return pregunta, pauta
        evitar.append(pregunta)
    raise ValueError(f"Tres intentos y la pregunta de {alumno['nombre']} sigue "
                     "pareciéndose a una ya hecha: escríbela a mano en el CSV.")


def preparar(tarea: str) -> list[dict]:
    """Arma la lista la primera vez y completa las preguntas que falten.

    Correrlo de nuevo no rehace lo hecho: solo genera las que están vacías, así
    que para cambiar una pregunta basta borrarla del CSV y volver a correrlo.
    """
    filas = leer(tarea) or _sin_respuesta(tarea)
    if not filas:
        print(f"No hay alumnos con envío y sin respuesta en {tarea}.")
        return []
    del_grupo = {}
    for f in storage.leer_csv(tarea):
        del_grupo.setdefault(f["grupo_archivo"], []).append(f["pregunta"])

    for alumno in filas:
        if alumno["pregunta"].strip():
            continue
        ya = del_grupo[alumno["grupo_archivo"]] + [
            a["pregunta"] for a in filas
            if a["grupo_archivo"] == alumno["grupo_archivo"] and a["pregunta"]]
        try:
            alumno["pregunta"], alumno["pauta"] = _pregunta_nueva(tarea, alumno, ya)
        except ValueError as e:
            print(f"  ✗ {e}")
            continue
        _guardar(tarea, filas)  # se guarda cada una: si algo falla, no se pierde lo hecho
        print(f"  ✓ {alumno['nombre']:28s} {alumno['pregunta_tarea']}: {alumno['pregunta'][:70]}...")

    _guardar(tarea, filas)
    print(f"\n{len(filas)} alumnos en {_ruta(tarea)}")
    return filas


def _cuerpo(tarea: str, alumno: dict) -> str:
    plantilla = (config.PROMPTS / "correo_segunda_oportunidad.md").read_text(encoding="utf-8")
    return plantilla.format(nombre=alumno["nombre"].split()[0], tarea=tarea,
                            pregunta_tarea=alumno["pregunta_tarea"],
                            pregunta=alumno["pregunta"])


def _asunto(tarea: str) -> str:
    return f"Nueva pregunta de comprensión — {config.CURSO} {tarea}"


def borradores(tarea: str):
    filas = leer(tarea)
    destino = config.SALIDAS / f"correos_segunda_oportunidad_{tarea}.txt"
    destino.write_text("\n\n" + ("=" * 70 + "\n\n").join(
        f"Para: {a['correo']}\nAsunto: {_asunto(tarea)}\n\n{_cuerpo(tarea, a)}\n"
        for a in filas), encoding="utf-8")
    print(destino)
    for a in filas:
        mostrar_correo(a["correo"], _asunto(tarea), _cuerpo(tarea, a), nombre=a.get("nombre", ""))
    return destino


def enviar(tarea: str) -> None:
    filas = leer(tarea)
    faltan = [a["nombre"] for a in filas if not a["pregunta"].strip() or not a["pauta"].strip()]
    if faltan:
        raise ValueError(f"Faltan preguntas o pautas para: {', '.join(faltan)}")
    for alumno in avanzar(filas, "alumnos"):
        if alumno["message_id"]:
            continue  # ya enviado: correrlo dos veces no repite correos
        alumno["message_id"] = enviar_correo(alumno["correo"], _asunto(tarea),
                                             _cuerpo(tarea, alumno))
        alumno["enviado"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _guardar(tarea, filas)
        # Desde acá, recolectar y corregir trabajan con la pregunta nueva. El
        # plazo del primer envío ya no vale (el de este va escrito en la
        # plantilla): con él, toda respuesta a la segunda pregunta era tardía.
        storage.actualizar_fila(tarea, alumno["grupo_archivo"], alumno["alumno_nombre"], {
            "pregunta": alumno["pregunta"], "pauta": alumno["pauta"],
            "message_id": alumno["message_id"], "plazo": ""})
        datos.log.registrar("envio", datos.TAREAS, tarea, alumno["correo"],
                            MessageId=alumno["message_id"], Detalle="segunda oportunidad")
        print(f"  ✓ {alumno['nombre']:28s} → {alumno['correo']}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2 or args[0] not in ("preparar", "borradores", "enviar"):
        sys.exit(__doc__)
    paso, tarea = args[0], args[1].upper()
    if paso == "enviar" and "--confirmar" not in sys.argv:
        sys.exit("Esto manda correos reales. Agrega --confirmar.")
    {"preparar": preparar, "borradores": borradores, "enviar": enviar}[paso](tarea)
