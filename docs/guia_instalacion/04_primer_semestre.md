# 4. Primer semestre

Todo lo de esta página se hace en el sitio, con la sesión iniciada (página 3, sección 3.8). La página «Configuración» tiene arriba el semestre activo y, debajo, pestañas agrupadas: «Tests semanales» (Alumnos, Preguntas), «Tareas» (Entregas, Feedback, Contexto), «La IA» (Prompts, Probar criterio, Parámetros) y «Registro» (Historial).

El instalador y su documentación llaman a esta página «Datos y Configuración»; en el menú del sitio aparece como «Configuración».

## 4.1 Revisar los parámetros

Los parámetros valen para todos los semestres. Conviene fijarlos antes del primer envío, incluso del primer envío simulado.

1. Abre «Configuración» y la pestaña «Parámetros» (grupo «La IA»).
2. **Grupos Control y Tratamiento.** El interruptor «Usar dos grupos (Control y Tratamiento)» viene prendido. Con él, cada alumno queda en uno de dos grupos al azar y recibe la versión de la pregunta de su grupo. Si el curso va a mandar la misma pregunta a todos, apágalo y haz clic en «Guardar» de esa sección. Decídelo ahora: el primer envío, simulado o real, asigna los grupos, y el grupo de un alumno no cambia después.
3. **Tutoría automática.** El interruptor «Responder dudas todos los días a las 18:00» viene apagado. Prendido, cada día a las 18:00 (hora de Santiago) el sistema responde por correo las dudas de los alumnos sobre su corrección. Déjalo apagado hasta terminar la sección 4.8.
4. **Modelo.** Por defecto, `gpt-5.4-mini`. El campo sugiere una lista de modelos conocidos. Si el instalador avisó que tu clave no ve ese modelo, elige o escribe otro que tu cuenta de OpenAI tenga disponible y haz clic en «Guardar».
5. **Precios de la API.** Sin precios, la página Inicio muestra el consumo en tokens. Para verlo en dólares, escribe los precios del modelo en US$ por millón de tokens, como los publica OpenAI, y haz clic en «Guardar».

## 4.2 Crear el semestre

1. Abre «Configuración». Sin semestres, la página muestra «Todavía no hay ningún semestre: crea el primero.» y la sección «Nuevo semestre…» abierta.
2. En «Identificador (ej. 2027-1)» escribe el semestre, por ejemplo `2027-1`. Admite letras, números, punto y guion.
3. Haz clic en «Crear y activar». El sitio copia la plantilla y deja ese semestre activo para todo el equipo.
4. Arriba aparece «Semestre activo» con `2027-1` y dos avisos: «⚠ falta la lista de alumnos» y «⚠ faltan las preguntas». Las dos secciones siguientes los resuelven.

Para probar el sistema sin tocar el semestre real, puedes crear antes un semestre `prueba` con una lista de alumnos que tenga solo tu correo, hacer en él las secciones 4.3 a 4.8, y después crear `2027-1` con «Nuevo semestre…» (como ya hay un semestre activo, el sitio pide confirmar el cambio). Cada semestre es independiente; el que está activo es el que usan los envíos.

## 4.3 Cargar la lista de alumnos

### El archivo

La lista es un archivo `alumnos.csv`: la primera fila tiene los nombres de las columnas, `Nombre` y `Correo`, escritos así, y después va un alumno por fila. Las columnas van separadas por coma.

```
Nombre,Correo
Ana Pérez Soto,ana.perez@ejemplo.cl
Bruno Díaz Rojas,bruno.diaz@ejemplo.cl
Carla Muñoz Vega,carla.munoz@ejemplo.cl
```

Hay dos columnas opcionales. `Grupo` no hace falta: con los grupos prendidos, el sistema la llena con `control` o `tratamiento` en el primer envío. `CorreosAlternativos` sirve para alumnos que responden desde otra cuenta; lleva esas otras direcciones separadas por punto y coma.

La forma más segura de armar el archivo es con Google Sheets:

1. En una hoja nueva, escribe `Nombre` en A1 y `Correo` en B1, y pega debajo la lista del curso.
2. Descárgala con «Archivo», «Descargar», «Valores separados por comas (.csv)».

