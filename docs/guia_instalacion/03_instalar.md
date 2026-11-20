# 3. Instalar

Necesitas la hoja de datos completa de la página 2. Usa la misma ventana del navegador donde está abierta la cuenta del curso: Cloud Shell trabaja con la cuenta de Google que tenga la sesión abierta, y el proyecto tiene que ser de esa cuenta.

## 3.1 Abrir Cloud Shell con el sistema

Cloud Shell es una terminal de Google que se abre en el navegador y ya trae los programas que usa el instalador. Hay dos formas de abrirla con el sistema descargado; usa una.

### Opción A: el botón

1. Abre este enlace: [Abrir en Cloud Shell](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/Mpalma325/proyecto-in5162)

   La dirección completa es `https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/Mpalma325/proyecto-in5162`.
2. Cloud Shell pregunta si confías en el repositorio. Marca la casilla «Confiar en el repositorio» (Trust repo) y haz clic en «Confirmar» (Confirm). Sin esa casilla, Cloud Shell abre en modo temporal (ephemeral mode) y borra la carpeta al cerrar la sesión, y con ella todo lo que guarda el instalador. Si después ves un aviso de que la sesión está en modo temporal, cierra la pestaña y vuelve a abrir el enlace marcando la casilla.
3. Cloud Shell descarga el sistema en la carpeta `~/cloudshell_open/proyecto-in5162` y abre un editor con una terminal abajo, ya ubicada en esa carpeta. Si no ves la terminal, ábrela desde el menú «Terminal», «Nueva terminal» (New Terminal), y escribe:

   ```
   cd ~/cloudshell_open/proyecto-in5162
   ```

### Opción B: a mano

1. Entra a `shell.cloud.google.com`. También puedes abrir `console.cloud.google.com` y hacer clic en el ícono «Activar Cloud Shell» (un recuadro con `>_`, arriba a la derecha).
2. En la terminal, escribe estas dos líneas, presionando Enter después de cada una:

   ```
   git clone https://github.com/Mpalma325/proyecto-in5162
   cd proyecto-in5162
   ```

   El sistema queda en la carpeta `~/proyecto-in5162`.

### Comprobar que estás en la carpeta

Escribe `ls instalar.py` y presiona Enter. La terminal debe responder `instalar.py`. Si dice `No such file or directory`, no estás en la carpeta del sistema: repite el `cd` de la opción que usaste.

### Cómo se usa la terminal

- Para pegar, usa Ctrl+V o clic derecho y «Pegar» (Paste).
- Cada comando se ejecuta al presionar Enter.
- Cuando el instalador pide una clave, lo que escribes o pegas no aparece en pantalla. Es lo normal: pega una sola vez y presiona Enter.
- Ctrl+C detiene el instalador. Se puede volver a correr y retoma donde quedó.
- Deja la pestaña abierta mientras dura la instalación. Si Cloud Shell se desconecta, vuelve a abrirlo, entra a la carpeta con `cd` y corre el mismo comando: el instalador retoma.

## 3.2 Revisar la versión de Node

**No verificado.** El instalador necesita Node.js 22 o más nuevo, y no se ha comprobado qué versión trae Cloud Shell. Revísalo antes de empezar:

```
node --version
```

Si la respuesta empieza con `v22`, `v23` o un número mayor, sigue a 3.3. Si empieza con un número menor (por ejemplo `v20.18.0`), escribe:

```
nvm install 22
nvm use 22
```

y comprueba con `node --version` que ahora diga `v22` o más. Si otro día el instalador avisa que Node es muy antiguo, repite estos dos comandos.

## 3.3 Correr el instalador

Si quieres ver antes todo lo que va a hacer, sin crear ni cambiar nada, corre `python3 instalar.py --simular`. Hace las mismas preguntas, no comprueba las claves, no guarda las respuestas y muestra cada comando en vez de ejecutarlo.

Para instalar, escribe:

```
python3 instalar.py
```

Lo primero que muestra es:

```
Instalación del sistema de tests y tareas para un curso nuevo.
Si algo falla, corrígelo y corre de nuevo: retoma donde quedó.

=== Revisando los programas
  ✓ Python 3.12.3, Node v22.12.0, npx y gcloud
```

Los números de versión pueden ser otros. Cada etapa empieza con una línea `===`. Las líneas con `✓` indican que algo quedó bien, las que tienen `+` indican algo creado y las que tienen `✗` indican un problema; la página 6 explica cada mensaje de error.

## 3.4 Las preguntas

El instalador pregunta en este orden y comprueba cada dato apenas lo escribes. Cada respuesta queda guardada en el archivo `.env` de la carpeta del sistema: si vuelves a correr el instalador, no pregunta de nuevo lo que ya está bien, solo lo muestra (las claves aparecen como `(ya guardada)`).

