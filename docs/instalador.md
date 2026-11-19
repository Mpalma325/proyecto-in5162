# Instalador en la nube (nota para quien mantiene el código)

`instalar.py` monta una copia del sistema para otro curso en las cuentas de Cloudflare y Google Cloud de quien lo corre. Está pensado para Google Cloud Shell, que ya trae `gcloud` con la sesión iniciada, Python 3, Node y git. Esta nota explica cómo está armado; la guía para el profesor está pendiente.

```
python3 instalar.py                  # instalar (o retomar una instalación a medias)
python3 instalar.py actualizar       # git pull, migraciones, motor y sitio
python3 instalar.py estado           # qué hay y qué falta, sin cambiar nada
python3 instalar.py credenciales     # cambiar la clave del correo, de OpenAI o el token de Cloudflare
python3 instalar.py --simular        # cualquiera de los anteriores, mostrando lo que haría
```

## Cómo está armado

| Archivo | Qué hace |
|---|---|
| `instalar.py` | Revisa la versión de Python y llama a `instalador.principal.main`. |
| `instalador/comun.py` | `Ejecutor`: único punto por donde pasan los programas (`gcloud`, `npx wrangler`, `node`, `git`, `npm`) y los pedidos HTTP. `Entorno` lee y escribe el `.env`. `Preguntador` hace las preguntas. |
| `instalador/validar.py` | Formato de cada dato y prueba de cada credencial apenas se escribe. |
| `instalador/cloudflare.py` | Subdominio de workers.dev, D1, R2, `wrangler.<curso>.toml`, migraciones, publicación, Access y subida de la plantilla. |
| `instalador/gcp.py` | Lo mismo que `motor/desplegar.ps1`, en Python. |
| `instalador/plantilla.py` | Arma la plantilla de `semestres/_template` con las marcas `«CURSO»`, `«NOMBRE_CURSO»` y `«PROFESOR»` llenas. |
| `instalador/principal.py` | Las preguntas, el orden de los pasos y los cuatro comandos. |

Como todo pasa por el `Ejecutor`, `--simular` imprime cada comando y cada pedido en vez de hacerlo, y `pruebas/instalador.py` reemplaza `subprocess.run`, `urlopen` y `smtplib.SMTP` por dobles. En simulación las consultas también se imprimen: el instalador supone que nada existe y muestra el camino completo.

El estado vive en el `.env` de la raíz, el mismo que usan la app y el motor. Cada paso anota ahí lo que obtuvo (`CLOUDFLARE_D1_ID`, `WEB_URL`, `MOTOR_URL`, `ACCESO_AUD`, etc.), y antes de crear algo pregunta si ya existe. Si una instalación se corta, se vuelve a correr `python3 instalar.py`: las preguntas ya contestadas se saltan y lo creado no se duplica.

## Qué pregunta y cómo lo comprueba

| Dato | Prueba (sin efectos) |
|---|---|
| Código, nombre del curso y profesor | Formato. Rechaza `in5162`, que ya está montado a mano. |
| Gmail y contraseña de aplicación | SMTP a `smtp.gmail.com:587`, STARTTLS, login y QUIT. No manda nada. |
| Clave de OpenAI | `GET /v1/models`; avisa si no aparece el modelo por defecto. |
| Account ID y token de Cloudflare | `GET /user/tokens/verify` (o el de tokens de cuenta) y un GET por permiso: Workers Scripts, D1, R2, Access Apps y Access Organizations, todos Edit. Detecta R2 o Zero Trust sin activar. |
| Proyecto de Google Cloud y región | `gcloud projects describe` y `gcloud billing projects describe`. Región por defecto `us-central1`. |
| Correos del equipo | Formato. |

Si la prueba no puede concluir (sin red, `gcloud billing` sin permiso), pregunta si seguir igual.

## Qué crea, en orden

