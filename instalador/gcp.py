"""
Google Cloud: el motor en Cloud Run. Es motor/desplegar.ps1 en Python, para
correr en Cloud Shell sin PowerShell. desplegar.ps1 sigue siendo lo que usa
IN5162; si cambia uno, hay que cambiar el otro (pruebas/instalador.py compara
los nombres de recursos, colas y variables de ambos).

Cada paso revisa si ya está hecho, así que se puede correr de nuevo.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from .cloudflare import archivo_temporal
from .comun import RAIZ, Ejecutor, Falla, paso

APIS = ("run.googleapis.com", "cloudbuild.googleapis.com", "cloudtasks.googleapis.com",
        "secretmanager.googleapis.com", "artifactregistry.googleapis.com", "iam.googleapis.com")
REPOSITORIO = "cloud-run-source-deploy"
# Se conservan las 2 últimas imágenes, para no pasar el medio GB gratuito.
POLITICA_LIMPIEZA = [
    {"name": "borrar-viejas", "action": {"type": "Delete"},
     "condition": {"tagState": "any", "olderThan": "1d"}},
    {"name": "mantener-las-2-ultimas", "action": {"type": "Keep"},
     "mostRecentVersions": {"keepCount": 2}},
]
# Secreto -> variable del .env de donde sale su valor.
SECRETOS = {
    "openai": "OPENAI_API_KEY",
    "correo-remitente": "CORREO_REMITENTE",
    "correo-clave": "CORREO_APP_PASSWORD",
    "token-motor": "WEB_TOKEN",
    "token-web": "TOKEN_WEB",
}
# Variable del motor -> secreto.
VARIABLES_SECRETAS = {
    "OPENAI_API_KEY": "openai",
    "CORREO_REMITENTE": "correo-remitente",
    "CORREO_APP_PASSWORD": "correo-clave",
    "TOKEN_MOTOR": "token-motor",
    "TOKEN_WEB": "token-web",
}


@dataclass
class Motor:
    curso: str      # el código, en cualquier caja: IN3401
    proyecto: str
    region: str
    web_url: str

    @property
    def c(self) -> str:
        return self.curso.lower()

    @property
    def servicio(self) -> str:
        return f"{self.c}-motor"

    @property
    def cola(self) -> str:
        return f"{self.c}-trabajos"

    @property
    def cola_simulaciones(self) -> str:
        return f"{self.c}-simulaciones"

    @property
    def cuenta(self) -> str:
        return f"{self.c}-motor@{self.proyecto}.iam.gserviceaccount.com"

    def secreto(self, corto: str) -> str:
        return f"{self.c}-{corto}"

    def variables(self, url_previa: str = "") -> str:
        v = (f"COLA=cloudtasks,GCP_PROYECTO={self.proyecto},GCP_REGION={self.region},"
             f"GCP_COLA={self.cola},GCP_COLA_SIMULACIONES={self.cola_simulaciones},"
             f"WEB_URL={self.web_url},CURSO={self.curso.upper()}")
        return v + (f",MOTOR_URL_PUBLICA={url_previa}" if url_previa else "")

    def secretos_para_run(self) -> str:
        return ",".join(f"{var}={self.secreto(s)}:latest" for var, s in VARIABLES_SECRETAS.items())


def _g(*args: str) -> list[str]:
    return ["gcloud", *args]


def guardar_secreto(ej: Ejecutor, proyecto: str, nombre: str, valor: str) -> str:
    """Crea el secreto, o le agrega una versión solo si el valor cambió.

    El valor va por la entrada estándar (--data-file=-): nunca queda en la
    línea de comandos ni en el registro. Cada versión activa por sobre las 6
    gratuitas se cobra, así que las anteriores se destruyen.
    Devuelve "creado", "actualizado" o "igual".
    """
    if not ej.existe(_g("secrets", "describe", nombre, "--project", proyecto)):
        ej.correr(_g("secrets", "create", nombre, "--data-file=-", "--replication-policy=automatic",
                     "--project", proyecto), entrada=valor)
        return "creado"
    r = ej.correr(_g("secrets", "versions", "access", "latest", "--secret", nombre,
                     "--project", proyecto), lectura=True, puede_fallar=True)
    if r.ok and r.salida.rstrip("\n") == valor.rstrip("\n"):
        return "igual"
    ej.correr(_g("secrets", "versions", "add", nombre, "--data-file=-", "--project", proyecto),
              entrada=valor)
    r = ej.correr(_g("secrets", "versions", "list", nombre, "--project", proyecto,
                     "--filter=state=ENABLED", "--sort-by=~createTime", "--format=value(name)"),
                  lectura=True, puede_fallar=True)
    for version in [v.strip() for v in r.salida.splitlines() if v.strip()][1:]:
        ej.correr(_g("secrets", "versions", "destroy", version, "--secret", nombre,
                     "--project", proyecto, "--quiet"))
    return "actualizado"


def numero_proyecto(ej: Ejecutor, proyecto: str) -> str:
    r = ej.correr(_g("projects", "describe", proyecto, "--format=value(projectNumber)"),
                  lectura=True, simulado="<numero-del-proyecto>")
    numero = r.salida.strip()
    if not numero:
        raise Falla(f"No pude leer el número del proyecto {proyecto}.")
    return numero


def comandos_cuenta_por_defecto(proyecto: str, numero: str) -> list[str]:
    cuenta = f"{numero}-compute@developer.gserviceaccount.com"
    return [f"gcloud projects remove-iam-policy-binding {proyecto} --member "
            f"serviceAccount:{cuenta} --role {rol} --condition None"
            for rol in ("roles/secretmanager.secretAccessor", "roles/cloudtasks.enqueuer")]


def explicar_cuenta_por_defecto(proyecto: str, numero: str, escribir=print) -> None:
    """Se muestra, no se corre: otro servicio del proyecto podría depender de esos roles."""
    escribir("\nEl motor corre con su propia cuenta de servicio, que solo lee sus 5 secretos y")
    escribir("crea tareas en sus 2 colas. La cuenta por defecto del proyecto")
    escribir(f"({numero}-compute@developer.gserviceaccount.com) no los necesita. Si nada más")
    escribir("en este proyecto la usa para leer secretos o crear tareas, quítale esos roles:")
    for c in comandos_cuenta_por_defecto(proyecto, numero):
        escribir(f"  {c}")
    escribir("No los quito yo porque no sé qué más hay en el proyecto. cloudbuild.builds.builder")
    escribir("se queda: con ella se construye el contenedor. Si la cuenta por defecto tiene")
    escribir("roles/editor, quitarle cloudtasks.enqueuer no cambia nada; lo que importa es")
    escribir("quitarle secretAccessor y, más adelante, editor.")


def desplegar_motor(ej: Ejecutor, m: Motor, valores: dict[str, str], escribir=print,
                    esperar=time.sleep) -> str:
    """Todo lo de desplegar.ps1. Devuelve la dirección del motor."""
    p, r = m.proyecto, m.region

    paso(f"Google Cloud: activando las APIs en {p}", escribir)
    ej.correr(_g("services", "enable", *APIS, "--project", p), mostrar=True)

    paso("Colas de trabajos", escribir)
    # De a uno y sin reintentos: dos trabajos a la vez se pisarían los archivos
    # del semestre, y repetir un envío mandaría los correos dos veces. Las
    # simulaciones no mandan correos ni cambian notas: pueden ir de a tres.
    for cola, simultaneos in ((m.cola, "1"), (m.cola_simulaciones, "3")):
        if ej.existe(_g("tasks", "queues", "describe", cola, "--location", r, "--project", p)):
            escribir(f"  ✓ {cola} ya existe")
        else:
            ej.correr(_g("tasks", "queues", "create", cola, "--location", r, "--project", p,
                         f"--max-concurrent-dispatches={simultaneos}", "--max-attempts=1"))
            escribir(f"  + {cola}")

    paso("Secretos (Secret Manager)", escribir)
    for corto, clave in SECRETOS.items():
        valor = valores.get(clave, "")
        if not valor:
            raise Falla(f"Falta {clave} en el .env.")
        if clave == "CORREO_APP_PASSWORD":
            valor = valor.replace(" ", "")
        estado = guardar_secreto(ej, p, m.secreto(corto), valor)
        escribir(f"  {m.secreto(corto)}: {estado}")

    paso("Permisos", escribir)
    numero = numero_proyecto(ej, p)
    # En los proyectos nuevos la cuenta por defecto es la que construye el
    # contenedor, y parte sin permisos para eso.
    ej.correr(_g("projects", "add-iam-policy-binding", p, "--member",
                 f"serviceAccount:{numero}-compute@developer.gserviceaccount.com",
                 "--role", "roles/cloudbuild.builds.builder", "--condition=None", "--quiet"))
    # El motor corre con una cuenta propia, con permisos solo sobre lo suyo: con
    # la cuenta por defecto, una falla en el motor alcanzaría los secretos de
    # otro curso en el mismo proyecto. No necesita run.invoker: la cola llama a
    # /ejecutar con un token propio, sin OIDC.
    if ej.existe(_g("iam", "service-accounts", "describe", m.cuenta, "--project", p)):
        escribir(f"  ✓ cuenta {m.cuenta} ya existe")
    else:
        ej.correr(_g("iam", "service-accounts", "create", m.servicio, "--project", p,
                     f"--display-name=Motor de {m.curso.upper()}"))
        escribir(f"  + cuenta {m.cuenta}")
        if not ej.simular:
            # Una cuenta recién creada tarda unos segundos en verse desde IAM.
            esperar(15)
    for corto in SECRETOS:
        ej.correr(_g("secrets", "add-iam-policy-binding", m.secreto(corto), "--project", p,
                     "--member", f"serviceAccount:{m.cuenta}",
                     "--role", "roles/secretmanager.secretAccessor"))
    for cola in (m.cola, m.cola_simulaciones):
        ej.correr(_g("tasks", "queues", "add-iam-policy-binding", cola, "--location", r,
                     "--project", p, "--member", f"serviceAccount:{m.cuenta}",
                     "--role", "roles/cloudtasks.enqueuer"))

    paso("Artifact Registry (donde quedan las imágenes del motor)", escribir)
    if ej.existe(_g("artifacts", "repositories", "describe", REPOSITORIO, "--location", r,
                    "--project", p)):
        escribir(f"  ✓ {REPOSITORIO} ya existe")
    else:
        ej.correr(_g("artifacts", "repositories", "create", REPOSITORIO,
                     "--repository-format=docker", "--location", r, "--project", p,
                     "--description=Imágenes de Cloud Run"))
        escribir(f"  + {REPOSITORIO}")
    with archivo_temporal(ej, json.dumps(POLITICA_LIMPIEZA)) as politica:
        ej.correr(_g("artifacts", "repositories", "set-cleanup-policies", REPOSITORIO,
                     "--location", r, "--project", p, f"--policy={politica}", "--no-dry-run",
                     "--quiet"))

    paso("Construyendo y desplegando el motor (la primera vez tarda unos minutos)", escribir)
    # La dirección propia va en el mismo deploy si el servicio ya existe:
    # --set-env-vars borra las demás variables, y una revisión sin
    # MOTOR_URL_PUBLICA no puede encolar trabajos.
    previa = ej.correr(_g("run", "services", "describe", m.servicio, "--region", r, "--project", p,
                          "--format=value(status.url)"), lectura=True, puede_fallar=True)
    url_previa = previa.salida.strip() if previa.ok else ""
    # 1 GB: la carpeta de trabajo vive en memoria, y un trabajo de tareas baja
    # todas las entregas del semestre.
    ej.correr(_g("run", "deploy", m.servicio, "--source", ".", "--region", r, "--project", p,
                 "--quiet", "--allow-unauthenticated", f"--service-account={m.cuenta}",
                 "--memory=1Gi", "--cpu=1", "--timeout=1800", "--concurrency=8",
                 "--max-instances=1", f"--set-secrets={m.secretos_para_run()}",
                 f"--set-env-vars={m.variables(url_previa)}"), cwd=RAIZ, mostrar=True)
    url = ej.correr(_g("run", "services", "describe", m.servicio, "--region", r, "--project", p,
                       "--format=value(status.url)"), lectura=True,
                    simulado=f"https://{m.servicio}-<id>.a.run.app").salida.strip()
    if not url:
        raise Falla("Cloud Run no devolvió la dirección del motor.")
    if url != url_previa:
        # Primer despliegue: la dirección recién se conoce ahora.
        ej.correr(_g("run", "services", "update", m.servicio, "--region", r, "--project", p,
                     "--quiet", f"--update-env-vars=MOTOR_URL_PUBLICA={url}"))
    return url


def reiniciar_motor(ej: Ejecutor, m: Motor) -> None:
    """Una revisión nueva, sin reconstruir: así el motor lee los secretos recién cambiados
    (Cloud Run resuelve `:latest` al arrancar cada instancia)."""
    ej.correr(_g("run", "services", "update", m.servicio, "--region", m.region, "--project",
                 m.proyecto, "--quiet",
                 f"--update-env-vars=CREDENCIALES_CAMBIADAS={int(time.time())}"), mostrar=True)