Excel en español suele guardar los CSV separados por punto y coma. El sitio los muestra bien, pero el motor solo lee comas, y con punto y coma no encuentra a ningún alumno al enviar. Antes de subir un archivo hecho en Excel, ábrelo con el Bloc de notas: la primera línea tiene que ser exactamente `Nombre,Correo`.

### Subirlo

1. En «Configuración», abre la pestaña «Alumnos». Sin lista, muestra «Archivo no encontrado: alumnos.csv» y el botón «Subir alumnos.csv».
2. Haz clic en «Subir alumnos.csv» y elige el archivo.
3. Aparece la tabla con el aviso «Cargado desde tu archivo. Revísalo y guarda para aplicarlo.» Revisa que haya dos columnas, Nombre y Correo, y que la cantidad de filas del pie («N filas · 2 columnas · alumnos.csv») sea la del curso.
4. Haz clic en «Guardar cambios». Aparece «Guardado.» y, unos segundos después, «Guardado. Los resultados ya muestran los cambios.»

Para cambios posteriores, la misma pestaña permite editar cada celda, agregar una fila («+ Agregar fila»), quitarla (la × al final de la fila) o reemplazar la lista completa («Reemplazar con un CSV…»). Cada cambio se aplica con «Guardar cambios».

## 4.4 Cargar las preguntas

Las preguntas de todo el semestre van en un archivo `preguntas.csv`, con una fila por semana. Lo práctico es subir el archivo de ejemplo del sistema y editar cada semana en el sitio.

### Conseguir el archivo de ejemplo

Usa una de estas dos vías:

- En GitHub, abre `https://github.com/Mpalma325/proyecto-in5162/blob/master/semestres/_template/tests_semanales/data/preguntas.example.csv` y descárgalo con el botón de descarga del archivo («Download raw file»).
- En Cloud Shell, abre el menú «Más» (⋮) de la terminal y elige «Descargar» (Download). Escribe la ruta del archivo dentro de tu carpeta personal: `cloudshell_open/proyecto-in5162/semestres/_template/tests_semanales/data/preguntas.example.csv` si usaste el botón de la página 3, o `proyecto-in5162/semestres/_template/tests_semanales/data/preguntas.example.csv` si clonaste a mano.

### Subirlo

1. En «Configuración», abre la pestaña «Preguntas». Sin archivo, dice «Este semestre todavía no tiene preguntas.csv. Súbelo desde «Tabla completa».»
2. Haz clic en «Tabla completa». Aparece «Archivo no encontrado: preguntas.csv» y el botón «Subir preguntas.csv».
3. Haz clic en «Subir preguntas.csv», elige el archivo de ejemplo y haz clic en «Guardar cambios».

### Editar cada semana

1. Haz clic en «Por semana». A la izquierda aparece la lista de semanas.
2. Elige una semana y completa:
   - «Tema»: el tema de la semana.
   - «Fecha de entrega»: tal como debe aparecer en el correo, por ejemplo `lunes 16/03/2027, 10:15`. El sitio la usa también para avisar cuándo toca evaluar.
   - Cada pregunta tiene «Pregunta» (lo que recibe el alumno) y «Pauta (solo la ve la IA)» (lo que se espera en la respuesta). Con dos grupos, «Distinta para Control y Tratamiento» permite escribir una versión para cada grupo.
3. «+ Agregar pregunta» suma otra pregunta, hasta tres por semana. «+ Agregar semana» suma una semana.
4. Haz clic en «Guardar semana N».

Las semanas del ejemplo que no uses se quitan desde «Tabla completa», con la × de su fila y «Guardar cambios».

Si prefieres armar el archivo completo en una planilla, estas son sus 15 columnas, en este orden: `Semana`, `Tema`, `Fecha de Entrega`, `Control P1`, `Control P2`, `Control P3`, `Control Pauta P1`, `Control Pauta P2`, `Control Pauta P3`, `Tratamiento P1`, `Tratamiento P2`, `Tratamiento P3`, `Tratamiento Pauta P1`, `Tratamiento Pauta P2`, `Tratamiento Pauta P3`. Va separado por comas, igual que la lista de alumnos.

Con alumnos y preguntas cargados, el aviso de arriba cambia a «✓ Alumnos y preguntas cargados».

## 4.5 Revisar los prompts

Los prompts son las instrucciones que recibe el modelo. Ahí está la política de corrección del curso: la escala, los criterios y el tono de los comentarios.

