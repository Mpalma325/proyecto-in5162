"""
instalar.py sin nube y sin red.

Los programas (gcloud, npx, node, git) y los pedidos HTTP pasan por el
Ejecutor del instalador; acá se reemplazan por respuestas inventadas, y el SMTP
por una clase falsa. Se revisa:
- que cada credencial se compruebe sin efectos (el SMTP inicia sesión y sale,
  sin mandar nada);
- que volver a correr no cree lo que ya existe;
- que --simular no corra nada y muestre todos los comandos;
- que la configuración de wrangler de un curso no arrastre datos de IN5162;
- que la plantilla de semestre no nombre a IN5162 y quede con el curso nuevo;
- que motor/desplegar.ps1 y el instalador creen lo mismo.
Nombres, correos y claves son inventados: el repositorio es público.
"""

import csv
import io
import json
import os
import re
import smtplib
import string
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, ".")
sys.path.insert(0, "pruebas")
from comun import check, resultado, titulo

from instalador import cloudflare as cfl
from instalador import gcp, plantilla, validar
from instalador.comun import Ejecutor, Entorno, Falla, Preguntador
from instalador.principal import Contexto, main, preparar_cloudflare

RAIZ = Path(".").resolve()
CUENTA = "0123456789abcdef0123456789abcdef"
SECRETOS_FALSOS = ("clave-correo-falsa", "sk-falsa-de-prueba", "token-cf-falso")


# ---------------------------------------------------------------- dobles


class Respuesta:
    def __init__(self, estado, datos):
        self.status, self._datos = estado, datos

    def read(self):
        return self._datos

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Red:
    """urlopen falso: [(método, regex de la URL, estado, cuerpo)], la primera que calce."""

    def __init__(self, rutas):
        self.rutas = rutas
        self.pedidos = []

    def __call__(self, req, timeout=None):
        self.pedidos.append((req.get_method(), req.full_url, req.data, dict(req.header_items())))
        for metodo, patron, estado, cuerpo in self.rutas:
            if metodo == req.get_method() and re.search(patron, req.full_url):
                datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
                if estado >= 400:
                    raise urllib.error.HTTPError(req.full_url, estado, "x", {}, io.BytesIO(datos))
                return Respuesta(estado, datos)
        raise urllib.error.URLError("la prueba no conoce esta URL")

    def hubo(self, metodo, patron):
        return any(m == metodo and re.search(patron, u) for m, u, _, _ in self.pedidos)


