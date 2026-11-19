"""
Cloudflare: el sitio (un Worker), su base D1, sus archivos en R2 y Access.

Los recursos se consultan y crean con la API de Cloudflare, que responde JSON
estable; wrangler se usa solo para lo que hace mejor: aplicar las migraciones
de la base y publicar el Worker. Nunca `wrangler login`: en Cloud Shell la
vuelta del navegador no llega, así que todo va con CLOUDFLARE_API_TOKEN.

La configuración de wrangler de cada instalación es un archivo aparte,
web/wrangler.<curso>.toml, generado desde web/wrangler.toml (el de IN5162, que
no se toca). Vive en web/ para que las rutas relativas (src/, public/,
migrations/) sigan valiendo, y git lo ignora.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

from . import plantilla
from .comun import WEB, Ejecutor, Falla
from .validar import CF_API

BASE_WRANGLER = WEB / "wrangler.toml"
# Las claves de web/wrangler.toml que cambian en cada instalación.
CAMPOS_WRANGLER = ("name", "database_name", "database_id", "bucket_name",
                   "CURSO", "ACCESO_EQUIPO", "ACCESO_AUD", "MOTOR_URL")
ENCABEZADO = (
    "# Generado por instalar.py a partir de wrangler.toml. No se edita a mano:\n"
    "# `python3 instalar.py actualizar` lo vuelve a escribir con los datos del .env.\n\n"
)


def nombre_config(curso: str) -> str:
    return f"wrangler.{curso.lower()}.toml"


def _toml_texto(valor: str) -> str:
    if any(c in valor for c in '"\\\n\r'):
        raise Falla(f"Valor inválido para wrangler.toml: {valor!r}")
    return f'"{valor}"'


def generar_wrangler(base: str, valores: dict[str, str]) -> str:
    """El wrangler.toml de esta instalación: el de IN5162 con los valores propios.

    Cada clave tiene que aparecer exactamente una vez en la base; si alguien la
    renombra, es mejor fallar acá que publicar un sitio con datos de IN5162.
    """
    texto = base.replace("\r\n", "\n")
    for clave in CAMPOS_WRANGLER:
        patron = re.compile(rf'^{re.escape(clave)} = ".*"$', re.M)
        if len(patron.findall(texto)) != 1:
            raise Falla(f"web/wrangler.toml cambió: no encuentro una sola línea «{clave} = ...». "
                        "Hay que actualizar instalador/cloudflare.py.")
        linea = f"{clave} = {_toml_texto(valores.get(clave, ''))}"
        texto = patron.sub(lambda m: linea, texto)
    return ENCABEZADO + texto


def leer_vars(texto: str) -> dict[str, str]:
    """Los `CLAVE = "valor"` de un wrangler.toml (sin interpretar secciones)."""
    return dict(re.findall(r'^([A-Za-z_]+) = "([^"]*)"$', texto, re.M))


def escribir_config(ej: Ejecutor, curso: str, valores: dict[str, str]) -> Path:
    destino = WEB / nombre_config(curso)
    texto = generar_wrangler(BASE_WRANGLER.read_text(encoding="utf-8"), valores)
    if ej.simular:
        ej.escribir(f"  [simular] escribiría web/{destino.name}")
    else:
        destino.write_text(texto, encoding="utf-8")
    return destino


@contextlib.contextmanager
def archivo_temporal(ej: Ejecutor, contenido: str, sufijo: str = ".json"):
    """Un archivo que solo lee su dueño y se borra al salir. En simulación no se crea."""
    if ej.simular:
        yield "<archivo-temporal>"
        return
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    try:
        os.chmod(ruta, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        yield ruta
    finally:
        with contextlib.suppress(OSError):
            os.remove(ruta)


class Cloudflare:
    def __init__(self, ej: Ejecutor, token: str, cuenta: str):
        self.ej = ej
        self.token = token
        self.cuenta = cuenta

    def entorno_wrangler(self) -> dict[str, str]:
        return {"CLOUDFLARE_API_TOKEN": self.token, "CLOUDFLARE_ACCOUNT_ID": self.cuenta,
                "WRANGLER_SEND_METRICS": "false"}

    # ------------------------------------------------------------ API

    def _api(self, metodo: str, ruta: str, datos=None, *, lectura: bool = True, simulado=None):
        return self.ej.pedir(metodo, f"{CF_API}/accounts/{self.cuenta}{ruta}", token=self.token,
                             datos=datos, lectura=lectura, simulado=simulado)

    @staticmethod
    def _ok(cuerpo) -> bool:
        return isinstance(cuerpo, dict) and bool(cuerpo.get("success"))

    @staticmethod
    def _codigos(cuerpo) -> set:
        errores = (cuerpo.get("errors") or []) if isinstance(cuerpo, dict) else []
        return {e.get("code") for e in errores if isinstance(e, dict)}

    @staticmethod
    def _texto_error(estado, cuerpo) -> str:
        if isinstance(cuerpo, dict) and cuerpo.get("errors"):
            return "; ".join(f"{e.get('code')}: {e.get('message')}" for e in cuerpo["errors"])
        return f"respondió {estado} {str(cuerpo)[:200]}"

    def subdominio(self) -> str | None:
        """El subdominio de workers.dev de la cuenta, o None si todavía no tiene."""
        estado, cuerpo = self._api("GET", "/workers/subdomain")
        if self._ok(cuerpo):
            return (cuerpo.get("result") or {}).get("subdomain") or None
        if estado == 404 or 10007 in self._codigos(cuerpo):
            return None
        raise Falla(f"No pude leer el subdominio de workers.dev: {self._texto_error(estado, cuerpo)}")

    def registrar_subdominio(self, nombre: str) -> tuple[bool, str]:
        estado, cuerpo = self._api("PUT", "/workers/subdomain", {"subdomain": nombre}, lectura=False,
                                   simulado=(200, {"success": True, "result": {"subdomain": nombre}}))
        if self._ok(cuerpo):
            return True, nombre
        return False, self._texto_error(estado, cuerpo)

    def id_d1(self, nombre: str) -> str | None:
        estado, cuerpo = self._api("GET", f"/d1/database?name={quote(nombre)}")
        if self._ok(cuerpo):
            for base in cuerpo.get("result") or []:
                if base.get("name") == nombre:
                    return base.get("uuid")
            return None
        if estado == 404:
            return None
        raise Falla(f"No pude listar las bases D1: {self._texto_error(estado, cuerpo)}")

    def crear_d1(self, nombre: str) -> str:
        estado, cuerpo = self._api("POST", "/d1/database", {"name": nombre}, lectura=False,
                                   simulado=(200, {"success": True,
                                                   "result": {"uuid": "<id-de-la-base>", "name": nombre}}))
        if not self._ok(cuerpo):
            raise Falla(f"No pude crear la base D1 {nombre}: {self._texto_error(estado, cuerpo)}")
        return cuerpo["result"]["uuid"]

    def bucket_existe(self, nombre: str) -> bool:
        estado, cuerpo = self._api("GET", f"/r2/buckets/{quote(nombre)}")
        if self._ok(cuerpo):
            return True
        if estado == 404 or 10006 in self._codigos(cuerpo):
            return False
        raise Falla(f"No pude consultar el bucket {nombre}: {self._texto_error(estado, cuerpo)}")

    def crear_bucket(self, nombre: str) -> None:
        estado, cuerpo = self._api("POST", "/r2/buckets", {"name": nombre}, lectura=False)
        if not self._ok(cuerpo):
            raise Falla(f"No pude crear el bucket {nombre}: {self._texto_error(estado, cuerpo)}")

    def consulta_d1(self, base_id: str, sql: str, params: list | None = None,
                    lectura: bool = False) -> list[dict]:
        estado, cuerpo = self._api("POST", f"/d1/database/{base_id}/query",
                                   {"sql": sql, "params": params or []}, lectura=lectura,
                                   simulado=(200, {"success": True, "result": [{"results": []}]}))
        if not self._ok(cuerpo):
            raise Falla(f"La consulta a D1 falló: {self._texto_error(estado, cuerpo)}")
        resultado = cuerpo.get("result") or [{}]
        return resultado[0].get("results") or []

    def worker_existe(self, nombre: str) -> bool:
        estado, cuerpo = self._api("GET", "/workers/scripts")
        if not self._ok(cuerpo):
            return False
        return any(s.get("id") == nombre for s in cuerpo.get("result") or [])

    def app_access(self, dominio: str) -> dict | None:
        estado, cuerpo = self._api("GET", "/access/apps")
        if not self._ok(cuerpo):
            return None
        return next((a for a in cuerpo.get("result") or [] if a.get("domain") == dominio), None)

    # ------------------------------------------------------------ wrangler

    def wrangler(self, *args: str, config: Path, mostrar: bool = True, **kw):
        return self.ej.correr(["npx", "wrangler", *args, "--config", config.name], cwd=WEB,
                              env=self.entorno_wrangler(), mostrar=mostrar, **kw)

    def aplicar_migraciones(self, config: Path) -> None:
        self.wrangler("d1", "migrations", "apply", "DB", "--remote", config=config)

    def migraciones_pendientes(self, config: Path) -> bool | None:
        r = self.wrangler("d1", "migrations", "list", "DB", "--remote", config=config,
                          mostrar=False, lectura=True, puede_fallar=True)
        if not r.ok:
            return None
        return "No migrations to apply" not in r.salida

    def publicar(self, config: Path, secretos: dict[str, str]) -> None:
        """Publica el sitio. Los tokens van en un archivo temporal (--secrets-file):
        así sirve también la primera vez, cuando el Worker todavía no existe."""
        self.ej.correr(["npm", "run", "preparar"], cwd=WEB, mostrar=True)
        with archivo_temporal(self.ej, json.dumps(secretos)) as ruta:
            self.wrangler("deploy", "--secrets-file", str(ruta), config=config)

    def configurar_access(self, config: Path, correos: list[str], web_url: str) -> dict[str, str]:
        """Corre scripts/acceso.mjs sobre la config de esta instalación y devuelve
        ACCESO_EQUIPO y ACCESO_AUD tal como quedaron escritos en ella."""
        self.ej.correr(["node", "scripts/acceso.mjs", "--config", config.name, *correos], cwd=WEB,
                       env={**self.entorno_wrangler(), "WEB_URL": web_url}, mostrar=True)
        if self.ej.simular:
            return {"ACCESO_EQUIPO": "<equipo>.cloudflareaccess.com", "ACCESO_AUD": "<aud>"}
        datos = leer_vars(config.read_text(encoding="utf-8"))
        return {"ACCESO_EQUIPO": datos.get("ACCESO_EQUIPO", ""), "ACCESO_AUD": datos.get("ACCESO_AUD", "")}


# ---------------------------------------------------------------- plantilla


def subir_plantilla(ej: Ejecutor, web_url: str, token: str, valores: dict[str, str],
                    intentos: int = 6, espera: float = 20) -> dict[str, list[str]]:
    """Sube a R2, por la API del sitio, los archivos de la plantilla que allá no están.

    Nunca reemplaza: si el profesor ya cambió un prompt de la plantilla desde la
    página, eso se queda. Un subdominio de workers.dev recién creado puede tardar
    unos minutos en responder, por eso los reintentos.
    """
    base = web_url.rstrip("/")
    for intento in range(intentos):
        estado, lista = ej.pedir("GET", f"{base}/api/motor/archivos/_template", token=token,
                                 simulado=(200, []))
        if estado == 200 and isinstance(lista, list):
            break
        if estado in (401, 403):
            raise Falla(f"El sitio rechazó el token del motor ({estado}). ¿Se publicó con los "
                        "secretos? Corre de nuevo el instalador.")
        if intento < intentos - 1:
            ej.escribir(f"  El sitio todavía no responde ({estado}); reintento en {int(espera)} s...")
            time.sleep(espera)
    else:
        raise Falla(f"El sitio {base} no responde. Si se acaba de crear, espera unos minutos y "
                    "corre de nuevo el instalador: retoma desde aquí.")
    hay = {a.get("ruta") for a in lista if isinstance(a, dict)}
    r = {"nuevos": [], "ya_estaban": [], "fallidos": []}
    for ruta, datos in plantilla.archivos(valores):
        if ruta in hay:
            r["ya_estaban"].append(ruta)
            continue
        destino = "/".join(quote(p) for p in ruta.split("/"))
        estado, cuerpo = ej.pedir("PUT", f"{base}/api/motor/archivo/_template/{destino}", token=token,
                                  datos=datos, lectura=False,
                                  cabeceras={"If-None-Match": "*", "X-In5162-Origen": "instalador"})
        if estado in (200, 201):
            r["nuevos"].append(ruta)
        elif estado == 409:
            r["ya_estaban"].append(ruta)
        else:
            r["fallidos"].append(f"{ruta} ({estado})")
    return r


def host(url: str) -> str:
    return urlsplit(url).netloc
