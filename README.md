# Proyecto IA IN5162

Herramientas de automatización docente para el curso IN5162. El curso usa dos mecanismos de evaluación continua: tests semanales de comprensión de video y tareas de código. Este proyecto automatiza todo el ciclo de cada uno: mandar la pregunta o el enunciado por correo, leer la respuesta del alumno desde el inbox, corregirla con GPT según una pauta, y devolver la nota y el feedback, también por correo.

Sobre esa base se monta además un estudio de impacto: en varias semanas, la mitad del curso (grupo "Control") recibe una pregunta, y la otra mitad (grupo "Tratamiento") recibe otra distinta sobre el mismo tema, para después evaluar el aprendizaje que los alumnos sacan de los tests semanales. El sistema separa a los alumnos en dos grupos y guarda esa asignación; se configura una vez y el resto del pipeline funciona igual.

Todo se puede correr desde la línea de comandos o desde la interfaz gráfica (`streamlit run app/main.py`). No hay lógica distinta entre una vía y otra: la app lanza exactamente los mismos comandos.

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Después, un archivo `.env` en la raíz del proyecto:

```
OPENAI_API_KEY=sk-...
CORREO_REMITENTE=in5162@uchile.cl
CORREO_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

El app password se genera en `myaccount.google.com/apppasswords` y **requiere 2FA activado** en esa cuenta. Google lo muestra separado en grupos de cuatro; esos espacios no son parte de la clave.

### Al clonar por primera vez

El repo no trae ningún semestre: las carpetas de `semestres/` llevan nombres, correos y respuestas de alumnos reales, así que están fuera de git. Hasta que haya uno, la app abre pidiendo que se cree y los comandos de terminal cortan con ese mismo mensaje.

Hay dos formas de tener uno. Crear uno vacío desde **Datos y Configuración** en la app, que lo copia de `semestres/_template/` y deja listos los prompts y los CSV de ejemplo; sirve para operar un curso nuevo, pero la reportería sale en blanco porque no hay nada que reportar. O recibir la carpeta de un semestre ya corrido y dejarla tal cual en `semestres/`; eso llega aparte del repo, por su contenido. Con eso funcionan la reportería, el ensayo de prompts y las pruebas.

```bash
python -m modulos.semestre     # sobre cuál se está trabajando
python pruebas/todas.py        # el ciclo completo, sin red ni API
```

Las pruebas corren sobre una copia desechable del semestre `2026-2` y avisan si no lo encuentran.

## Cómo está organizado

```
modulos/
  semestre/   cuál semestre está activo y dónde viven sus datos
  config.py   credenciales, modelo y parámetros
  mail/       enviar y leer correo, limpiar los cuerpos
  ia/         llamadas al modelo de lenguaje
  datos/      las tres tablas del semestre
  tests/      flujo de tests semanales
  tareas/     flujo de tareas
