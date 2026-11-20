"""
Los cinco comandos de instalar.py: instalar, actualizar, estado, credenciales y acceso.

El orden de `instalar` sale de qué necesita cada pieza:
  1. las preguntas, cada una comprobada apenas se responde;
  2. Cloudflare: el subdominio (que da la dirección del sitio), la base y el
     bucket, y las migraciones;
  3. el motor en Google Cloud, que necesita la dirección del sitio;
  4. Access, y recién ahí se publica el sitio, que necesita la dirección del
     motor y los datos de Access;
  5. la plantilla de semestre, por la API del sitio ya publicado.
Cada paso revisa lo que ya existe: si algo falla a mitad, se corrige y se corre
de nuevo el mismo comando.
"""

from __future__ import annotations

import argparse
import imaplib
import json
import re
import secrets
import smtplib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import cloudflare as cfl
from . import gcp, validar
from .cloudflare import Cloudflare
from .comun import RAIZ, WEB, Ejecutor, Entorno, Falla, Preguntador, paso

DEFECTO_REGION = "us-central1"
# Sin esto, un curso nuevo heredaría la tutoría diaria de las 18:00, que manda
# correos reales. El profesor la prende en Configuración › La IA › Parámetros.
TUTORIA_APAGADA = ("INSERT OR IGNORE INTO parametros (clave, valor, actualizado, por) "
                   "VALUES ('TUTORIA_AUTOMATICA', 'false', ?, 'instalador')")


@dataclass
class Contexto:
    ej: Ejecutor
    env: Entorno
    preg: Preguntador
    escribir: object = print
    smtp: object = smtplib.SMTP
    imap: object = imaplib.IMAP4_SSL
    esperar: object = time.sleep
    # Lo que se fue sabiendo en esta corrida (no siempre va al .env).
    datos: dict = field(default_factory=dict)


# ---------------------------------------------------------------- preguntas


def _valor(ctx: Contexto, clave: str, texto: str, *, secreto: bool = False, defecto: str = "",
           revisar=None, normalizar=None, de_nuevo: bool = False) -> str:
    """El valor de `clave`: el del .env si ya está y es válido, o se pregunta.

    `revisar` devuelve un mensaje de error o None. Con `de_nuevo`, se pregunta
    aunque haya valor, ofreciendo el actual (Enter lo deja igual).
    """
    actual = ctx.env.get(clave)
    if actual and not de_nuevo:
        error = revisar(actual) if revisar else None
        if not error:
            ctx.escribir(f"  {texto}: {'(ya guardada)' if secreto else actual}")
            return actual
        ctx.escribir(f"  ✗ {clave} en el .env no sirve: {error}")
    if de_nuevo and actual:
        texto += " (Enter para dejarla igual)" if secreto else ""
        defecto = actual
    while True:
        v = ctx.preg.pedir(texto, defecto=defecto, secreto=secreto)
        v = normalizar(v) if normalizar else v.strip()
        error = revisar(v) if revisar else None
        if not error:
            ctx.env.set(clave, v)
            return v
        ctx.escribir(f"  ✗ {error}")


def _comprobar(ctx: Contexto, que: str, preguntar, probar) -> tuple:
    """Pregunta y comprueba en vuelta hasta que sirva.

    `preguntar(de_nuevo)` devuelve los valores; `probar(*valores)` devuelve
    (ok, mensaje). Si no se pudo comprobar (ok None), se ofrece seguir igual.
    """
    de_nuevo = False
    while True:
        valores = preguntar(de_nuevo)
        if ctx.ej.simular:
            ctx.escribir(f"  [simular] no compruebo {que}")
            return valores
        ok, mensaje = probar(*valores)
        if ok:
            ctx.escribir(f"  ✓ {mensaje}")
            return valores
        ctx.escribir(f"  ✗ {mensaje}")
        if ok is None and ctx.preg.si_no("No pude comprobarlo. ¿Sigo de todos modos?"):
            return valores
        de_nuevo = True


