# 6. Problemas

## Cómo falla el instalador

Cuando un paso no se puede completar, el instalador se detiene y muestra:

```
✗ <qué pasó y qué hacer>

Cuando esté corregido, corre de nuevo el mismo comando: retoma donde quedó.
```

Siempre se resuelve igual: corrige lo que dice el mensaje y corre de nuevo el mismo comando. Las preguntas ya respondidas no se repiten y lo que ya se creó no se duplica. Si lo detienes con Ctrl+C, muestra `Interrumpido. Se puede correr de nuevo: retoma donde quedó.`

Cuando la falla viene de un programa externo (`gcloud`, `wrangler`, `npm`, `node`), el mensaje empieza con `Falló:` seguido del comando, y debajo vienen las últimas líneas que escribió ese programa. La causa está en esas últimas líneas.

Algunas comprobaciones no pueden concluir porque el servicio no respondió. En ese caso el instalador pregunta:

```
No pude comprobarlo. ¿Sigo de todos modos? (s/N):
```

Presionar Enter (no) vuelve a preguntar el dato y a comprobarlo. Escribir `s` sigue sin comprobar; úsalo solo si estás seguro del dato y el servicio sigue sin responder después de varios intentos.

Esta página sigue el orden de la instalación. Busca el mensaje con Ctrl+F.

## Al abrir Cloud Shell

**`git clone` responde `Repository not found` o pide usuario y contraseña.** La dirección del repositorio está mal escrita o el repositorio no es público. Copia la dirección exacta de la página 3; si el error sigue, avisa a quien mantiene el sistema.

**`ls instalar.py` responde `No such file or directory`.** No estás en la carpeta del sistema. Escribe `cd ~/cloudshell_open/proyecto-in5162` (si usaste el botón) o `cd ~/proyecto-in5162` (si clonaste a mano).

**Cloud Shell abrió con otra cuenta de Google.** Cierra la pestaña de Cloud Shell, abre una ventana privada, inicia sesión solo con la cuenta del curso y abre Cloud Shell desde ahí.

## Antes de las preguntas

**`Este instalador necesita Python 3.11 o más nuevo (tienes ...).`** Cloud Shell trae una versión más nueva, así que este mensaje no debería aparecer ahí. Si aparece, escribe `python3 --version` y manda el resultado a quien mantiene el sistema.

**`Falta Node.js 22 o más nuevo. En Cloud Shell: nvm install 22`** o **`Node.js v... es muy antiguo para wrangler (pide 22 o más). En Cloud Shell: nvm install 22 && nvm use 22, y corre de nuevo.`** Escribe `nvm install 22`, luego `nvm use 22`, y corre de nuevo el instalador. Ver página 3, sección 3.2.

**`Falta npx. Cloud Shell lo trae; si corres en otro equipo, instálalo.`**, lo mismo con `gcloud`, o **`No encontré el programa «...». ¿Está instalado y en el PATH?`** Estás corriendo el instalador fuera de Cloud Shell. Ábrelo en Cloud Shell (página 3, sección 3.1).

**`Se cortó la entrada antes de terminar las preguntas.`** Se presionó Ctrl+D o se cortó la conexión mientras el instalador esperaba una respuesta. Corre de nuevo.

**`Falta este dato.`** Presionaste Enter sin escribir nada en una pregunta que no tiene valor por defecto. Escribe el dato.

## El curso

**`Solo letras, números y guiones, empezando por una letra (ej. IN3401).`** El código tiene un carácter no permitido (espacio, punto, tilde) o empieza con un número. Escríbelo de nuevo, por ejemplo `ABC123`.

**`IN5162 ya está instalado a mano y se actualiza con motor/desplegar.ps1 y npm run deploy. Este instalador es para cursos nuevos.`** Escribe el código de tu curso.

**`No puede quedar vacío: va en la firma de los correos.`** o **`Sin llaves { }: los correos las usan para sus campos.`** Escribe el nombre sin llaves.

## El correo

**`No parece un correo (nombre@dominio.cl).`** Revisa que el correo esté completo, sin espacios.

El instalador inicia sesión primero en el servidor de envío (SMTP, `smtp.gmail.com`) y después en el de lectura del buzón (IMAP, `imap.gmail.com`). Cada mensaje dice cuál de los dos falló.

