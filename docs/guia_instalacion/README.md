# Guía de instalación

Esta guía instala, para un curso, una copia propia del sistema de tests semanales y tareas: un sitio web desde el que el equipo docente opera el curso, un motor en Google Cloud que manda las preguntas y corrige las respuestas, y un correo del curso por donde salen y llegan los mensajes. Se sigue en orden, una página después de otra.

| Página | Qué se hace | Tiempo |
|---|---|---|
| [1. Antes de empezar](01_antes_de_empezar.md) | Qué se crea, qué se paga y qué hay que decidir antes | 10 minutos de lectura |
| [2. Cuentas y claves](02_cuentas_y_claves.md) | Correo del curso, OpenAI, Cloudflare y Google Cloud, y cada dato que pide el instalador | 45 a 60 minutos |
| [3. Instalar](03_instalar.md) | Abrir Cloud Shell, correr el instalador, responder sus preguntas y entrar al sitio | 20 a 30 minutos |
| [4. Primer semestre](04_primer_semestre.md) | Crear el semestre, cargar alumnos y preguntas, simular y hacer el primer envío | 30 minutos |
| [5. Mantenimiento](05_mantenimiento.md) | Actualizar, cambiar una clave, revisar el estado, cambiar quién entra, recuperar la instalación | Consulta |
| [6. Problemas](06_problemas.md) | Cada mensaje de error del instalador y del sitio, y qué hacer | Consulta |

## Lo que necesitas tener a mano

- Un computador con un navegador. No se instala nada en él: el instalador corre en Google Cloud Shell, una terminal que se abre en el navegador.
- Una tarjeta de crédito. Google Cloud la pide para activar la facturación aunque no cobre, OpenAI cobra por adelantado y Cloudflare puede pedirla para activar sus planes gratuitos.
- Un teléfono, para la verificación en dos pasos del correo del curso.
- Una hora sin interrupciones para las páginas 2 y 3.

## Cómo leer esta guía

Lo que aparece `así` se escribe o se copia tal cual. ABC123, «Taller de Datos», profesor@ejemplo.cl y curso.abc123@gmail.com son ejemplos: cámbialos por los datos de tu curso.

Los botones y menús se nombran como aparecen en cada servicio. Google muestra su consola y su cuenta en español; Cloudflare y OpenAI muestran sus paneles en inglés, así que esos rótulos van en inglés.

El instalador todavía no se ha probado de punta a punta en una cuenta nueva. Los puntos que no se han comprobado contra los servicios reales están marcados con **No verificado**, y cada uno dice cómo revisarlo y qué hacer si falla.