def preguntar_curso(ctx: Contexto) -> None:
    paso("El curso", ctx.escribir)
    ctx.datos["curso"] = _valor(ctx, "CURSO", "Código del curso, como lo verán los alumnos (ej. IN3401)",
                                revisar=validar.error_codigo, normalizar=lambda v: v.strip().upper())
    ctx.datos["nombre"] = _valor(ctx, "NOMBRE_CURSO", "Nombre del curso (ej. Economía de la Empresa)",
                                 revisar=validar.error_nombre)
    ctx.datos["profesor"] = _valor(ctx, "PROFESOR", "Nombre del profesor o profesora a cargo",
                                   revisar=validar.error_nombre)


def preguntar_correo(ctx: Contexto, de_nuevo: bool = False) -> None:
    paso("El correo del curso (manda las preguntas y recibe las respuestas)", ctx.escribir)

    def preguntar(otra_vez):
        correo = _valor(ctx, "CORREO_REMITENTE", "Correo del curso (Gmail o Google Workspace)",
                        revisar=validar.error_correo, normalizar=lambda v: v.strip().lower(),
                        de_nuevo=otra_vez or de_nuevo)
        clave = _valor(ctx, "CORREO_APP_PASSWORD",
                       "Contraseña de aplicación de ese correo (las 16 letras; los espacios no importan)",
                       secreto=True, normalizar=lambda v: v.replace(" ", "").strip(),
                       de_nuevo=otra_vez or de_nuevo)
        return correo, clave

    _comprobar(ctx, "el correo", preguntar,
               lambda c, k: validar.probar_correo(c, k, smtp=ctx.smtp, imap=ctx.imap))


def preguntar_openai(ctx: Contexto, de_nuevo: bool = False) -> None:
    paso("OpenAI (corrige las respuestas)", ctx.escribir)

    def preguntar(otra_vez):
        return (_valor(ctx, "OPENAI_API_KEY", "Clave de la API de OpenAI (sk-...)", secreto=True,
                       de_nuevo=otra_vez or de_nuevo),)

    _comprobar(ctx, "la clave de OpenAI", preguntar, lambda k: validar.probar_openai(k, ctx.ej))


def preguntar_cloudflare(ctx: Contexto, de_nuevo: bool = False) -> None:
    paso("Cloudflare (el sitio, la base de datos y quién entra)", ctx.escribir)

    def preguntar(otra_vez):
        cuenta = _valor(ctx, "CLOUDFLARE_ACCOUNT_ID", "Account ID de Cloudflare",
                        revisar=validar.error_cuenta_cf, normalizar=lambda v: v.strip().lower(),
                        de_nuevo=otra_vez)
        token = _valor(ctx, "CLOUDFLARE_API_TOKEN", "Token de la API de Cloudflare", secreto=True,
                       de_nuevo=otra_vez or de_nuevo)
        return token, cuenta

    def probar(token, cuenta):
        ok, mensaje, _ = validar.probar_cloudflare(token, cuenta, ctx.ej)
        return ok, mensaje

    _comprobar(ctx, "el token de Cloudflare", preguntar, probar)


def preguntar_google(ctx: Contexto) -> None:
    paso("Google Cloud (el motor)", ctx.escribir)
    if not ctx.ej.simular:
        ok, mensaje = validar.probar_gcloud_sesion(ctx.ej)
        if not ok:
            raise Falla(mensaje)
        ctx.escribir(f"  ✓ gcloud con la sesión de {mensaje}")

    def preguntar(otra_vez):
        return (_valor(ctx, "GCP_PROYECTO", "Id del proyecto de Google Cloud",
                       revisar=validar.error_proyecto, normalizar=lambda v: v.strip().lower(),
                       de_nuevo=otra_vez),)

    _comprobar(ctx, "el proyecto", preguntar, lambda p: validar.probar_proyecto(p, ctx.ej))
    _valor(ctx, "GCP_REGION", "Región de Google Cloud (us-central1 entra en la capa gratuita)",
           defecto=DEFECTO_REGION, revisar=validar.error_region,
           normalizar=lambda v: v.strip().lower())


def preguntar_equipo(ctx: Contexto) -> list[str]:
    paso("Quién puede entrar al sitio", ctx.escribir)
    ctx.escribir("  Entran con un código que les llega al correo. Todos tienen el mismo acceso,")
    ctx.escribir("  que incluye mandar correos a los alumnos.")
    texto = _valor(ctx, "ACCESO_CORREOS", "Correos del equipo docente, separados por coma",
                   revisar=lambda v: validar.lista_correos(v)[1],
                   normalizar=lambda v: ",".join(validar.lista_correos(v)[0]) or v)
    return validar.lista_correos(texto)[0]