Cuando una pregunta trae un valor entre corchetes, como `[us-central1]`, presionar Enter sin escribir nada acepta ese valor.

### El curso

```
=== El curso
Código del curso, como lo verán los alumnos (ej. IN3401):
```

Escribe el código, por ejemplo `ABC123`. Puede ir en minúsculas: el instalador lo pasa a mayúsculas.

```
Nombre del curso (ej. Economía de la Empresa):
```

Escribe `Taller de Datos`.

```
Nombre del profesor o profesora a cargo:
```

Escribe el nombre como debe aparecer en la firma de los correos.

### El correo del curso

```
=== El correo del curso (manda las preguntas y recibe las respuestas)
Correo del curso (Gmail o Google Workspace):
Contraseña de aplicación de ese correo (las 16 letras; los espacios no importan):
```

Escribe el correo y pega la contraseña de aplicación. El instalador inicia sesión en los dos servidores de Gmail que usa el sistema, el de envío (SMTP) y el de lectura del buzón (IMAP), y sale sin mandar ni leer ningún correo. Si funciona, responde:

```
  ✓ curso.abc123@gmail.com inició sesión en smtp.gmail.com (envío) y en imap.gmail.com (lectura).
```

Si Gmail rechaza los datos, el instalador dice en cuál de los dos servidores falló y pregunta otra vez los dos datos. El correo aparece entre corchetes (Enter lo deja igual) y la contraseña dice `(Enter para dejarla igual)`. La página 6, «El correo», dice qué hacer con cada mensaje.

### OpenAI

```
=== OpenAI (corrige las respuestas)
Clave de la API de OpenAI (sk-...):
```

Pega la clave. El instalador le pide al modelo una respuesta de 1 token, que gasta una fracción de centavo del saldo. Así comprueba que la clave sirve y que la cuenta tiene saldo. Si funciona, responde:

```
  ✓ La clave de OpenAI sirve y la cuenta tiene saldo (una respuesta de 1 token de gpt-5.4-mini).
```

Si responde `✗ La clave sirve, pero la cuenta de OpenAI no tiene saldo (insufficient_quota)...`, carga saldo como dice la página 2 (2.2), vuelve a la terminal y presiona Enter: el instalador deja la misma clave y la prueba de nuevo. Un pago recién hecho puede tardar unos minutos en verse; si el mensaje se repite, espera y presiona Enter otra vez. Los demás mensajes de OpenAI están en la página 6.

También puede responder `✓ La clave sirve, pero la cuenta no tiene el modelo gpt-5.4-mini, que es el que se usa por defecto, así que no pude comprobar el saldo...`. La instalación sigue igual. En la página 4 se elige otro modelo; revisa el saldo en `platform.openai.com/settings/organization/billing`.

### Cloudflare

```
=== Cloudflare (el sitio, la base de datos y quién entra)
Account ID de Cloudflare:
Token de la API de Cloudflare:
```

Pega el Account ID y luego el token. El instalador revisa el token, la cuenta y los cinco permisos, y que R2 y Zero Trust estén activados. Si todo está bien, responde:

```
  ✓ El token de Cloudflare sirve y tiene los permisos que hacen falta.
```

Si responde que falta activar R2 o Zero Trust, actívalo en el navegador (página 2), vuelve a la terminal y presiona Enter dos veces: el instalador deja los mismos datos y los revisa de nuevo. Si faltan permisos, agrégalos al token como dice la página 6 y haz lo mismo.

### Google Cloud

```
=== Google Cloud (el motor)
  ✓ gcloud con la sesión de curso.abc123@gmail.com
```

Esta línea dice con qué cuenta de Google trabaja Cloud Shell. Tiene que ser la cuenta dueña del proyecto. Si muestra otra cuenta, presiona Ctrl+C, cierra Cloud Shell y vuelve a abrirlo desde una ventana privada donde solo esté abierta la cuenta del curso.

Al llegar aquí, Cloud Shell puede abrir una ventana «Autorizar Cloud Shell» (Authorize Cloud Shell). Haz clic en «Autorizar».

```
Id del proyecto de Google Cloud:
```

Escribe el ID del proyecto, por ejemplo `abc123-motor`. El instalador revisa que exista y que tenga la facturación activada:

```
  ✓ El proyecto abc123-motor existe y tiene la facturación activada.
```

```
Región de Google Cloud (us-central1 entra en la capa gratuita) [us-central1]:
```

Presiona Enter.

### Quién puede entrar al sitio

```
=== Quién puede entrar al sitio
  Entran con un código que les llega al correo. Todos tienen el mismo acceso,
  que incluye mandar correos a los alumnos.
Correos del equipo docente, separados por coma:
```

