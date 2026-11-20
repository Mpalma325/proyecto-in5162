# 5. Mantenimiento

Todo lo de esta página, salvo la última sección, se hace en Cloud Shell, desde la carpeta del sistema. El instalador tiene cuatro comandos:

```
python3 instalar.py                  # instala, o completa lo que falte
python3 instalar.py actualizar       # trae la versión nueva y vuelve a publicar
python3 instalar.py estado           # qué existe y qué falta, sin cambiar nada
python3 instalar.py credenciales     # cambia la clave del correo, la de OpenAI o el token de Cloudflare
```

## 5.1 Volver a la carpeta del sistema

1. Entra a `shell.cloud.google.com` con la cuenta del curso, en una ventana privada o en un perfil donde solo esté esa cuenta.
2. Entra a la carpeta. Si instalaste con el botón:

   ```
   cd ~/cloudshell_open/proyecto-in5162
   ```

   Si clonaste a mano:

   ```
   cd ~/proyecto-in5162
   ```

3. Comprueba que estás en la carpeta correcta con `ls .env`. Debe responder `.env`. Si responde `No such file or directory`, estás en otra carpeta o la carpeta se perdió (sección 5.6).

## 5.2 Actualizar a una versión nueva

Cuando quien mantiene el sistema avise que hay una versión nueva:

1. Revisa en el sitio que no haya un trabajo corriendo (el historial de trabajos aparece en «Tests semanales» y en «Tareas»). Si la tutoría automática está prendida, no actualices entre las 17:30 y las 18:30.
2. En Cloud Shell, desde la carpeta del sistema:

   ```
   python3 instalar.py actualizar
   ```

3. Empieza con `=== Trayendo la última versión del código`. Si hay código nuevo, dice `Código nuevo: sigo con la versión recién traída.` y sigue con esa versión.
4. Después repite las etapas de publicación de la instalación: dependencias del sitio, migraciones de la base, construcción del motor (tarda unos minutos), publicación del sitio y plantilla.
5. Termina con `=== Listo: sitio y motor con la última versión`.

`actualizar` no hace preguntas y no toca los datos del curso. De la plantilla solo sube los archivos que no estaban, así que los prompts que el equipo editó en el sitio quedan como están. Los semestres ya creados conservan sus prompts; los cambios de la plantilla aplican a los semestres que se creen después.

## 5.3 Cambiar una credencial

Hace falta cuando:

- cambiaste la contraseña del Gmail del curso (Google anula las contraseñas de aplicación) o borraste la contraseña de aplicación;
- creaste una clave de OpenAI nueva o borraste la anterior;
- el token de Cloudflare venció o lo borraste.

Pasos:

1. Ten a mano la credencial nueva: una contraseña de aplicación nueva (página 2, sección 2.1), una clave de OpenAI nueva (2.2) o un token nuevo (2.3).
2. En Cloud Shell, desde la carpeta del sistema:

   ```
   python3 instalar.py credenciales
   ```

3. El instalador muestra:

   ```
   === Cambiar una credencial
     1. El correo del curso o su contraseña de aplicación
     2. La clave de OpenAI
     3. El token de Cloudflare
   ¿Cuál? (1, 2 o 3):
   ```

   Escribe el número y presiona Enter.
4. Pregunta los datos de esa credencial, con el valor actual entre corchetes o con `(Enter para dejarla igual)`. Pega el valor nuevo donde cambió y presiona Enter donde no. Comprueba la credencial igual que en la instalación.
5. Con la opción 1 o 2, guarda el valor en Secret Manager y reinicia el motor. Termina con `✓ el próximo trabajo ya usa la credencial nueva`. Con la opción 3 termina con `Guardado en el .env. Lo usan instalar y actualizar; el sitio no lo necesita.`

La opción 1 también permite cambiar el correo del curso por otro. Hazlo solo entre semestres: el sistema busca las respuestas en el buzón del correo configurado, y las respuestas a preguntas mandadas desde el correo anterior llegan al buzón anterior.

## 5.4 Revisar el estado

```
python3 instalar.py estado
```

Solo consulta. Muestra una línea por cada pieza: `✓` si está, `✗` si falta y `?` si no se pudo saber (Cloudflare no respondió). La lista completa de una instalación sana está en la página 3, sección 3.7. Si algo aparece con `✗`, `python3 instalar.py` lo crea sin tocar lo que ya existe.

Úsalo cuando el sitio no responde o un trabajo queda sin avanzar: la línea `motor responde` dice si el motor está en pie.

## 5.5 Cambiar quién entra al sitio

La lista de correos quedó guardada en el archivo `.env`, en la línea `ACCESO_CORREOS`. El instalador no la vuelve a preguntar, así que se cambia editando esa línea.

1. En Cloud Shell, desde la carpeta del sistema, abre el archivo:

   ```
   nano .env
   ```

2. Con las flechas del teclado, baja hasta la línea que empieza con `ACCESO_CORREOS=`.
3. Deja después del `=` la lista completa de quienes deben entrar, separados por coma y sin espacios, por ejemplo `ACCESO_CORREOS=profesor@ejemplo.cl,ayudante@ejemplo.cl,nuevo@ejemplo.cl`. La lista reemplaza a la anterior: quien no esté en ella deja de entrar.
4. Guarda con Ctrl+O y Enter, y sal con Ctrl+X.
5. Corre el instalador:

   ```
   python3 instalar.py
   ```

   Muestra las respuestas guardadas, vuelve a comprobar las credenciales y repite las etapas sin duplicar nada. En la etapa de Access dice `Actualizada: ABC123 sitio (...)` y `Pueden entrar:` con la lista nueva. Como también vuelve a construir el motor, tarda unos minutos.

Las personas también se pueden cambiar en el panel de Cloudflare (`one.dash.cloudflare.com`, Access, Applications, la aplicación «ABC123 sitio», Policies). Ese cambio dura hasta la próxima vez que corras `python3 instalar.py`, que deja la lista del `.env`. `actualizar` no toca Access.

## 5.6 Si se pierde la carpeta de Cloud Shell

El archivo `.env` de la carpeta del sistema guarda todas las respuestas del instalador y lo que fue creando. Cloud Shell borra la carpeta personal si no se usa durante 120 días (Google avisa por correo antes). Para que no pase, abre Cloud Shell y corre `python3 instalar.py estado` al menos una vez por semestre.

Si la carpeta se perdió, los datos del curso no se pierden: están en Cloudflare. Para recuperar la instalación:

1. Si no tienes anotadas las claves, crea otras nuevas: contraseña de aplicación (página 2, sección 2.1), clave de OpenAI (2.2) y token de Cloudflare (2.3).
2. Abre Cloud Shell y descarga de nuevo el sistema (página 3, sección 3.1).
3. Corre `python3 instalar.py` y responde las preguntas con los mismos datos de la instalación original: el mismo código de curso, la misma cuenta de Cloudflare y el mismo proyecto de Google Cloud.
4. El instalador encuentra el sitio, la base, el almacenamiento, el motor y Access que ya existen y no los duplica. Genera de nuevo los tokens internos entre el sitio y el motor, y publica los dos con ellos.

## 5.7 Cada semestre nuevo

No hace falta Cloud Shell. En el sitio, «Configuración», «Nuevo semestre…», escribe el identificador (por ejemplo `2027-2`), haz clic en «Crear y activar» y confirma. El semestre anterior queda guardado y se puede volver a mirar en «Resultados». Después carga la lista de alumnos y las preguntas como en la página 4.