def pedir_equipo_nuevo(ctx: Contexto) -> list[str]:
    """La lista nueva de correos, con la actual como valor por defecto. No la
    guarda: el .env cambia recién cuando Access quedó con ella."""
    actual = ",".join(validar.lista_correos(ctx.env.get("ACCESO_CORREOS"))[0])
    if actual:
        ctx.escribir(f"  Hoy entran: {actual.replace(',', ', ')}")
    ctx.escribir("  La lista nueva reemplaza a la actual: quien no esté en ella deja de entrar.")
    while True:
        texto = ctx.preg.pedir("Correos del equipo docente, separados por coma", defecto=actual)
        correos, error = validar.lista_correos(texto)
        if not error:
            return correos
        ctx.escribir(f"  ✗ {error}")


def tokens_internos(ctx: Contexto) -> None:
    """Los dos tokens entre el sitio y el motor. Se crean una vez y los dos los
    leen del .env: el motor desde Secret Manager, el sitio como secretos."""
    for clave in ("WEB_TOKEN", "TOKEN_WEB"):
        if not ctx.env.get(clave):
            ctx.env.set(clave, secrets.token_urlsafe(32))


# ---------------------------------------------------------------- programas


def revisar_programas(ctx: Contexto, git: bool = False) -> None:
    paso("Revisando los programas", ctx.escribir)
    r = ctx.ej.correr(["node", "--version"], lectura=True, puede_fallar=True, simulado="v22.0.0")
    if not r.ok:
        raise Falla("Falta Node.js 22 o más nuevo. En Cloud Shell: nvm install 22")
    try:
        mayor = int(r.salida.strip().lstrip("v").split(".")[0])
    except ValueError:
        mayor = 0
    if mayor < 22:
        raise Falla(f"Node.js {r.salida.strip()} es muy antiguo para wrangler (pide 22 o más). "
                    "En Cloud Shell: nvm install 22 && nvm use 22, y corre de nuevo.")
    for programa in (["npx", "--version"], ["gcloud", "--version"]) + ((["git", "--version"],) if git else ()):
        if not ctx.ej.correr(programa, lectura=True, puede_fallar=True, simulado="ok").ok:
            raise Falla(f"Falta {programa[0]}. Cloud Shell lo trae; si corres en otro equipo, instálalo.")
    ctx.escribir(f"  ✓ Python {sys.version.split()[0]}, Node {r.salida.strip()}, npx y gcloud")


def dependencias_web(ctx: Contexto, siempre: bool = False) -> None:
    if siempre or not (WEB / "node_modules" / ".bin").exists():
        paso("Instalando las dependencias del sitio (npm ci)", ctx.escribir)
        ctx.ej.correr(["npm", "ci", "--no-audit", "--no-fund"], cwd=WEB, mostrar=True)


# ---------------------------------------------------------------- piezas


def _cf(ctx: Contexto) -> Cloudflare:
    return Cloudflare(ctx.ej, ctx.env.get("CLOUDFLARE_API_TOKEN"), ctx.env.get("CLOUDFLARE_ACCOUNT_ID"))


def _valores_wrangler(ctx: Contexto) -> dict[str, str]:
    c = ctx.env.get("CURSO").lower()
    return {
        "name": c, "database_name": c, "database_id": ctx.env.get("CLOUDFLARE_D1_ID"),
        "bucket_name": f"{c}-semestres", "CURSO": ctx.env.get("CURSO").upper(),
        "ACCESO_EQUIPO": ctx.env.get("ACCESO_EQUIPO"), "ACCESO_AUD": ctx.env.get("ACCESO_AUD"),
        "MOTOR_URL": ctx.env.get("MOTOR_URL"),
    }


def _config(ctx: Contexto) -> Path:
    """web/wrangler.<curso>.toml al día con el .env. Lo que el archivo tenía y el
    .env no (el id de la base, los datos de Access) vuelve al .env."""
    config, conservados = cfl.escribir_config(ctx.ej, ctx.env.get("CURSO"), _valores_wrangler(ctx))
    for clave, valor in conservados.items():
        ctx.env.set(clave, valor)
        ctx.escribir(f"  ✓ {clave} recuperado de web/{config.name}")
    return config


