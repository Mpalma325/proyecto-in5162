"""
Dónde espera un trabajo hasta que se ejecuta.

Evaluar una semana tarda minutos, y alguien tiene que mantener abierta la
conexión con el motor mientras tanto. En Cloud Run eso lo hace Cloud Tasks: una
cola de Google que llama a /ejecutar y espera hasta 30 minutos. Si el motor
respondiera antes de terminar, Cloud Run le quitaría la CPU al trabajo.

En el PC no hay Cloud Tasks, y un hilo hace lo mismo. El resto del motor no se
entera de cuál se está usando:

    COLA=local        un hilo en este proceso (por defecto; para desarrollo)
    COLA=cloudtasks   Cloud Tasks. Necesita GCP_PROYECTO, GCP_REGION,
                      GCP_COLA y MOTOR_URL_PUBLICA.

Los trabajos reales corren de a uno. Dos a la vez podrían escribir el mismo
archivo del semestre y perder lo del otro; en Cloud Tasks su cola se crea con
max-concurrent-dispatches=1 por la misma razón. Las simulaciones no mandan
correos ni cambian notas, y van a otra cola (GCP_COLA_SIMULACIONES) que deja
correr varias a la vez; si alguna llegara a escribir el mismo archivo, la subida
con etag lo rechaza en vez de pisarlo.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import urllib.request

from . import trabajo

_pendientes: "queue.Queue[str]" = queue.Queue()
_hilo: threading.Thread | None = None


def _trabajador() -> None:
    while True:
        id_trabajo = _pendientes.get()
        try:
            trabajo.ejecutar(id_trabajo)
        finally:
            _pendientes.task_done()


def _local(id_trabajo: str) -> None:
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _hilo = threading.Thread(target=_trabajador, name="cola-local", daemon=True)
        _hilo.start()
    _pendientes.put(id_trabajo)


def _token_google() -> str:
    """Token del servicio de Cloud Run, pedido al servidor de metadatos.

    Dentro de Cloud Run no hace falta ninguna clave: el servicio ya tiene
    identidad, y este pedido la convierte en un token de acceso.
    """
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())["access_token"]


def _es_simulacion(id_trabajo: str) -> bool:
    try:
        return bool(trabajo.sitio.ver_trabajo(id_trabajo).get("prueba"))
    except Exception:  # noqa: BLE001  (si no se sabe, va a la cola de a uno)
        return False


def _cloudtasks(id_trabajo: str) -> None:
    proyecto = os.environ["GCP_PROYECTO"]
    region = os.environ["GCP_REGION"]
    simulaciones = os.environ.get("GCP_COLA_SIMULACIONES")
    cola = simulaciones if simulaciones and _es_simulacion(id_trabajo) else os.environ["GCP_COLA"]
    destino = os.environ["MOTOR_URL_PUBLICA"].rstrip("/") + "/ejecutar"
    tarea = {
        "task": {
            "httpRequest": {
                "url": destino,
                "httpMethod": "POST",
                # El motor se protege con su propio token, no con la identidad
                # de Google: así el mismo /ejecutar sirve en el PC y en la nube.
                "headers": {"Content-Type": "application/json",
                            "X-In5162-Token": os.environ["TOKEN_WEB"]},
                "body": base64.b64encode(json.dumps({"id": id_trabajo}).encode()).decode(),
            },
            # Lo máximo que permite Cloud Tasks para un pedido HTTP.
            "dispatchDeadline": "1800s",
        }
    }
    url = (f"https://cloudtasks.googleapis.com/v2/projects/{proyecto}/locations/{region}"
           f"/queues/{cola}/tasks")
    req = urllib.request.Request(
        url, data=json.dumps(tarea).encode(), method="POST",
        headers={"Authorization": f"Bearer {_token_google()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def encolar(id_trabajo: str) -> None:
    if os.environ.get("COLA", "local") == "cloudtasks":
        _cloudtasks(id_trabajo)
    else:
        _local(id_trabajo)