Escribe los correos separados por coma, incluido el tuyo: `profesor@ejemplo.cl, ayudante@ejemplo.cl`. Para cambiar esta lista más adelante, sigue la página 5.

## 3.5 Lo que hace después

Con las respuestas completas, el instalador sigue solo. Muestra bastante texto de los programas que usa (`npm`, `wrangler`, `gcloud`); no hace falta leerlo mientras no aparezca una línea con `✗`. Estas son las etapas, en orden.

### Dependencias del sitio

```
=== Instalando las dependencias del sitio (npm ci)
```

Descarga lo que necesita el sitio para publicarse. Solo ocurre la primera vez.

### Dirección del sitio, base de datos y archivos

```
=== Cloudflare: dirección del sitio, base de datos y archivos
```

Si la cuenta de Cloudflare todavía no tiene un subdominio de workers.dev, el instalador hace aquí su única pregunta extra:

```
  La cuenta todavía no tiene un subdominio de workers.dev. Es parte de la
  dirección del sitio: https://abc123.<subdominio>.workers.dev
Subdominio (minúsculas, números y guiones) [abc123-cursos]:
```

Presiona Enter para aceptar `abc123-cursos` o escribe otro nombre. El subdominio vale para toda la cuenta de Cloudflare y no se puede repetir entre cuentas: si otra cuenta ya lo usa, Cloudflare lo rechaza y el instalador pide otro. Luego muestra:

```
  ✓ el sitio quedará en https://abc123.abc123-cursos.workers.dev
  + base D1 abc123
  + bucket abc123-semestres
```

**No verificado.** El registro del subdominio con un token limitado a los cinco permisos de la página 2 no se ha probado. Si el instalador responde `✗ Cloudflare no lo aceptó (...). Prueba con otro.` con todos los nombres que pruebas, presiona Ctrl+C y créalo desde el panel: en `dash.cloudflare.com`, abre «Workers & Pages» y, en la columna derecha, la opción para elegir o cambiar el subdominio («Subdomain»). Después corre de nuevo `python3 instalar.py`: encuentra el subdominio y no vuelve a preguntar.

### Base de datos

```
=== Base de datos: migraciones pendientes
```

Crea las tablas del sitio. Termina con:

```
  ✓ tutoría automática apagada (se prende en Configuración › La IA › Parámetros)
```

La tutoría automática responde por correo, todos los días a las 18:00, las dudas de los alumnos sobre su corrección. Queda apagada para que el sistema no mande correos reales antes de que lo pruebes. En el sitio, el interruptor está en Configuración › La IA › Parámetros (la página 4 lo explica).

### El motor en Google Cloud

```
=== Google Cloud: activando las APIs en abc123-motor
=== Colas de trabajos
=== Secretos (Secret Manager)
=== Permisos
=== Artifact Registry (donde quedan las imágenes del motor)
=== Construyendo y desplegando el motor (la primera vez tarda unos minutos)
```

Activa los servicios de Google Cloud que usa el motor, crea las dos colas (`abc123-trabajos` y `abc123-simulaciones`), guarda las cinco claves en Secret Manager, crea la cuenta de servicio `abc123-motor` con permiso solo sobre esas claves y esas colas, y construye y publica el motor. La construcción es la etapa más larga. Termina con:

```
  ✓ motor en https://abc123-motor-xxxxxxxxxx-uc.a.run.app
```

**No verificado.** Si el proyecto pertenece a una organización (por ejemplo, la de una universidad) con la política *Domain Restricted Sharing*, Google no deja publicar el motor con acceso abierto, y el sitio no puede llamarlo. Se detecta así: durante esta etapa aparece un aviso o error de `gcloud` que menciona la política IAM o `allUsers`, o al final `python3 instalar.py estado` muestra `✗ motor responde` (sección 3.7). Si pasa, sigue la página 6, «El motor no responde»: ahí está cómo confirmarlo y cómo mover el motor a un proyecto «Sin organización» creado con una cuenta @gmail.com.

### Access

```
=== Cloudflare Access: quién puede entrar
Equipo de Access: abc123-curso.cloudflareaccess.com
Agregado el inicio de sesión con código al correo.
Creada: ABC123 sitio (abc123.abc123-cursos.workers.dev)
Creada: ABC123 motor (abc123.abc123-cursos.workers.dev/api/motor)
Creada: ABC123 subir (abc123.abc123-cursos.workers.dev/api/subir)

Pueden entrar: profesor@ejemplo.cl, ayudante@ejemplo.cl
wrangler.abc123.toml actualizado. Falta publicar el sitio.
```