**`Gmail rechazó el correo o la contraseña de aplicación al iniciar sesión para enviar (SMTP, smtp.gmail.com). Revisa que la cuenta tenga verificación en dos pasos y que la contraseña sea una de aplicación (myaccount.google.com/apppasswords), no la de siempre.`** Las causas posibles son cuatro: pegaste la contraseña normal de la cuenta, la verificación en dos pasos no está activa, la contraseña de aplicación se borró o se anuló (Google las anula al cambiar la contraseña de la cuenta), o el correo tiene un error. Crea una contraseña de aplicación nueva (página 2, sección 2.1) y pégala cuando el instalador la pida de nuevo.

**`Gmail aceptó la contraseña para enviar (SMTP), pero rechazó el inicio de sesión para leer el buzón (IMAP, imap.gmail.com): ...`** El correo y la contraseña están bien, pero la cuenta no deja leer el buzón por IMAP, que es como el sistema recibe las respuestas de los alumnos. Después de los dos puntos viene el motivo que dio Gmail.

- Si el correo es de Google Workspace (por ejemplo, de una universidad), el administrador desactivó IMAP. Usa una cuenta @gmail.com: activa en ella la verificación en dos pasos, crea una contraseña de aplicación (página 2, sección 2.1) y escribe ese correo y esa contraseña cuando el instalador los pida de nuevo.
- **No verificado.** Con una cuenta @gmail.com no debería pasar. Si pasa, abre Gmail con esa cuenta, haz clic en el engranaje, «Ver todos los ajustes», pestaña «Reenvío y correo POP/IMAP», y revisa que el acceso IMAP esté habilitado. Guarda los cambios, vuelve a la terminal y presiona Enter dos veces: el instalador deja el mismo correo y la misma contraseña y los prueba de nuevo.

**`No pude conectarme a smtp.gmail.com:587, el servidor de envío (SMTP) (...). ¿Hay conexión?`**, **`El envío (SMTP) funcionó, pero no pude conectarme a imap.gmail.com:993, el servidor de lectura (IMAP) (...). ¿Hay conexión?`** o **`El servidor de envío (SMTP, smtp.gmail.com) cortó la conexión (...).`** (o lo mismo con el de lectura). Gmail no respondió. Presiona Enter para reintentar. Si sigue igual después de unos minutos y estás seguro de la contraseña, responde `s`.

## OpenAI

El instalador prueba la clave pidiéndole al modelo una respuesta de 1 token. Así sabe si la clave sirve y si la cuenta tiene saldo.

**`La clave sirve, pero la cuenta de OpenAI no tiene saldo (insufficient_quota). Carga saldo en platform.openai.com/settings/organization/billing y presiona Enter para probar de nuevo; ...`** La cuenta no tiene saldo o no tiene un medio de pago registrado. Carga saldo como dice la página 2, sección 2.2, vuelve a la terminal y presiona Enter: el instalador deja la misma clave y la prueba de nuevo. Un pago recién hecho puede tardar unos minutos en verse; si el mensaje se repite, espera y presiona Enter otra vez.

**`OpenAI rechazó la clave (401). Se copió incompleta o se borró: crea otra en platform.openai.com/api-keys y pégala.`** Como OpenAI no vuelve a mostrar una clave, crea otra (página 2, sección 2.2) y pégala.

**`La clave no tiene permiso para usar los modelos (...). Crea otra en platform.openai.com/api-keys con «Permissions» en «All» y pégala.`** La clave se creó con permisos restringidos. Crea otra como dice la página 2, sección 2.2, con «Permissions» en «All», y pégala. La clave anterior se puede borrar en la misma página.

**`OpenAI respondió 429: demasiadas llamadas seguidas con esta clave. Espera un minuto y presiona Enter dos veces: ...`** OpenAI limita cuántas llamadas por minuto acepta de cada cuenta. Espera un minuto y presiona Enter dos veces: la primera responde que no a `¿Sigo de todos modos?` y la segunda deja la misma clave, que se prueba de nuevo.

**`OpenAI no deja usar esta clave (403: ...). Revisa en platform.openai.com que la cuenta y el proyecto de la clave estén activos.`** Después de «403:» viene el motivo que dio OpenAI. Entra a `platform.openai.com` con la cuenta del curso y resuelve el aviso que muestre sobre la cuenta. Si el proyecto de la clave fue archivado, crea una clave nueva en el proyecto por defecto (página 2, sección 2.2) y pégala.

