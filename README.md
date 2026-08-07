# Proyecto IA IN5162

Herramientas de automatización docente para el curso IN5162. El curso usa dos mecanismos de evaluación continua: tests semanales de comprensión de video y tareas de código. Este proyecto automatiza todo el ciclo de cada uno: mandar la pregunta o el enunciado por correo, leer la respuesta del alumno desde el inbox, corregirla con GPT según una pauta, y devolver la nota y el feedback, también por correo.

Sobre esa base se monta además un estudio de impacto: en varias semanas, la mitad del curso (grupo "Control") recibe una pregunta, y la otra mitad (grupo "Tratamiento") recibe otra distinta sobre el mismo tema, para después evaluar el aprendizaje que los alumnos sacan de los tests semanales. El sistema separa a los alumnos en dos grupos y guarda esa asignación, se configura una vez y el resto del pipeline funciona igual.

Todo se puede correr desde línea de comandos (cada paso es un script de Python) o desde la interfaz gráfica en **[app/](app/)** (`streamlit run app/main.py`), que envuelve los mismos scripts con botones, editores de CSV y un panel de métricas — no hay lógica distinta entre una vía y otra, la app solo llama a las mismas funciones.

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Cada subproyecto requiere su propio `.env` con `OPENAI_API_KEY`, `CORREO_REMITENTE` y `CORREO_APP_PASSWORD`. Ver `.env.example` en cada carpeta.

## Tests Semanales

Cada semana del curso tiene un tema (por ejemplo "Regression Modelling") y una o más preguntas abiertas asociadas a los videos de esa semana, cada una con su propia pauta de corrección. Todo esto vive en `preguntas.csv`: una fila por semana, con las preguntas y pautas de Control y de Tratamiento en columnas separadas (si el curso no usa grupos, ambas columnas quedan iguales).

El flujo tiene tres pasos, cada uno un script independiente en `tests_semanales/src/` (y una pestaña en la app):

1. **Enviar preguntas** (`enviar_preguntas.py`): recorre la planilla de alumnos y le manda un correo a cada uno que todavía no tenga la pregunta de esa semana enviada. El correo que le llega a cada alumno depende de su grupo (Control o Tratamiento). El script asigna el grupo en el momento del primer envío,dejándolo registrado en la fila de ese alumno en el CSV. El envío queda registrado tanto en el CSV (columna "Envío N") como en un archivo interno de Message-IDs, que es lo que permite después reconocer la respuesta del alumno como reply a ese correo específico.

2. **Evaluar respuestas** (`evaluar_respuestas.py`): se conecta al inbox por IMAP y busca correos nuevos (no leídos) cuyo asunto corresponda al módulo de esa semana. Para cada uno, identifica de qué alumno es (por el remitente, o por el Message-ID al que está respondiendo si el remitente no calza directo — por ejemplo si escribió desde otra cuenta), limpia el texto de la respuesta (saca firmas, citas del correo original, el "El fulano escribió:" que agregan los clientes de correo), y se la pasa a GPT junto con la pregunta y la pauta de su grupo. GPT devuelve una nota preliminar y una evaluación de "originalidad" (qué tan probable es que la respuesta se haya generado con IA en vez de ser del alumno). Con eso arma un correo de feedback y lo manda de vuelta como respuesta al alumno, y marca el correo original como leído para no volver a procesarlo. Si alguien manda la respuesta dos veces, la segunda no se vuelve a evaluar — se le avisa que ya tenía nota.

3. **Resumen semana** (`resumen_semana.py`): junta todas las respuestas ya evaluadas de la semana y le pide a GPT un resumen de cómo le fue al curso en general (qué entendieron bien, qué se les dificultó), que queda como un `.txt` descargable — pensado para que el profesor tenga una lectura rápida sin revisar respuesta por respuesta.

## Tareas

A diferencia de los tests semanales (una pregunta fija que responde toda la sección), las tareas de código son grupales y cada grupo entrega un HTML distinto (exportado desde U-Cursos) con su código y resultados. El sistema le genera **una pregunta de comprensión distinta a cada integrante** del grupo, sobre una parte específica de lo que ese grupo hizo — la idea es que un alumno no pueda responder copiándole a un compañero, porque a cada uno le preguntan por un fragmento distinto de su propio trabajo.

El flujo tiene cuatro pasos, en `tareas/src/`:

1. **Generar preguntas** (`paso1_generar.py`): toma cada HTML subido, lo limpia (extrae el código, los resultados y la tabla de "roles" que dice quién hizo qué dentro del grupo) y se lo manda a GPT, que devuelve una pregunta y una pauta personalizada por integrante, apuntando a la parte del trabajo que le correspondió a esa persona. Luego intenta emparejar el nombre de cada integrante con la planilla de alumnos para obtener su correo — si no encuentra una coincidencia automática, pide que se resuelva a mano (ya sea en la terminal o editando el CSV resultante desde la app).

2. **Enviar preguntas** (`paso2_enviar.py`): manda la pregunta generada a cada integrante con correo ya resuelto, guardando el Message-ID de cada envío para el paso siguiente.

3. **Recolectar respuestas** (`paso3_recolectar.py`): revisa el inbox buscando respuestas (por Message-ID) a los correos que se mandaron en el paso 2, y guarda el texto de cada una en el CSV.

4. **Corregir** (`paso4_corregir.py`): para cada respuesta recolectada, arma un prompt con la pregunta, la pauta y la respuesta del alumno, se lo pasa a GPT para obtener una nota (en la escala configurada) y un comentario, guarda ambos en el CSV y le manda el feedback al alumno por correo.

Cada paso solo toca las filas que están en el estado que le corresponde (por ejemplo, el paso 4 ignora las filas que todavía no tienen respuesta), así que se pueden correr varias veces seguidas sin duplicar envíos ni volver a corregir algo ya corregido — cada script retoma donde quedó la vez anterior.

## Datos de semestre

El curso se repite semestre a semestre con alumnos distintos, así que todo lo que es específico de un semestre (alumnos, preguntas y pautas de esa semana, entregas subidas, notas, correos ya enviados) vive en `semestres/<id>/` — una carpeta por semestre. Abrir un semestre nuevo no borra ni pisa los datos del anterior; queda uno "activo" a la vez. Esta carpeta nunca se sube a git, porque tiene nombres y correos reales de alumnos.

Las credenciales y los parámetros de revisión (modelo, escala de notas, grupos control/tratamiento) son globales y no cambian entre semestres.

Para crear y cargar un semestre nuevo, ir a **Datos y Configuración** en la UI. Ver [`docs/GUIA_INICIO.md`](docs/GUIA_INICIO.md) para el paso a paso completo, pensado para alguien que nunca ha tocado el proyecto.
