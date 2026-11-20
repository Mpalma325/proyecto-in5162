# Sitio del curso

Una página web a la que se entra desde cualquier equipo o teléfono: Inicio (en qué va la semana, lo que requiere atención y el gasto en la API), Tests semanales, Tareas, Resultados (la reportería) y Configuración. Los botones corren los mismos scripts de `modulos/` que la línea de comandos; lo que cambia es dónde corren.

## Piezas

- **La página** (`public/`): HTML y JavaScript sin framework. La reportería corre `modulos/datos/agregaciones.py` en el navegador con Pyodide, así que calcula exactamente lo mismo que `modulos/datos/reportes.py`.
- **El Worker** (`src/index.ts`): la API. Guarda los trabajos y la reportería en D1, y los archivos de cada semestre en R2.
- **El motor** (`../motor/`): un servicio en Google Cloud Run que ejecuta los trabajos. Ver `motor/MOTOR.md`.

Cuando alguien aprieta "Evaluar", el Worker anota el trabajo y le avisa al motor. El motor baja el semestre desde R2 a una carpeta desechable, corre `python -m modulos.tests.evaluar`, va mandando la salida (que la página muestra en vivo) y al terminar sube los archivos que cambiaron y recalcula la reportería. Cerrar la pestaña no detiene nada.

## Dónde queda cada cosa

| Qué | Dónde |
|---|---|
| CSV, prompts y entregas de cada semestre | R2, con las mismas rutas que en disco: `semestres/2026-2/alumnos.csv` |
| La tabla de la reportería | D1, tabla `panel` |
| Los trabajos pedidos y su salida | D1, tabla `trabajos` |
| Modelo, temperatura, escala de notas, grupos | D1, tabla `parametros`. El motor se los pasa a cada script como variables de entorno |
| Quién cambió cada archivo, y la versión anterior | D1, tabla `ediciones`; las versiones en R2, bajo `historial/` |
| Clave de OpenAI, correo y su contraseña | Solo en el motor (Secret Manager). Nunca pasan por el sitio |

## Lo que protege al curso

- **Nadie entra sin Cloudflare Access.** El Worker verifica la firma del token que agrega Access (`src/acceso.ts`) contra las claves del equipo y la aplicación (`ACCESO_EQUIPO`, `ACCESO_AUD`). Si Access no está configurado, o esos dos datos faltan, no entrega datos: la página queda vacía, no abierta. `ACCESO=abierto` existe solo para desarrollo local.
- **Todo trabajo es de prueba salvo pedido explícito.** El Worker guarda `prueba: true` a menos que llegue `false` como booleano, y el motor agrega `--dry-run` en ese caso. Todo lo que manda correos reales pide confirmación antes de salir.
- **Los comandos los arma el motor.** La página elige un flujo de una lista cerrada (`FLUJOS`, igual en el Worker y en `motor/trabajo.py`) y el motor valida semana, tarea y nombres de archivo.
- **Desde la página solo se escriben los archivos que se editan a mano**: las listas de alumnos, las preguntas, los prompts, las entregas y la asignación de preguntas de tareas (`EDITABLES` en el Worker). Una entrega ya subida no se reemplaza. Los demás archivos solo los escriben los trabajos.
- **Toda escritura desde la página tiene que venir de la página.** El Worker rechaza cualquier pedido que no sea de lectura si su `Origin` no es el sitio: así una página ajena, abierta por alguien con sesión, no puede pedir un trabajo a su nombre. La cookie de Access va además con `SameSite=Lax`.
- **Nada se pisa sin saberlo.** Cada escritura lleva la versión que se leyó (`If-Match`); si en la nube cambió mientras tanto, el Worker responde 409 en vez de reemplazarla. Vale para el motor, la página y `subir`.
- **Historial.** Antes de reemplazar un archivo, el Worker guarda la versión anterior en R2 (`historial/`) y anota quién la cambió en la tabla `ediciones`. Se ve en Configuración › Registro › Historial.
- **Dos tokens con lo mínimo.** `TOKEN_MOTOR` lo usa el motor para leer y escribir archivos y trabajos; no sirve para ver la reportería ni para pedir trabajos. `TOKEN_WEB` lo usa el Worker para avisarle al motor.

## En el PC, para desarrollar

Se necesita `web/.dev.vars` (no se sube a git):

```
ACCESO=abierto
TOKEN_MOTOR=<un valor cualquiera>
TOKEN_WEB=<otro valor>
```

```bash
# en web/
npm install
npm run db:local        # crea las tablas en la base local (aplica migrations/)
npm run dev             # el sitio, en http://127.0.0.1:8787

# en la raíz, con los mismos tokens: el motor local
TOKEN_MOTOR=... TOKEN_WEB=... python -m motor.servidor

# copiar los semestres del disco al R2 local (WEB_TOKEN = TOKEN_MOTOR)
python -m modulos.web.subir --archivos
```

