"""
Cómo habla el motor con el sitio web (el Worker de Cloudflare).

Todo pasa por acá: bajar y subir archivos del semestre, leer qué trabajo hay que
ejecutar e ir informando su salida. Usa TOKEN_MOTOR, que sirve para eso y nada
más: no permite ver la reportería ni pedir trabajos.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


def _url(ruta: str) -> str:
    base = os.environ.get("WEB_URL", "http://127.0.0.1:8787").rstrip("/")
    return f"{base}/api/{ruta}"


def _pedir(metodo: str, ruta: str, cuerpo: bytes | None = None,
           tipo: str = "application/json", intentos: int = 3,
           extra: dict | None = None) -> bytes:
    token = os.environ["TOKEN_MOTOR"]
    ultimo = None
    for i in range(intentos):
        req = urllib.request.Request(
            _url(ruta), data=cuerpo, method=metodo,
            headers={"Authorization": f"Bearer {token}", "Content-Type": tipo,
                     # Cloudflare rechaza con 403 (error 1010) el agente por
                     # defecto de urllib, "Python-urllib".
                     "User-Agent": "in5162-motor/1.0", **(extra or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            # Un 4xx es un error nuestro: repetirlo no lo arregla.
            if 400 <= e.code < 500:
                raise RuntimeError(f"{metodo} {ruta}: {e.code} {e.read()[:200]!r}") from e
            ultimo = e
        except urllib.error.URLError as e:
            ultimo = e
        time.sleep(1 + 2 * i)
    raise RuntimeError(f"{metodo} {ruta}: sin respuesta del sitio ({ultimo})")


def _ruta_archivo(semestre: str, ruta: str) -> str:
    return f"motor/archivo/{semestre}/" + "/".join(urllib.parse.quote(p) for p in ruta.split("/"))


def listar_archivos(semestre: str) -> list[dict]:
    return json.loads(_pedir("GET", f"motor/archivos/{semestre}"))


def bajar_archivo(semestre: str, ruta: str) -> bytes:
    return _pedir("GET", _ruta_archivo(semestre, ruta))


def subir_archivo(semestre: str, ruta: str, datos: bytes, origen: str = "motor",
                  etag: str | None = None) -> None:
    """`origen` queda en el historial de ediciones: "trabajo <id>".

    `etag` es el de la versión que se bajó: si en la nube cambió desde entonces,
    el sitio responde 409 en vez de pisarla. Sin etag, el archivo tiene que ser
    nuevo.
    """
    condicion = {"If-Match": etag} if etag else {"If-None-Match": "*"}
    _pedir("PUT", _ruta_archivo(semestre, ruta), datos, "application/octet-stream",
           extra={"X-In5162-Origen": origen, **condicion})


def ver_trabajo(id_trabajo: str) -> dict:
    return json.loads(_pedir("GET", f"motor/trabajos/{id_trabajo}"))


def informar(id_trabajo: str, salida: str = "", estado: str | None = None,
             codigo: int | None = None) -> None:
    cuerpo = {"salida": salida}
    if estado:
        cuerpo["estado"] = estado
    if codigo is not None:
        cuerpo["codigo"] = codigo
    _pedir("POST", f"motor/trabajos/{id_trabajo}",
           json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"))


def _sin_nan(v):
    # Una nota "nan" en notas.csv llega como float('nan'), y json.dumps la
    # escribe como NaN, que no es JSON válido: el sitio rechazaba todo el panel.
    return None if isinstance(v, float) and v != v else v


def subir_panel(semestre: str, filas: list[dict]) -> None:
    limpias = [{k: _sin_nan(v) for k, v in f.items()} for f in filas]
    _pedir("POST", f"subir/{semestre}",
           json.dumps({"filas": limpias}, ensure_ascii=False).encode("utf-8"))


def leer_parametros() -> dict[str, str]:
    """Los parámetros editados en la página: modelo, temperatura, grupos..."""
    return {f["clave"]: f["valor"] for f in json.loads(_pedir("GET", "motor/parametros"))}