**`La clave sirve, pero la cuenta no tiene el modelo gpt-5.4-mini, que es el que se usa por defecto, así que no pude comprobar el saldo. ...`** No detiene la instalación. Después de instalar, en el sitio, abre Configuración › La IA › Parámetros y cambia el modelo por uno que tu cuenta de OpenAI tenga disponible (página 4, sección 4.1). Revisa también el saldo en `platform.openai.com/settings/organization/billing`: esta prueba no alcanzó a comprobarlo.

**`No pude conectarme a OpenAI (...)`** o **`OpenAI respondió ...: ...`** OpenAI no respondió bien. Presiona Enter para reintentar; si después del número viene un mensaje de OpenAI, ese mensaje dice la causa.

## Cloudflare: Account ID y token

**`El Account ID son 32 letras y números. Está en dash.cloudflare.com, en la columna derecha de la página de cualquier dominio o en Workers & Pages.`** Lo que pegaste no tiene el formato. Cópialo de nuevo (página 2, sección 2.3).

**`Cloudflare no reconoce el token o no está activo. Cópialo de nuevo: dash.cloudflare.com → My Profile → API Tokens.`** El token se copió incompleto, venció o se borró. Cloudflare no vuelve a mostrar un token: crea otro con los cinco permisos y pégalo.

**`El token es válido pero no encuentro la cuenta .... Revisa el Account ID.`** El Account ID es de otra cuenta, o el token se creó con «Account Resources» apuntando a otra cuenta. Revisa los dos.

**`Al token le faltan permisos: ... Edítalo en My Profile → API Tokens y agrégalos (sobre esta cuenta).`** El mensaje nombra los permisos que faltan. Para agregarlos:

1. Entra a `dash.cloudflare.com/profile/api-tokens`.
2. En la fila del token, abre el menú «...» y elige «Edit».
3. Agrega una fila por cada permiso que falta, con «Account» en la primera lista y «Edit» en la tercera.
4. Haz clic en «Continue to summary» y luego en «Update token». El token sigue siendo el mismo.
5. Vuelve a la terminal y presiona Enter dos veces para que el instalador lo revise de nuevo.

**`R2 no está activado: actívalo en dash.cloudflare.com → R2 (plan gratuito) antes de seguir.`** Activa R2 (página 2, sección 2.3) y presiona Enter dos veces en la terminal.

**`Zero Trust no está activado: actívalo en one.dash.cloudflare.com con el plan Free; sin él nadie podrá entrar al sitio.`** Activa Zero Trust (página 2, sección 2.3) y presiona Enter dos veces.

**`Cloudflare no respondió al revisar: ... No pude comprobar esos permisos.`** Presiona Enter para reintentar.

**No verificado.** La revisión de permisos no se ha probado con tokens creados como tokens de la cuenta («Account API Tokens»). Si usaste uno de esos y el instalador lo rechaza, crea el token desde «My Profile», como dice la página 2.

## Google Cloud: proyecto y región

**`gcloud no tiene una sesión iniciada. En Cloud Shell viene iniciada; si no, corre: gcloud auth login`** Cierra Cloud Shell y vuelve a abrirlo. Si sigue igual, escribe `gcloud auth login`, abre el enlace que muestra, elige la cuenta del curso, copia el código que da Google, pégalo en la terminal y corre de nuevo el instalador.

**`✓ gcloud con la sesión de ...` muestra otra cuenta.** Presiona Ctrl+C y abre Cloud Shell con la cuenta del curso (ver «Al abrir Cloud Shell»).

**`El id del proyecto (no el nombre): 6 a 30 minúsculas, números y guiones, como aparece en console.cloud.google.com.`** Escribiste el nombre del proyecto. Copia el ID desde el selector de proyectos de la consola.

**`No encuentro el proyecto ..., o tu cuenta no tiene acceso. Revisa el id en console.cloud.google.com (arriba, al lado del logo).`** El ID tiene un error, o Cloud Shell está abierto con una cuenta que no es la dueña del proyecto. Revisa la línea `✓ gcloud con la sesión de ...` y el ID.

**`El proyecto ... no tiene la facturación activada. Actívala en console.cloud.google.com/billing/linkedaccount?project=....`** Abre esa dirección, vincula la cuenta de facturación (página 2, sección 2.4), vuelve a la terminal y presiona Enter: el ID aparece entre corchetes y se revisa de nuevo.