1. En «Configuración», abre la pestaña «Prompts». Arriba hay una lista «Prompt» con el nombre de cada uno y su archivo entre paréntesis.
2. Revisa al menos los de Tests Semanales: «Cómo corrige la IA cada respuesta» (`evaluar_respuesta.md`; hoy da de 0 a 3 puntos por pregunta y la nota va de 4,0 a 7,0), «Correo con la pregunta de la semana» (`correo_pregunta.md`), «Correo con la corrección» (`correo_correccion.md`) y «Cómo responde la IA las dudas de los alumnos» (`tutoria.md`).
3. El nombre del curso y el del profesor ya están escritos donde corresponde. Si cambias algo, haz clic en «Guardar cambios»; vale desde el próximo envío o corrección.

Si editas `evaluar_respuesta.md`, deja las etiquetas `NOTA FINAL:` y `ORIGINALIDAD:` tal como están. El sistema lee la nota y la originalidad de la respuesta del modelo buscando esas etiquetas; sin ellas, la nota no se registra.

## 4.6 Simular el primer envío

1. Abre «Tests semanales» y la pestaña «1 · Enviar preguntas».
2. En «Número de semana» deja `1`. Debajo aparecen las preguntas de esa semana.
3. Comprueba que «Solo simular» esté marcado (viene marcado). El botón dice «Simular envío».
4. Haz clic en «Simular envío». El trabajo corre en el motor y su salida aparece en la página: las preguntas de cada grupo, un correo de ejemplo por grupo con el destinatario, y al final `Se enviaría a N alumno(s).`
5. Comprueba que N sea la cantidad de alumnos del curso y que el correo de ejemplo se vea como quieres.

La simulación no manda ningún correo. Sí deja asignados los grupos de los alumnos, si los grupos están prendidos.

Si la salida dice `Nada por enviar.`, el motor no encontró alumnos pendientes: revisa que la lista use comas (sección 4.3).

## 4.7 El primer envío real

1. En la misma pestaña, desmarca «Solo simular». El botón cambia a «Enviar preguntas» y aparece el aviso «Cada alumno pendiente recibe la pregunta por correo. No se puede deshacer.»
2. Haz clic en «Enviar preguntas». El sitio pide confirmar: «Vas a mandar la pregunta de la semana 1 a todos los alumnos que no la tienen. Son correos reales.» Confirma.
3. La salida muestra una línea con `✓` por cada alumno y termina con `N enviado(s), M fallido(s)`.

Si vuelves a pedir el envío de la misma semana, solo les llega a quienes todavía no la tienen (por ejemplo, alumnos agregados después).

## 4.8 Evaluar las respuestas

Los alumnos responden al correo de la pregunta. El sistema busca las respuestas entre los correos **sin leer** de la bandeja de entrada del correo del curso. Por eso:

- No abras en Gmail las respuestas de los alumnos antes de evaluar. Si abriste alguna, márcala como no leída.
- No muevas esas respuestas a otra carpeta ni las archives antes de evaluar. Revisa también la carpeta de spam y devuelve a la bandeja de entrada lo que haya caído ahí.

Después de la fecha de entrega:

1. Abre «Tests semanales» y la pestaña «2 · Evaluar respuestas», con la semana que corresponde.
2. Con «Solo simular» marcado, haz clic en «Simular evaluación». La salida empieza con `Módulo N — X respuesta(s) encontrada(s)` y muestra qué haría con cada una, sin llamar al modelo, sin mandar correos y sin marcar nada como leído. Al terminar, el sitio permite elegir qué respuestas evaluar de verdad.
3. Para evaluar de verdad, desmarca «Solo simular». El botón cambia a «Evaluar y mandar feedback». Haz clic y confirma. El modelo corrige cada respuesta, la nota queda guardada y cada alumno recibe su corrección por correo.

La pestaña «3 · Resumen semana» genera, con el modelo, un resumen de la semana para el equipo docente; no manda correos. La pestaña «Responder dudas» responde a mano las dudas de los alumnos sobre su corrección, con el mismo modo de simulación. Cuando el ciclo te deje conforme, puedes prender la tutoría automática en Parámetros (sección 4.1).

La página «Resultados» muestra las notas, la tasa de respuesta y la comparación entre grupos del semestre. Las tareas grupales se operan desde la página «Tareas».