1. `npm ci` en `web/` si falta `node_modules`.
2. Cloudflare, por API: subdominio de workers.dev si la cuenta no tiene (wrangler no lo registra sin terminal interactiva), base D1 `<curso>` y bucket R2 `<curso>-semestres`.
3. `web/wrangler.<curso>.toml` y `wrangler d1 migrations apply DB --remote` con esa configuración.
4. `TUTORIA_AUTOMATICA = false` en la tabla `parametros`, con `INSERT OR IGNORE` (si el profesor ya la cambió, se respeta).
5. Google Cloud, como `desplegar.ps1`: APIs, colas `<curso>-trabajos` (de a 1) y `<curso>-simulaciones` (de a 3), los 5 secretos `<curso>-*`, la cuenta de servicio `<curso>-motor` con permiso sobre cada secreto y cada cola, el repositorio `cloud-run-source-deploy` con su política de limpieza y `gcloud run deploy`. En el primer despliegue hace un `services update` para anotar `MOTOR_URL_PUBLICA`.
6. Access, con `node scripts/acceso.mjs --config wrangler.<curso>.toml <correos>`.
7. `wrangler deploy --config wrangler.<curso>.toml --secrets-file <temporal>`. El archivo temporal lleva `TOKEN_MOTOR` y `TOKEN_WEB`, queda con permisos 600 y se borra al terminar.
8. La plantilla de semestre a R2 por la API del sitio (`PUT /api/motor/archivo/_template/...` con `If-None-Match: *`). Solo sube lo que falta, así que `actualizar` no pisa los prompts que el curso ya editó.

Al final muestra, sin correrlos, los comandos para quitarle a la cuenta de servicio por defecto (`<número>-compute@developer.gserviceaccount.com`) los roles `secretmanager.secretAccessor` y `cloudtasks.enqueuer`. No los corre porque no sabe qué más usa esa cuenta en el proyecto.

## Decisiones

**Una configuración de wrangler por curso.** `web/wrangler.toml` sigue siendo la de IN5162. El instalador genera `web/wrangler.<curso>.toml` copiándola y cambiando ocho valores (`name`, `database_name`, `database_id`, `bucket_name`, `CURSO`, `ACCESO_EQUIPO`, `ACCESO_AUD`, `MOTOR_URL`). Git ignora esos archivos, así que `git pull` en Cloud Shell no choca. Si alguien cambia la forma de `wrangler.toml` y una de esas claves deja de aparecer exactamente una vez, el instalador falla y lo dice. Si el archivo ya existe, `database_id`, `ACCESO_EQUIPO` y `ACCESO_AUD` no se pisan: cuando el `.env` no los tiene, se conservan los del archivo y vuelven al `.env`; cuando dice otra cosa, el instalador se detiene y nombra el valor. El cron, `migrations_dir` y `ACCESO = "cloudflare"` se heredan.

**API de Cloudflare para los recursos y wrangler para lo demás.** Con la API se puede preguntar si algo existe sin crearlo y leer los errores por código. Algo cuenta como ausente solo si una respuesta exitosa no lo trae, o con el «no existe» propio del recurso (404 o 10006 en R2, 10007 en el subdominio). Un 5xx o un permiso que falta detiene el instalador, para que no cree un duplicado; en `estado` se muestra como «?». Wrangler queda para las migraciones y la publicación, que es donde aporta. Nunca se usa `wrangler login`: todo va con `CLOUDFLARE_API_TOKEN`.

**`acceso.mjs` ya no cae en IN5162.** Antes, sin `WEB_URL` ni cuenta en el `.env`, usaba la dirección y el account ID de IN5162. Ahora exige `WEB_URL`, toma la cuenta de `CLOUDFLARE_ACCOUNT_ID` o, si el token alcanza una sola cuenta, de `GET /accounts`, y acepta `--config`. El `.env` de IN5162 no tiene `CLOUDFLARE_ACCOUNT_ID`; conviene agregarlo antes de volver a correr `acceso.mjs`.

**Marcas en la plantilla.** `semestres/_template` ya no nombra a IN5162. Los prompts y correos llevan `«CURSO»`, `«NOMBRE_CURSO»` y `«PROFESOR»`. El repositorio queda con las marcas, y las llena una sola función (`llenar_marcas`, en `modulos/semestre/gestion.py`) en los tres lugares donde se copia la plantilla: `instalar.py` al subirla al sitio, `semestre.crear()` en la app del PC y `modulos.web.subir --archivos`. Si falta un dato, no se copia nada. En los archivos con HTML (los correos y prompts de `tests_semanales`) el valor va escapado, así que un `&` en el nombre del curso se ve bien en el correo. Las llaves `{...}` de los correos son de `str.format`: un nombre con llaves se rechaza al preguntarlo y al llenar la plantilla. El ejemplo de alumnos quedó en `semestres/_template/alumnos.example.csv` con las columnas que lee el código (`Nombre,Correo`).