**`No pude revisar la facturación del proyecto (...).`** **No verificado:** en un proyecto recién creado, esta revisión puede fallar si la cuenta no tiene permiso para leer la facturación. Si tú vinculaste la facturación y la página «Facturación» del proyecto la muestra vinculada, responde `s`.

**`Una región de Google Cloud, como us-central1.`** Presiona Enter para usar `us-central1`.

## Quién entra

**`Escribe al menos un correo.`** o **`No parecen correos: ...`** Revisa los correos que nombra el mensaje. Se separan con coma. Los mismos mensajes aparecen en `python3 instalar.py acceso`, que vuelve a preguntar la lista.

## Cloudflare: sitio, base y archivos

**`✗ Solo minúsculas, números y guiones.`** El subdominio tiene un carácter no permitido. Escribe otro.

**`✗ Cloudflare no lo aceptó (...). Prueba con otro.`** El subdominio ya es de otra cuenta. Prueba con otro nombre. **No verificado:** si Cloudflare rechaza todos los nombres, el token puede no alcanzar para registrarlo; créalo en el panel como dice la página 3, sección 3.5, y corre de nuevo el instalador.

**`No pude leer el subdominio de workers.dev: ...`**, **`No pude listar las bases D1: ...`**, **`No pude crear la base D1 ...: ...`**, **`No pude consultar el bucket ...: ...`**, **`No pude crear el bucket ...: ...`** o **`La consulta a D1 falló: ...`** Después de los dos puntos viene el código y el mensaje de Cloudflare. Si el mensaje habla de autenticación o permisos (por ejemplo, el código 10000), revisa que el token tenga las cinco filas con «Edit» (página 2, sección 2.3). Si habla de un error interno o de un servicio no disponible, espera unos minutos y corre de nuevo.

**`Falló: npx wrangler d1 migrations apply ...`** o **`Falló: npx wrangler deploy ...`** **No verificado:** el instalador revisa cinco permisos del token, pero la publicación con `wrangler` no se ha probado con un token limitado a esos cinco. Lee las últimas líneas. Si nombran un permiso que falta, agrégalo al token como en «Al token le faltan permisos» y corre de nuevo. Si no nombran un permiso, manda esas líneas a quien mantiene el sistema.

**`web/wrangler.abc123.toml tiene database_id = "...", y en el .env CLOUDFLARE_D1_ID es "...". No lo piso: ...`** (o lo mismo con `ACCESO_EQUIPO` o `ACCESO_AUD`). El archivo de configuración del sitio y el `.env` dicen cosas distintas, lo que suele pasar si se editó el `.env` a mano. El mensaje dice qué hacer en cada caso. Si no sabes cuál de los dos es el correcto, no borres nada y manda el mensaje a quien mantiene el sistema.

**`web/wrangler.toml cambió: no encuentro una sola línea «...». Hay que actualizar instalador/cloudflare.py.`** Es un error de la versión del sistema que descargaste. Avisa a quien mantiene el sistema.

## Google Cloud: el motor

**`Falló: gcloud services enable ...`** Lee las últimas líneas. Si hablan de facturación («billing»), revisa que el proyecto tenga la facturación vinculada (página 2, sección 2.4); si la acabas de vincular, espera unos minutos y corre de nuevo.

**`Falló: gcloud secrets add-iam-policy-binding ...`** o **`Falló: gcloud tasks queues add-iam-policy-binding ...`** con un mensaje de que la cuenta de servicio no existe. **No verificado:** el instalador espera 15 segundos después de crear la cuenta del motor, y no se ha comprobado si alcanza. Espera un minuto y corre de nuevo.

**`Falló: gcloud run deploy ...`** La construcción o la publicación del motor falló. Lee las últimas líneas y corre de nuevo una vez. Si vuelve a fallar con el mismo mensaje, mándalo a quien mantiene el sistema. Si el mensaje menciona una política de la organización, `allUsers` o un dominio no permitido, ve a «El motor no responde».

**`Cloud Run no devolvió la dirección del motor.`** o **`No pude leer el número del proyecto ....`** Corre de nuevo.

## Access, publicación y plantilla

**`Falló: node scripts/acceso.mjs ...`** con `Zero Trust no está activado en esta cuenta. Actívalo en one.dash.cloudflare.com (plan Free).` Activa Zero Trust (página 2, sección 2.3) y corre de nuevo. Si las últimas líneas muestran un error de Cloudflare con el código 10000, al token le faltan los permisos de Access: revisa las dos filas «Access: ...» del token.

