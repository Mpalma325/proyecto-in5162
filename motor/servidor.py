"""
El motor: el servicio que ejecuta los trabajos pedidos desde la página.

    POST /trabajos   el sitio avisa que hay un trabajo nuevo. Se encola y se
                     responde enseguida.
    POST /ejecutar   la cola pide ejecutarlo. Responde cuando termina.
    GET  /salud      para saber si está vivo.

Los dos POST exigen TOKEN_WEB, en el encabezado Authorization o en
X-In5162-Token (Cloud Tasks usa el segundo). El servicio puede ser público en
Cloud Run porque sin ese token no hace nada.

En el PC, para desarrollo:

    python -m motor.servidor

lee el .env de la raíz para las claves del correo y de OpenAI. En Cloud Run esas
claves llegan como variables de entorno desde Secret Manager.

Sin dependencias fuera de la biblioteca estándar: el servidor es trivial y un
framework no agregaría nada que sirva acá.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import cola, trabajo


def _cargar_env_local() -> None:
    """En el PC, toma las claves del .env de la raíz. No pisa lo que ya esté definido."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Manejador(BaseHTTPRequestHandler):
    server_version = "in5162-motor"

    def _responder(self, estado: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _autorizado(self) -> bool:
        esperado = os.environ.get("TOKEN_WEB", "")
        recibido = (self.headers.get("X-In5162-Token")
                    or self.headers.get("Authorization", "").removeprefix("Bearer ").strip())
        return bool(esperado) and hmac.compare_digest(recibido, esperado)

    def _id(self) -> str | None:
        largo = int(self.headers.get("Content-Length") or 0)
        try:
            datos = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return None
        id_trabajo = str(datos.get("id", ""))
        return id_trabajo if 8 <= len(id_trabajo) <= 64 else None

    def do_GET(self):  # noqa: N802
        if self.path == "/salud":
            self._responder(200, {"ok": True, "flujos": sorted(trabajo.FLUJOS)})
        else:
            self._responder(404, {"error": "No existe esa ruta."})

    def do_POST(self):  # noqa: N802
        if self.path not in ("/trabajos", "/ejecutar"):
            self._responder(404, {"error": "No existe esa ruta."})
            return
        if not self._autorizado():
            self._responder(401, {"error": "Token inválido."})
            return
        id_trabajo = self._id()
        if not id_trabajo:
            self._responder(400, {"error": "Falta el id del trabajo."})
            return
        if self.path == "/trabajos":
            cola.encolar(id_trabajo)
            self._responder(202, {"encolado": id_trabajo})
        else:
            trabajo.ejecutar(id_trabajo)
            self._responder(200, {"ejecutado": id_trabajo})

    def log_message(self, formato, *args):
        # Una línea por pedido, sin el ruido por defecto de http.server.
        sys.stderr.write(f"[motor] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}\n")


def main() -> None:
    _cargar_env_local()
    faltan = [v for v in ("TOKEN_WEB", "TOKEN_MOTOR") if not os.environ.get(v)]
    if faltan:
        sys.exit(f"Faltan variables: {', '.join(faltan)}")
    puerto = int(os.environ.get("PORT", "8090"))
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
    print(f"[motor] escuchando en :{puerto}  cola={os.environ.get('COLA', 'local')}  "
          f"sitio={os.environ.get('WEB_URL', 'http://127.0.0.1:8787')}", flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
