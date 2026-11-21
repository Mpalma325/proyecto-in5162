# 1. Antes de empezar

## Qué se crea

El instalador crea todo en cuentas del curso. En Cloudflare publica el sitio, con una base de datos (D1) y un almacenamiento de archivos (R2) donde quedan los alumnos, las preguntas, los prompts y las notas de cada semestre; el sitio queda cerrado con Cloudflare Access, que solo deja entrar a los correos que indiques. En Google Cloud despliega el motor en Cloud Run, que es el que manda los correos, lee las respuestas y llama a OpenAI; las claves del correo y de OpenAI quedan guardadas en Secret Manager y no pasan por el sitio. Después de instalar, el curso se opera desde el sitio y no depende de ningún computador encendido.

## Qué se paga

Con el uso de un curso, el sitio y el motor quedan dentro de los planes gratuitos de Cloudflare y Google Cloud. Esto es lo que da cada plan gratuito y lo que usó IN5162, el curso donde se desarrolló el sistema:

- Cloud Run (el motor): 180.000 segundos de CPU al mes, unas 50 horas de trabajos. En IN5162, un mes normal ronda una hora.
- Cloudflare R2 (los archivos): 10 GB. IN5162 usa del orden de 100 MB por semestre, casi todo en entregas de tareas.
- Cloudflare Workers y D1 (el sitio y la base): 100.000 visitas y 5 millones de lecturas al día. IN5162 usa unos cientos.
- Cloudflare Access (quién entra): 50 personas.
- Secret Manager y Artifact Registry (claves e imágenes del motor): 6 versiones de secretos y 0,5 GB. El sistema usa 5 secretos y el instalador deja solo las 2 últimas imágenes del motor.

Lo que se paga es OpenAI, por cada llamada al modelo: al corregir una respuesta, al generar el resumen de una semana, al responder dudas y, en las tareas, al generar y corregir las preguntas. El monto depende de cuántos alumnos, preguntas y semanas tenga el curso y del modelo elegido; el proyecto no tiene medido el gasto de un semestre completo. Como referencia, la documentación del proyecto muestra un trabajo de 3 llamadas con el modelo por defecto (gpt-5.4-mini) que costó US$ 0,0097 con los precios de ese momento. Después de instalar, la página Inicio del sitio muestra el consumo de cada trabajo y del semestre: en dólares si cargas los precios del modelo en Configuración › La IA › Parámetros (página 4), y en tokens si no.

Para que no haya sorpresas, la página 2 deja dos topes: una alerta de presupuesto en Google Cloud y un saldo prepagado en OpenAI, sin recarga automática.

## Qué decidir antes

1. **El código del curso**, por ejemplo `ABC123`. Va en el asunto de los correos que reciben los alumnos y en el nombre de todo lo que se crea: el sitio queda en `https://abc123.<subdominio>.workers.dev` y el motor se llama `abc123-motor`. Admite letras, números y guiones, empieza con una letra y tiene entre 2 y 21 caracteres. Cambiarlo después equivale a instalar de nuevo.
2. **El nombre del curso** («Taller de Datos») y **la firma de los correos**. El nombre va en los prompts de corrección. Los correos los manda el sistema, así que por defecto firman con el equipo y el código, «Equipo ABC123», y no con una persona; así no hay que cambiar nada cuando el curso cambia de profesor. Si prefieres otra firma, el instalador la pregunta, y en cada semestre se puede editar en los prompts de correo. Ninguno de los dos puede llevar llaves `{ }`.
3. **Quiénes entran al sitio**: los correos del equipo docente. Todos tienen el mismo acceso, y ese acceso incluye mandar correos a los alumnos. Entran con un código que les llega al correo, así que no necesitan crear cuentas.
4. **Qué cuenta es dueña de todo.** Usa una sola cuenta de Gmail del curso (por ejemplo curso.abc123@gmail.com) para el correo, OpenAI, Cloudflare y Google Cloud. Hay tres motivos:
   - Las cuentas sobreviven al cambio de ayudantes o de profesor.
   - Las cuentas de la universidad (Google Workspace) pueden tener desactivadas las contraseñas de aplicación, que el sistema necesita para el correo, y pueden tener una política que impide publicar el motor. Ninguna de las dos cosas se ha probado con una cuenta universitaria; una cuenta @gmail.com no tiene esas restricciones.
   - El correo tiene que ser solo de este curso. El sistema toma de la bandeja de entrada los correos sin leer que responden a sus preguntas; si otra persona u otro curso usa ese buzón, las respuestas se mezclan.

## Datos de los alumnos

El sistema guarda nombres, correos, respuestas y notas de los alumnos en Cloudflare, los procesa en Google Cloud (región us-central1, en Estados Unidos) y manda las respuestas a OpenAI para corregirlas. Si tu universidad tiene reglas sobre dónde pueden estar los datos de los estudiantes, revísalas antes de cargar la lista real del curso.

## Hoja de datos

El instalador pide estos datos, en este orden. En la página 2 los vas a ir obteniendo; cópialos en un archivo de texto en tu computador a medida que aparezcan, porque OpenAI y Cloudflare muestran sus claves una sola vez. Borra ese archivo al terminar la página 3: las claves quedan guardadas en la instalación.

1. Código del curso (`ABC123`)
2. Nombre del curso (`Taller de Datos`)
3. Firma de los correos (`Equipo ABC123` si dejas la que viene)
4. Correo del curso (`curso.abc123@gmail.com`)
5. Contraseña de aplicación del correo (16 letras)
6. Clave de la API de OpenAI (empieza con `sk-`)
7. Account ID de Cloudflare (32 letras y números)
8. Token de la API de Cloudflare
9. ID del proyecto de Google Cloud (`abc123-motor`)
10. Región de Google Cloud (se deja la que propone: `us-central1`)
11. Correos del equipo docente (`profesor@ejemplo.cl, ayudante@ejemplo.cl`)
