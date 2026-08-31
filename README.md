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

Cada semestre es una carpeta aparte, así que abrir uno nuevo no pisa los datos del anterior. Solo uno está activo a la vez, y se cambia desde **Datos y Configuración** en la app. Estas carpetas nunca se suben a git: tienen nombres y correos reales.

Antes de un envío conviene confirmar sobre cuál se está trabajando, porque los comandos toman el activo sin preguntar:

```bash
python -m modulos.semestre
```

## Tests Semanales

Cada semana tiene un tema y una o más preguntas abiertas sobre los videos, cada una con su pauta de corrección. Todo eso vive en `preguntas.csv`: una fila por semana, con las versiones de Control y de Tratamiento en columnas separadas (si el curso no usa grupos, quedan iguales).

```bash
python -m modulos.tests.chequeo 4      # qué pasaría al evaluar, sin enviar nada
python -m modulos.tests.enviar 4       # envía la pregunta de la semana
python -m modulos.tests.evaluar 4      # evalúa y devuelve el feedback
python -m modulos.tests.resumen 4      # resume cómo le fue al curso
```

**Enviar** le manda a cada alumno la versión que le corresponde según su grupo. A quien no tiene grupo se lo asigna en ese momento, mitad y mitad, con una semilla fija para que sea reproducible; una vez puesto no cambia nunca, porque define qué versión de pregunta le tocó.

**Evaluar** busca en el inbox los correos no leídos del módulo de esa semana, identifica de quién es cada uno (por el remitente, o por el Message-ID al que responde si escribió desde otra cuenta), limpia el texto y se lo pasa al modelo junto con la pauta de su grupo. Devuelve una nota y una evaluación de originalidad, manda el feedback y marca el correo como leído. A quien ya tiene nota no se le re-evalúa: se le avisa.

La nota se guarda **apenas se corrige a cada alumno**, no al final. Si el proceso muere a mitad, el correo ya salió y la API ya se gastó, así que perder ese registro obligaría a repetir todo.

## Tareas

A diferencia de los tests, las tareas son grupales: cada grupo entrega un HTML con su código. El sistema genera **una pregunta distinta por integrante**, sobre la parte del trabajo que le tocó, para que nadie pueda responder copiándole a un compañero.

```bash
python -m modulos.tareas.generar T1    # una pregunta y pauta por integrante
python -m modulos.tareas.enviar T1
python -m modulos.tareas.recolectar T1
python -m modulos.tareas.corregir T1
```

El paso de generar empareja el nombre de cada integrante con la planilla de alumnos para obtener su correo. Cuando no encuentra una coincidencia clara lo deja en blanco, y hay que resolverlo a mano antes de enviar: es preferible eso a mandarle la pregunta al alumno equivocado.

Las preguntas generadas quedan en `feedback_T*.csv`, que es lo único propio de este flujo; el estado (envíos, respuestas, notas) va a las mismas tablas que los tests.

## Cuidado con los envíos

`enviar`, `evaluar` y `corregir` **mandan correos reales a los alumnos**. Todos aceptan `--dry-run` para ver qué harían sin enviar nada, y `chequeo` nunca envía.

Antes de tocar el código conviene correr las pruebas: recorren el ciclo completo sobre una copia desechable del semestre, con el correo y el modelo simulados, y la borran al terminar.

```bash
python pruebas/todas.py
```

## Si algo se pierde

El historial completo se puede reconstruir leyendo el buzón:

```bash
python -m modulos.tests.reconstruir
```

Abre el correo en modo lectura —no marca ni envía nada— y vuelca al log lo que encuentre. Tarda un par de minutos y muestra el avance. Sirve cuando se perdió el registro local, cuando los envíos se hicieron desde otro equipo, o para traer un semestre entero que se llevó fuera del sistema.