**`acceso.mjs terminó sin dejar ACCESO_EQUIPO y ACCESO_AUD.`** Corre de nuevo. Si se repite, avisa a quien mantiene el sistema.

**`El sitio todavía no responde (...); reintento en 20 s...`** Es normal en un sitio recién publicado. El instalador reintenta hasta seis veces.

**`El sitio ... no responde. Si se acaba de crear, espera unos minutos y corre de nuevo el instalador: retoma desde aquí.`** Espera diez minutos y corre de nuevo.

**`El sitio rechazó el token del motor (...). ¿Se publicó con los secretos? Corre de nuevo el instalador.`** Corre de nuevo: vuelve a publicar el sitio con sus tokens.

**`No pude subir: ...`** Corre de nuevo. Solo sube los archivos que faltan.

## El motor no responde

Se detecta porque `python3 instalar.py estado` muestra `✗ motor responde`, o porque en el sitio los trabajos quedan en espera sin empezar. Entre paréntesis, esa línea muestra el código HTTP y el comienzo de lo que respondió el motor, por ejemplo `✗ motor responde  (HTTP 403: 403 Forbidden Error: Forbidden Your client does not have permission to get URL /salud from this serv…)`, o `sin respuesta: ...` si no respondió.

1. Corre `python3 instalar.py estado`. Si alguna línea del motor (colas, cuenta, secretos, `motor desplegado`) tiene `✗`, corre `python3 instalar.py` para que la cree.
2. Si todo está con `✓` salvo `motor responde`, mira lo que dice esa línea. Con `HTTP 403` y `Forbidden`, sigue en el paso 3. Con otro código o con `sin respuesta`, abre en el navegador la dirección del motor que aparece en la línea `motor desplegado`, agregándole `/salud` al final (por ejemplo `https://abc123-motor-xxxxxxxxxx-uc.a.run.app/salud`). Si muestra un texto que empieza con `{"ok": true`, el motor está bien y el problema era pasajero: vuelve a consultar el estado en unos minutos. Si sigue fallando, manda la línea `motor responde` completa a quien mantiene el sistema.
3. Si la línea `motor responde` o el navegador muestran `Error: Forbidden` y un texto de que no tienes permiso para ver esa dirección, el proyecto está bajo una organización que no deja publicar servicios con acceso abierto (*Domain Restricted Sharing*). **No verificado:** puede pasar con cuentas universitarias de Google Workspace.

Para resolver el caso `Forbidden`, el motor tiene que ir en un proyecto sin organización:

1. Con una cuenta @gmail.com (la del curso), crea un proyecto nuevo con la facturación vinculada (página 2, sección 2.4). Comprueba que en «Ubicación» diga «Sin organización».
2. Si esa cuenta es la misma con la que abres Cloud Shell, entra a la carpeta del sistema, abre el `.env` con `nano .env`, borra la línea completa que empieza con `GCP_PROYECTO=` (Ctrl+K borra la línea donde está el cursor), guarda con Ctrl+O y Enter, sal con Ctrl+X, y corre `python3 instalar.py`. Va a preguntar el ID del proyecto: escribe el nuevo.
3. Si esa cuenta es otra, su Cloud Shell no tiene la carpeta del sistema. Ábrelo con esa cuenta, descarga el sistema (página 3, sección 3.1) y corre `python3 instalar.py` con los mismos datos de antes y el ID del proyecto nuevo (si no tienes anotadas las claves, ver página 5, sección 5.6). El instalador encuentra lo que ya existe en Cloudflare y no lo duplica.

En los dos casos, el instalador despliega el motor en el proyecto nuevo y vuelve a publicar el sitio con la dirección nueva del motor.

## Actualizar, credenciales, estado y acceso

**`Al .env le falta ... ¿Se terminó la instalación? Corre: python3 instalar.py`** Estás en otra carpeta o la instalación no terminó. Revisa la carpeta (página 5, sección 5.1). Si estás en la correcta, corre `python3 instalar.py` para completarla.

**`python3 instalar.py estado` muestra `✗ plantilla de semestre en el sitio`.** Con `HTTP 200, 0 archivos`, la plantilla no se subió. Con `HTTP 401` o `HTTP 403`, el sitio no aceptó el token del motor. En los dos casos corre `python3 instalar.py`: sube los archivos que faltan y vuelve a publicar el sitio con sus tokens.