def _motor(ctx: Contexto) -> gcp.Motor:
    return gcp.Motor(ctx.env.get("CURSO"), ctx.env.get("GCP_PROYECTO"), ctx.env.get("GCP_REGION"),
                     ctx.env.get("WEB_URL"))


def preparar_cloudflare(ctx: Contexto, cf: Cloudflare) -> None:
    """El subdominio de workers.dev, la base D1 y el bucket R2, si faltan."""
    c = ctx.env.get("CURSO").lower()
    paso("Cloudflare: dirección del sitio, base de datos y archivos", ctx.escribir)
    sub = cf.subdominio()
    if not sub:
        ctx.escribir("  La cuenta todavía no tiene un subdominio de workers.dev. Es parte de la")
        ctx.escribir(f"  dirección del sitio: https://{c}.<subdominio>.workers.dev")
        while True:
            pedido = ctx.preg.pedir("Subdominio (minúsculas, números y guiones)",
                                    defecto=f"{c}-cursos").strip().lower()
            if not validar.SUBDOMINIO.match(pedido):
                ctx.escribir("  ✗ Solo minúsculas, números y guiones.")
                continue
            ok, detalle = cf.registrar_subdominio(pedido)
            if ok:
                sub = pedido
                break
            ctx.escribir(f"  ✗ Cloudflare no lo aceptó ({detalle}). Prueba con otro.")
    web_url = f"https://{c}.{sub}.workers.dev"
    ctx.env.set("WEB_URL", web_url)
    ctx.escribir(f"  ✓ el sitio quedará en {web_url}")

    base = cf.id_d1(c)
    if base:
        ctx.escribir(f"  ✓ base D1 {c} ya existe")
    else:
        base = cf.crear_d1(c)
        ctx.escribir(f"  + base D1 {c}")
    ctx.env.set("CLOUDFLARE_D1_ID", base)

    if cf.bucket_existe(f"{c}-semestres"):
        ctx.escribir(f"  ✓ bucket {c}-semestres ya existe")
    else:
        cf.crear_bucket(f"{c}-semestres")
        ctx.escribir(f"  + bucket {c}-semestres")


def migrar_base(ctx: Contexto, cf: Cloudflare) -> None:
    paso("Base de datos: migraciones pendientes", ctx.escribir)
    config = _config(ctx)
    cf.aplicar_migraciones(config)


def apagar_tutoria(ctx: Contexto, cf: Cloudflare) -> None:
    """Un curso nuevo parte sin la tutoría diaria (manda correos reales). Si el
    profesor ya la prendió, no se toca: INSERT OR IGNORE."""
    cf.consulta_d1(ctx.env.get("CLOUDFLARE_D1_ID"), TUTORIA_APAGADA,
                   [datetime.now(timezone.utc).isoformat()])
    ctx.escribir(f"  ✓ tutoría automática apagada (se prende en {validar.PARAMETROS})")


def desplegar_motor(ctx: Contexto) -> str:
    valores = ctx.env.valores()
    url = gcp.desplegar_motor(ctx.ej, _motor(ctx), valores, escribir=ctx.escribir, esperar=ctx.esperar)
    ctx.env.set("MOTOR_URL", url)
    ctx.escribir(f"  ✓ motor en {url}")
    return url


def configurar_access(ctx: Contexto, cf: Cloudflare, correos: list[str]) -> None:
    paso("Cloudflare Access: quién puede entrar", ctx.escribir)
    config = _config(ctx)
    datos = cf.configurar_access(config, correos, ctx.env.get("WEB_URL"))
    if not datos["ACCESO_EQUIPO"] or not datos["ACCESO_AUD"]:
        raise Falla("acceso.mjs terminó sin dejar ACCESO_EQUIPO y ACCESO_AUD.")
    for k, v in datos.items():
        ctx.env.set(k, v)


def publicar_sitio(ctx: Contexto, cf: Cloudflare) -> None:
    paso("Publicando el sitio", ctx.escribir)
    config = _config(ctx)
    cf.publicar(config, {"TOKEN_MOTOR": ctx.env.get("WEB_TOKEN"), "TOKEN_WEB": ctx.env.get("TOKEN_WEB")})


