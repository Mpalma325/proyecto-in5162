"""
Lo que usan todos los pasos del instalador: correr programas, hablar con APIs,
leer y escribir el .env y hacer preguntas.

Todo lo que sale de este equipo pasa por `Ejecutor`. Así `--simular` puede
mostrar cada comando y cada pedido en vez de hacerlo, y las pruebas pueden
reemplazar `subprocess.run` y `urlopen` sin tocar la red.
"""

from __future__ import annotations

import getpass
import json
import os
import shlex
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
ENV = RAIZ / ".env"
# Cloudflare rechaza con 403 (error 1010) el agente por defecto de urllib.
AGENTE = "instalador-curso/1.0"


class Falla(Exception):
    """Un paso no se pudo completar. El mensaje dice qué hacer."""


@dataclass
class Resultado:
    codigo: int
    salida: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.codigo == 0


def texto_comando(cmd) -> str:
    return " ".join(shlex.quote(str(p)) for p in cmd)


class Ejecutor:
    """Corre programas y pedidos HTTP, o los muestra si `simular` es verdadero.

    En simulación nada sale del equipo. Una consulta (`lectura=True`) responde
    como si el recurso no existiera, salvo que se le dé un valor `simulado`; así
    la simulación muestra todo lo que haría una instalación desde cero.
    """

    def __init__(self, simular: bool = False, escribir=print,
                 correr_proceso=subprocess.run, abrir=urllib.request.urlopen):
        self.simular = simular
        self.escribir = escribir
        self._correr = correr_proceso
        self._abrir = abrir
        # Cada comando y cada pedido, en orden. Lo leen las pruebas.
        self.registro: list[str] = []

    # ------------------------------------------------------------ programas

    def correr(self, cmd: list[str], *, cwd: Path | None = None, entrada: str | None = None,
               env: dict | None = None, lectura: bool = False, simulado: str | None = None,
               mostrar: bool = False, puede_fallar: bool = False) -> Resultado:
        """Corre `cmd` y devuelve su resultado.

        - `entrada` va por la entrada estándar: así una clave nunca queda en la
          línea de comandos ni en el registro.
        - `mostrar` deja que la salida llegue a la pantalla mientras corre (los
          despliegues tardan minutos); si no, se captura.
        - Sin `puede_fallar`, un código distinto de cero es una Falla.
        """
        linea = texto_comando(cmd)
        if cwd and Path(cwd).resolve() != RAIZ:
            linea = f"(en {Path(cwd).resolve().relative_to(RAIZ).as_posix()}/) {linea}"
        self.registro.append(linea)
        if self.simular:
            self.escribir(f"  [simular] $ {linea}")
            if lectura:
                return Resultado(0, simulado) if simulado is not None else Resultado(1)
            return Resultado(0, simulado or "")
        # En Windows gcloud y npx son .cmd: subprocess no los encuentra por nombre.
        programa = shutil.which(cmd[0]) or cmd[0]
        entorno = {**os.environ, **(env or {})}
        try:
            if mostrar:
                r = self._correr([programa, *cmd[1:]], cwd=cwd, env=entorno,
                                 input=entrada, text=True, encoding="utf-8", errors="replace",
                                 **({} if entrada is not None else {"stdin": subprocess.DEVNULL}))
                resultado = Resultado(r.returncode)
            else:
                r = self._correr([programa, *cmd[1:]], cwd=cwd, env=entorno,
                                 input=entrada, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace",
                                 **({} if entrada is not None else {"stdin": subprocess.DEVNULL}))
                resultado = Resultado(r.returncode, r.stdout or "", r.stderr or "")
        except FileNotFoundError:
            raise Falla(f"No encontré el programa «{cmd[0]}». ¿Está instalado y en el PATH?")
        if not resultado.ok and not puede_fallar:
            detalle = (resultado.error or resultado.salida).strip()[-1500:]
            raise Falla(f"Falló: {linea}" + (f"\n{detalle}" if detalle else ""))
        return resultado

    def existe(self, cmd: list[str], **kw) -> bool:
        """Si una consulta (un `describe`) termina bien. No muestra nada."""
        return self.correr(cmd, lectura=True, puede_fallar=True, **kw).ok

    # ------------------------------------------------------------ HTTP

    def pedir(self, metodo: str, url: str, *, token: str | None = None, datos=None,
              cabeceras: dict | None = None, lectura: bool = True, simulado=None,
              tiempo: float = 30) -> tuple[int, object]:
        """Hace un pedido HTTP y devuelve (estado, cuerpo).

        El cuerpo viene como JSON si se puede leer así, si no como bytes. Un 4xx
        o 5xx no es excepción: se devuelve con su estado. Si no hubo conexión,
        el estado es 0 y el cuerpo, el motivo.
        """
        self.registro.append(f"{metodo} {url}")
        if self.simular:
            self.escribir(f"  [simular] {metodo} {url}")
            if simulado is not None:
                return simulado
            return (404, None) if lectura else (200, {"success": True, "result": {}})
        h = {"User-Agent": AGENTE, **(cabeceras or {})}
        if token:
            h["Authorization"] = f"Bearer {token}"
        cuerpo = None
        if isinstance(datos, (dict, list)):
            cuerpo = json.dumps(datos).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        elif isinstance(datos, (bytes, bytearray)):
            cuerpo = bytes(datos)
            h.setdefault("Content-Type", "application/octet-stream")
        req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=h)
        try:
            with self._abrir(req, timeout=tiempo) as r:
                return r.status, _cuerpo(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _cuerpo(e.read())
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return 0, str(getattr(e, "reason", e))


def _cuerpo(datos: bytes):
    try:
        return json.loads(datos.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return datos


# ---------------------------------------------------------------- .env


class Entorno:
    """El .env de la raíz: lo leen modulos/config.py, el motor local y acceso.mjs.

    Se reescribe línea a línea, sin tocar comentarios ni el orden. En simulación
    los cambios quedan solo en memoria.
    """

    def __init__(self, ruta: Path = ENV, simular: bool = False):
        self.ruta = Path(ruta)
        self.simular = simular
        self.lineas: list[str] = (self.ruta.read_text(encoding="utf-8").splitlines()
                                  if self.ruta.exists() else [])

    def valores(self) -> dict[str, str]:
        datos = {}
        for linea in self.lineas:
            s = linea.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            datos[k.strip()] = v.strip().strip('"').strip("'")
        return datos

    def get(self, clave: str, defecto: str = "") -> str:
        return self.valores().get(clave, defecto)

    def set(self, clave: str, valor: str) -> None:
        if "\n" in valor or "\r" in valor:
            raise ValueError(f"{clave}: el valor no puede tener saltos de línea.")
        nueva = f"{clave}={valor}"
        for i, linea in enumerate(self.lineas):
            s = linea.strip()
            if not s.startswith("#") and "=" in s and s.split("=", 1)[0].strip() == clave:
                if self.lineas[i] == nueva:
                    return
                self.lineas[i] = nueva
                break
        else:
            self.lineas.append(nueva)
        self._guardar()

    def _guardar(self) -> None:
        if self.simular:
            return
        self.ruta.write_text("\n".join(self.lineas) + "\n", encoding="utf-8")
        try:
            # Tiene claves: que solo lo lea su dueño.
            os.chmod(self.ruta, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


# ---------------------------------------------------------------- preguntas


class Preguntador:
    """Hace las preguntas. Las pruebas le pasan una lista de respuestas."""

    def __init__(self, leer=input, leer_secreto=getpass.getpass, escribir=print):
        self._leer = leer
        self._leer_secreto = leer_secreto
        self.escribir = escribir

    def pedir(self, texto: str, *, defecto: str = "", secreto: bool = False) -> str:
        sufijo = f" [{defecto}]" if defecto and not secreto else ""
        while True:
            try:
                valor = (self._leer_secreto if secreto else self._leer)(f"{texto}{sufijo}: ")
            except EOFError:
                raise Falla("Se cortó la entrada antes de terminar las preguntas.")
            valor = (valor or "").strip() or defecto
            if valor:
                return valor
            self.escribir("  Falta este dato.")

    def si_no(self, texto: str, defecto: bool = False) -> bool:
        try:
            r = (self._leer(f"{texto} ({'S/n' if defecto else 's/N'}): ") or "").strip().lower()
        except EOFError:
            raise Falla("Se cortó la entrada antes de terminar las preguntas.")
        return defecto if not r else r[0] in "sy"


def paso(texto: str, escribir=print) -> None:
    escribir(f"\n=== {texto}")
