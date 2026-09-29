# Módulo `tareas`

El flujo de las Tareas de código: a partir del HTML que entrega cada grupo,
genera **una pregunta distinta por integrante** sobre la parte del trabajo que
le tocó, se la envía, recolecta la respuesta y la corrige.

La pregunta es personalizada a propósito: así un alumno no puede responder
copiándole a un compañero, porque a cada uno le preguntan por otro fragmento.

## Qué hace y qué no

**Sí:** limpiar el HTML entregado, extraer el código y la tabla de roles, armar
el prompt que genera las preguntas, emparejar nombres con correos y coordinar
el registro.

**No:** hablar SMTP/IMAP, llamar a la API ni escribir CSV a mano. Como flujo,
sí importa a `mail`, `ia` y `datos`.

## Los pasos

| Archivo | Qué hace |
|---|---|
| `chequeo.py` | Dice qué pasaría al generar, sin llamar al modelo |
| `generar.py` | Lee los HTML y genera pregunta + pauta por integrante |
| `enviar.py` | Manda cada pregunta a su alumno |
| `recolectar.py` | Busca las respuestas en el buzón, por Message-ID |
| `corregir.py` | Corrige y manda el feedback |

Auxiliares: `limpieza_html.py` (extrae secciones del entregable),
`alumnos.py` (empareja nombres del HTML con correos del roster),
`storage.py` (el `feedback_T*.csv`), `asignacion.py` (qué pregunta le toca a
cada uno cuando el grupo no declaró roles), `ia_prompts.py`, `config.py`.

## Cómo se ejecuta

Desde la raíz del proyecto:

```
python -m modulos.tareas.chequeo T1
python -m modulos.tareas.generar T1
python -m modulos.tareas.enviar T1
python -m modulos.tareas.recolectar T1
python -m modulos.tareas.corregir T1
```

## Lo que llega de U-Cursos

La descarga es un zip con un comprimido por alumno adentro. Cada uno trae el
HTML renderizado, el `.Rmd`, los datos y a veces basura de macOS, y varios
grupos entregan su HTML con el mismo nombre. De eso se encarga
`app/utils/runner.py`, que entra a los comprimidos anidados, prefija cada
archivo con el nombre del grupo para que no se pisen, y guarda el `.Rmd` con el
mismo nombre base que su HTML. Lo que no reconoce lo informa en pantalla.

Algunos alumnos entregan `.rar`. No hay lector de rar en la biblioteca estándar,
así que se usa el `tar` de Windows, que trae libarchive y lee RAR4 y RAR5 sin
instalar nada. Va por ruta explícita a `System32`: si el PATH tiene primero el
`tar` de Git Bash, ese es GNU tar y no abre rar. Fuera de Windows se buscan
`unar` y `unrar`; si no hay ninguno, la entrega se reporta en vez de perderse.

## Cuando el entregable no viene como se espera

En T1 de 2026-2, cuatro de trece entregas no calzaban con el template, y por eso
el paso 1 revisa antes de llamar al modelo.

Los ids de sección que genera RMarkdown dependen del encabezado que escribió el
grupo, así que `pregunta-1` no siempre existe: apareció como `desarrollo-p1`,
como `p1`, y hubo un grupo que reemplazó los títulos por los suyos. Se prueban
las tres formas, y cuando no hay ancla para la pregunta 1 se corta desde el
inicio del desarrollo.

La tabla de roles se busca por su caption, pero el caption también aparece
dentro del bloque de código cuando el grupo entrega con `echo=TRUE`. Buscando
desde la primera ocurrencia se agarra la tabla anterior, que es cualquier tabla
de resultados; por eso se recorren las ocurrencias desde la última y se valida
que la tabla encontrada tenga cara de tabla de roles antes de aceptarla.

Un grupo puede no llenar la tabla y dejar `Integrante 1`, o dejar una fila
`Null`. Los nombres del template se descartan uno a uno, sin botar al resto del
grupo. Cuando ninguno sirve, los integrantes salen del campo `author` del
documento, que RMarkdown deja en un `<meta>` del HTML.

También pasa que el HTML se renderizó antes de escribir el código y queda con
los comentarios del template mientras el trabajo está en el `.Rmd` de al lado.
Si el `.Rmd` trae más contenido, se usa ese.

Una entrega se salta, sin gastar API, cuando no se pudo recortar ninguna de las
cuatro preguntas, cuando suma menos de 8.000 caracteres, o cuando no hay forma
de saber quiénes son los integrantes.

## Antes de gastar la API

`chequeo` recorre las entregas y deja en pantalla lo mismo que haría `generar`,
pero sin llamar al modelo: cuánto se recortó de cada pregunta, de dónde salieron
los integrantes, quién no resuelve a un correo y con qué candidatos, qué se va a
saltar y por qué, y quién del roster queda sin pregunta. Como no cuesta nada, se
puede correr las veces que haga falta mientras se arreglan las entregas.

Ese mismo informe es lo primero que muestra la pestaña 1 de la app, antes del
botón de generar. El cálculo vive acá y la app solo lo dibuja, así que la
terminal y la pantalla no pueden discrepar.

En el listado de quién queda sin pregunta cae también el equipo docente, si está
en el roster. Hay que leer la lista, no contarla.

## Preguntas cuando no se sabe quién hizo qué

Sin tabla de roles no hay cómo saber qué le tocó a cada uno. En vez de dejar al
grupo sin preguntas, el flujo reparte P1 a P4 entre los integrantes y le indica
al modelo sobre cuál interrogar a cada uno. El reparto lo decide el flujo y no
el modelo, con el nombre del archivo como semilla, así que dos corridas sobre la
misma entrega asignan lo mismo.

Lo mismo corre para quien declaró solo interpretación o redacción en las cuatro
preguntas y quedaría sin nada que responder: se le asigna una pregunta en una
segunda pasada.

Lo que salga del sorteo se puede cambiar desde la pestaña 1, con un selector por integrante, y queda guardado en
`entregas/<TAREA>/asignacion_<TAREA>.csv`. `generar` lee ese archivo y lo pone
encima del sorteo: manda lo que esté ahí, y lo que no esté se reparte como
siempre. Un valor que no sea P1 a P4 se ignora y queda el sorteo. El archivo
aparece solo cuando alguien tocó la asignación, así que no existir es lo
normal.

## Cuidado

**`paso2` y `paso4` mandan correos reales.** Ambos aceptan `--dry-run`.

El emparejamiento de nombres del paso 1 usa similitud de texto y **se equivoca**
con nombres parecidos: ya pasó con dos alumnos que compartían el primer nombre.
Cuando no encuentra coincidencia clara lo deja en blanco y hay que resolverlo a
mano en el CSV antes del paso 2. No conviene bajarle el umbral para que "acierte
más": es peor mandarle la pregunta al alumno equivocado que dejarla pendiente.

Sobre el umbral hay una excepción que sí es segura. El caso más común es que el
alumno firme con su nombre y un apellido mientras el roster trae dos, lo que
deja la similitud entre 0,72 y 0,81: nueve de treinta y cinco en T1. Esos se
aceptan por contención, no por parecido: todos los tokens del nombre escrito
tienen que estar en el del roster, tienen que ser al menos dos, y ningún otro
alumno puede cumplir lo mismo. Pedir dos tokens deja fuera el apellido suelto,
que es justo donde el emparejamiento se equivoca, y la unicidad evita elegir
entre dos alumnos que comparten el primer nombre. En T1 quedó a mano un grupo
que firmó solo con apellidos, y uno de esos apellidos lo tenían dos alumnos
distintos.