def subir_plantilla(ctx: Contexto) -> None:
    paso("Plantilla de semestre, con el nombre del curso", ctx.escribir)
    valores = {"CURSO": ctx.env.get("CURSO").upper(), "NOMBRE_CURSO": ctx.env.get("NOMBRE_CURSO"),
               "PROFESOR": ctx.env.get("PROFESOR")}
    r = cfl.subir_plantilla(ctx.ej, ctx.env.get("WEB_URL"), ctx.env.get("WEB_TOKEN"), valores,
                            espera=0 if ctx.ej.simular else 20)
    ctx.escribir(f"  ✓ {len(r['nuevos'])} archivos nuevos, {len(r['ya_estaban'])} ya estaban "
                 "(esos no se tocan)")
    if r["fallidos"]:
        raise Falla("No pude subir: " + ", ".join(r["fallidos"]))


# ---------------------------------------------------------------- comandos


def instalar(ctx: Contexto, args) -> int:
    ctx.escribir("Instalación del sistema de tests y tareas para un curso nuevo.")
    ctx.escribir("Si algo falla, corrígelo y corre de nuevo: retoma donde quedó.")
    revisar_programas(ctx)
    preguntar_curso(ctx)
    preguntar_correo(ctx)
    preguntar_openai(ctx)
    preguntar_cloudflare(ctx)
    preguntar_google(ctx)
    correos = preguntar_equipo(ctx)
    tokens_internos(ctx)

    dependencias_web(ctx)
    cf = _cf(ctx)
    preparar_cloudflare(ctx, cf)
    migrar_base(ctx, cf)
    apagar_tutoria(ctx, cf)
    desplegar_motor(ctx)
    configurar_access(ctx, cf, correos)
    publicar_sitio(ctx, cf)
    subir_plantilla(ctx)

    paso("Listo", ctx.escribir)
    ctx.escribir(f"Sitio:   {ctx.env.get('WEB_URL')}")
    ctx.escribir(f"Motor:   {ctx.env.get('MOTOR_URL')}")
    ctx.escribir(f"Entran:  {', '.join(correos)}")
    m = _motor(ctx)
    gcp.explicar_cuenta_por_defecto(m.proyecto, gcp.numero_proyecto(ctx.ej, m.proyecto), ctx.escribir)
    ctx.escribir("\nLo que sigue:")
    ctx.escribir("  1. Entrar al sitio (llega un código al correo), abrir Configuración y crear")
    ctx.escribir("     el semestre con «Nuevo semestre…»: queda activo.")
    ctx.escribir("  2. Subir la lista de alumnos (columnas Nombre y Correo) y las preguntas.")
    ctx.escribir("  3. Revisar los prompts: ahí está la política de corrección del curso.")
    ctx.escribir("  4. Probar en modo prueba antes del primer envío real.")
    ctx.escribir(f"  5. La tutoría diaria de las 18:00 quedó apagada: se prende en {validar.PARAMETROS}.")
    ctx.escribir("  6. Crear una alerta de presupuesto en console.cloud.google.com/billing.")
    return 0


def _exigir(ctx: Contexto, claves: tuple[str, ...]) -> None:
    faltan = [k for k in claves if not ctx.env.get(k)]
    if faltan:
        raise Falla("Al .env le falta " + ", ".join(faltan) +
                    ". ¿Se terminó la instalación? Corre: python3 instalar.py")


# Cada clave una vez: los tokens internos también están entre los secretos del motor.
INSTALADO = tuple(dict.fromkeys((
    "CURSO", "NOMBRE_CURSO", "PROFESOR", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_D1_ID", "WEB_URL", "WEB_TOKEN", "TOKEN_WEB", "GCP_PROYECTO", "GCP_REGION",
    "MOTOR_URL", "ACCESO_EQUIPO", "ACCESO_AUD", *gcp.SECRETOS.values())))