pruebas/       pruebas de punta a punta, sin red ni API
app/           interfaz Streamlit
semestres/     los datos de cada semestre (fuera de git)
```

La regla que sostiene la estructura: **`mail`, `ia` y `datos` no se llaman entre sí.** Cada uno hace lo suyo sin saber de los otros, y son los flujos (`tests`, `tareas`) los que los coordinan. Por eso agregar un flujo nuevo no obliga a tocar nada de los demás.

Cada módulo lleva su `.md` al lado, explicando qué le corresponde, qué puede importar y con qué hay que tener cuidado al modificarlo.

## Los datos de un semestre

Tres archivos en `semestres/<id>/`:

| Archivo | Qué guarda | Cómo cambia |
|---|---|---|
| `alumnos.csv` | quiénes son: nombre, correo, grupo | casi nunca |
| `notas.csv` | en qué van: si se les envió, si respondieron, qué nota | se reescribe |
| `log_envios.csv` | qué pasó y cuándo, con el texto de cada respuesta y evaluación | **solo se agrega al final** |

El log guarda una fila por **evento** (envío, respuesta, evaluación, error), no por alumno. Nunca se edita lo ya escrito, así que si dos personas operan el curso desde equipos distintos basta juntar los archivos: no se pisan. De ahí sale `datos.log.como_interacciones()`, que arma la vista de una fila por alumno-semana cuando se necesita para análisis.

### Operar desde dos computadores

Git no sincroniza estas carpetas, así que cada equipo acumula solo lo que hizo: los envíos quedan donde se mandaron y las evaluaciones donde se corrigieron. Reemplazar una carpeta por la del otro borra esa mitad. Para sumarlas, cada uno le pasa su `log_envios.csv` al otro y corre:

```bash
python -m modulos.datos.fusionar ruta/al/log_del_otro.csv --simular   # qué entraría
python -m modulos.datos.fusionar ruta/al/log_del_otro.csv             # incorporarlo
```

Agrega los eventos que faltan, ignora los que ya están y deja `notas.csv` al día. Correrlo dos veces no duplica nada, y antes de escribir deja una copia del log en `log_envios.csv.previo`. Cruzando los dos logs en ambos sentidos, los dos equipos quedan con la historia completa.

Los prompts y `alumnos.csv` no se fusionan: si los dos los editan, hay que decidir a mano cuál queda.

Cada semestre es una carpeta aparte, así que abrir uno nuevo no pisa los datos del anterior. Solo uno está activo a la vez, y se cambia desde **Datos y Configuración** en la app. Estas carpetas nunca se suben a git: tienen nombres y correos reales.

Antes de un envío conviene confirmar sobre cuál se está trabajando, porque los comandos toman el activo sin preguntar:

```bash
python -m modulos.semestre
```

## El sitio web

Las cuatro páginas de la app también existen como sitio web, para operar el curso desde cualquier equipo sin depender de un PC encendido. La página y los archivos viven en Cloudflare; los scripts de `modulos/` corren tal cual en un servicio de Google Cloud Run, el motor. Cómo funciona, cómo probarlo en local y cómo publicarlo: `web/SITIO.md` y `motor/MOTOR.md`. Para montarlo en otro curso: `python3 instalar.py` en Google Cloud Shell; cómo está armado, en `docs/instalador.md`.

## La reportería

La pantalla de inicio de la app es la reportería del curso. Muestra, para el semestre que se elija: los indicadores generales, la evolución semana a semana de la nota media y la tasa de respuesta, la distribución de notas y de originalidad, la comparación entre Control y Tratamiento con la diferencia entre ambos brazos, el listado de alumnos ordenado por nota, la ficha de cada uno con sus textos y las evaluaciones que recibió, y las dos listas accionables: quién no ha respondido y quién respondió sin que se le pusiera nota.

Todo se filtra por semana y por grupo, y el panel completo se descarga en CSV.

La pestaña **Originalidad** mira aparte lo que el modelo califica como tal. El acumulado del semestre con su porcentaje, cómo se reparten las cinco categorías dentro de cada semana, el nivel medio semana a semana, y la nota media que sacó cada categoría. Arriba va la correlación entre el nivel de originalidad y la nota: son dos juicios del mismo prompt sobre el mismo texto, y ese número dice cuánto se mueven juntos. Va entre −1 y 1; es una correlación de rangos, sirve para la dirección y la fuerza y no se puede leer como una regresión.

Las cinco categorías van de "Muy Baja" a "Muy Alta" y se pintan con un solo tono de claro a oscuro, porque están ordenadas. Lo que el modelo escribió y no calza con ninguna aparece en las tablas con el nivel vacío y queda fuera de los promedios.

Un semestre se mira a la vez y **nunca se mezcla con otro**: los alumnos, los grupos y las preguntas son distintos, así que un promedio entre semestres no significa nada. El selector de arriba cambia solo lo que se ve; el semestre sobre el que corren los envíos se cambia en Datos y Configuración, y la reportería avisa cuando no coinciden.

Las agregaciones viven en `modulos/datos/reportes.py`, no en la app. Todo sale de `panel()`, que arma una fila por alumno e ítem; lo demás son cortes de esa misma tabla, así que una métrica se calcula en un solo lugar y dos vistas no pueden discrepar. La app solo dibuja.

## Tests Semanales

Cada semana tiene un tema y una o más preguntas abiertas sobre los videos, cada una con su pauta de corrección. Todo eso vive en `preguntas.csv`: una fila por semana, con las versiones de Control y de Tratamiento en columnas separadas (si el curso no usa grupos, quedan iguales).

```bash
python -m modulos.tests.chequeo 4      # qué pasaría al evaluar, sin enviar nada
python -m modulos.tests.enviar 4       # envía la pregunta de la semana
python -m modulos.tests.evaluar 4      # evalúa y devuelve el feedback
python -m modulos.tests.resumen 4      # resume cómo le fue al curso
python -m modulos.tests.tutoria        # responde las dudas sobre las correcciones
python -m modulos.tests.experimento --prompt candidato.md -n 20   # prueba otro prompt
```

**Enviar** le manda a cada alumno la versión que le corresponde según su grupo. A quien no tiene grupo se lo asigna en ese momento, mitad y mitad, con una semilla fija para que sea reproducible; una vez puesto no cambia nunca, porque define qué versión de pregunta le tocó.

**Evaluar** busca en el inbox los correos no leídos del módulo de esa semana, identifica de quién es cada uno (por el remitente, o por el Message-ID al que responde si escribió desde otra cuenta), limpia el texto y se lo pasa al modelo junto con la pauta de su grupo. Devuelve una nota y una evaluación de originalidad, manda el feedback y marca el correo como leído. A quien ya tiene nota no se le re-evalúa: se le avisa.

La nota se guarda **apenas se corrige a cada alumno**, no al final. Si el proceso muere a mitad, el correo ya salió y la API ya se gastó, así que perder ese registro obligaría a repetir todo.

**Tutoría.** Un alumno recibe su nota y responde preguntando por qué un 6 y no un 7, qué tendría que haber puesto, o qué significa algún concepto que le quedó dando vueltas. Eso lo atiende `tutoria`, que corre aparte del ciclo del curso: cuando uno quiera, sin fecha, y si nunca se corre no pasa nada.

La nota **no se modifica**. El agente explica la corrección y enseña; recorregir sería otra cosa. Si el alumno insiste en apelar, se le dice que por esa vía no se cambian notas y que lo converse con el equipo docente.

Estos correos se reconocen porque responden al feedback y no a la pregunta original, lo que se sabe por el Message-ID al que contestan. `evaluar` los deja sin leer para que los tome `tutoria`. La conversación se corta a las cuatro vueltas por alumno y semana.

## Probar un prompt antes de cambiarlo

La política pedagógica completa vive en el prompt de evaluación, así que cambiarlo mueve las notas y las categorías de originalidad de todo el curso. Para verlo antes de aplicarlo está la pestaña **Probar un prompt** de Tests Semanales, y el mismo comando por terminal.

Se le da el prompt candidato y cuántas respuestas probar. Toma esa cantidad al azar entre las que ya tienen nota, las vuelve a pasar por el modelo con el prompt nuevo, y devuelve la comparación una a una: qué nota tenía cada una y cuál le pone el candidato, qué originalidad le veía y cuál le ve ahora, cuántas subieron y cuántas bajaron, y cómo queda la distribución de originalidad antes y después.

```bash
python -m modulos.tests.experimento --prompt candidato.md -n 20
python -m modulos.tests.experimento --prompt candidato.md -n 30 --semana 4
python -m modulos.tests.experimento --prompt candidato.md -n 10 --dry-run
```

`--dry-run` muestra qué respuestas tomaría sin llamar al modelo. Sirve para ver el tamaño de la muestra antes de gastar la API, que es lo único que gasta esto: una llamada por respuesta.

La muestra se elige con semilla (`--semilla`, 19 por defecto). Dejarla fija entre dos corridas hace que los dos prompts se prueben sobre las mismas respuestas, que es la única forma de que la comparación signifique algo.

**No manda correos, no cambia ninguna nota y no escribe en el log.** El alumno ya recibió su feedback y esa nota es la que vale; lo que sale de acá va a un CSV aparte, `experimento_<fecha>.csv`, en la carpeta de datos del semestre. Tampoco toca el archivo del prompt: la evaluación real sigue usando el de siempre hasta que alguien lo edite a mano.

Un aviso que conviene leer si aparece: si el prompt candidato no menciona `NOTA FINAL:` ni `ORIGINALIDAD:`, no hay de dónde sacar el resultado y la comparación sale vacía igual.

## Tareas

A diferencia de los tests, las tareas son grupales: cada grupo entrega un HTML con su código. El sistema genera **una pregunta distinta por integrante**, sobre la parte del trabajo que le tocó, para que nadie pueda responder copiándole a un compañero.

```bash
python -m modulos.tareas.chequeo T1    # qué pasaría al generar, sin llamar al modelo
python -m modulos.tareas.generar T1    # una pregunta y pauta por integrante
python -m modulos.tareas.enviar T1
python -m modulos.tareas.recolectar T1
python -m modulos.tareas.corregir T1
```

Las entregas se suben desde **Datos y Configuración → Datos del curso → Entregas (Tareas)**, con el zip de U-Cursos tal como se descarga. Adentro viene un comprimido por alumno, y la app entra a cada uno, se queda con el HTML y con el `.Rmd` que lo acompaña, y les pone el nombre del grupo para que dos entregas con el mismo nombre de archivo no se pisen. Los `.rar` también se abren. Lo que no reconoce lo lista en pantalla en vez de descartarlo callado.

El paso de generar empareja el nombre de cada integrante con la planilla de alumnos para obtener su correo. Cuando no encuentra una coincidencia clara lo deja en blanco, y hay que resolverlo a mano antes de enviar: es preferible eso a mandarle la pregunta al alumno equivocado.

Antes de gastar la API conviene mirar el chequeo, que lee las entregas y dice lo que haría `generar` sin llamar al modelo: cuánto se recortó de cada pregunta, de dónde salieron los integrantes, quién no resuelve a un correo y con qué candidatos, y quién del roster queda sin pregunta. Es lo primero que muestra la pestaña 1 de la app, así que se ve sin pedirlo. Cuando un grupo no declaró roles, ahí mismo se puede cambiar qué pregunta le toca a cada integrante; lo elegido queda en un CSV junto a las entregas y `generar` lo respeta.

Los entregables no siempre siguen el template: cambian los títulos de las secciones, dejan la tabla de roles sin llenar, o suben un HTML renderizado antes de escribir el código. El paso 1 reconoce esos casos, saca los integrantes del campo `author` cuando la tabla no sirve, y lee el `.Rmd` cuando el HTML viene vacío. Si un grupo no declaró roles, reparte las cuatro preguntas entre sus integrantes con semilla fija en vez de dejarlos sin nada. Lo que no puede resolver lo salta antes de gastar la API y dice por qué. `modulos/tareas/TAREAS.md` tiene el detalle.

Las preguntas generadas quedan en `feedback_T*.csv`, que es lo único propio de este flujo; el estado (envíos, respuestas, notas) va a las mismas tablas que los tests.

## Cuidado con los envíos

`enviar`, `evaluar` y `corregir` **mandan correos reales a los alumnos**. Todos aceptan `--dry-run` para ver qué harían sin enviar nada, y `chequeo` nunca envía.

Antes de tocar el código conviene correr las pruebas: recorren el ciclo completo sobre una copia desechable del semestre, con el correo y el modelo simulados, y la borran al terminar.

```bash
python pruebas/todas.py
```

## Forkear el proyecto

Está pensado para que otra persona lo tome y pruebe cosas encima sin editar código.

Se cambian por `.env`: el modelo, la temperatura y el tope de tokens; los servidores de correo, que vienen apuntando a Gmail; si el curso usa dos grupos y con qué semilla se reparten; y la escala de notas de las tareas.

Se cambian editando archivos, no código: los prompts, que viven en `semestres/<id>/<flujo>/prompts/*.md` y son propios de cada semestre. Ahí está la política pedagógica completa —la escala, los criterios, el tono, qué se le dice a quien copió—, así que probar otra forma de evaluar es editar un `.md`. Un semestre nuevo los copia desde `semestres/_template/`.

Lo que sí requiere tocar código: cambiar de proveedor de IA. La interfaz está aislada en `modulos/ia/cliente.py` detrás de una sola función, `completar(system, user) -> Respuesta`, así que es un archivo, pero hay que escribirlo.

Un detalle a tener presente: el prompt de evaluación y el que lee la nota están acoplados por las etiquetas `NOTA FINAL:` y `ORIGINALIDAD:`. Si se cambian en el prompt hay que cambiarlas también en `modulos/tests/evaluar.py`, o la nota deja de extraerse en silencio.

Para trabajar sobre un semestre sin cambiar el activo:

```bash
IN5162_SEMESTRE=2026-1 python -m modulos.tests.resumen 3
```

## Si algo se pierde

El historial completo se puede reconstruir leyendo el buzón:

```bash
python -m modulos.tests.reconstruir
```

Abre el correo en modo lectura —no marca ni envía nada— y vuelca al log lo que encuentre: los envíos con su Message-ID, las respuestas de los alumnos y las evaluaciones, cada uno con la fecha real del correo. Tarda un par de minutos y muestra el avance. Sirve cuando se perdió el registro local, cuando los envíos se hicieron desde otro equipo, o para traer un semestre entero que se llevó fuera del sistema.

Se puede correr las veces que haga falta: antes de escribir mira lo que el log ya tiene y solo agrega lo que falta. Con `--simular` dice cuánto agregaría sin escribir nada.

Al terminar deja el estado al día, porque escribir el log no basta: quien decide qué está pendiente, y de dónde sale la reportería, es `notas.csv`. Si el log ya está completo y lo único desalineado es el estado —el caso típico cuando alguien te pasa su log, o cuando los envíos se hicieron en el otro equipo— eso solo se hace sin abrir el correo, así que tampoco hacen falta las credenciales del buzón:

```bash
python -m modulos.tests.reconstruir --solo-estado --simular
python -m modulos.tests.reconstruir --solo-estado
```

Completar el estado **solo agrega**: crea la casilla que falte y llena el campo vacío, y nunca pisa una nota ya escrita ni borra una fila. Una nota corregida a mano se queda como está.
