# Despliega el motor en Google Cloud Run y deja todo conectado.
#
#   .\motor\desplegar.ps1 -Proyecto in5162-motor -WebUrl https://in5162.<tu-cuenta>.workers.dev
#   .\motor\desplegar.ps1 -Curso in3401 -Proyecto in3401-motor -WebUrl https://in3401.<tu-cuenta>.workers.dev
#
# -Curso da nombre a todo lo que se crea (servicio, cola, secretos). Por
# defecto in5162, que es como se llama lo que ya está desplegado.
#
# Se puede correr las veces que haga falta: cada paso revisa si ya está hecho.
# Necesita gcloud instalado y con sesión iniciada (gcloud auth login), y un
# proyecto de Google Cloud con facturación activada.
#
# Las claves se leen del .env de la raíz y se guardan en Secret Manager: nunca
# quedan en la línea de comandos, en el historial ni en la imagen del contenedor.

param(
    [Parameter(Mandatory = $true)] [string] $Proyecto,
    [Parameter(Mandatory = $true)] [string] $WebUrl,
    # Región de precio base: la cuota gratuita de Cloud Run aplica sin
    # recargo. El motor no guarda datos (su carpeta de trabajo se borra al
    # terminar), así que estar lejos de Chile no cambia nada.
    [string] $Region = "us-central1",
    [string] $Curso = "in5162",
    [string] $Servicio = "",
    [string] $Cola = ""
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$c = $Curso.ToLower()
if ($c -notmatch '^[a-z][a-z0-9-]{1,20}$') { throw "-Curso: solo minúsculas, números y guiones (ej. in5162)." }
if (-not $Servicio) { $Servicio = "$c-motor" }
if (-not $Cola) { $Cola = "$c-trabajos" }

function Paso($texto) { Write-Host "`n=== $texto" -ForegroundColor Cyan }

# gcloud escribe avisos y progreso en stderr, y PowerShell 5.1 con "Stop" los
# toma como error fatal. Acá se juzga por el código de salida: los avisos se
# muestran en gris y solo se devuelve lo que gcloud escribió en stdout.
function G {
    $antes = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $salida = & gcloud @args 2>&1 } finally { $ErrorActionPreference = $antes }
    $avisos = @($salida | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] })
    $avisos | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    if ($LASTEXITCODE -ne 0) { throw "Falló: gcloud $($args -join ' ')" }
    return @($salida | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] })
}

# Si un recurso ya existe (un describe que termina bien), sin mostrar nada.
function Existe {
    $antes = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & gcloud @args 2>&1 | Out-Null } finally { $ErrorActionPreference = $antes }
    return $LASTEXITCODE -eq 0
}

function LeerEnv($nombre) {
    $linea = Get-Content (Join-Path $raiz ".env") | Where-Object { $_ -match "^\s*$nombre\s*=" } | Select-Object -First 1
    if (-not $linea) { throw "Falta $nombre en el .env de la raíz." }
    return ($linea -replace "^\s*$nombre\s*=\s*", "").Trim().Trim('"').Trim("'")
}

function Secreto($nombre, $valor) {
    # El valor va por un archivo temporal para que no aparezca en la línea de comandos.
    $tmp = New-TemporaryFile
    try {
        [IO.File]::WriteAllText($tmp, $valor)
        if (Existe secrets describe $nombre --project $Proyecto) {
            # Solo una versión nueva si la clave cambió: cada versión activa por
            # sobre las 6 gratuitas se cobra, y volver a desplegar no debe sumar.
            $antes = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            $vigente = (& gcloud secrets versions access latest --secret $nombre --project $Proyecto 2>$null) -join "`n"
            $ErrorActionPreference = $antes
            if ($vigente -ne $valor) {
                G secrets versions add $nombre --data-file=$tmp --project $Proyecto | Out-Null
                # Las anteriores quedan destruidas: no se usan y cuestan.
                foreach ($v in (G secrets versions list $nombre --project $Proyecto --filter "state=ENABLED" --sort-by "~createTime" --format "value(name)" | Select-Object -Skip 1)) {
                    G secrets versions destroy $v --secret $nombre --project $Proyecto --quiet | Out-Null
                }
            }
        } else {
            G secrets create $nombre --data-file=$tmp --replication-policy=automatic --project $Proyecto | Out-Null
        }
    } finally {
        Remove-Item $tmp -Force
    }
}

Paso "Proyecto $Proyecto, región $Region"
G config set project $Proyecto | Out-Null

Paso "Activando las APIs (Cloud Run, Cloud Build, Cloud Tasks, Secret Manager)"
G services enable run.googleapis.com cloudbuild.googleapis.com cloudtasks.googleapis.com `
    secretmanager.googleapis.com artifactregistry.googleapis.com | Out-Null

Paso "Cola de trabajos: de a uno, sin reintentos"
# De a uno, porque dos trabajos a la vez podrían pisarse los archivos del
# semestre. Sin reintentos, porque repetir un envío mandaría correos dos veces.
if (-not (Existe tasks queues describe $Cola --location $Region)) {
    G tasks queues create $Cola --location $Region `
        --max-concurrent-dispatches 1 --max-attempts 1 | Out-Null
}