Todo queda en `web/.wrangler/`, en el PC. El motor local trabaja sobre copias y no toca `semestres/`.

## Publicarlo

Así se publicó IN5162, a mano. Un curso nuevo usa `python3 instalar.py` desde Google Cloud Shell, que hace todo esto (ver `docs/instalador.md`).

Son pasos que se hacen una vez. Todos quedan dentro de los planes gratuitos de Cloudflare y de Google Cloud con el uso del curso, pero Google pide una tarjeta: conviene crear una alerta de presupuesto de 1 dólar.

1. **Cloudflare.** En `web/`:
   ```bash
   npx wrangler login
   npx wrangler d1 create in5162                  # copiar el id a wrangler.toml
   npx wrangler d1 migrations apply DB --remote  # las tablas: migrations/
   npx wrangler r2 bucket create in5162-semestres
   ```
2. **El motor.** Con `gcloud` instalado y la sesión iniciada:
   ```powershell
   .\motor\desplegar.ps1 -Proyecto <id-del-proyecto> -WebUrl https://in5162.<subdominio>.workers.dev
   ```
   Al final imprime la dirección del motor y cómo leer los dos tokens.
3. **Conectar el sitio con el motor.** Poner la dirección en `MOTOR_URL` de `wrangler.toml` y cargar los tokens:
   ```bash
   npx wrangler secret put TOKEN_MOTOR
   npx wrangler secret put TOKEN_WEB
   npm run deploy
   ```
4. **Cloudflare Access.** Activar Zero Trust en one.dash.cloudflare.com (plan Free) y crear un token de API con los permisos *Access: Apps and Policies → Edit* y *Access: Organizations, Identity Providers, and Groups → Edit*. Pegarlo en el `.env` como `CLOUDFLARE_API_TOKEN` y, en `web/`:
   ```bash
   node scripts/acceso.mjs profe@uchile.cl ayudante@uchile.cl
   npm run deploy
   ```
   El script crea la aplicación con esa lista de correos (se entra con un código que llega al correo), deja una excepción para `/api/motor` y `/api/subir` (el motor no puede iniciar sesión en Access, y esas rutas ya exigen `TOKEN_MOTOR`) y anota en `wrangler.toml` los datos con que el Worker verifica la firma. Para cambiar la lista, se corre de nuevo con la lista completa. El script no está probado contra una cuenta real.
5. **Subir los semestres.** `python -m modulos.web.subir --archivos` con `WEB_URL` apuntando al sitio publicado. Esto sube a Cloudflare los datos de los alumnos: nombres, correos y respuestas. Desde ahí **la nube es la fuente**: `subir` solo agrega lo que allá no existe, y no reemplaza nada distinto salvo con `--forzar` (la versión reemplazada queda en el historial).

## Cambios a la base

Cada cambio es un archivo nuevo en `migrations/` (`0002_algo.sql`); los que ya están no se editan. `npx wrangler d1 migrations apply DB --remote` aplica los que falten y anota cuáles corrió en la tabla `d1_migrations`. `0001_inicial.sql` es lo que antes era `schema.sql`. La base de IN5162 se creó antes de las migraciones: el comando para marcarla como ya migrada está en `docs/instalador.md`.

## Respaldo

Con el sitio en uso, lo nuevo queda en la nube y `semestres/` en el PC se queda atrás.

```bash
python -m modulos.web.bajar 2026-2 --comparar   # qué difiere entre la nube y el PC
python -m modulos.web.bajar 2026-2              # copia completa en respaldos/web/<fecha>/
```

Nunca escribe en `semestres/`. Si se quiere poner al día la copia local, se copia a mano desde el respaldo.

## Costos

Con el uso del curso todo queda dentro de los planes gratuitos: Cloudflare (Workers, D1, R2 hasta 10 GB, Access hasta 50 personas) y Google Cloud (Cloud Run, Cloud Tasks, 6 versiones de secretos, 0,5 GB de imágenes). Para no pasarse, `desplegar.ps1` solo crea una versión nueva de un secreto si la clave cambió, y Artifact Registry guarda solo las 2 últimas imágenes del motor. El proyecto de Google tiene una alerta de presupuesto de 1.000 CLP. Lo único que se paga es OpenAI, como siempre.

## Pruebas

`python pruebas/web.py` comprueba que el puente de la reportería calcule lo mismo que `reportes.py`, que el editor de CSV guarde los archivos sin alterarlos, que solo entre quien trae un token de Access bien firmado y que el Worker, el motor y la página tengan las mismas listas de flujos y parámetros. `python pruebas/motor.py` corre el ciclo de un trabajo sin red.