Crea en Cloudflare la aplicación que cierra el sitio, con la lista de correos. Las aplicaciones «motor» y «subir» son excepciones para que el motor pueda hablar con el sitio; esas rutas exigen su propio token.

### Publicar el sitio y subir la plantilla

```
=== Publicando el sitio
=== Plantilla de semestre, con el nombre del curso
```

Publica el sitio y sube la plantilla con la que se crea cada semestre: los prompts y correos, con el código, el nombre del curso y el del profesor ya escritos. Un sitio recién creado puede tardar unos minutos en responder. Mientras tanto aparece, hasta seis veces:

```
  El sitio todavía no responde (...); reintento en 20 s...
```

Es normal. Termina con:

```
  ✓ 17 archivos nuevos, 0 ya estaban (esos no se tocan)
```

## 3.6 El final

Una instalación completa termina así (con tus datos):

```
=== Listo
Sitio:   https://abc123.abc123-cursos.workers.dev
Motor:   https://abc123-motor-xxxxxxxxxx-uc.a.run.app
Entran:  profesor@ejemplo.cl, ayudante@ejemplo.cl
```

Guarda la dirección del sitio en tus marcadores y compártela con el equipo. La del motor la usa el sitio; solo se abre para diagnosticar un problema (página 6).

Después viene un párrafo que empieza con `El motor corre con su propia cuenta de servicio` y muestra dos comandos `gcloud projects remove-iam-policy-binding ...`. Es un paso de seguridad opcional: le quita a la cuenta de servicio por defecto del proyecto permisos que el motor no usa. El sistema funciona sin hacerlo. Si el proyecto es solo para este curso, puedes copiar cada uno de los dos comandos, pegarlo en la terminal y presionar Enter. Si un comando responde con un error de que ese vínculo no existe («not found»), esa cuenta no tenía ese permiso y no hay nada que quitar.

Al final aparece «Lo que sigue», con seis puntos. Son los pasos de la página 4. El último, la alerta de presupuesto, ya quedó hecho en la página 2.

## 3.7 Comprobar la instalación

En la terminal, escribe:

```
python3 instalar.py estado
```

Solo consulta; no crea ni cambia nada. Con la instalación completa responde:

```
=== Estado de la instalación
  ✓ .env completo
  ✓ token de Cloudflare
  ✓ base D1  (abc123)
  ✓ bucket R2  (abc123-semestres)
  ✓ sitio publicado  (abc123)
  ✓ Access configurado  (abc123.abc123-cursos.workers.dev)
  ✓ migraciones de la base al día
  ✓ proyecto de Google Cloud
  ✓ cola abc123-trabajos
  ✓ cola abc123-simulaciones
  ✓ cuenta del motor  (abc123-motor@abc123-motor.iam.gserviceaccount.com)
  ✓ secreto abc123-openai
  ✓ secreto abc123-correo-remitente
  ✓ secreto abc123-correo-clave
  ✓ secreto abc123-token-motor
  ✓ secreto abc123-token-web
  ✓ motor desplegado  (https://abc123-motor-xxxxxxxxxx-uc.a.run.app)
  ✓ motor responde  (HTTP 200)
  ✓ plantilla de semestre en el sitio  (HTTP 200, 17 archivos)

Todo en su lugar.
```

Las dos últimas líneas muestran el código HTTP con que respondieron el motor y el sitio. Si alguna falla, la línea muestra el código y el comienzo del texto de la respuesta, por ejemplo `✗ motor responde  (HTTP 403: 403 Forbidden Error: Forbidden Your client does not have permission to get URL /salud from this serv…)`; la página 6, «El motor no responde», dice qué hacer.

Si alguna línea tiene `✗`, corre de nuevo `python3 instalar.py`: crea lo que falta sin tocar lo que ya existe. Una línea con `?` significa que Cloudflare no respondió al consultar; espera unos minutos y vuelve a consultar.

## 3.8 Entrar al sitio

1. Abre la dirección del sitio (`https://abc123.abc123-cursos.workers.dev`).
2. Aparece la página de inicio de sesión de Cloudflare Access, con el nombre del equipo que elegiste en Zero Trust. Escribe tu correo, que tiene que ser uno de la lista del equipo, y pide el código («Send me a code»).
3. Cloudflare manda un código a ese correo. Si no llega en unos minutos, revisa la carpeta de spam.
4. Escribe el código en la página. Se abre el sitio en la página Inicio, con el menú «Inicio», «Tests semanales», «Tareas», «Resultados», «Configuración» y «Cerrar sesión».

La sesión dura 24 horas; después Cloudflare vuelve a pedir el código.

Con esto la instalación está completa. Borra el archivo de texto con la hoja de datos: las claves quedaron guardadas en el `.env` de Cloud Shell y en Secret Manager.