def actualizar(ctx: Contexto, args) -> int:
    _exigir(ctx, INSTALADO)
    if not args.sin_git:
        paso("Trayendo la última versión del código", ctx.escribir)
        cambios = ctx.ej.correr(["git", "status", "--porcelain", "--untracked-files=no"], cwd=RAIZ,
                                lectura=True, simulado="")
        if cambios.salida.strip():
            raise Falla("Hay archivos del repositorio cambiados en este equipo; git no puede "
                        "traer la versión nueva encima:\n" + cambios.salida.rstrip() +
                        "\nSi no son tuyos a propósito: git checkout -- . (los descarta)")
        antes = ctx.ej.correr(["git", "rev-parse", "HEAD"], cwd=RAIZ, lectura=True, simulado="a").salida
        ctx.ej.correr(["git", "pull", "--ff-only"], cwd=RAIZ, mostrar=True)
        despues = ctx.ej.correr(["git", "rev-parse", "HEAD"], cwd=RAIZ, lectura=True, simulado="a").salida
        if antes.strip() != despues.strip() and not ctx.ej.simular:
            # El instalador mismo pudo cambiar: el resto lo hace la versión nueva.
            ctx.escribir("  Código nuevo: sigo con la versión recién traída.")
            return subprocess.run([sys.executable, str(RAIZ / "instalar.py"), "actualizar",
                                   "--sin-git"]).returncode
    revisar_programas(ctx)
    dependencias_web(ctx, siempre=True)
    cf = _cf(ctx)
    migrar_base(ctx, cf)
    url_antes = ctx.env.get("MOTOR_URL")
    desplegar_motor(ctx)
    if ctx.env.get("MOTOR_URL") != url_antes:
        ctx.escribir("  La dirección del motor cambió; el sitio se publica con la nueva.")
    publicar_sitio(ctx, cf)
    subir_plantilla(ctx)
    paso("Listo: sitio y motor con la última versión", ctx.escribir)
    return 0


def respuesta_http(estado_http: int, cuerpo, largo: int = 100) -> str:
    """Lo que `estado` muestra de un pedido: el código HTTP y, si no es 200, un
    extracto del cuerpo (el texto de una página HTML, sin etiquetas ni estilos)
    que diga por qué."""
    if estado_http == 0:
        return f"sin respuesta: {str(cuerpo)[:largo]}"
    if estado_http == 200:
        return "HTTP 200"
    if isinstance(cuerpo, (bytes, bytearray)):
        cuerpo = bytes(cuerpo).decode("utf-8", "replace")
    elif isinstance(cuerpo, (dict, list)):
        cuerpo = json.dumps(cuerpo, ensure_ascii=False)
    texto = re.sub(r"<(style|script)\b.*?</\1\s*>", " ", str(cuerpo or ""), flags=re.S | re.I)
    texto = " ".join(re.sub(r"<[^>]*>", " ", texto).split())
    if len(texto) > largo:
        texto = texto[:largo].rstrip() + "…"
    return f"HTTP {estado_http}: {texto}" if texto else f"HTTP {estado_http}"


