# Guía de inicio — IN5162 (Tests Semanales y Tareas)

Esta guía está pensada para pegarse en Notion. Cubre desde instalar la app hasta correr el flujo semanal completo.

## 1. Antes de empezar

Esta app automatiza el envío, evaluación y feedback de los tests semanales y las tareas del curso, usando GPT para corregir y Gmail para enviar/recibir correos.

Necesitas:
- Python instalado.
- Una cuenta de Gmail con verificación en dos pasos activada (para generar una "app password").
- Una API key de OpenAI.

## 2. Instalación

1. Clona el repositorio.
2. Crea un entorno virtual e instala las dependencias:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Lanza la app:
   ```
   streamlit run app/main.py
   ```
4. Se abre en el navegador con cuatro secciones: **Inicio**, **Tests Semanales**, **Tareas**, **Datos y Configuración**.

## 3. Configurar credenciales y modelo (Parámetros de la revisión)

Ve a **Datos y Configuración → Parámetros de la revisión**. Estos valores son globales: se comparten entre todos los semestres, así que solo se configuran una vez.

- **Credenciales**: API key de OpenAI, correo remitente y app password de Gmail. Para generar la app password necesitas 2FA activado en la cuenta de Gmail, en `myaccount.google.com/apppasswords`.
- **Modelo OpenAI**: modelo, temperatura y máximo de tokens por evaluación.
- **Escala de notas — Tareas**: nota mínima y máxima que usa GPT al corregir.
- **Grupos control/tratamiento — Tests Semanales**: si el curso usa dos grupos de preguntas distintas, actívalo aquí y define la semilla de asignación aleatoria.

## 4. Crear y seleccionar un semestre

Un **semestre** es una carpeta que agrupa todos los datos de un curso: alumnos, preguntas, prompts y entregas. Cada semestre nuevo empieza limpio, sin pisar los datos del anterior.

En la barra superior de **Datos y Configuración**:
- El selector muestra el semestre activo — todo lo que hagas en la app (enviar, evaluar, cargar datos) opera sobre ese semestre.
- El botón **+ Nuevo semestre** crea una carpeta nueva con los CSV y prompts de ejemplo (no copia los datos del semestre activo actual) y la activa.

**Qué NO se copia de un semestre a otro:** alumnos, preguntas, prompts, entregas, resultados de corrección.

**Qué SÍ se comparte entre todos los semestres:** credenciales, modelo, escala de notas, configuración de grupos (todo lo de la sección "Parámetros de la revisión").

## 5. Cargar los datos del curso

En **Datos y Configuración → Datos del curso**:

- **Alumnos (Tests)**: CSV con columnas `Nombre`, `Correo` (y las que se agregan automáticamente por semana).
- **Preguntas**: una fila por semana, con columnas `Semana`, `Tema`, `Fecha de Entrega`, `Control P1/P2/P3`, `Control Pauta P1/P2/P3`, `Tratamiento P1/P2/P3`, `Tratamiento Pauta P1/P2/P3`.
- **Alumnos (Tareas)**: CSV con columnas `nombre`, `correo`.
- **Entregas (Tareas)**: sube un `.zip` con los HTML exportados de U-Cursos (uno por grupo), o archivos `.html` sueltos. Se extraen automáticamente a la carpeta de entregas del semestre activo.
- **Feedback Tareas**: vista de solo lectura del CSV que va generando el pipeline de tareas.
- **Prompts**: edita las plantillas de corrección y los correos que se envían a los alumnos.

Todos los editores de CSV permiten editar filas directamente en el navegador y guardar, o descargar el CSV para editarlo aparte.

## 6. Flujo semanal — Tests Semanales

En **Tests Semanales**, tres pasos en pestañas:

1. **Enviar preguntas**: envía la pregunta de la semana a los alumnos pendientes. Usa "Modo prueba" para verificar sin enviar correos reales.
2. **Evaluar respuestas**: lee el inbox, evalúa las respuestas con GPT y envía el feedback a cada alumno.
3. **Resumen semana**: genera un resumen en `.txt` a partir de las evaluaciones, descargable directamente.

El log de cada ejecución queda visible en pantalla (✓ éxito, ✗ error, ⚠ advertencia, → info).

## 7. Flujo de Tareas

En **Tareas**, cuatro pasos en pestañas:

1. **Generar preguntas**: procesa los HTML subidos en Datos del curso y genera una pregunta de comprensión personalizada por alumno.
2. **Enviar preguntas**: envía las preguntas generadas a cada alumno con correo identificado.
3. **Recolectar respuestas**: busca en el inbox las respuestas a los correos enviados.
4. **Corregir**: evalúa las respuestas con GPT, asigna notas y envía el feedback.

Si un integrante queda sin correo resuelto automáticamente, corrígelo manualmente en **Datos y Configuración → Feedback Tareas** antes del paso 2.

## 8. Leer el panel de control (Inicio)

La página de Inicio muestra:
- El semestre activo.
- Métricas rápidas de Tests Semanales (semana activa, respondieron, sin responder, evaluados) y de Tareas (enviados, respondieron, corregidos, con una barra de progreso del pipeline).
- Gráficos de analítica: promedio de nota y tasa de respuesta por semana (Tests Semanales), y por tarea (Tareas).

## 9. Solución de problemas comunes

- **"No encontré OPENAI_API_KEY"**: falta configurar credenciales en Parámetros de la revisión.
- **No aparecen alumnos ni preguntas**: revisa que el semestre activo (arriba en Datos y Configuración) sea el correcto.
- **El envío de correos falla**: verifica que la app password de Gmail sea válida y que la cuenta tenga 2FA activado.
- **Las entregas no aparecen en el selector de Tareas**: el `.zip` debe contener archivos `.html` directamente (o en subcarpetas) — cualquier otro formato se ignora.