class Procesos:
    """subprocess.run falso: [(regex del comando, código, stdout)], la primera que calce.
    Lo que no calza termina bien y sin salida."""

    def __init__(self, respuestas=()):
        self.respuestas = list(respuestas)
        self.llamadas = []  # (línea, entrada)

    def __call__(self, cmd, **kw):
        linea = " ".join([Path(cmd[0]).stem, *map(str, cmd[1:])])
        self.llamadas.append((linea, kw.get("input")))
        for patron, codigo, salida in self.respuestas:
            if re.search(patron, linea):
                return subprocess.CompletedProcess(cmd, codigo, salida, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def hubo(self, patron):
        return any(re.search(patron, l) for l, _ in self.llamadas)


def prohibido(*a, **k):
    raise AssertionError("en simulación no se corre ni se pide nada")


class SmtpFalso:
    ultima = None

    def __init__(self, host, puerto, timeout=None):
        self.llamadas = [("conectar", host, puerto)]
        SmtpFalso.ultima = self

    def ehlo(self):
        self.llamadas.append("ehlo")

    def starttls(self, context=None):
        self.llamadas.append("starttls")

    def login(self, usuario, clave):
        self.llamadas.append("login")
        if clave != "buena":
            raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    def quit(self):
        self.llamadas.append("quit")

    def sendmail(self, *a, **k):
        self.llamadas.append("sendmail")

    def send_message(self, *a, **k):
        self.llamadas.append("send_message")


def preguntador(respuestas):
    cola = list(respuestas)
    salida = []

    def leer(texto):
        salida.append(texto)
        if not cola:
            raise EOFError
        return cola.pop(0)

    return Preguntador(leer=leer, leer_secreto=leer, escribir=salida.append), cola


def cf_ok(resultado_):
    return {"success": True, "errors": [], "result": resultado_}


def cf_error(codigo, mensaje="error"):
    return {"success": False, "errors": [{"code": codigo, "message": mensaje}], "result": None}


# ---------------------------------------------------------------- 1. formato

titulo("1. los datos se revisan al escribirlos")
check("IN3401 sirve como código", validar.error_codigo("IN3401") is None)
check("in5162 no: ya está instalado a mano", validar.error_codigo("in5162") is not None)
check("un código con espacios no", validar.error_codigo("IN 34") is not None)
correos, err = validar.lista_correos("Profe@Ejemplo.cl, ayudante@ejemplo.cl;profe@ejemplo.cl")
check("lista de correos: minúsculas, sin repetidos, coma o punto y coma",
      correos == ["profe@ejemplo.cl", "ayudante@ejemplo.cl"] and err is None, correos)
check("un correo mal escrito se rechaza", validar.lista_correos("profe@, otro@ejemplo.cl")[1] is not None)
check("región us-central1 sí, 'chile' no",
      validar.error_region("us-central1") is None and validar.error_region("chile") is not None)
check("id de proyecto vs nombre del proyecto",
      validar.error_proyecto("curso-motor-123") is None and validar.error_proyecto("Mi Proyecto") is not None)
check("account id de Cloudflare: 32 hexadecimales",
      validar.error_cuenta_cf(CUENTA) is None and validar.error_cuenta_cf("abc") is not None)

# ---------------------------------------------------------------- 2. correo

titulo("2. el correo se prueba iniciando sesión, sin mandar nada")
ok, msg = validar.probar_correo("curso@ejemplo.cl", "buena", smtp=SmtpFalso)
ll = SmtpFalso.ultima.llamadas
check("con la clave buena, ok", ok is True, msg)
check("STARTTLS antes del login, y QUIT al final",
      ll.index("starttls") < ll.index("login") and ll[-1] == "quit", ll)
check("no se manda ningún mensaje", "sendmail" not in ll and "send_message" not in ll, ll)
check("va a smtp.gmail.com:587", ll[0] == ("conectar", "smtp.gmail.com", 587), ll[0])
ok, msg = validar.probar_correo("curso@ejemplo.cl", "mala", smtp=SmtpFalso)
check("clave rechazada: dice que es la contraseña de aplicación",
      ok is False and "aplicación" in msg and SmtpFalso.ultima.llamadas[-1] == "quit", msg)


def smtp_caido(*a, **k):
    raise OSError("sin red")


ok, msg = validar.probar_correo("curso@ejemplo.cl", "buena", smtp=smtp_caido)
check("sin conexión no se sabe (None), no es un rechazo", ok is None, msg)

# ---------------------------------------------------------------- 3. OpenAI

titulo("3. la clave de OpenAI se prueba listando modelos")
red = Red([("GET", r"api\.openai\.com/v1/models$", 200, {"data": [{"id": "gpt-5.4-mini"}]})])
ok, msg = validar.probar_openai("sk-falsa-de-prueba", Ejecutor(abrir=red))
check("clave buena", ok is True, msg)
check("solo un GET a /v1/models, con la clave en Authorization",
      len(red.pedidos) == 1 and red.pedidos[0][0] == "GET"
      and red.pedidos[0][3].get("Authorization") == "Bearer sk-falsa-de-prueba", red.pedidos)
red = Red([("GET", r"/v1/models$", 401, {"error": {"message": "Incorrect API key"}})])
ok, msg = validar.probar_openai("sk-mala", Ejecutor(abrir=red))
check("clave mala: rechazo claro", ok is False and "rechazó" in msg, msg)
red = Red([("GET", r"/v1/models$", 200, {"data": [{"id": "otro-modelo"}]})])
ok, msg = validar.probar_openai("sk-x", Ejecutor(abrir=red))
check("sin el modelo por defecto: sirve, con aviso", ok is True and "gpt-5.4-mini" in msg, msg)

# ---------------------------------------------------------------- 4. Cloudflare

titulo("4. el token de Cloudflare: válido y con los permisos que se usan")
A = rf"/accounts/{CUENTA}"
base_cf = [
    ("GET", r"/user/tokens/verify$", 200, cf_ok({"status": "active"})),
    ("GET", A + r"/workers/scripts$", 200, cf_ok([])),
    ("GET", A + r"/d1/database$", 200, cf_ok([])),
    ("GET", A + r"/r2/buckets$", 200, cf_ok({"buckets": []})),
    ("GET", A + r"/access/apps$", 200, cf_ok([])),
    ("GET", A + r"/access/organizations$", 200, cf_ok({"auth_domain": "equipo.cloudflareaccess.com"})),
]
red = Red(base_cf)
ok, msg, det = validar.probar_cloudflare("token-cf-falso", CUENTA, Ejecutor(abrir=red))
check("con todo, ok", ok is True, msg)
check("solo consultas (GET)", all(m == "GET" for m, *_ in red.pedidos), red.pedidos)
red = Red([("GET", A + r"/d1/database$", 403, cf_error(10000, "Authentication error"))] + base_cf)
ok, msg, det = validar.probar_cloudflare("token-cf-falso", CUENTA, Ejecutor(abrir=red))
check("sin permiso de D1: lo nombra", ok is False and "D1: Edit" in msg, msg)
red = Red([("GET", A + r"/access/organizations$", 404, cf_error(9999))] + base_cf)
ok, msg, det = validar.probar_cloudflare("token-cf-falso", CUENTA, Ejecutor(abrir=red))
check("Zero Trust sin activar: lo dice", ok is False and "Zero Trust" in msg, msg)
red = Red([("GET", A + r"/r2/buckets$", 403, cf_error(10042, "Please enable R2"))] + base_cf)
ok, msg, det = validar.probar_cloudflare("token-cf-falso", CUENTA, Ejecutor(abrir=red))
check("R2 sin activar: lo dice", ok is False and "R2" in msg, msg)
red = Red([("GET", r"/tokens/verify$", 401, cf_error(1000, "Invalid API Token"))])
ok, msg, det = validar.probar_cloudflare("malo", CUENTA, Ejecutor(abrir=red))
check("token inválido: rechazo", ok is False and "token" in msg.lower(), msg)
check("prueba también el verify de tokens de cuenta",
      red.hubo("GET", A + r"/tokens/verify$"), red.pedidos)

# ---------------------------------------------------------------- 5. Google Cloud

titulo("5. el proyecto de Google Cloud: existe y tiene facturación")
p = Procesos([(r"^gcloud projects describe", 0, "123456789\n"), (r"billing projects describe", 0, "True\n")])
ok, msg = validar.probar_proyecto("curso-motor", Ejecutor(correr_proceso=p))
check("existe y factura", ok is True, msg)
check("solo describe (nada que cambie)", all("describe" in l for l, _ in p.llamadas), p.llamadas)
p = Procesos([(r"^gcloud projects describe", 0, "123\n"), (r"billing", 0, "False\n")])
ok, msg = validar.probar_proyecto("curso-motor", Ejecutor(correr_proceso=p))
check("sin facturación: dice dónde activarla", ok is False and "billing" in msg, msg)
p = Procesos([(r"^gcloud projects describe", 1, "")])
ok, msg = validar.probar_proyecto("curso-motor", Ejecutor(correr_proceso=p))
check("proyecto inexistente", ok is False and "No encuentro" in msg, msg)

# ---------------------------------------------------------------- 6. motor idempotente

titulo("6. el motor: lo que ya existe no se vuelve a crear")
VALORES = {"OPENAI_API_KEY": "sk-falsa-de-prueba", "CORREO_REMITENTE": "curso@ejemplo.cl",
           "CORREO_APP_PASSWORD": "abcd efgh ijkl mnop", "WEB_TOKEN": "t-motor", "TOKEN_WEB": "t-web"}
m = gcp.Motor("ZZ9999", "curso-motor", "us-central1", "https://zz9999.sub.workers.dev")
URL = "https://zz9999-motor-abc.a.run.app"
secretos_actuales = {"zz9999-openai": "sk-falsa-de-prueba", "zz9999-correo-remitente": "curso@ejemplo.cl",
                     "zz9999-correo-clave": "abcdefghijklmnop", "zz9999-token-motor": "t-motor",
                     "zz9999-token-web": "t-web"}
todo_existe = Procesos(
    [(rf"secrets versions access latest --secret {n} ", 0, v) for n, v in secretos_actuales.items()]
    + [(r"^gcloud projects describe", 0, "123456789\n"), (r"run services describe", 0, URL + "\n")])
url = gcp.desplegar_motor(Ejecutor(correr_proceso=todo_existe), m, VALORES, escribir=lambda *a: None,
                          esperar=lambda s: None)
check("devuelve la dirección del motor", url == URL, url)
for patron, que in [(r"queues create", "colas"), (r"service-accounts create", "cuenta de servicio"),
                    (r"secrets create", "secretos"), (r"versions add", "versiones de secretos"),
                    (r"repositories create", "repositorio"), (r"services update", "segunda revisión")]:
    check(f"no crea {que} que ya existen", not todo_existe.hubo(patron),
          [l for l, _ in todo_existe.llamadas if re.search(patron, l)])
check("despliega con la cuenta propia y su dirección ya puesta",
      todo_existe.hubo(r"run deploy zz9999-motor .*--service-account=zz9999-motor@curso-motor\.iam"
                       r"\.gserviceaccount\.com.*MOTOR_URL_PUBLICA=" + re.escape(URL)))
check("permisos por secreto (5) y por cola (2), no a nivel de proyecto",
      sum(bool(re.search(r"secrets add-iam-policy-binding zz9999-", l)) for l, _ in todo_existe.llamadas) == 5
      and sum(bool(re.search(r"queues add-iam-policy-binding", l)) for l, _ in todo_existe.llamadas) == 2
      and not todo_existe.hubo(r"projects add-iam-policy-binding .*secretAccessor"))
check("no quita roles de la cuenta por defecto (solo los muestra)",
      not todo_existe.hubo(r"remove-iam-policy-binding"))

nada = Procesos([(r"^gcloud projects describe", 0, "123\n"), (r"describe", 1, "")])
# El primer describe del servicio (antes de desplegar) falla; el segundo da la URL.
llamadas_run = {"n": 0}


def describe_servicio(cmd, **kw):
    linea = " ".join([Path(cmd[0]).stem, *cmd[1:]])
    if "run services describe" in linea:
        llamadas_run["n"] += 1
        return subprocess.CompletedProcess(cmd, 1 if llamadas_run["n"] == 1 else 0,
                                           "" if llamadas_run["n"] == 1 else URL, "")
    return nada(cmd, **kw)


esperas = []
gcp.desplegar_motor(Ejecutor(correr_proceso=describe_servicio), m, VALORES, escribir=lambda *a: None,
                    esperar=esperas.append)
check("desde cero: crea las 2 colas, de a 1 y de a 3, sin reintentos",
      nada.hubo(r"queues create zz9999-trabajos .*--max-concurrent-dispatches=1 --max-attempts=1")
      and nada.hubo(r"queues create zz9999-simulaciones .*--max-concurrent-dispatches=3 --max-attempts=1"))
check("crea la cuenta zz9999-motor y espera a que IAM la vea",
      nada.hubo(r"service-accounts create zz9999-motor") and esperas == [15], esperas)
check("crea los 5 secretos", sum("secrets create" in l for l, _ in nada.llamadas) == 5)
check("las claves van por la entrada estándar, nunca en la línea de comandos",
      all(v not in l for l, _ in nada.llamadas for v in VALORES.values())
      and any(e == "sk-falsa-de-prueba" for _, e in nada.llamadas))
check("la contraseña de aplicación se guarda sin espacios",
      any(e == "abcdefghijklmnop" for _, e in nada.llamadas))
check("crea el repositorio de imágenes y le pone la limpieza",
      nada.hubo(r"repositories create cloud-run-source-deploy") and nada.hubo(r"set-cleanup-policies"))
check("primer despliegue: después anota su dirección", nada.hubo(r"services update zz9999-motor .*MOTOR_URL_PUBLICA="))

cambio = Procesos([(r"secrets versions access latest --secret zz9999-openai ", 0, "sk-vieja"),
                   (r"secrets versions list zz9999-openai", 0, "projects/x/secrets/zz9999-openai/versions/3\n"
                                                          "projects/x/secrets/zz9999-openai/versions/2\n")])
estado = gcp.guardar_secreto(Ejecutor(correr_proceso=cambio), "curso-motor", "zz9999-openai", "sk-nueva")
check("clave cambiada: versión nueva y se destruye la anterior",
      estado == "actualizado" and cambio.hubo(r"versions add zz9999-openai")
      and cambio.hubo(r"versions destroy projects/x/secrets/zz9999-openai/versions/2")
      and not cambio.hubo(r"versions destroy .*versions/3"), cambio.llamadas)

# ---------------------------------------------------------------- 7. desplegar.ps1

titulo("7. desplegar.ps1 (IN5162) y el instalador crean lo mismo")
ps1 = (RAIZ / "motor" / "desplegar.ps1").read_text(encoding="utf-8")
vars_ps1 = re.search(r'\$variables = "([^"]+)"', ps1).group(1)
nombres_ps1 = set(re.findall(r"([A-Z_]+)=", vars_ps1))
nombres_py = set(re.findall(r"([A-Z_]+)=", m.variables()))
check("las mismas variables de entorno del motor", nombres_ps1 == nombres_py, (nombres_ps1, nombres_py))
secretos_ps1 = set(re.findall(r'"\$c-([a-z-]+)"', ps1)) - {"motor", "trabajos", "simulaciones"}
check("los mismos 5 secretos", secretos_ps1 == set(gcp.SECRETOS), secretos_ps1)
run_ps1 = set(re.findall(r"([A-Z_]+)=\$c-([a-z-]+):latest", ps1))
check("cada variable lee el mismo secreto", run_ps1 == set(gcp.VARIABLES_SECRETAS.items()), run_ps1)
check("mismas colas y límites",
      "--max-concurrent-dispatches 1 --max-attempts 1" in ps1 and "--max-concurrent-dispatches 3 --max-attempts 1" in ps1
      and '"$c-trabajos"' in ps1 and '"$c-simulaciones"' in ps1)
opciones = lambda t: set(re.findall(r"--(memory|cpu|timeout|concurrency|max-instances)[ =]([0-9A-Za-z]+)", t))  # noqa: E731
check("mismos recursos de Cloud Run", opciones(ps1) == opciones((RAIZ / "instalador" / "gcp.py").read_text(encoding="utf-8")))

# ---------------------------------------------------------------- 8. Cloudflare idempotente

titulo("8. Cloudflare: subdominio, base y bucket solo si faltan")
with tempfile.TemporaryDirectory() as tmp:
    env = Entorno(Path(tmp) / ".env")
    env.set("CURSO", "ZZ9999")
    red = Red([("GET", A + r"/workers/subdomain$", 200, cf_ok({"subdomain": "miscursos"})),
               ("GET", A + r"/d1/database\?name=zz9999$", 200, cf_ok([{"name": "zz9999", "uuid": "uuid-1"}])),
               ("GET", A + r"/r2/buckets/zz9999-semestres$", 200, cf_ok({"name": "zz9999-semestres"}))])
    ej = Ejecutor(abrir=red, escribir=lambda *a: None)
    preg, _ = preguntador([])
    ctx = Contexto(ej=ej, env=env, preg=preg, escribir=lambda *a: None)
    preparar_cloudflare(ctx, cfl.Cloudflare(ej, "token-cf-falso", CUENTA))
    check("todo existe: ningún POST ni PUT", all(mt == "GET" for mt, *_ in red.pedidos), red.pedidos)
    check("WEB_URL sale del subdominio", env.get("WEB_URL") == "https://zz9999.miscursos.workers.dev")
    check("el id de la base queda en el .env", env.get("CLOUDFLARE_D1_ID") == "uuid-1")

    red = Red([("GET", A + r"/workers/subdomain$", 404, cf_error(10007, "not found")),
               ("PUT", A + r"/workers/subdomain$", 200, cf_ok({"subdomain": "zz9999-cursos"})),
               ("GET", A + r"/d1/database\?name=", 200, cf_ok([])),
               ("POST", A + r"/d1/database$", 200, cf_ok({"uuid": "uuid-nuevo", "name": "zz9999"})),
               ("GET", A + r"/r2/buckets/", 404, cf_error(10006, "The specified bucket does not exist")),
               ("POST", A + r"/r2/buckets$", 200, cf_ok({}))])
    ej = Ejecutor(abrir=red, escribir=lambda *a: None)
    preg, cola = preguntador([""])
    ctx = Contexto(ej=ej, env=env, preg=preg, escribir=lambda *a: None)
    preparar_cloudflare(ctx, cfl.Cloudflare(ej, "token-cf-falso", CUENTA))
    check("cuenta nueva: registra el subdominio propuesto", red.hubo("PUT", r"/workers/subdomain$")
          and json.loads(next(d for mt, u, d, _ in red.pedidos if mt == "PUT")) == {"subdomain": "zz9999-cursos"})
    check("crea la base y el bucket", red.hubo("POST", r"/d1/database$") and red.hubo("POST", r"/r2/buckets$"))
    check("y anota el id nuevo", env.get("CLOUDFLARE_D1_ID") == "uuid-nuevo")

# ---------------------------------------------------------------- 9. wrangler.<curso>.toml

titulo("9. la configuración de wrangler del curso no arrastra datos de IN5162")
base = cfl.BASE_WRANGLER.read_text(encoding="utf-8")
valores = {"name": "zz9999", "database_name": "zz9999", "database_id": "uuid-1",
           "bucket_name": "zz9999-semestres", "CURSO": "ZZ9999",
           "ACCESO_EQUIPO": "equipo.cloudflareaccess.com", "ACCESO_AUD": "aud-1",
           "MOTOR_URL": URL}
toml = cfl.generar_wrangler(base, valores)
leido = cfl.leer_vars(toml)
check("cada valor del curso quedó", all(leido.get(k) == v for k, v in valores.items()),
      {k: leido.get(k) for k in valores})
de_in5162 = {k: v for k, v in cfl.leer_vars(base).items() if k in cfl.CAMPOS_WRANGLER}
check("ningún valor de IN5162 sobrevive", not any(f'"{v}"' in toml for v in de_in5162.values() if v), de_in5162)
check("conserva el cron, las migraciones y Access obligatorio",
      'crons = ["0 21 * * *", "0 22 * * *"]' in toml and 'migrations_dir = "migrations"' in toml
      and 'ACCESO = "cloudflare"' in toml)
check("el archivo es por curso y git lo ignora",
      cfl.nombre_config("ZZ9999") == "wrangler.zz9999.toml"
      and "wrangler.*.toml" in (RAIZ / "web" / ".gitignore").read_text(encoding="utf-8"))
try:
    cfl.generar_wrangler(base.replace('bucket_name = "', 'bucket = "'), valores)
    check("si wrangler.toml cambia de forma, falla en vez de adivinar", False)
except Falla:
    check("si wrangler.toml cambia de forma, falla en vez de adivinar", True)
try:
    cfl.generar_wrangler(base, {**valores, "CURSO": 'X"Y'})
    check("un valor con comillas no rompe el TOML", False)
except Falla:
    check("un valor con comillas no rompe el TOML", True)

# ---------------------------------------------------------------- 10. plantilla

titulo("10. la plantilla de semestre es neutra y queda con el curso nuevo")
PROHIBIDO = re.compile(r"IN5162|Ingenier[ií]a (en|de) Marketing|FCFM|uchile|grupos de 3|ChatGPT|ggplot|\bcódigo R\b", re.I)
crudos = {p.relative_to(plantilla.PLANTILLA).as_posix(): p.read_text(encoding="utf-8")
          for p in plantilla.PLANTILLA.rglob("*") if p.is_file() and p.suffix in (".md", ".csv")}
menciones = {r: PROHIBIDO.findall(t) for r, t in crudos.items() if PROHIBIDO.search(t)}
check(f"ningún archivo de la plantilla ({len(crudos)}) nombra a IN5162 ni su contexto", not menciones, menciones)
datos_curso = {"CURSO": "ZZ9999", "NOMBRE_CURSO": "Curso de Prueba", "PROFESOR": "Ana Prueba"}
archivos = dict(plantilla.archivos(datos_curso))
textos = {r: d.decode("utf-8") for r, d in archivos.items() if r.endswith((".md", ".csv"))}
check("no queda ninguna marca «...» sin llenar", not any("«" in t for t in textos.values()),
      [r for r, t in textos.items() if "«" in t])
check("los prompts de corrección y tutoría nombran al curso",
      all("ZZ9999 (Curso de Prueba)" in textos[r] for r in (
          "tests_semanales/prompts/evaluar_respuesta.md", "tests_semanales/prompts/tutoria.md",
          "tareas/prompts/corregir_respuesta.md", "tareas/prompts/generar_preguntas.md")))
check("los correos firman con el profesor y el curso",
      "Ana Prueba y el equipo docente de ZZ9999" in textos["tareas/prompts/correo_pregunta.md"]
      and "Ana Prueba y el equipo docente de ZZ9999" in textos["tests_semanales/prompts/correo_pregunta.md"])
campos = lambda t: {c for _, c, _, _ in string.Formatter().parse(t) if c}  # noqa: E731
formato = ["tareas/prompts/correo_pregunta.md", "tareas/prompts/correo_feedback.md",
           "tareas/prompts/correo_segunda_oportunidad.md"]
check("los correos que se llenan con str.format no ganan campos nuevos",
      all(campos(textos[r]) == campos(crudos[r]) for r in formato),
      {r: campos(textos[r]) ^ campos(crudos[r]) for r in formato})
check("y se pueden llenar", all(textos[r].format(**{c: "x" for c in campos(textos[r])}) for r in formato))
check("los .gitkeep viajan (R2 no tiene carpetas vacías)", "tareas/data/entregas/.gitkeep" in archivos)
check("CRLF de un clon en Windows se sube como LF", not any("\r" in t for t in textos.values()))
filas = list(csv.DictReader(io.StringIO(textos["alumnos.example.csv"])))
check("el ejemplo de alumnos usa las columnas que lee el código (Nombre, Correo)",
      filas and set(filas[0]) == {"Nombre", "Correo"}, filas[:1])
check("los ejemplos viejos (nombre,correo, en tareas/ y tests_semanales/) ya no están",
      not any(r.endswith("data/alumnos.example.csv") for r in archivos))
preguntas = list(csv.DictReader(io.StringIO(textos["tests_semanales/data/preguntas.example.csv"])))
check("el ejemplo de preguntas tiene todas sus columnas bien cerradas",
      preguntas and all(None not in f and len(f) == 15 for f in preguntas), preguntas[:1])
try:
    plantilla.renderizar("Hola «OTRA»", datos_curso)
    check("una marca desconocida es un error", False)
except ValueError:
    check("una marca desconocida es un error", True)

# El semestre que se crea en el PC (la app) llena las mismas marcas.
from modulos.semestre import gestion  # noqa: E402

originales = (gestion.PROJECT_ROOT, gestion.SEMESTRES_DIR)
del_entorno = {k: os.environ.pop(k) for k in gestion.MARCAS if k in os.environ}
with tempfile.TemporaryDirectory() as tmp:
    gestion.PROJECT_ROOT, gestion.SEMESTRES_DIR = Path(tmp), Path(tmp) / "semestres"
    gestion.SEMESTRES_DIR.mkdir()
    (Path(tmp) / ".env").write_text("CURSO=ZZ9999\nNOMBRE_CURSO=Curso de Prueba\n", encoding="utf-8")
    try:
        gestion.crear("2099-1")
        check("en el PC, sin PROFESOR en el .env: no crea el semestre", False)
    except ValueError as e:
        check("en el PC, sin PROFESOR en el .env: no crea el semestre y dice qué falta",
              "PROFESOR" in str(e) and not (gestion.SEMESTRES_DIR / "2099-1").exists(), str(e))
    (Path(tmp) / ".env").write_text("CURSO=ZZ9999\nNOMBRE_CURSO=Curso de Prueba\nPROFESOR=Ana Prueba\n",
                                    encoding="utf-8")
    gestion.crear("2099-1")
    creado = gestion.SEMESTRES_DIR / "2099-1"
    textos_pc = {p.relative_to(creado).as_posix(): p.read_text(encoding="utf-8")
                 for p in creado.rglob("*") if p.suffix in (".md", ".csv")}
    check("en el PC, con los datos: ninguna marca sin llenar", not any("«" in t for t in textos_pc.values()))
    check("y queda igual que lo que instalar.py sube al sitio",
          textos_pc == {r: t for r, t in textos.items()}, set(textos_pc) ^ set(textos))
gestion.PROJECT_ROOT, gestion.SEMESTRES_DIR = originales
os.environ.update(del_entorno)

# IN5162 sube la plantilla desde el PC con modulos.web.subir --archivos.
from modulos.web import subir  # noqa: E402

ruta_eval = "tests_semanales/prompts/evaluar_respuesta.md"
check("subir.py también sube la plantilla llena, igual que instalar.py",
      subir._contenido("_template", plantilla.PLANTILLA / ruta_eval, datos_curso) == archivos[ruta_eval])
check("y los archivos de un semestre los sube tal cual",
      subir._contenido("2099-1", plantilla.PLANTILLA / ruta_eval, None)
      == (plantilla.PLANTILLA / ruta_eval).read_bytes())

# ---------------------------------------------------------------- 11. .env

titulo("11. el .env se reescribe sin perder lo que había")
with tempfile.TemporaryDirectory() as tmp:
    ruta = Path(tmp) / ".env"
    ruta.write_text("# comentario\nMODELO=gpt-5.4-mini\nCURSO=VIEJO\n", encoding="utf-8")
    env = Entorno(ruta)
    env.set("CURSO", "ZZ9999")
    env.set("NOMBRE_CURSO", "Curso de Prueba")
    texto = ruta.read_text(encoding="utf-8")
    check("cambia la clave, agrega la nueva, conserva comentario y orden",
          texto.splitlines() == ["# comentario", "MODELO=gpt-5.4-mini", "CURSO=ZZ9999",
                                 "NOMBRE_CURSO=Curso de Prueba"], texto)
    sim = Entorno(ruta, simular=True)
    sim.set("CURSO", "OTRO")
    check("en simulación no escribe", Entorno(ruta).get("CURSO") == "ZZ9999" and sim.get("CURSO") == "OTRO")

# ---------------------------------------------------------------- 12. --simular

titulo("12. --simular no corre nada y muestra todo lo que haría")
RESPUESTAS = ["zz9999", "Curso de Prueba", "Ana Prueba", "curso@ejemplo.cl", "clave-correo-falsa",
              "sk-falsa-de-prueba", CUENTA, "token-cf-falso", "curso-motor", "",
              "profe@ejemplo.cl, ayudante@ejemplo.cl", ""]
with tempfile.TemporaryDirectory() as tmp:
    ruta_env = Path(tmp) / ".env"
    salida = []
    ej = Ejecutor(simular=True, correr_proceso=prohibido, abrir=prohibido, escribir=salida.append)
    preg, cola = preguntador(RESPUESTAS)
    ctx = Contexto(ej=ej, env=Entorno(ruta_env, simular=True), preg=preg, escribir=salida.append,
                   smtp=prohibido)
    antes = sorted(p.name for p in (RAIZ / "web").iterdir())
    codigo = main(["--simular"], ctx)
    texto = "\n".join(map(str, salida))
    reg = "\n".join(ej.registro)
    check("termina bien", codigo == 0, texto[-1500:])
    check("contestó todas las preguntas", not cola, cola)
    check("no escribió el .env", not ruta_env.exists())
    check("no escribió wrangler.zz9999.toml", sorted(p.name for p in (RAIZ / "web").iterdir()) == antes)
    esperados = [
        r"PUT .*/accounts/[0-9a-f]{32}/workers/subdomain",
        r"POST .*/d1/database$", r"POST .*/r2/buckets$",
        r"npx wrangler d1 migrations apply DB --remote --config wrangler\.zz9999\.toml",
        r"POST .*/d1/database/.*/query",
        r"gcloud services enable run\.googleapis\.com",
        r"gcloud tasks queues create zz9999-trabajos", r"gcloud tasks queues create zz9999-simulaciones",
        r"gcloud secrets create zz9999-openai --data-file=-",
        r"gcloud iam service-accounts create zz9999-motor",
        r"gcloud run deploy zz9999-motor --source \.",
        r"node scripts/acceso\.mjs --config wrangler\.zz9999\.toml profe@ejemplo\.cl ayudante@ejemplo\.cl",
        r"npx wrangler deploy --secrets-file .* --config wrangler\.zz9999\.toml",
        r"PUT https://zz9999\.zz9999-cursos\.workers\.dev/api/motor/archivo/_template/tests_semanales/prompts/evaluar_respuesta\.md",
    ]
    for patron in esperados:
        check(f"muestra: {patron[:70]}", re.search(patron, reg, re.M), "")
    orden = [reg.find(s) for s in ("migrations apply", "run deploy", "acceso.mjs", "wrangler deploy", "_template/")]
    check("en orden: base, motor, Access, sitio, plantilla", orden == sorted(orden) and -1 not in orden, orden)
    check("nunca wrangler login ni --remote fuera de las migraciones",
          "wrangler login" not in reg and reg.count("--remote") == 1)
    check("las claves no aparecen en la salida ni en los comandos",
          not any(s in texto or s in reg for s in SECRETOS_FALSOS))
    check("muestra (sin correr) cómo quitar roles a la cuenta por defecto",
          "remove-iam-policy-binding" in texto and "remove-iam-policy-binding" not in reg)
    check("la tutoría automática parte apagada",
          re.search(r"POST .*/query", reg) and "tutoría automática apagada" in texto)

# ---------------------------------------------------------------- 13. actualizar, estado, credenciales

titulo("13. actualizar, estado y credenciales")
COMPLETO = {"CURSO": "ZZ9999", "NOMBRE_CURSO": "Curso de Prueba", "PROFESOR": "Ana Prueba",
            "CLOUDFLARE_API_TOKEN": "token-cf-falso", "CLOUDFLARE_ACCOUNT_ID": CUENTA,
            "CLOUDFLARE_D1_ID": "uuid-1", "WEB_URL": "https://zz9999.miscursos.workers.dev",
            "WEB_TOKEN": "t-motor", "TOKEN_WEB": "t-web", "GCP_PROYECTO": "curso-motor",
            "GCP_REGION": "us-central1", "MOTOR_URL": URL, "ACCESO_EQUIPO": "equipo.cloudflareaccess.com",
            "ACCESO_AUD": "aud-1", "OPENAI_API_KEY": "sk-falsa-de-prueba",
            "CORREO_REMITENTE": "curso@ejemplo.cl", "CORREO_APP_PASSWORD": "clave-correo-falsa"}


def contexto_simulado(valores, respuestas=()):
    tmp = tempfile.mkdtemp()
    ruta = Path(tmp) / ".env"
    ruta.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
    salida = []
    ej = Ejecutor(simular=True, correr_proceso=prohibido, abrir=prohibido, escribir=salida.append)
    preg, cola = preguntador(respuestas)
    return Contexto(ej=ej, env=Entorno(ruta, simular=True), preg=preg, escribir=salida.append,
                    smtp=prohibido), salida


ctx, salida = contexto_simulado({"CURSO": "ZZ9999"})
check("actualizar sin instalación completa: se niega y dice qué falta",
      main(["actualizar", "--simular"], ctx) == 1 and any("CLOUDFLARE_D1_ID" in str(s) for s in salida))
ctx, salida = contexto_simulado(COMPLETO)
codigo = main(["actualizar", "--simular"], ctx)
reg = "\n".join(ctx.ej.registro)
check("actualizar: trae el código, migra, despliega motor y sitio",
      codigo == 0 and all(s in reg for s in ("git pull --ff-only", "npm ci", "d1 migrations apply",
                                              "gcloud run deploy", "wrangler deploy")), reg[-800:])
check("actualizar no vuelve a configurar Access ni apaga la tutoría",
      "acceso.mjs" not in reg and "/query" not in reg)
ctx, salida = contexto_simulado(COMPLETO)
codigo = main(["estado", "--simular"], ctx)
check("estado solo consulta: ningún create, deploy ni PUT",
      not re.search(r" create | deploy |^PUT |^POST .*/(d1/database|r2/buckets)$|remove-iam",
                    "\n".join(ctx.ej.registro), re.M), ctx.ej.registro)
ctx, salida = contexto_simulado(COMPLETO, ["2", "sk-otra-falsa"])
codigo = main(["credenciales", "--simular"], ctx)
reg = "\n".join(ctx.ej.registro)
check("credenciales: guarda la clave nueva y reinicia el motor sin reconstruirlo",
      codigo == 0 and "secrets create zz9999-openai" in reg and "run services update zz9999-motor" in reg
      and "run deploy" not in reg and "sk-otra-falsa" not in reg, reg)

# ---------------------------------------------------------------- 14. acceso.mjs

titulo("14. acceso.mjs ya no cae en la cuenta de IN5162")
fuente = (RAIZ / "web" / "scripts" / "acceso.mjs").read_text(encoding="utf-8")
check("no tiene ninguna cuenta ni dirección fija",
      not re.search(r"[0-9a-f]{32}", fuente) and "in5162-web.workers.dev" not in fuente)
r = subprocess.run(["node", str(RAIZ / "web" / "scripts" / "acceso.mjs"), "--config",
                    "wrangler.no-existe.toml", "profe@ejemplo.cl"], capture_output=True, text=True,
                   encoding="utf-8")
check("con --config de un archivo que no existe, se detiene antes de tocar la red",
      r.returncode != 0 and "No existe" in r.stderr, r.stderr[-300:])

sys.exit(resultado())