def estado(ctx: Contexto, args) -> int:
    """Qué existe y qué falta. Solo consulta: no crea ni cambia nada."""
    filas: list[tuple[str, bool | None, str]] = []
    marca = lambda ok: "✓" if ok else ("?" if ok is None else "✗")  # noqa: E731

    faltan = [k for k in INSTALADO if not ctx.env.get(k)]
    filas.append((".env completo", not faltan, ", ".join(faltan) and f"falta {', '.join(faltan)}"))
    c = ctx.env.get("CURSO").lower()
    token, cuenta = ctx.env.get("CLOUDFLARE_API_TOKEN"), ctx.env.get("CLOUDFLARE_ACCOUNT_ID")
    if c and token and cuenta:
        cf = _cf(ctx)
        ok, mensaje, det = validar.probar_cloudflare(token, cuenta, ctx.ej)
        filas.append(("token de Cloudflare", ok, "" if ok else mensaje))
        if ok is not False:
            web = ctx.env.get("WEB_URL")
            for nombre, consulta, detalle in (
                    ("base D1", lambda: cf.id_d1(c) is not None, c),
                    ("bucket R2", lambda: cf.bucket_existe(f"{c}-semestres"), f"{c}-semestres"),
                    ("sitio publicado", lambda: cf.worker_existe(c), c),
                    ("Access configurado", lambda: bool(web) and cf.app_access(cfl.host(web)) is not None,
                     cfl.host(web) if web else "")):
                try:
                    filas.append((nombre, consulta(), detalle))
                except Falla as e:
                    # Cloudflare no respondió bien: no se sabe, que no es lo mismo que «falta».
                    filas.append((nombre, None, str(e)))
            config = WEB / cfl.nombre_config(c)
            if config.exists() or ctx.ej.simular:
                pendientes = cf.migraciones_pendientes(config)
                filas.append(("migraciones de la base al día", None if pendientes is None else not pendientes,
                              "" if pendientes is not True else "corre: python3 instalar.py actualizar"))
            else:
                filas.append((f"web/{config.name}", False, "corre: python3 instalar.py actualizar"))
    p, r = ctx.env.get("GCP_PROYECTO"), ctx.env.get("GCP_REGION")
    if c and p and r:
        m = _motor(ctx)
        ok, mensaje = validar.probar_proyecto(p, ctx.ej)
        filas.append(("proyecto de Google Cloud", ok, "" if ok else mensaje))
        if ok is not False:
            for cola in (m.cola, m.cola_simulaciones):
                filas.append((f"cola {cola}", ctx.ej.existe(
                    ["gcloud", "tasks", "queues", "describe", cola, "--location", r, "--project", p]), ""))
            filas.append(("cuenta del motor", ctx.ej.existe(
                ["gcloud", "iam", "service-accounts", "describe", m.cuenta, "--project", p]), m.cuenta))
            for corto in gcp.SECRETOS:
                filas.append((f"secreto {m.secreto(corto)}", ctx.ej.existe(
                    ["gcloud", "secrets", "describe", m.secreto(corto), "--project", p]), ""))
            url = ctx.ej.correr(["gcloud", "run", "services", "describe", m.servicio, "--region", r,
                                 "--project", p, "--format=value(status.url)"],
                                lectura=True, puede_fallar=True).salida.strip()
            filas.append(("motor desplegado", bool(url), url))
            if url:
                estado_http, cuerpo = ctx.ej.pedir("GET", f"{url}/salud")
                filas.append(("motor responde", estado_http == 200, respuesta_http(estado_http, cuerpo)))
    web, token_motor = ctx.env.get("WEB_URL"), ctx.env.get("WEB_TOKEN")
    if web and token_motor:
        estado_http, lista = ctx.ej.pedir("GET", f"{web}/api/motor/archivos/_template", token=token_motor)
        if estado_http == 200 and isinstance(lista, list):
            filas.append(("plantilla de semestre en el sitio", bool(lista), f"HTTP 200, {len(lista)} archivos"))
        else:
            filas.append(("plantilla de semestre en el sitio", False, respuesta_http(estado_http, lista)))

    paso("Estado de la instalación", ctx.escribir)
    for nombre, ok, detalle in filas:
        ctx.escribir(f"  {marca(ok)} {nombre}" + (f"  ({detalle})" if detalle else ""))
    malos = [f for f in filas if f[1] is False]
    if malos:
        ctx.escribir("\nFalta algo. `python3 instalar.py` crea lo que falta sin tocar lo que ya está.")
        return 1
    ctx.escribir("\nTodo en su lugar.")
    return 0


def credenciales(ctx: Contexto, args) -> int:
    """Cambiar una clave sin reinstalar. Reemplaza lo que antes era editar el
    .env y correr motor/desplegar.ps1 (que en Cloud Shell no hay cómo correr)."""
    _exigir(ctx, INSTALADO)
    paso("Cambiar una credencial", ctx.escribir)
    ctx.escribir("  1. El correo del curso o su contraseña de aplicación")
    ctx.escribir("  2. La clave de OpenAI")
    ctx.escribir("  3. El token de Cloudflare")
    opcion = ctx.preg.pedir("¿Cuál? (1, 2 o 3)").strip()
    if opcion == "1":
        preguntar_correo(ctx, de_nuevo=True)
    elif opcion == "2":
        preguntar_openai(ctx, de_nuevo=True)
    elif opcion == "3":
        preguntar_cloudflare(ctx, de_nuevo=True)
        ctx.escribir("  Guardado en el .env. Lo usan instalar y actualizar; el sitio no lo necesita.")
        return 0
    else:
        raise Falla("Elige 1, 2 o 3.")
    m = _motor(ctx)
    paso("Guardando en Secret Manager y reiniciando el motor", ctx.escribir)
    valores = ctx.env.valores()
    for corto, clave in gcp.SECRETOS.items():
        if clave in ("WEB_TOKEN", "TOKEN_WEB"):
            continue
        valor = valores[clave].replace(" ", "") if clave == "CORREO_APP_PASSWORD" else valores[clave]
        ctx.escribir(f"  {m.secreto(corto)}: {gcp.guardar_secreto(ctx.ej, m.proyecto, m.secreto(corto), valor)}")
    gcp.reiniciar_motor(ctx.ej, m)
    ctx.escribir("  ✓ el próximo trabajo ya usa la credencial nueva")
    return 0