**`Falló: node scripts/acceso.mjs ...` al correr `python3 instalar.py acceso`.** El `.env` queda con la lista anterior. Access puede haber quedado a medio cambiar: el script borra la regla de quién entra antes de crear la nueva, y si falla entre los dos pasos nadie puede entrar al sitio hasta que el comando termine bien. Lee las últimas líneas y sigue lo que dice «Access, publicación y plantilla»; después corre de nuevo `python3 instalar.py acceso`.

**`✗ Access ya cambió, pero el sitio no se publicó y sigue con los datos de antes.`** al correr `python3 instalar.py acceso`. La lista nueva ya quedó en Access y en el `.env`, pero el sitio todavía verifica la sesión con los datos viejos y no deja entrar a nadie. Corre `python3 instalar.py actualizar`: publica el sitio con lo que hay en el `.env`. No repitas `acceso`, porque no vería nada que publicar.

**`Hay archivos del repositorio cambiados en este equipo; git no puede traer la versión nueva encima:`** seguido de una lista de archivos. Alguien editó archivos del sistema en Cloud Shell. Si no fue a propósito, descarta esos cambios con `git checkout -- .` y corre de nuevo `python3 instalar.py actualizar`. Esto no toca el `.env`.

**`Elige 1, 2 o 3.`** En `credenciales`, escribe solo el número.

## En el sitio

**No llega el código para entrar.** Revisa la carpeta de spam. El correo tiene que estar escrito igual que en la lista del equipo. Para ver la lista, corre `python3 instalar.py acceso` en Cloud Shell: la muestra en la línea `Hoy entran:`. Si el correo falta o está mal escrito, escribe la lista corregida (página 5, sección 5.5); si está bien, presiona Ctrl+C para salir sin cambiar nada.

**La página carga pero no muestra datos, o dice `No pude cargar la página: ...`.** Corre `python3 instalar.py estado`. Si `Access configurado` o `sitio publicado` tienen `✗`, corre `python3 instalar.py`.

**Al crear un semestre: `No encontré la plantilla de semestre en R2.`** La plantilla no se subió. Corre `python3 instalar.py` en Cloud Shell y vuelve a crear el semestre.

**Al crear un semestre: `Usa un identificador como 2027-1: letras, números, punto o guion.`** El identificador tiene espacios u otros caracteres. Escríbelo de nuevo.

**Al crear un semestre: `El semestre ... ya existe: elígelo en la lista de arriba.`** Ya está creado. Elígelo en «Semestre activo».

**La simulación del envío dice `Nada por enviar.`** El motor no encontró alumnos pendientes para esa semana. Si todavía no mandaste esa semana, la lista de alumnos no se leyó: revisa en Configuración › Tests semanales › Alumnos que la tabla tenga las columnas `Nombre` y `Correo`, escritas así, y una fila por alumno (página 4, sección 4.3). Si no las tiene, corrige el archivo y súbelo de nuevo con «Reemplazar con un CSV…».

**La evaluación encuentra 0 respuestas.** El sistema solo toma correos sin leer de la bandeja de entrada del correo del curso. Revisa en Gmail si las respuestas están marcadas como leídas, archivadas o en spam; márcalas como no leídas y devuélvelas a la bandeja de entrada. Revisa también que la fecha de entrega haya pasado y que los alumnos hayan respondido al correo de la pregunta.

**Un envío o una evaluación falla y la salida dice `Username and Password not accepted` o `Invalid credentials`.** Gmail rechazó la contraseña de aplicación: se anuló o se borró. Crea una nueva (página 2, sección 2.1) y cárgala con `python3 instalar.py credenciales`, opción 1 (página 5, sección 5.3).

**La evaluación muestra líneas `✗ ...: error GPT: ...` con `insufficient_quota` o `You exceeded your current quota`.** Se acabó el saldo de OpenAI. Carga saldo en `platform.openai.com` («Settings», «Billing») y repite la evaluación de esa semana: las respuestas que no se corrigieron quedaron sin leer en el buzón, y las que ya tienen nota no se corrigen de nuevo.

**La evaluación muestra `error GPT` con `Incorrect API key` o un error 401.** La clave de OpenAI se borró. Crea otra (página 2, sección 2.2), cárgala con `python3 instalar.py credenciales`, opción 2, y repite la evaluación.

**Los trabajos quedan en espera y no empiezan.** Ver «El motor no responde».