Paso "Secretos"
Secreto "$c-openai" (LeerEnv "OPENAI_API_KEY")
Secreto "$c-correo-remitente" (LeerEnv "CORREO_REMITENTE")
Secreto "$c-correo-clave" ((LeerEnv "CORREO_APP_PASSWORD") -replace " ", "")
# Los tokens entre el sitio y el motor son los mismos que ya tiene el Worker:
# WEB_TOKEN (el TOKEN_MOTOR del Worker) y TOKEN_WEB, del .env. Si no están, se
# crean la primera vez y hay que cargarlos también en el Worker (ver al final).
$tokens = @{ "$c-token-motor" = "WEB_TOKEN"; "$c-token-web" = "TOKEN_WEB" }
foreach ($t in $tokens.Keys) {
    $linea = Get-Content (Join-Path $raiz ".env") | Where-Object { $_ -match "^\s*$($tokens[$t])\s*=" } | Select-Object -First 1
    if ($linea) {
        Secreto $t (LeerEnv $tokens[$t])
    } elseif (-not (Existe secrets describe $t --project $Proyecto)) {
        $bytes = New-Object byte[] 32
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        Secreto $t ([Convert]::ToBase64String($bytes) -replace '[+/=]', '')
    }
}

# La identidad del servicio necesita leer los secretos y crear tareas en la cola.
# En los proyectos nuevos, además, es la que construye el contenedor, y parte sin
# permisos para eso: de ahí cloudbuild.builds.builder.
$numero = (G projects describe $Proyecto --format "value(projectNumber)") -join ""
$cuenta = "$numero-compute@developer.gserviceaccount.com"
foreach ($rol in "roles/secretmanager.secretAccessor", "roles/cloudtasks.enqueuer", "roles/cloudbuild.builds.builder") {
    G projects add-iam-policy-binding $Proyecto --member "serviceAccount:$cuenta" --role $rol --condition None | Out-Null
}

Paso "Construyendo y desplegando el motor (tarda unos minutos la primera vez)"
# 1 GB: la carpeta de trabajo vive en memoria, y un trabajo de tareas baja
# todas las entregas del semestre (más de 100 MB en un semestre completo).
Push-Location $raiz
try {
    G run deploy $Servicio --source . --region $Region `
        --allow-unauthenticated `
        --memory 1Gi --cpu 1 --timeout 1800 --concurrency 4 --max-instances 1 `
        --set-secrets "OPENAI_API_KEY=$c-openai:latest,CORREO_REMITENTE=$c-correo-remitente:latest,CORREO_APP_PASSWORD=$c-correo-clave:latest,TOKEN_MOTOR=$c-token-motor:latest,TOKEN_WEB=$c-token-web:latest" `
        --set-env-vars "COLA=cloudtasks,GCP_PROYECTO=$Proyecto,GCP_REGION=$Region,GCP_COLA=$Cola,WEB_URL=$WebUrl,CURSO=$($Curso.ToUpper())" | Out-Host
} finally {
    Pop-Location
}

# Cada despliegue guarda una imagen nueva; se conservan las 2 últimas para no
# pasar el medio GB gratuito de Artifact Registry.
$politica = New-TemporaryFile
try {
    '[{"name":"borrar-viejas","action":{"type":"Delete"},"condition":{"tagState":"any","olderThan":"1d"}},' +
    '{"name":"mantener-las-2-ultimas","action":{"type":"Keep"},"mostRecentVersions":{"keepCount":2}}]' |
        Set-Content -Encoding ascii $politica
    G artifacts repositories set-cleanup-policies cloud-run-source-deploy --location $Region `
        --policy $politica --no-dry-run | Out-Null
} finally {
    Remove-Item $politica -Force
}

$url = (G run services describe $Servicio --region $Region --format "value(status.url)") -join ""
# El motor necesita saber su propia dirección para que la cola lo llame.
G run services update $Servicio --region $Region --update-env-vars "MOTOR_URL_PUBLICA=$url" | Out-Null

Paso "Listo"
Write-Host "Motor:        $url"
Write-Host "Salud:        $(Invoke-RestMethod "$url/salud" | ConvertTo-Json -Compress)"
Write-Host ""
Write-Host "Falta conectarlo con el sitio. En web/:"
Write-Host "  npx wrangler secret put TOKEN_MOTOR   (pegar el valor de abajo)"
Write-Host "  npx wrangler secret put TOKEN_WEB"
Write-Host "  y en wrangler.toml: MOTOR_URL = `"$url`""
Write-Host ""
Write-Host "Los valores están en Secret Manager:"
Write-Host "  gcloud secrets versions access latest --secret $c-token-motor"
Write-Host "  gcloud secrets versions access latest --secret $c-token-web"