def acceso(ctx: Contexto, args) -> int:
    """Cambiar quién entra al sitio sin reinstalar. Corre acceso.mjs con la lista
    nueva, que reemplaza la política de la aplicación de Access, y la guarda en
    ACCESO_CORREOS. El sitio se publica de nuevo solo si Access cambió los datos
    con que el Worker verifica la sesión (ACCESO_EQUIPO, ACCESO_AUD)."""
    _exigir(ctx, INSTALADO)
    revisar_programas(ctx)
    paso("Cambiar quién entra al sitio", ctx.escribir)
    correos = pedir_equipo_nuevo(ctx)
    cf = _cf(ctx)
    antes = (ctx.env.get("ACCESO_EQUIPO"), ctx.env.get("ACCESO_AUD"))
    configurar_access(ctx, cf, correos)
    ctx.env.set("ACCESO_CORREOS", ",".join(correos))
    if ctx.ej.simular:
        ctx.escribir("  [simular] el sitio se publica de nuevo solo si cambian ACCESO_EQUIPO o ACCESO_AUD")
    elif (ctx.env.get("ACCESO_EQUIPO"), ctx.env.get("ACCESO_AUD")) != antes:
        ctx.escribir("  Access cambió los datos con que el sitio verifica la sesión: lo publico de nuevo.")
        try:
            dependencias_web(ctx)
            publicar_sitio(ctx, cf)
        except BaseException:
            # El .env ya tiene los datos nuevos de Access: repetir `acceso` no vería
            # la diferencia y no publicaría. `actualizar` publica con lo del .env.
            ctx.escribir("  ✗ Access ya cambió, pero el sitio no se publicó y sigue con los datos de antes.")
            ctx.escribir("    Nadie va a poder entrar hasta publicarlo: corre  python3 instalar.py actualizar")
            raise
    else:
        ctx.escribir("  ✓ el sitio no necesita publicarse de nuevo: Access mantuvo la misma aplicación")
    paso("Listo", ctx.escribir)
    ctx.escribir(f"Entran:  {', '.join(correos)}")
    ctx.escribir("Quien salió de la lista y tenía la sesión abierta puede seguir entrando hasta que")
    ctx.escribir("venza su sesión (24 horas).")
    return 0


COMANDOS = {"instalar": instalar, "actualizar": actualizar, "estado": estado,
            "credenciales": credenciales, "acceso": acceso}


def leer_argumentos(argv: list[str] | None):
    p = argparse.ArgumentParser(
        prog="instalar.py",
        description="Instala, actualiza o revisa el sistema del curso en Cloudflare y Google Cloud.")
    p.add_argument("accion", nargs="?", default="instalar", choices=list(COMANDOS),
                   help="instalar (por defecto), actualizar, estado, credenciales o acceso")
    p.add_argument("--simular", action="store_true",
                   help="muestra cada comando y cada pedido en vez de hacerlo; no cambia nada")
    p.add_argument("--sin-git", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str] | None = None, ctx: Contexto | None = None) -> int:
    args = leer_argumentos(argv)
    if ctx is None:
        ej = Ejecutor(simular=args.simular)
        ctx = Contexto(ej=ej, env=Entorno(simular=args.simular), preg=Preguntador())
    if ctx.ej.simular:
        ctx.escribir("SIMULACIÓN: se muestran los comandos y pedidos; no se crea ni cambia nada.")
    try:
        return COMANDOS[args.accion](ctx, args)
    except Falla as e:
        ctx.escribir(f"\n✗ {e}")
        ctx.escribir("\nCuando esté corregido, corre de nuevo el mismo comando: retoma donde quedó.")
        return 1
    except KeyboardInterrupt:
        ctx.escribir("\nInterrumpido. Se puede correr de nuevo: retoma donde quedó.")
        return 130