Para IN5162 cambian dos cosas. Crear un semestre desde la app del PC pide ahora `NOMBRE_CURSO` y `PROFESOR` en el `.env`. Y `subir --archivos --forzar` reemplazaría la plantilla que IN5162 tiene en R2, con su texto de siempre, por la neutra llena con esos datos; sin `--forzar` no la toca.

**`TUTORIA_AUTOMATICA`.** Si el parámetro no existe, la tutoría de las 18:00 corre como siempre, así IN5162 no cambia. Los cursos nuevos parten con `false`. Se prende y apaga en Datos y Configuración › Parámetros. Lo leen `programado()` en `web/src/index.ts` y la lista de parámetros del motor y de `modulos/config.py`, para que la prueba de coherencia entre ambos siga pasando.

**Cambiar credenciales.** La página de Parámetros decía que bastaba editar el `.env`, pero el motor lee los secretos de Secret Manager. `python3 instalar.py credenciales` prueba la clave nueva, crea una versión del secreto, destruye la anterior y saca una revisión nueva del motor sin reconstruirlo.

**`desplegar.ps1` sigue igual.** IN5162 lo puede seguir usando. La sección 7 de `pruebas/instalador.py` compara ambos: variables de entorno, secretos, colas y recursos de Cloud Run.

## Migraciones de la base

`web/schema.sql` pasó a ser `web/migrations/0001_inicial.sql` y `wrangler.toml` declara `migrations_dir = "migrations"`. Wrangler anota cada archivo aplicado en la tabla `d1_migrations` de la base.

Para cambiar la base se agrega `web/migrations/0002_<que>.sql`; los archivos ya publicados no se editan. `python3 instalar.py actualizar` aplica lo pendiente en cada curso. En local: `npm run db:local`.

IN5162 se creó con `schema.sql`, antes de las migraciones, y su base no tiene `d1_migrations`. Hay que marcarla una sola vez como que ya tiene la 0001. Antes, comprobar que `ediciones` tiene la columna `detalle` (la 0001 la incluye):

```
cd web
npx wrangler d1 execute in5162 --remote --command "PRAGMA table_info(ediciones)"
npx wrangler d1 execute in5162 --remote --command "CREATE TABLE IF NOT EXISTS d1_migrations(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL); INSERT OR IGNORE INTO d1_migrations (name) VALUES ('0001_inicial.sql');"
npx wrangler d1 migrations list in5162 --remote
```

El último comando debe responder que no hay migraciones pendientes. Si se olvida este paso, aplicar la 0001 sobre IN5162 tampoco rompe nada: todas sus sentencias son `CREATE ... IF NOT EXISTS`. La tabla `d1_migrations` es la que crea wrangler 4.136; se probó contra una base local construida con el `schema.sql` antiguo.

## Pruebas

`pruebas/instalador.py` (en `pruebas/todas.py`) corre sin red ni nube y con nombres inventados. Cubre la validación de cada credencial, que volver a correr no cree lo que existe, el recorrido completo con `--simular`, `actualizar`, `estado`, `credenciales`, la configuración por curso, la plantilla y la coherencia con `desplegar.ps1`. `web/scripts/probar-programado.mjs`, que corre desde `pruebas/web.py`, prueba el interruptor de la tutoría.

## Lo que no se probó contra servicios reales

Nada de esto se corrió contra cuentas reales. Pendiente de una primera instalación de prueba:

- Que Cloud Shell traiga Node 22 o más (wrangler 4.136 lo exige). Si no, el instalador sugiere `nvm install 22`.
- Los GET que prueban los permisos del token de Cloudflare, en especial con tokens de cuenta, y el `GET /accounts` de respaldo en `acceso.mjs`.
- El registro del subdominio de workers.dev por API con un token limitado a esos permisos.
- `gcloud billing projects describe` en un proyecto recién creado, sin el rol de facturación.
- Una organización con *Domain Restricted Sharing* impide `--allow-unauthenticated`. Las cuentas universitarias de Google Workspace pueden tenerla.
- La espera de 15 segundos después de crear la cuenta de servicio, y los permisos por secreto y por cola hechos antes del primer `run deploy`.
- El inicio de sesión SMTP con una contraseña de aplicación real, y el `PUT` de la plantilla contra un sitio recién publicado (se reintenta seis veces cada 20 segundos mientras Access y el Worker se propagan).
- La política de limpieza de Artifact Registry compartida por todos los servicios del proyecto.
