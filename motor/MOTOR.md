# Motor

El servicio que ejecuta en la nube los trabajos que se piden desde la página
(`web/SITIO.md`): enviar, evaluar, corregir, generar preguntas. Corre en Google Cloud Run y usa los scripts
de `modulos/` tal cual; no hay una versión web de la lógica del curso.

## Cómo funciona un trabajo

1. En la página alguien aprieta "Evaluar". El sitio (Worker de Cloudflare) lo
   guarda en D1 y le avisa al motor.
2. El motor lo pone en la cola y responde enseguida. En Cloud Run la cola es
   Cloud Tasks; en el PC, un hilo (`cola.py`).
3. La cola llama a `/ejecutar`. El motor arma una carpeta de trabajo desechable
   con una copia de `modulos/` y los archivos del semestre bajados de R2, y
   corre el script con `IN5162_SEMESTRE` apuntando a ese semestre.
4. Mientras corre, va mandando la salida al sitio, y la página la muestra.
5. Al terminar sube a R2 los archivos que cambiaron, recalcula la reportería y
   borra la carpeta.

La cola existe porque evaluar una semana tarda minutos. Si el motor respondiera
antes de terminar, Cloud Run le quitaría la CPU al trabajo; Cloud Tasks mantiene
la conexión abierta hasta 30 minutos.

## Lo que no hay que romper

- **Todo trabajo es de prueba salvo pedido explícito.** Solo `prueba: false`, el
  booleano, quita el `--dry-run`. Un `"false"` escrito como texto no cuenta.
- **Los comandos se arman acá** (`FLUJOS` en `trabajo.py`), no en la página. La
  página elige un flujo de una lista cerrada y el motor valida los argumentos.
- **La carpeta de trabajo es propia.** En el PC el motor nunca toca `semestres/`
  real: una prueba no puede pisar los datos del curso.
- **Un trabajo empezado no se repite.** Si la cola lo entrega dos veces, la
  segunda no hace nada, porque podría mandar correos repetidos. Por lo mismo la
  cola se crea sin reintentos.
- **De a uno.** Dos trabajos a la vez podrían escribir el mismo archivo del
  semestre; la cola se crea con un solo despacho simultáneo.
- **Solo baja lo que necesita** (`_en_perfil`). Un trabajo de tests baja unos
  3 MB; si bajara también las entregas de tareas, serían más de 100.

## Los flujos

| Flujo | Qué corre | Correo o modelo |
|---|---|---|
| `tests.enviar`, `tests.evaluar`, `tests.tutoria` | los scripts de `modulos/tests/` | correos reales solo con `prueba: false` |
| `tests.resumen` | `modulos.tests.resumen` | llama al modelo, no manda correos |
| `tests.chequeo` | `modulos.tests.chequeo` | ninguno |
| `tests.experimento` | "Probar un prompt": guarda el candidato como `prompt_candidato.md` y corre `modulos.tests.experimento` | en modo prueba solo lista la muestra; sin él, una llamada al modelo por respuesta |
| `tareas.chequeo` | revisa las entregas y deja `tareas/cache/chequeo_<T>.json`, que dibuja la página | ninguno |
| `tareas.generar` | `modulos.tareas.generar --no-interactivo` con los HTML elegidos | llama al modelo |
| `tareas.enviar`, `tareas.corregir` | los scripts de `modulos/tareas/` | correos reales solo con `prueba: false` |
| `tareas.recolectar` | `modulos.tareas.recolectar` | lee el buzón |
| `datos.panel` | nada: solo recalcula la reportería después de editar alumnos o preguntas | ninguno |

Un flujo nuevo se agrega en `FLUJOS` de `trabajo.py` y en `FLUJOS` de
`web/src/index.ts`. `pruebas/web.py` falla si las dos listas no coinciden.

## Parámetros

Modelo, temperatura, tokens, escala de notas, tarea por defecto y grupos se
editan en la página (Datos y Configuración → Parámetros) y quedan en D1. Antes
de cada trabajo el motor los lee y se los pasa al script como variables de
entorno, que `config.py` prefiere sobre el `.env`. Solo pasan las claves de
`PARAMETROS`: si la tabla trajera otra cosa, como una clave de API, no llega.

## Credenciales

| Variable | Para qué |
|---|---|
| `TOKEN_WEB` | el sitio le avisa al motor que hay un trabajo, y la cola lo ejecuta |
| `TOKEN_MOTOR` | el motor lee y escribe archivos y trabajos en el sitio |
| `OPENAI_API_KEY`, `CORREO_REMITENTE`, `CORREO_APP_PASSWORD` | las de siempre; viven solo acá |

En Cloud Run vienen de Secret Manager. El sitio nunca ve la clave de OpenAI ni
la del correo.

## En el PC, para desarrollar

```bash
# en web/: el sitio local
npm run dev
# en la raíz: el motor, con los mismos tokens que web/.dev.vars
TOKEN_WEB=... TOKEN_MOTOR=... python -m motor.servidor
```

Toma las claves del correo y de OpenAI del `.env` de la raíz.

## Publicarlo

```powershell
.\motor\desplegar.ps1 -Proyecto <id-del-proyecto> -WebUrl https://<sitio>.workers.dev
```

Activa las APIs, crea la cola, guarda las claves en Secret Manager y despliega.
Se puede correr de nuevo sin romper nada. Lo que sube a Google para construir
el contenedor lo decide `.gcloudignore`, que ignora todo salvo `modulos/` y
`motor/`: `semestres/` y `.env` no viajan nunca.

## Pruebas

`pruebas/motor.py` corre el ciclo completo con el sitio reemplazado por un
diccionario en memoria, sin red.
