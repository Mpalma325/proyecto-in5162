# Diseño: instancias, revisión docente y escala de notas

> **Decisiones al 19/11/2026 (mandan sobre el resto del documento).** Este diseño es del 02/11 y se recuperó de la transcripción de esa sesión.
>
> - **Nombres de instancia (reemplaza las decisiones 1 y 9).** Cada instancia tiene un tipo que elige el docente («Control», «Test», «Evaluación», «Instancia» u otro) y un número automático que cuenta las instancias de ese tipo: «Control 1», «Control 2», «Test 1». No hay semanas: cada instancia tiene fecha y hora de envío y de cierre, y puede haber varias en un mismo día. Por dentro sigue un id entero que el docente no ve. Propuesta pendiente de confirmar: el asunto del correo lleva el nombre visible y la respuesta se reconoce por In-Reply-To, con el nombre del asunto como respaldo; 2026-2 conserva «Módulo N».
> - **3. Revisión:** la nota cuenta solo cuando el docente la acepta y sale el correo. Aprobada.
> - **4. Tutoría:** automática, como está (el usuario cree que nadie la usó).
> - **5.** 2026-2 ya cerró: no se toca.
> - **6.** Tareas mantiene su escala. Su revisión docente ya existe desde 5f35641; la sección 2.7 hay que adaptarla a eso.
> - **7. Streamlit:** fuera del diseño; no se usa para nada.
> - **8. Correo de semestre nuevo:** puntajes y nota (02/11).
> - **Escala:** transformación lineal (02/11). **2 (confirmación)** y el detalle de la escala: pendientes de confirmar tras explicarlos de nuevo el 19/11.

Puntos 3, 4 y 7 de `PENDIENTES_PO.md`, diseñados juntos porque los tres cambian cómo se guarda una corrección. Fecha: 02/11/2026. Rutas relativas a la raíz del repo. Leí código y la plantilla; de los semestres reales solo miré nombres de columnas y tamaños de archivo. Dejé fuera los cambios en curso del otro agente (`modulos/ia/cliente.py`, `web/public/consumo.js`, `motor/desplegar.ps1`, cabeceras), salvo para marcar dónde hay que coordinarse. No ejecuté pruebas.

Al final (sección 10) está la respuesta, punto por punto, a los 42 hallazgos de `critica_previa.md`, y en la sección 11 dónde quedó cada uno de los 37 puntos de la segunda revisión.

Convención de nombres: «instancia» nombra el concepto y el código (columna `Instancia`, argumento `instancia`). Los textos de pantalla usan la palabra de la decisión 9, hoy «Test»; la sección 9 dice qué cambia si se elige otra.

Los números de línea de `web/public/comun.js`, `datos.js`, `app.js`, `consumo.js`, `modulos/ia/cliente.py`, `motor/desplegar.ps1` y `web/public/_headers` son los del árbol de trabajo del 02/11, con cambios sin commitear de otro agente (costo real y seguridad); pueden moverse. Los demás coinciden con `HEAD` (205d735).

## 0. Las ideas que sostienen el diseño

1. **Una instancia es una fila de `preguntas.csv` con un id entero correlativo.** El id sigue siendo el `Item` de `notas.csv`, del log y del panel, así que ningún dato existente se reescribe. Lo nuevo (título, fechas, estado) va en columnas opcionales. Un archivo sin esas columnas se lee como hoy y cada fila se titula «Semana N».
2. **«Tener Nota» sigue significando «se le mandó el feedback con esa nota».** La corrección que espera revisión no escribe `Nota`. Se marca con una columna nueva, `Corregido`, y su propuesta vive en un evento nuevo del log, `correccion`. Una corrección descartada se cierra con `Descartada` y el evento `descarte`. Los lectores que deciden «¿hay que corregir a este alumno?» pasan a un predicado común, `ya_corregido` (Corregido, Nota o Descartada), y los que deciden «¿hay nota?» (Resultados, panel, `reconstruir_estado`) no cambian.
3. **El evento `evaluacion` sigue siendo «se envió el feedback»** y guarda lo que efectivamente salió: el bloque enviado, la nota final y el `MessageId`. Tutoría, `_es_repregunta`, el panel y el historial de prompts siguen leyendo `evaluacion` sin cambios.
4. **Lo que escriben las personas y lo que escriben los trabajos van en archivos distintos.** Hoy ningún archivo de `EDITABLES` lo escribe un trabajo (`web/src/index.ts:100-110`), y por eso la subida con etag del motor (`motor/trabajo.py:441-462`) nunca choca con una edición de la página. El diseño mantiene esa regla: las decisiones del docente van en `revision/<id>.json` (solo la página), y notas, log y escala los escriben solo los trabajos.
5. **El código calcula la nota.** El modelo entrega puntajes por pregunta. El código calcula el logro (puntaje obtenido / puntaje máximo, entre 0 y 1) y la nota con la escala del semestre. Con la escala 4,0–7,0 la fórmula da exactamente lo mismo que el prompt actual: `4 + 3·Σp/(3n) = 4 + promedio(p)` (`semestres/_template/tests_semanales/prompts/evaluar_respuesta.md:28-38`).
6. **2026-2 no cambia de comportamiento en ninguna fase.** Sin `escala_notas.json` rige 4,0–7,0 con un decimal; sin `configuracion.json` la revisión está apagada; su prompt actual (HTML con `NOTA FINAL`) se sigue leyendo con el extractor de hoy.

## 1. Modelo de datos

### 1.1 Instancias: `tests_semanales/data/preguntas.csv` ampliado

Se conserva el archivo y sus 15 columnas. Se agregan columnas opcionales; el editor de la página ya conserva las columnas que no conoce, porque reemplaza celdas dentro de la fila completa (`web/public/preguntas.js:100-120`), y Python lee con `DictReader`, que ignora las que no usa (`modulos/tests/preguntas.py:50-58`).

Columna del id: `Instancia` o, en archivos existentes, `Semana`. Los lectores aceptan las dos; los archivos nuevos que crea el editor usan `Instancia`. Un archivo con las dos es un error visible.

Columnas nuevas, todas opcionales:

- `Titulo`: lo que ve el docente («Semana 3», «Control 2a»). Vacío o ausente equivale a «Semana N» en archivos con columna `Semana` y a «Test N» en los que usan `Instancia`.
- `Envio`: fecha de envío prevista, ISO (`2026-11-09` o `2026-11-09T09:00`). Sirve al ciclo de Inicio y Tests; el envío sigue siendo manual (programarlo es otro pendiente, `PENDIENTES_PO.md:95`).
- `Estado`: `borrador` o `confirmada`. Ausente equivale a confirmada, para que los semestres existentes sigan enviándose.
- `Confirmada`: quién y cuándo, texto (`correo · 2026-11-02T10:15`). Lo escribe la página al confirmar; la edición queda además en `ediciones`.

`Fecha de Entrega` sigue siendo texto libre: es lo que se le muestra al alumno en `{FECHA_ENTREGA}` (`modulos/tests/enviar.py:45`) y lo que ya interpreta `fechaEntrega` en el ciclo (`web/public/ciclo.js:71-75`).

Regla del id, igual en todas partes: `^[1-9][0-9]{0,2}$` (1 a 999). Correlativo, nunca se reutiliza, sin relación con la semana del calendario: la 5 y la 6 pueden caer en la misma semana. Una fila con id inválido o repetido es un error que se muestra; hoy Python la descarta en silencio (`modulos/tests/preguntas.py:53-57`) y la página la trunca con `parseInt` (`web/public/preguntas.js:30-33`).

Cómo se garantiza que un id no se reutilice. Hoy `agregarSemana` toma el máximo de `preguntas.csv` más uno (`web/public/preguntas.js:123-125`), y en «Tabla completa» (`web/public/datos.js:228-242`) se puede borrar cualquier fila: si se borra la última instancia ya enviada, la siguiente hereda sus `Item` en `notas.csv`, el log y el panel. Dos reglas:

- El siguiente id es `max(ids de preguntas.csv, Item de tests en notas.csv) + 1`. `agregarInstancia` recibe además los `Item` de `notas.csv`, que la página ya lee para el ciclo (`web/public/ciclo.js:45-63`).
- No se puede borrar una instancia con envíos. El editor no ofrece borrar una instancia que tenga alguna fila con `Enviado` en `notas.csv`, y «Tabla completa» rechaza el guardado si desaparece un id con envíos («el test 4 ya se envió a 52 alumnos; no se puede borrar»). Una instancia que falta en `preguntas.csv` pero tiene filas en `notas.csv` (archivo editado fuera de la página) se sigue mostrando en Resultados como «Test N», sin título.

Límites que se mantienen y quedan escritos: dos grupos (control y tratamiento) y hasta tres preguntas por grupo (`modulos/tests/preguntas.py:66-75`, `web/public/preguntas.js:14-20`). Una pregunta puede tener subpreguntas (a, b, c) dentro del enunciado, como hoy.

Archivo ausente o con solo la cabecera: «todavía no hay tests». `cargar_semana` levanta un error claro («el test 5 no existe; créalo en Preguntas») y ya no `FileNotFoundError` con la instrucción de poner un CSV (`modulos/tests/preguntas.py:44-48`). La plantilla trae `preguntas.csv` con solo la cabecera nueva, además del `.example`.

### 1.2 Configuración del semestre: `configuracion.json` (raíz, la escribe la página)

```json
{
  "revision": "auto",
  "correo_muestra": "nota"
}
```

- `revision`: `auto` (corregir y enviar en el mismo trabajo, como hoy) o `revisar` (corregir y dejar borradores). Ausente equivale a `auto`. Al evaluar se puede cambiar para esa corrida (argumento del trabajo).
- `correo_muestra`: qué números ve el alumno en el correo de corrección de Tests: `nota` (puntaje por pregunta y nota, como hoy), `puntajes` (solo puntaje por pregunta) o `nada` (solo comentarios y originalidad). Ausente equivale a `nota`. No aplica a Tareas: su correo (`tareas/prompts/correo_feedback.md`, con `{nota}` y `{ajuste}`) muestra el ajuste con signo, que es lo que el alumno necesita saber (decisión 6).

Va en la raíz porque el motor baja los `.json` de la raíz en todos los perfiles (`motor/trabajo.py:213-224`). Se agrega a `EDITABLES` como `^configuracion\.json$`. Es por semestre, a diferencia de `parametros`, que es global (`web/schema.sql:56-61`).

«Ausente» describe a los semestres que ya existen (2026-2 y anteriores), que siguen como hoy. Los semestres nuevos no dependen del valor por defecto: la plantilla trae `semestres/_template/configuracion.json` con lo elegido en la decisión 8 (recomendado: `{"revision": "auto", "correo_muestra": "puntajes"}`). El sitio copia también los archivos de la raíz de la plantilla al crear un semestre (`web/src/index.ts:606-617` lista todo el prefijo `semestres/_template/`). La revisión parte en `auto` porque el product owner la pidió como «paso intermedio opcional» (`PENDIENTES_PO.md:51`). Cómo llega a R2: 4 y R8.

### 1.3 Escala: `escala_notas.json` (raíz, lo escribe solo el trabajo `datos.escala`)

```json
{
  "tipo": "lineal",
  "minima": 4.0,
  "maxima": 7.0,
  "decimales": 1,
  "aprobacion": null,
  "exigencia": null,
  "puntaje_maximo_pregunta": 3
}
```

- Lineal: `nota = minima + logro × (maxima − minima)`.
- Dos tramos (opcional, la escala chilena con exigencia): si `logro < exigencia`, `nota = minima + (aprobacion − minima) × logro / exigencia`; si no, `nota = aprobacion + (maxima − aprobacion) × (logro − exigencia) / (1 − exigencia)`. Con 1,0 / 4,0 / 7,0 y exigencia 0,6 es la escala del 60 %.
- Redondeo: `Decimal` con `ROUND_HALF_UP` a `decimales` (0, 1 o 2), y se escribe con coma («6,5», «83»). `round()` de Python redondea al par y daría 5,2 para 5,25.
- Inversa (nota → logro): existe en los dos tipos y se usa para el legado y para ajustes.
- Ausente: rige el valor de arriba (4,0–7,0, un decimal), que reproduce las notas de hoy.

La escala solo aplica a Tests. Tareas sigue con lo suyo (`modulos/tareas/escala.py:9-23`: `tareas/escala.json` o `NOTA_MIN`/`NOTA_MAX`), y por eso la escala de tests no reutiliza esos nombres ni el formulario «Escala de las tareas» (`web/public/datos.js:1047-1084`).

¿Por qué la escribe un trabajo y no la página? Porque cambiarla obliga a recalcular `notas.csv`, que solo escriben los trabajos. Si la página guardara la escala y otro paso recalculara, habría un rato con notas en una escala y gráficos en otra. El trabajo `datos.escala` escribe la escala y recalcula en la misma corrida, en la cola de uno en uno.

### 1.4 `notas.csv`

`COLUMNAS_NOTAS` (`modulos/datos/esquema.py:23-28`) pasa a:

`Correo, Flujo, Item, Enviado, Respondio, Nota, Originalidad, Corregido, Logro, Descartada`

- `Corregido`: ISO, cuándo quedó la corrección (del modelo o del docente). Con `Nota` vacía significa «corregida, sin enviar».
- `Logro`: de 0 a 1 con cuatro decimales, para tests. Vacío en las filas viejas, en tareas y en ajustes fuera de escala.
- `Descartada`: ISO, cuándo un trabajo registró el descarte decidido en Revisar (2.3). Cierra la casilla sin nota y sin feedback.

Estados derivados, que calculan igual Python (`modulos/sabana.py:102-107`) y la página (`web/public/ciclo.js:45-63`):

- sin enviar: sin `Enviado`.
- sin responder: con `Enviado`, sin `Respondio`.
- sin corregir: con `Respondio`, sin `Corregido`, `Nota` ni `Descartada`.
- por revisar: con `Corregido`, sin `Nota` ni `Descartada`. Incluye las del modo automático cuyo envío falló («corregida, sin enviar»).
- descartada: con `Descartada` y sin `Nota`. Cuenta como cerrada: no entra a «por revisar» ni a «sin corregir», ni a las notas.
- con nota: con `Nota`. Es lo único que entra a Resultados, como hoy.

Un solo predicado decide si a un alumno hay que corregirlo: `notas.ya_corregido(correo, flujo, item)` = tiene `Corregido`, `Nota` o `Descartada`. Lo usan `evaluar.main` (paso 3 de 2.2), los candidatos de la simulación (2.2), `tests.chequeo` (2.8) y los pendientes de `tareas.corregir` (2.7). `ya_evaluado` (`modulos/datos/notas.py:92-95`) sigue significando «tiene nota» para quien pregunta eso.

`_csv.escribir` (`modulos/datos/_csv.py:22-32`) cambia en dos cosas:

- Conserva las columnas que el archivo ya tenga y que el llamador no conozca, como hace `fusionar` (`modulos/datos/log.py:335-342`). Hoy las descarta, y una copia vieja del código borraría `Corregido` y `Logro` al escribir.
- Escribe a `<archivo>.tmp` y termina con `replace`, como ya hace `_ampliar_columnas` (`modulos/datos/_csv.py:61-67`). Hoy abre con `"w"` y escribe encima; `_upsert` reescribe `notas.csv` entero en cada cambio (`modulos/datos/notas.py:50-67`), y si el proceso muere a mitad (por ejemplo, el corte de los 25 minutos, 2.2), queda truncado y `_guardar` lo sube igual (`motor/trabajo.py:441-462`, `:515-519`).

### 1.5 `log_envios.csv`: eventos y columnas

Columnas nuevas al final de `COLUMNAS_LOG` (`modulos/datos/esquema.py:44-61`): `Puntajes` (por ejemplo `3;2;0.5`) y `Logro`. El log se amplía solo con `_ampliar_columnas` (`modulos/datos/_csv.py:43-67`).

Eventos (`modulos/datos/esquema.py:34-42`), con lo que cambia:

- `respuesta`: ahora guarda `MessageId` (el Message-ID del correo del alumno) y `RespondeA` (su In-Reply-To, que es el `MessageId` de nuestro `envio`). Con eso el envío diferido sabe con qué hilar y un correo ya procesado se reconoce. `lectura.buscar_no_leidos` ya entrega los dos datos (`modulos/mail/lectura.py:65-66`). Un segundo correo del mismo alumno a la misma instancia, que recibe el correo de duplicado (2.2, paso 3), también se registra como `respuesta`, con su `MessageId` y `Detalle=duplicado`; así la tarjeta de Revisar puede decir «respondió otra vez el 03/11» y mostrar ese texto, y el paso 1 de 2.2 lo reconoce si vuelve a aparecer sin leer. Todo lector que toma «la respuesta» del alumno toma la primera sin `Detalle=duplicado`: `reconstruir_estado` (`Respondio`), `como_interacciones` (`modulos/datos/log.py:183-216`), la sábana (`modulos/sabana.py:55-62`) y la tutoría (`modulos/tests/tutoria.py:100-102`, que ya toma la primera).
- `correccion` (nuevo): la propuesta. `Modelo` (o `docente:<correo>` si la escribió una persona), `Versiones`, `TokensEntrada`, `TokensSalida`, `Puntajes`, `Logro`, `Nota` calculada, `Originalidad`, `EvaluacionIA` (la salida cruda del modelo: JSON en el formato nuevo de Tests, HTML en el viejo, y en Tareas el JSON completo, con `señales_copia_ia` y `justificacion_interna`, que hoy se imprimen y se pierden, `modulos/tareas/corregir.py:163-179`) y `Detalle` (`modo=auto` o `modo=revisar`). Los tokens van solo aquí.
- `descarte` (nuevo): el docente decidió no mandar feedback. `Detalle` con el motivo y quién (`motivo; por X`). Lo registra el trabajo de feedback al leer la decisión (2.3), nunca la página.
- `evaluacion`: el feedback que salió. `MessageId` del correo enviado, `Nota` y `Puntajes` finales, `Logro`, `Originalidad`, `EvaluacionIA` = el bloque que se insertó en `{EVALUACION}`, ya sin los números que el semestre oculta. Copia `Modelo` y `Versiones` de la corrección y agrega la huella de la plantilla del correo y la escala (`escala=4-7/1`). `Detalle`: `auto`, o `revisado por X; puntajes 2;3 → 3;3` cuando el docente cambió algo. Sin tokens.
- `ajuste`: igual que hoy, y además `Logro` y, si se avisó, `MessageId` del aviso.
- `recalculo` (nuevo): cambio de nota por cambio de escala. `Nota`, `Logro`, `Detalle` (`escala 4-7/1 → 1-7/1 60 %; por X`).

`DEL_AGENTE` (`modulos/datos/esquema.py:65`) suma `ajuste`: solo calza cuando el ajuste trae `MessageId`, es decir, cuando se avisó. `correccion` no entra, porque no le llega al alumno.

`DEL_AGENTE` mezcla flujos. Hoy no se nota porque el `evaluacion` de Tareas no guarda `MessageId` (`modulos/tareas/corregir.py:167-173`, `:188`). Desde que 2.7 lo guarde, un alumno que conteste su feedback de T1 caería en `tests.tutoria`: `cargar_semana(int("T1"))` (`modulos/tests/tutoria.py:112`) levanta `ValueError`, se registra un `error` con flujo `test` e ítem `T1` (`:120-123`), el correo queda sin leer y se repite cada día a las 18:00 (`web/src/index.ts:443-452`); `reconstruir_estado` crearía además una casilla `(correo, test, T1)`. Por eso `fila_por_message_id` (`modulos/datos/log.py:101`) gana el filtro `flujo=`, y lo usan con `flujo=TESTS` `tutoria._pendientes` (`modulos/tests/tutoria.py:57`) y `evaluar._es_repregunta` (`modulos/tests/evaluar.py:143`). Las dudas sobre feedback de Tareas no tienen tutoría automática en este diseño: quedan sin leer en el buzón, como hoy, y la salida de `tests.tutoria` las cuenta aparte («2 respuestas a feedback de Tareas: sin tutoría automática; revisar en Gmail»). El filtro entra en la fase 1, antes de que exista el `MessageId` de Tareas.

`reconstruir_estado` (`modulos/datos/log.py:64-92`): `correccion` llena `Corregido` y `Logro`; `descarte` llena `Descartada`; `evaluacion`, `ajuste` y `recalculo` llenan `Nota` (el último manda); `respuesta` con `Detalle=duplicado` no toca `Respondio`. Además guarda, por casilla, la lista ordenada de notas que el log fue dejando (`historia_nota`), que usa la sincronización.

`sincronizar_desde_log` (`modulos/datos/notas.py:108-160`) suma `Corregido`, `Logro` y `Descartada` a los campos que completa. Hoy nunca pisa un valor escrito (`:145-153`), así que un `recalculo` o un `ajuste` que llega por `poner_al_dia` o `fusionar` (`modulos/datos/poner_al_dia.py:102`, `modulos/datos/fusionar.py:49`) no actualiza `Nota`. La regla nueva distingue «la tabla va atrasada» de «alguien la editó a mano», que es lo que el docstring protege: si la `Nota` de la tabla es una de las notas anteriores de `historia_nota` (no la última), se reemplaza por la última, con su `Logro`; si es un valor que el log nunca tuvo, es una edición a mano y no se toca, como hoy. El resumen cuenta aparte las notas puestas al día por esta regla. `modulos/datos/comparar.py:99` y `:138` suman `Corregido`, `Logro` y `Descartada` a las columnas que comparan.

### 1.6 Decisiones de revisión: `tests_semanales/revision/<id>.json` y `tareas/revision/<T>.json`

Las escribe solo la página. Se agregan a `EDITABLES` con `^(tests_semanales/revision/[1-9][0-9]{0,2}|tareas/revision/T\d{1,2})\.json$`. Cada guardado pasa por `subirArchivo`, que deja la versión anterior en `historial/` y una fila en `ediciones` (`web/src/index.ts:277-308`): la auditoría de cada edición viene gratis.

```json
{
  "alumno@uchile.cl": {
    "estado": "aprobada",
    "base": "2026-11-02T09:41:07-03:00",
    "puntajes": [3, 2],
    "justificaciones": ["…", "…"],
    "originalidad": "Media",
    "retroalimentacion": "…",
    "nota_legado": null,
    "html_legado": null,
    "manual": false,
    "por": "profe@uchile.cl",
    "cuando": "2026-11-02T10:15:00-03:00"
  }
}
```

- `estado`: `aprobada` (lista, espera el botón grande), `enviar` (aprobada y pedida ahora), `descartada` (no se manda feedback; con motivo en `retroalimentacion`). «Por revisar» es la ausencia de entrada; «enviada» y «descarte registrado» se deducen de `notas.csv` y del log (`Nota`, `Descartada`), nunca se escriben aquí. Un `descartada` todavía no registrado se puede deshacer en la página («Volver a revisar»); una vez que el trabajo lo registró, la casilla está cerrada y la única forma de darle nota es un ajuste (2.4).
- `base`: el `Timestamp` de la fila `correccion` sobre la que se editó, copiado tal cual del log (por ejemplo `2026-11-02T09:41:07-03:00`, que `log.registrar` escribe con segundos, `modulos/datos/log.py:21-22`). La entrada ya está bajo el correo y el id del archivo, así que el `Timestamp` basta para identificar la corrección. Python y JS leen la misma cadena del mismo CSV y la comparan sin normalizar, sin el riesgo de una huella de texto que un lado limpie distinto (`web/public/criterio.js:50-55` normaliza `\r\n` y bordes). Si aparece una corrección más nueva, la decisión queda vieja: el trabajo la ignora y la página pide revisar otra vez. Una prueba lee el mismo log con los dos lados y compara los valores (5 › Pruebas).
- `manual`: `true` cuando la corrección es de `docente:*` («Las corrijo yo»). Esa entrada solo se envía con `estado: enviar` y `puntajes` (o `nota_legado`) completos (2.3).
- Campos del formato nuevo: `puntajes`, `justificaciones`, `originalidad`, `retroalimentacion`. Solo se guardan los que el docente cambió; lo demás sale de la corrección.
- Campos del legado (2026-2, prompt HTML): `nota_legado` y `html_legado`. Ver 1.7.
- Concurrencia: cada guardado toca un alumno. Si `subirArchivo` responde 409 porque otro docente guardó antes, la página vuelve a leer, reaplica solo ese alumno y reintenta una vez.

Por qué R2 y no una tabla de D1 (la crítica, punto 16, proponía D1): todo el flujo de Python lee y escribe archivos del semestre y se prueba sin red (`pruebas/e2e_tests_semanales.py`); con D1, el trabajo de envío y las pruebas necesitarían endpoints nuevos del sitio y un doble del sitio en las pruebas. La objeción de fondo de la crítica, que la página y un trabajo escriban lo mismo, se resuelve con la separación de 0.4: el trabajo solo lee este archivo. Y la página no lanza un trabajo por cada edición: escribe directo.

### 1.7 Formato de la corrección del modelo

Formato nuevo (semestres que estrenen el prompt nuevo). El modelo devuelve JSON, como ya hace Tareas (`modulos/tareas/corregir.py:79`, `response_format={"type": "json_object"}`):

```json
{
  "preguntas": [
    {"rotulo": "P1", "respuesta": "…", "puntaje": 2, "justificacion": "…"},
    {"rotulo": "P2", "respuesta": "…", "puntaje": 3, "justificacion": "…"}
  ],
  "originalidad": "Media",
  "justificacion_originalidad": "…",
  "retroalimentacion": "…"
}
```

No trae puntaje total ni nota. El código (módulo nuevo `modulos/tests/correccion.py`):

- valida cada `puntaje` contra la rúbrica (0; 0,5; 1; 2; 3) y contra `puntaje_maximo_pregunta`;
- compara el número de bloques con las preguntas no vacías del grupo; menos bloques que preguntas es un aviso en la salida y en la tarjeta de revisión (el modelo juntó preguntas, cosa medida en `modulos/tests/experimento.py:226-228`);
- calcula `logro = Σ puntaje / (3 × bloques)` y la nota con la escala;
- arma el HTML del correo según `correo_muestra`. El mismo armado existe en JS (`web/public/correccion.js`) para la vista previa de la revisión, y una prueba compara las dos salidas sobre los mismos casos, como ya se hace con el asunto (`pruebas/web.py:247-253`). Con `correo_muestra: nota` el bloque conserva las etiquetas de hoy (`EVALUACIÓN: x / 3` por pregunta y una línea `NOTA FINAL: 6,5`), para que `reconstruir` (`modulos/tests/reconstruir.py:433-441`), `extraer_nota_y_originalidad` y `evaluacionDeTexto` (`web/public/comun.js:243`) sigan leyendo el correo enviado;
- arma el texto para el docente (`correccion.texto_docente`): puntajes, justificaciones, nota y originalidad, siempre con la línea `NOTA FINAL`, haya visto o no el alumno los números. Lo usan el resumen (2.8) y Probar criterio (5 › Tests).

Formato viejo (2026-2 y anteriores): el HTML con `NOTA FINAL`. `extraer_nota_y_originalidad` (`modulos/tests/evaluar.py:28-48`) se conserva tal cual. El `Logro` se calcula con la inversa de la escala vigente (`(nota − 4) / 3` con 4–7). En revisión, el docente edita la nota y el texto: la página reescribe la línea `NOTA FINAL` del HTML con la nota nueva (si no, el correo diría otra nota) y deja editar el HTML completo en un área de texto. Con `correo_muestra` distinto de `nota`, el armado quita del HTML las líneas `EVALUACIÓN: x / 3`, `PUNTAJE TOTAL` y `NOTA FINAL`.

Cuál formato es se decide por el contenido: si la salida es un JSON con `preguntas`, es el nuevo; si no, el viejo. Cada semestre conserva su prompt en R2, así que conviven sin configuración.

### 1.8 D1

- `panel` (`web/schema.sql:14-33`): `ALTER TABLE panel ADD COLUMN Logro REAL; ADD COLUMN NotaModelo REAL; ADD COLUMN PorRevisar INTEGER; ADD COLUMN Descartada INTEGER;`. `NotaModelo` es la nota de la última `correccion` (o de la `evaluacion` en filas viejas). `PorRevisar` es el estado «por revisar» de 1.4: con `Corregido`, sin `Nota` ni `Descartada`. `Descartada` es el estado «descartada»: sin ella, una casilla descartada (con `Respondio`, sin `Nota`, sin `PorRevisar`) se vería en Resultados como «sin corregir». `PorRevisar` y `Descartada` van a `BOOLEANAS` (`web/src/index.ts:66`). Las cuatro se agregan al final de `COLUMNAS` (`web/src/index.ts:59-63`) y de `reportes.panel` (`modulos/datos/reportes.py:97-114`) en el mismo orden.
- `trabajos.argumentos`: los trabajos nuevos usan `{"instancia": 5}`; el motor y la página siguen leyendo `semana` en los viejos.
- `parametros`: no cambia. Escala y revisión son por semestre y viven en R2.
- No hay tabla nueva.

### 1.9 Quién escribe qué

- Solo la página: `preguntas.csv`, prompts, `alumnos.csv`, `configuracion.json`, `revision/*.json`.
- Solo los trabajos: `notas.csv`, `log_envios.csv`, `escala_notas.json`, cachés y exportes.
- Excepción que ya existe y no cambia: `alumnos.csv` lo escribe también `tests.enviar` al asignar grupos (`modulos/tests/enviar.py:71-74`).

## 2. Flujos

### 2.1 Enviar la pregunta (`tests.enviar`)

Igual que hoy, más dos reglas: en modo real no envía una instancia en `borrador` (la simulación sí la muestra), y el cuerpo admite `{TITULO}` además de `{SEMANA}`, que pasa a valer el id. El asunto sigue siendo `Evaluación de Progreso Individual Módulo {id}: {tema}` (`modulos/tests/enviar.py:51-52`), porque es la llave con que se reconocen las respuestas (`modulos/mail/lectura.py:77-88`) y con ids enteros distintos dos instancias abiertas no se confunden. La frase «La pregunta de la semana es» / «Las preguntas de la semana son» (`modulos/tests/enviar.py:30-35`) pasa a «La pregunta es» / «Las preguntas son» solo en archivos cuya columna de id es `Instancia`, es decir, en semestres creados después de la fase 2. Un archivo con columna `Semana` (2026-2 y anteriores) conserva el texto de hoy, para no cambiar a mitad del experimento el correo que reciben los dos grupos (idea 6). `_construir_bloque_preguntas` recibe el estilo desde `SemanaInfo` (que sabe qué columna tenía el archivo), su gemela en `web/public/preguntas.js:217-223` sigue la misma regla, y la limpieza de `modulos/mail/limpieza.py:243` acepta las dos formas.

### 2.2 Corregir (`tests.evaluar`)

Argumentos nuevos: `instancia` (o `semana`), `revisar` (true/false; ausente = lo de `configuracion.json`), `sin_modelo` (true: el docente corregirá a mano), `solo` como hoy. `sin_modelo` implica `revisar`: el motor agrega `--revisar` siempre que venga `sin_modelo`, y `evaluar.main` lo vuelve a forzar por si se llama desde la terminal. Sin eso, en un semestre en `auto` (2026-2) el paso 6 mandaría al alumno una corrección vacía. `evaluar.main` (`modulos/tests/evaluar.py:148`) queda así, por cada correo sin leer de la instancia:

1. Si su Message-ID ya está en un evento `respuesta` (también los de `Detalle=duplicado`), ya se procesó: se marca leído y nada más. Arregla el correo de duplicado que hoy recibe quien ya tiene nota cuando un `marcar_leidos` falló o el trabajo se cortó (`modulos/tests/evaluar.py:214-237`, `311-324`).
2. Repregunta, alumno sin identificar y no elegido: como hoy (`modulos/tests/evaluar.py:186-210`).
3. Si `notas.ya_corregido` (Corregido, Nota o Descartada, 1.4): correo de duplicado, como hoy, y además un evento `respuesta` con `MessageId`, `RespondeA`, el texto y `Detalle=duplicado` (1.5). Coincide con lo que promete `correo_pregunta.md` («se evaluará solamente tu primer envío»).
4. Simulación: como hoy; guarda candidatos y no llama al modelo. Cada candidato lleva `estado` en vez de `ya_tiene_nota` (`modulos/tests/evaluar.py:199-205`): `con nota` (con la nota), `por revisar`, `descartada` o vacío. `elegirCandidatos` (`web/public/comun.js:847-908`) deja sin marcar a todo candidato con `estado` y le pone la etiqueta («por revisar», `:903`), en vez de mirar solo la nota (`:867`). Mientras convivan trabajos viejos, la página acepta también `ya_tiene_nota`.
5. Corrige: llama al modelo, o con `sin_modelo` deja una corrección vacía con `Modelo=docente:<pedido_por>` y `Detalle=modo=revisar`. Registra `notas.marcar_respondio`, `Corregido` y `Logro`, el evento `respuesta` (con `MessageId` y `RespondeA`) y el evento `correccion`. Si el modelo falla, no registra nada y el correo queda sin leer, como hoy.
6. Con `revisar`: sigue con el siguiente alumno. Sin `revisar` (automático): llama a `revision.enviar_una` (2.3) en la misma iteración.
7. Al final marca leídos los procesados, como hoy.

En automático, antes de corregir, el trabajo manda las correcciones automáticas que quedaron sin enviar en una corrida anterior (las «corregida, sin enviar» de `modo=auto`). Así se arregla el feedback perdido: hoy, si falla el envío, igual se registra la nota y se marca leído, y el alumno no recibe nada (`modulos/tests/evaluar.py:267-303`). Esto corre solo si el modo efectivo de la corrida es automático: si el semestre pasó a `revisar`, esas correcciones pendientes quedan «por revisar» (regla de 2.3).

Un trabajo con `revisar` va como real (`prueba:false`), a la cola de uno en uno, porque escribe. Puede mandar correos de duplicado, así que `mandaCorreos` (`web/public/comun.js:488-491`) lo cuenta como que «puede mandar correos» y la insignia lo dice. El texto de la pestaña Evaluar cambia con el modo elegido (`web/public/tests.js:40-48`): en automático, el botón dice «Evaluar y mandar feedback» y la confirmación habla de correos; con revisión, «Corregir y dejar para revisión», y la confirmación dice que el alumno no recibe nada todavía, salvo el correo de duplicado a quien mande dos respuestas.

Corte por tiempo. El motor mata el proceso a los 25 minutos (`motor/trabajo.py:336`, `:370-372`, `:388`) sin pasar por `avanzar`; en `tests.evaluar` automático y en `tests.feedback` un corte entre `enviar_correo` y el registro deja un correo enviado sin `evaluacion` ni `Nota`, y la corrida siguiente lo reenvía. Con un curso grande el corte es predecible, así que no se trata solo como riesgo (R1). Cambios:

- A los 22 minutos (`AVISO_SEGUNDOS = LIMITE_SEGUNDOS − 180`), un segundo reloj escribe el archivo de `IN5162_CANCELAR` (el mismo de «Detener», `motor/trabajo.py:383`) sin marcar `salida.cancelado`, y deja en la salida «Se acerca el límite de 25 minutos: el trabajo para antes del alumno siguiente; vuelve a correrlo para seguir». `avanzar` (`modulos/progreso.py:33-43`) para entre alumnos, el script guarda y marca leídos, y `_guardar` sube lo hecho (`motor/trabajo.py:515-519`). El trabajo queda «fallido» con ese texto, para que `fallidosSinResolver` (`web/public/comun.js:473-485`) lo muestre en Inicio hasta que se repita.
- El `proc.kill()` de los 25 minutos se queda como último recurso, por si el script no para.
- En `enviar_una`, después del correo, primero se agrega el evento `evaluacion` al log (una línea, `_csv.agregar`) y después se reescribe `notas.csv`. Si el proceso muere entre los dos, la selección de 2.3 ya ve la `evaluacion` y no lo reenvía, y `enviar_pendientes` y `evaluar.main`, solo en modo real (una simulación no escribe tablas, 3), corren `notas.sincronizar_desde_log()` al empezar, que completa la `Nota` que faltó (solo llena campos vacíos, 1.5). El hueco que queda es el de R1: un corte entre `enviar_correo` y la línea del log.

### 2.3 Enviar el feedback (`tests.feedback` y `tareas.feedback`, nuevos)

Un módulo genérico, `modulos/revision/enviar.py`, con `--flujo test|tarea --item <id>`. Dos entradas en `FLUJOS` (en `motor/trabajo.py:167-200` y en `web/src/index.ts:70-75`, que `pruebas/web.py:161-163` exige iguales) porque el perfil de archivos es distinto. No es `CORTABLE`: para entre alumnos con `avanzar` (`modulos/progreso.py`).

Elige, entre los alumnos con `correccion` y sin `evaluacion` posterior, sin `Nota` ni `Descartada`:

- con decisión `enviar` y `base` igual al `Timestamp` de su última `correccion`: se envía;
- con decisión `descartada` y `base` vigente: se registra el descarte (abajo);
- sin decisión, con `modo=auto`, de `Modelo` distinto de `docente:*`, y solo si la configuración vigente al momento de enviar (`configuracion.json`, o el argumento `revisar` de la corrida) es `auto`: se envía. Si el semestre pasó a `revisar`, esas correcciones automáticas pendientes quedan «por revisar» y salen solo con una decisión. Así, quien cambia a revisión porque desconfía de una corrida no ve salir sin revisar las que fallaron antes;
- una corrección de `docente:*` nunca sale sin decisión `enviar` con `puntajes` (o `nota_legado`) completos; si falta algo, se salta y se dice.

Para cada uno que se envía, `enviar_una`:

1. Junta la corrección con la decisión (si la `base` no coincide, lo salta y lo dice).
2. Calcula puntajes, logro y nota finales con la escala; arma el bloque y el cuerpo con el armador del flujo (abajo).
3. Envía con el asunto y el hilo del armador del flujo.
4. Solo si el envío funcionó: agrega el evento `evaluacion` al log y después `notas.registrar_nota` (en ese orden, 2.2 › Corte por tiempo). Si falla, queda «corregida, sin enviar» y la próxima corrida lo intenta otra vez.

Descarte: agrega el evento `descarte` (`Detalle` = motivo y quién) y marca `Descartada` en `notas.csv`. No manda correo. Con eso los estados derivados (1.4), el panel (`Descartada`, 1.8), el ciclo (`web/public/ciclo.js:59-61`), Inicio (`web/public/inicio.js:37-43`), la sábana y el contador de Revisar dejan de contarla como pendiente.

Armador por flujo (`modulos/revision/armado.py`), que `enviar_una` recibe según `--flujo`:

- Tests: bloque según `correo_muestra` (1.7), cuerpo con `tests_semanales/prompts/correo_correccion.md` y `_construir_cuerpo_correccion` (`modulos/tests/evaluar.py`, se muda sin cambios), `in_reply_to` = `RespondeA` del evento `respuesta` (el mismo hilo que hoy, `modulos/tests/evaluar.py:270-275`) y asunto `Re: …Módulo {id}…`.
- Tareas: lo de hoy (`modulos/tareas/corregir.py:184-188`): correo nuevo, sin hilo, asunto `Revisión de tu respuesta — {CURSO} {T}`, cuerpo con `tareas/prompts/correo_feedback.md` armado con `str.format` y los campos de `_construir_cuerpo_feedback` (`:93-102`). La `respuesta` de Tareas no guarda `MessageId` (`modulos/tareas/recolectar.py:57-58`), así que no hay a qué responder; hilarlo queda fuera. `correo_muestra` no aplica (1.2). La tarjeta de Revisar de Tareas muestra `señales_copia_ia` y `justificacion_interna` desde `correccion.EvaluacionIA` (1.5), solo para el docente.

Modo prueba. Todo trabajo es prueba salvo `prueba: false` (`web/src/index.ts:411-412`, `motor/trabajo.py:47-50`). En prueba, `tests.feedback` y `tareas.feedback` eligen igual, arman cada correo y lo muestran con `mostrar_correo` (como la simulación de `tests.evaluar`, `modulos/tests/evaluar.py:228-231`), sin enviar ni registrar nada, y listan los descartes que registrarían. Los botones de Revisar piden `prueba: false`. Los dos flujos entran a `SIMULABLES` (`web/public/comun.js:456-457`) y a `mandaCorreos`.

Notas de Tareas guardadas con `--no-enviar` antes de la fase 3. Con la regla «`Nota` = se envió el feedback», esas casillas cuentan como enviadas y `tareas.feedback` no las elige. Se reconocen porque su `evaluacion` no anota `correo_feedback.md@` en `Versiones` (`modulos/tareas/corregir.py:47-57`, `:172`). No verifiqué si 2026-2 tiene casos. La simulación de `tareas.feedback` las lista aparte («3 notas guardadas sin feedback antes de la revisión»); en real quedan como están, salvo que la corrida traiga `antiguas: true`, que las manda con la nota y el comentario guardados y agrega su `evaluacion` con `MessageId`.

Como cada alumno queda registrado apenas sale su correo, repetir el trabajo no repite correos y «Detener» funciona igual que en `tests.enviar` (`modulos/tests/enviar.py:108-125`).

Botones de la página y lo que piden:

- «Aprobar»: escribe `estado: aprobada`. No lanza trabajo.
- «Aprobar y enviar»: escribe `estado: enviar` y lanza `tests.feedback` para la instancia, salvo que ya haya uno pendiente (aún sin empezar), que lo recogerá porque lee las decisiones al bajar el semestre.
- «Descartar…»: pide motivo, escribe `estado: descartada` y lanza o reutiliza el trabajo igual que «Aprobar y enviar», para que el descarte quede registrado.
- «Enviar las N aprobadas»: pasa todas las `aprobada` a `enviar` en un solo guardado y lanza un trabajo.

Así cuarenta clics en «Aprobar y enviar» no generan cuarenta trabajos en la cola de uno en uno.

### 2.4 Ajustar con o sin aviso (`datos.ajustar`)

- Se rechaza si la casilla está «por revisar»: esa nota se cambia en la revisión.
- Validación de Tests por la escala del semestre: nota entre `min(1, minima)` y `maxima`, con hasta `decimales` decimales. Con 4–7 da 1,0–7,0, igual que hoy (`modulos/datos/ajustar.py:33-36`). El patrón del motor (`motor/trabajo.py:91-93`) se abre a `\d{1,3}([.,]\d{1,2})?` y el rango lo valida `ajustar`. `escala_notas.json` está en la raíz y el perfil `tests` la baja (`motor/trabajo.py:223-224`).
- Tareas no cambia en esta etapa: ninguna página ajusta notas de Tareas (la única llamada es la de Resultados, con `flujo: "test"`, `web/public/app.js:1108-1109`), y validar con `modulos/tareas/escala.py` necesitaría `tareas/prompts/escala.json`, que el perfil `tests` de `datos.ajustar` no baja (`motor/trabajo.py:229-230`). `ajustar.py` conserva para Tareas la validación de hoy.
- Guarda `Logro` = inversa de la nota si cae entre mínima y máxima; si no (por ejemplo un 3,0 con escala 4–7), `Logro` vacío y el ajuste queda fijo ante un cambio de escala.
- `--avisar`, solo para Tests (el motor lo rechaza con `flujo: "tarea"`): manda un correo con `tests_semanales/prompts/correo_ajuste.md` (nuevo en la plantilla; si el semestre no lo tiene, un texto fijo en el código), respondiendo al `MessageId` de la última `evaluacion`, y guarda el `MessageId` del aviso en el evento `ajuste`. Si la última `evaluacion` no tiene `MessageId` (feedback anterior a que se guardara), el aviso sale como correo nuevo con el asunto `Re: …Módulo {id}…`. Si el alumno contesta, la tutoría lo recoge (por `DEL_AGENTE`) y recibe como contexto el motivo del ajuste. Con `correo_muestra: nada`, la plantilla por defecto dice que su corrección se revisó, sin número. Ni la plantilla ni el texto fijo usan la etiqueta `NOTA FINAL` («tu nota quedó en 6,0»), para que `reconstruir` (`modulos/tests/reconstruir.py:433-441`) no tome un aviso por la corrección.
- Con `avisar` el trabajo manda correo y no es cortable (ya no está en `CORTABLES`, `motor/trabajo.py:343-344`). Hoy la página pide `datos.ajustar` sin `prueba` (`web/public/app.js:1108-1109`), el Worker lo guarda como prueba (`web/src/index.ts:411-412`) y el motor lo corre en real igual, porque `_ajuste` no mira `prueba` (`motor/trabajo.py:80-99`). Con aviso, ese trabajo saldría en el historial como «prueba» y sin insignia, porque `mandaCorreos` descarta todo trabajo `prueba` y todo flujo fuera de `SIMULABLES` (`web/public/comun.js:456-458`, `:488-491`). Reglas: el motor exige `prueba is False` para `avisar` y, si no viene, rechaza el trabajo con «el aviso necesita prueba:false» (no cambia la nota sin el aviso pedido); la página manda `prueba: false` cuando la casilla está marcada; `mandaCorreos` cuenta `datos.ajustar` con `avisar` y `prueba` falso. `datos.ajustar` no entra a `SIMULABLES`: los ajustes históricos están en D1 con `prueba = 1` y fueron reales, y `esSimulacion` (`web/public/comun.js:461`) pasaría a mostrarlos como simulaciones. El ajuste sin aviso sigue como hoy. La vista previa del aviso la arma la página antes de pedir el trabajo (6).

### 2.5 Cambiar la escala (`datos.escala`, nuevo)

Argumentos: la escala propuesta, `prueba`. El motor valida: `0 ≤ minima < maxima ≤ 1000`, `decimales` 0–2, y en dos tramos `minima < aprobacion < maxima` y `0 < exigencia < 1`.

- Simulación: lista cuántas notas de tests cambian, cuántas ya se comunicaron por correo con número (las `evaluacion` cuyo bloque mostraba la nota), media antes y después, el mayor cambio y los ajustes fijos que no se tocan.
- Real: escribe `escala_notas.json`; para cada fila de test con `Nota` recalcula desde `Logro` (o, si está vacío, desde la inversa de la escala anterior), reescribe `notas.csv` y deja un evento `recalculo` por fila cambiada. No llama al modelo ni manda correos. Las correcciones por revisar no tienen nota guardada: la toman al enviarse.
- Ajustes fijos y filas sin escala anterior conocida quedan como están, listados en la salida.
- En 2026-2 no se usa: cambiaría notas ya comunicadas en un experimento en curso (R5). El diseño no lo bloquea por código, porque un semestre cerrado puede querer reexpresar sus notas para un informe; lo frena en la página: si la simulación encuentra notas ya comunicadas con número, «Guardar y recalcular» pide escribir el id del semestre («2026-2») además de confirmar, y la confirmación dice cuántos alumnos vieron una nota que va a cambiar. `datos.escala` entra a `SIMULABLES` (su prueba es la simulación) y no a `mandaCorreos`.

### 2.6 Tutoría, duplicados y otros correos

Cómo queda cada correo automático cuando la revisión está activa:

- Correo de duplicado: sigue automático; es texto fijo, sin modelo.
- Tutoría diaria del cron (`web/src/index.ts:443-453`): sigue automática (decisión 4). Con revisión no hay repreguntas sobre feedback no enviado, porque el alumno todavía no recibió nada que contestar. Recibe como contexto el bloque enviado (`evaluacion.EvaluacionIA`), ya sin los números que el semestre oculta (`modulos/tests/tutoria.py:98-101`), y el prompt de tutoría de la plantilla agrega que no revele una nota que el correo no mostró. Solo atiende respuestas a feedback de Tests (filtro de flujo en `fila_por_message_id`, 1.5); las respuestas a feedback de Tareas quedan sin leer y se cuentan aparte en la salida.
- Segunda oportunidad de Tareas: ya tiene preparar, borradores y enviar (`motor/trabajo.py:70-77`); no cambia.
- Aviso de ajuste: solo con la casilla marcada (2.4).

### 2.7 Tareas

`tareas.corregir` (`modulos/tareas/corregir.py:105-191`) adopta el mismo corte: registra `correccion` y `Corregido` en vez de `Nota`, y en automático envía con `revision.enviar_una`, que guarda el `MessageId` en `evaluacion` (hoy se descarta, `modulos/tareas/corregir.py:188`). `--no-enviar` pasa a ser `revisar`; el tramo «nota guardada sin feedback y sin salida» (`modulos/tareas/corregir.py:181-182`, `web/public/tareas.js:43-51`) desaparece. La tarjeta de revisión de Tareas edita la nota (lista de valores de `tareas/escala.json` o rango `NOTA_MIN`–`NOTA_MAX`) y el comentario. Tareas conserva su escala (decisión 6). De paso se corrige que `Versiones` anote `escala=NOTA_MIN-NOTA_MAX` aunque mande `escala.json` (`modulos/tareas/corregir.py:55`).

Pendientes de `tareas.corregir`. Hoy son «con respuesta y sin nota» (`modulos/tareas/corregir.py:118-122`, con `ya_evaluado`). En `revisar` la corrección no escribe `Nota`, y la corrida siguiente volvería a llamar al modelo para todos los que esperan revisión, gastaría API y dejaría una `correccion` nueva que deja vieja la `base` de las decisiones ya tomadas. Los pendientes y los candidatos de la simulación (`:123-129`) pasan a usar `ya_corregido` (1.4); los candidatos llevan `estado` como en Tests (2.2, paso 4).

`tareas.feedback`: el armador de Tareas y el tratamiento de las notas guardadas con `--no-enviar` están en 2.3. El ajuste con aviso no aplica a Tareas (2.4).

### 2.8 Resumen y chequeo

`tests.resumen` hoy vuelve a corregir cada respuesta con el modelo (`modulos/tests/resumen.py:46`), con las preguntas del grupo control para todos (`info.preguntas`, `modulos/tests/preguntas.py:23-25`), y solo toma a quien tiene `Nota` (`resumen.py:21-30`). Con revisión, una instancia sin feedback enviado no tendría resumen; con el prompt JSON, `resumen_respuestas.md:1` recibiría JSON en vez de bloques con `NOTA FINAL`. Cambia a:

- toma a quien tenga `Corregido` o `Nota` y no `Descartada`;
- para cada uno lee del log la última `correccion` (o la `evaluacion`, en filas anteriores a la fase 3) y la pasa a texto con `correccion.texto_docente` (1.7), que siempre trae puntajes, `NOTA FINAL` y originalidad, y en el legado HTML deja el bloque tal cual;
- no llama al modelo por alumno: solo la llamada de `generar_resumen` (`modulos/tests/ia_prompts.py:100-112`). Se ahorra una llamada por respuesta (hoy, 52 en una instancia completa);
- el mensaje al modelo lleva las preguntas de los dos grupos, rotuladas, y cada evaluación dice su grupo, para que el resumen no mezcle preguntas de control con respuestas de tratamiento. Es el único lugar donde el grupo es visible en el flujo de revisión, y es para el resumen del equipo docente, no para la tarjeta (R3).

`tests.chequeo` (`modulos/tests/chequeo.py:68-93`) hoy separa «ya tienen nota (se les avisa)» de «a evaluar» solo por `Nota`; con revisión, los corregidos sin enviar saldrían como «a evaluar» y el chequeo prometería correcciones que serán correos de duplicado. Pasa a usar `ya_corregido` y muestra cuatro líneas: con nota, por revisar, descartadas (todas reciben el correo de duplicado si vuelven a escribir) y a evaluar.

### 2.9 De dónde lee la pestaña Revisar

El panel de D1 no sirve: `EvaluacionIA` pasa a ser lo enviado (1.5) y las por revisar no tienen `evaluacion`. La pestaña lee en el navegador, como ya hacen Probar criterio (`web/public/probar.js:308`) y la vista de datos (`web/public/datos.js:583`):

- `log_envios.csv`: la `respuesta` (y las de `Detalle=duplicado`, para el aviso «respondió otra vez»), la última `correccion` de cada alumno (propuesta, `Timestamp` para `base`, `Modelo`, avisos de bloques) y si ya hubo `evaluacion` o `descarte`;
- `notas.csv`: el estado (1.4);
- `tests_semanales/revision/<id>.json` (o `tareas/revision/<T>.json`): las decisiones, con su etag para el guardado (1.6);
- `alumnos.csv`: el nombre. El grupo no se muestra (R3);
- `tests_semanales/data/preguntas.csv`: las preguntas del grupo de cada alumno, para contar bloques.

Costo: el log de 2026-2 pesa 0,9 MB hoy y, con `correccion` y `evaluacion` por alumno, crecería un 30–50 % por semestre (R10, sin medir). Se baja una vez al abrir la pestaña y se filtra por `Flujo` e `Item`; al guardar una decisión no se vuelve a bajar. Si el log pasa de unos 5 MB, el paso siguiente es que el trabajo de corrección deje un `tests_semanales/revision/propuestas_<id>.json` con solo lo que la pestaña necesita; queda fuera de este diseño.

## 3. Compatibilidad con 2026-2

Sin tocar sus datos, en cada fase:

- Instancias: su `preguntas.csv` tiene la columna `Semana` y ninguna de las nuevas, así que cada fila es una instancia confirmada titulada «Semana N». Los `Item` de `notas.csv`, del log y del panel ya son esos números. El correo de la pregunta conserva «La pregunta de la semana es» porque el archivo usa `Semana` (2.1).
- Revisión: sin `configuracion.json` rige `auto`: corrige y envía en el mismo trabajo, como hoy. Lo único distinto es que cada corrección deja además un evento `correccion` y que un envío fallido ya no se pierde. El correo que sale tiene que ser idéntico al de hoy: con `correo_muestra: nota` y el formato viejo, `enviar_una` usa el mismo `_construir_cuerpo_correccion` (`modulos/tests/evaluar.py:72`) con el HTML del modelo sin tocar. Una prueba de la fase 3 arma el cuerpo con el código de antes del corte y con `enviar_una`, sobre el mismo HTML de entrada, y exige igualdad byte a byte (5 › Pruebas).
- Escala: sin `escala_notas.json` rige 4,0–7,0 con un decimal. Su prompt sigue siendo HTML con `NOTA FINAL`, leído con el extractor de hoy (decisión 5). Ninguna nota cambia. Desde la fase 4, «Cambiar la escala» aparece también en 2026-2; no se usa en ese semestre, y la página lo frena con la confirmación reforzada de 2.5.
- Lo único que se reescribe es el formato: la primera vez que un trabajo real escriba `notas.csv` o el log después de la fase 1, cada archivo gana columnas vacías al final (`Corregido`, `Logro`, `Descartada`; `Puntajes`, `Logro`). La versión anterior queda en `historial/` (`web/src/index.ts:293-297`).
- Simulaciones y etags. El motor sube lo que cambió también en las simulaciones (`motor/trabajo.py:515-519`), y las simulaciones corren en paralelo con los trabajos reales. Hoy ninguna escribe `notas.csv` ni el log: `_ampliar_columnas` solo corre al agregar al log, la simulación no agrega, y lo único que deja `tests.evaluar` en prueba es su `candidatos_<id>_<trabajo>.json`, con nombre propio (`modulos/tests/evaluar.py:326-329`). Si una simulación empezara a escribir esas tablas, chocaría por etag con un trabajo real (`motor/trabajo.py:441-462`) y uno de los dos perdería lo guardado. Regla del diseño: ningún camino de prueba llama a `_csv.escribir`, `_csv.agregar`, `notas.sincronizar_desde_log` (sin `simular`) ni `migracion.asegurar` con algo que migrar. Una prueba nueva corre en prueba cada flujo de `SIMULABLES` y los nuevos (`tests.feedback`, `tareas.feedback`, `datos.escala`) sobre una copia de semestre y compara la huella de `notas.csv` y del log antes y después (5 › Pruebas). Va en la fase 1, antes de que existan columnas nuevas que una escritura de simulación pudiera agregar. Revisé los caminos de prueba de `tests.evaluar`, `tests.enviar`, `tests.tutoria`, `tareas.enviar` y `tareas.corregir`: ninguno escribe `notas.csv` ni el log. Sí hay una escritura de simulación que ya existe y el diseño no cambia: `tests.enviar` asigna grupos y escribe `alumnos.csv` antes de mirar `dry_run` (`modulos/tests/enviar.py:71-74`, `:88`). Por eso la prueba nueva compara `notas.csv` y el log, no `alumnos.csv`; mover esa asignación al modo real es otro cambio, fuera de este diseño.
- Los trabajos guardados con `{"semana": 4}` siguen mostrándose y repitiéndose bien, porque el motor y la página leen las dos claves.
- La revisión se puede encender a mitad de semestre sin migrar nada: las casillas con `Nota` cuentan como enviadas y las demás siguen el flujo nuevo. Si se enciende, conviene hacerlo para los dos grupos a la vez (riesgo R3).

## 4. Migración

Qué se recalcula: nada al publicar. Las notas solo cambian si alguien corre `datos.escala` en modo real, y eso deja un evento por fila.

Qué queda igual: todas las notas, ajustes, eventos y `Item` de 2025-2, 2026-1 y 2026-2; los trabajos históricos de D1; los prompts de cada semestre en R2.

Qué se agrega:

- Columnas vacías en `notas.csv` y en el log (al primer trabajo que escriba).
- Tres columnas en `panel` de D1, con `ALTER TABLE` a mano, como ya prevé `web/schema.sql:78` para `ediciones`. El panel se llena de nuevo con el siguiente trabajo o con `datos.panel`.
- Archivos de la plantilla de R2: nuevos (`preguntas.csv` con cabecera, `configuracion.json`, `correo_ajuste.md`) y cambiados (`evaluar_respuesta.md` en JSON, `correo_pregunta.md` con `{ESCALA}`, `tutoria.md` que no revela números, `correo_correccion.md` sin la encuesta «del 1 al 7»). No afectan a semestres ya creados (`web/src/index.ts:606-622` copia la plantilla solo al crear uno).

Cómo llega la plantilla a R2. `subir.py --archivos` sube la plantilla (`modulos/web/subir.py:145-149`), pero solo los archivos que no existen en la nube: los que cambiaron quedan como «distintos» salvo con `--forzar` (`:101-103`), que las reglas prohíben (`PENDIENTES_PO.md:14`) y que además fuerza todos los semestres de la corrida y su reportería (`:150-161`). Los cambiados no llegarían. Además la página no puede escribir en `_template` (`web/src/index.ts:116-118`, solo el motor). Se agrega `python -m modulos.web.subir --plantilla`: sube solo `_template`, reemplaza los distintos con el etag que leyó (si cambió entretanto, falla en vez de pisar), no toca semestres ni reportería, y con `--simular` lista qué reemplazaría. Cada reemplazo pasa por `subirArchivo`, que deja la versión anterior en `historial/` (`web/src/index.ts:293-297`). Va en la lista de cada despliegue (R8).

Notas de Tareas guardadas con `--no-enviar` antes de la fase 3: no se migran; `tareas.feedback` las lista y las manda solo con `antiguas: true` (2.3).

`Logro` de las filas viejas no se escribe: se deduce con la inversa cuando hace falta (recalcular, sábana, panel). No vale la pena rellenarlo y además arrastraría el redondeo del modelo.

Puntaje por pregunta de las correcciones viejas: no se migra. Se puede leer de `EvaluacionIA` (líneas `EVALUACIÓN: x / 3`) para un análisis, con los controles que propuso el mapa de escala (número de bloques contra preguntas del grupo; promedio + 4 contra `NOTA FINAL`). Queda fuera de este diseño.

## 5. Cambios por capa

### Datos (`modulos/datos/`)

- `esquema.py:23-28`: `Corregido`, `Logro`, `Descartada` al final de `COLUMNAS_NOTAS`. `:34-42`: eventos `correccion`, `descarte` y `recalculo`. `:44-61`: `Puntajes`, `Logro`. `:65`: `DEL_AGENTE` suma `ajuste`.
- `_csv.py:22-32`: `escribir` conserva las columnas extra del archivo y escribe a `.tmp` + `replace` (1.4).
- `log.py:101-118`: `fila_por_message_id` gana `flujo=` (1.5). `:64-92`: `reconstruir_estado` con `correccion`, `descarte`, `recalculo`, `historia_nota` y sin las `respuesta` de `Detalle=duplicado`. `:183-216`: `como_interacciones` agrega `NotaModelo`, `Logro`, `PorRevisar` (correccion sin evaluacion ni descarte posterior), `Descartada`, `RevisadoPor`, y toma la primera respuesta no duplicada.
- `notas.py:80-83`: `registrar_nota` acepta `logro`; nuevas `marcar_corregido`, `marcar_descartada`, `por_revisar`, `ya_corregido`. `:92-95`: `ya_evaluado` sigue siendo «tiene nota». `:145-153`: sincroniza `Corregido`, `Logro` y `Descartada`, y pone al día la `Nota` atrasada según `historia_nota` (1.5).
- `comparar.py:99`, `:138`: compara también `Corregido`, `Logro`, `Descartada`.
- `ajustar.py:28-53`: rango de Tests por escala, `Logro`, `--avisar` solo en Tests, rechazo si está por revisar; Tareas valida como hoy (2.4).
- `reportes.py:97-114`: `Logro`, `NotaModelo`, `PorRevisar`, `Descartada`.
- `agregaciones.py:58-61`: sin cambio (ids enteros). `:212-238`: `NOTA_MAXIMA` y el ancho del tramo salen de la escala (ancho = `(maxima − minima)/6` redondeado a 0,5, 1, 5 o 10; con 4–7 da 0,5 como hoy). Los tres lugares que hoy cuentan «respondió y sin nota» separan por revisar y descartadas, para que el número del indicador y la lista que abre el clic coincidan: `pendientes_de_evaluar` (`:543-548`) excluye `PorRevisar` y `Descartada`; `_agregar` (`:130-140`) cambia `PendientesEvaluar` a respondieron − notas − por revisar − descartadas y suma `PorRevisar`; `casillas` (`:90-95`) suma `estado="por_revisar"` y saca de `sin_nota` las por revisar y las descartadas. Nueva `por_revisar`. La copia de `web/public/py/` se regenera con `web/scripts/copiar-py.mjs`.
- Nuevo `modulos/escala.py`: leer escala, `nota(logro)`, `logro(nota)`, redondeo y formato.
- Nuevo `modulos/datos/escala_trabajo.py` (flujo `datos.escala`).

### Tests (`modulos/tests/`)

- `preguntas.py:43-102`: archivo opcional, columna `Instancia|Semana`, id estricto, repetidos como error, `titulo`, `envio`, `estado`. `SemanaInfo` se queda con ese nombre y gana `titulo`; `cargar_semana` sigue existiendo.
- `enviar.py:30-35`, `:47`, `:51-52`, `:67-69`: texto según la columna del archivo (2.1), `{TITULO}`, rechazo de borradores.
- `evaluar.py:148-351`: el flujo de 2.2. `:144`: `_es_repregunta` con `flujo=TESTS`. `:199-205`: los candidatos llevan `estado` (2.2, paso 4). `:214-237`: el predicado es `ya_corregido` y el duplicado se registra como `respuesta` con `Detalle=duplicado`. `:262`: el extractor pasa a `correccion.leer(salida)` (JSON o HTML). `:267-303`: el envío y el registro se mudan a `revision.enviar_una`. `:353-372`: argumentos `--revisar` y `--sin-modelo` (que implica `--revisar`).
- Nuevo `correccion.py`: leer JSON o HTML, validar, calcular, armar HTML según `correo_muestra` (con `NOTA FINAL` cuando se muestra la nota), quitar números del HTML viejo, `texto_docente`.
- `ia_prompts.py:30-60`: pide JSON cuando el prompt lo declara. Depende de que `ia.completar` acepte `response_format`; `modulos/ia/cliente.py` lo está cambiando el otro agente, así que esto va después de su cambio. `:100-112`: `generar_resumen` recibe las preguntas de los dos grupos y los textos de `texto_docente` (2.8).
- `resumen.py:11-60`: deja de llamar a `evaluar_respuesta` por alumno; lee las correcciones del log y toma `Corregido` o `Nota` (2.8).
- `chequeo.py:68-93`: `ya_corregido` y cuatro líneas: con nota, por revisar, descartadas, a evaluar (2.8).
- `tutoria.py:57`: `_pendientes` con `flujo=TESTS` y conteo aparte de respuestas a feedback de Tareas (1.5). `:98-112`: contexto con el bloque enviado y, si lo hubo, el motivo del ajuste. `int(item)` en `:112` se queda (ids enteros). `:130`: asunto de reserva sin cambio.
- `experimento.py:108-118`: con el prompt nuevo calcula la nota con la escala del semestre y compara contra `NotaModelo` (la del modelo, sin ajustes ni ediciones), mostrando también la final. `:95-96`: `candidatas` excluye las casillas cuya última `correccion` es de `docente:*`, que no tienen nota del modelo contra la cual comparar. `:465`: `EvaluacionAntes` deja de salir de `EvaluacionIA` del panel (desde la fase 3 es el bloque enviado: sin los números ocultos y con las ediciones del docente) y pasa a ser `texto_docente` de la última `correccion` del log; en filas anteriores a la fase 3, la `evaluacion`. `:346`: acepta `NOTA FINAL` o el JSON con `puntaje`. `:409` y `:759`: se quedan (ids enteros); la columna «Semana» de la salida pasa a «Test».
- `reconstruir.py:131` y `sabana.py:68-82`: leen el id con el mismo ayudante que `preguntas.py`. `reconstruir.py:427-441`: sin cambio de código. Con `correo_muestra: nota` el feedback sigue trayendo `NOTA FINAL` (1.7) y el aviso de ajuste no usa esa etiqueta (2.4), así que el primer «Re:» con `NOTA FINAL` sigue siendo la corrección. Con notas ocultas no recupera notas, y queda escrito que desde 2026-2 la fuente es el log.

### Revisión (`modulos/revision/`, nuevo)

- `decisiones.py`: leer `revision/<id>.json`, juntar con la corrección, verificar `base` contra el `Timestamp` de la última `correccion`.
- `armado.py`: armador de Tests y de Tareas (asunto, cuerpo, hilo; 2.3).
- `enviar.py`: `enviar_una` (log antes que `notas.csv`), registro de descartes, selección con la configuración vigente, modo prueba con `mostrar_correo`, `antiguas` en Tareas, `enviar_pendientes` y el `main` de `tests.feedback`/`tareas.feedback`.

### Tareas

- `tareas/corregir.py:105-191`: corte en `correccion` (con el JSON completo en `EvaluacionIA`) + `enviar_una`; `--revisar`; `MessageId` en `evaluacion`; `:55` anota la escala real. `:118-129`: pendientes y candidatos con `ya_corregido` y `estado`.

### Correo

- `mail/lectura.py:77-88`: sin cambio de lógica (ids enteros). Mejora incluida en la fase 2: antes de filtrar por asunto, un correo cuyo In-Reply-To calza con un `envio` de la instancia se acepta aunque el alumno haya cambiado el asunto. Requiere pasar al filtro el correo entero en vez del asunto (`modulos/mail/lectura.py:52`).
- `mail/limpieza.py:243`: acepta el texto viejo y el nuevo.

### Motor (`motor/trabajo.py`)

- `:40-44`: `_semana` pasa a `_instancia`: lee `instancia` o `semana`, exige `^[1-9][0-9]{0,2}$`.
- `:80-99`: `_ajuste` con ítem `\d{1,3}`, nota `\d{1,3}([.,]\d{1,2})?`, `avisar` booleano, solo con `flujo: "test"` y `prueba is False` (2.4).
- `:167-200`: `tests.evaluar` con `--revisar`/`--sin-modelo` (`sin_modelo` agrega también `--revisar`); `tests.feedback` y `tareas.feedback` con `_prueba` y `antiguas`; `datos.escala`; `tareas.corregir` cambia `no_enviar` por `revisar` y sigue aceptando `no_enviar` como sinónimo.
- `:205-206`: `PARAMETROS` no cambia.
- `:336-400`: aviso de cancelación a los 22 minutos con el archivo de `IN5162_CANCELAR`, sin marcar `cancelado`; el `kill` de los 25 queda de último recurso (2.2 › Corte por tiempo).
- `:343-344`: `CORTABLES` no cambia (ninguno de los nuevos es cortable).

### Worker (`web/src/index.ts`) y D1

- `:59-66`: `COLUMNAS` y `BOOLEANAS`.
- `:70-75`: `FLUJOS` suma `tests.feedback`, `tareas.feedback`, `datos.escala`.
- `:100-110`: `EDITABLES` suma `configuracion.json` y `revision/*.json`.
- `:84-85`: `NOTA_MIN`/`NOTA_MAX` se quedan para Tareas.
- `web/schema.sql:14-33`: las tres columnas del panel (y el `ALTER TABLE` comentado al lado, como en `:78`).
- `modulos/web/subir.py:55`, `:162`: sube el panel con las columnas nuevas. `:131-149`: opción `--plantilla` (4).

### Páginas (`web/public/`)

- `preguntas.js`: `:19-20` columnas obligatorias sin cambio y opcionales nuevas; `:30-33` id estricto; `:36-43` lista con título, envío y estado; `:100-120` escribe título, envío y estado; `:123-133` `agregarInstancia` crea el archivo con cabecera si no existe y calcula el id con `preguntas.csv` y `notas.csv` (1.1); `:217-235` texto del bloque según la columna del archivo (2.1) y asunto; `:527-536` sin archivo ofrece «+ Nuevo test» en vez de mandar a subir el CSV. Botón «Confirmar test». No ofrece borrar un test con envíos.
- `datos.js:48-56`, `:1131-1138`: URL `#datos/preguntas/<id>` igual. `:228-242`: «Tabla completa» ofrece crear el archivo vacío además de subirlo, y al guardar `preguntas.csv` rechaza que desaparezca un id con envíos (1.1). `:1188-1200`: el aviso «faltan las preguntas» pasa a «todavía no hay tests». Sección nueva «Semestre» en Configuración: revisión, `correo_muestra`, escala (con la confirmación reforzada de 2.5).
- `ciclo.js:45-98`: lee `Corregido` y `Descartada`; estados «por revisar» y «descartada» (cerrada); `proximoPaso` usa `Envio` de cada instancia y, si no hay, la heurística de 7 días (solo legado); varias instancias abiertas a la vez. `:65`: el regex del resumen se queda.
- `inicio.js:21-31`: tarjeta con el título de la instancia; `:37-43`: «N correcciones esperando revisión» con enlace a Revisar, sin contar descartadas. `:45` y `:131`: leen el id con `idDe`.
- `tests.js:40-48`: en Evaluar, el selector «Después de corregir: enviar / dejar para revisión», y el botón y la confirmación según el modo (2.2). `:204`, `:241-254`: simulación previa, ruta de candidatos y descarga del resumen leen el id con `idDe`. `:239-252`: la lista de candidatos ofrece «Corregir con IA» y «Corregir yo». `:271`, `:313`: el número 1–52 se cambia por una lista de tests con título; los trabajos nuevos mandan `instancia`. Pestaña nueva «3 · Revisar».
- `comun.js` (línea de hoy; el archivo está cambiando, ver el inicio): nuevo `idDe(argumentos)` = `argumentos.instancia ?? argumentos.semana`, que usan todas las lecturas del id de un trabajo: `sobreQue` (`:394-396`), `claveTrabajo` (`:464`), `tests.js`, `inicio.js` y `probar.js`. `:456-457`: `SIMULABLES` suma `tests.feedback`, `tareas.feedback`, `datos.escala` (no `datos.ajustar`, 2.4). `:488-491`: `mandaCorreos` cuenta `tests.feedback`, `tareas.feedback` y `tests.evaluar` reales (por los duplicados) y `datos.ajustar` con `avisar` y `prueba` falso; no cuenta `datos.escala`. `:847-908`: `elegirCandidatos` lee `estado` (o `ya_tiene_nota` en trabajos viejos), desmarca y rotula, y cambia el texto del botón según el modo. `:243`: `evaluacionDeTexto` conoce el JSON.
- Nuevo `correccion.js` (armado del correo, gemelo de `correccion.py`) y `revision.js` (pantalla de revisión; qué lee, 2.9; `base` = `Timestamp` de la `correccion`).
- `app.js:149-172`: «El correo que recibió» usa `evaluacion.EvaluacionIA`, que ya es lo enviado. `:244-248`: `dominioNotas` deja de recortar a `[1, 7]` y recorta a `[min(1, minima), maxima]` con un margen de `(maxima − minima)/6`; con 4–7 da lo de hoy. Como el piso es el de los ajustes (2.4) y no `minima`, un 3,0 en escala 4–7 queda dentro del gráfico. Lo usan las tres llamadas de hoy (`:557`, `:737`, `:1041`). `:1095-1123`: ajuste con validación por escala, casilla «Avisarle al alumno», `prueba: false` cuando está marcada, y texto de confirmación según la casilla. `:161`, `:1051`: `Number(c.Item)` se queda. Títulos de instancia en ejes y fichas.
- `probar.js:142`, `:206`, `:262`: lista de tests en vez de 1–52, y el trabajo manda `instancia`. `:288`: la columna del historial lee `idDe`. `criterio.js:64-85`: sin cambio (ids enteros); muestra nota del modelo y final.
- `sabana.js:19`: columnas nuevas de la sábana. `tareas.js:270-271`: la lista de elegidos pasa `revisar`.
- `prompts.js:15`: `evaluar_respuesta.md` debe tener `NOTA FINAL:` + `ORIGINALIDAD:` (viejo) o pedir JSON con `puntaje` y `originalidad` (nuevo).

### Plantilla (`semestres/_template/`)

- `configuracion.json` (raíz de la plantilla): nuevo, con el valor de la decisión 8 (1.2).
- `tests_semanales/data/preguntas.csv`: solo cabecera con `Instancia,Titulo,Envio,Estado,Confirmada` más las 15 de siempre.
- `tests_semanales/prompts/evaluar_respuesta.md`: misma rúbrica, salida JSON sin nota (fase 4).
- `correo_pregunta.md:9`: la frase de la escala usa `{ESCALA}` («una nota en la escala de 4,0 a 7,0»), o se borra si el semestre oculta la nota.
- `correo_correccion.md:5`: la encuesta «cuéntanos del 1 al 7 qué te pareció esta corrección» es el único número que queda en un correo con `correo_muestra: nada`, y se puede leer como la nota. Pasa a «Si quieres, cuéntanos qué tan útil te resultó esta corrección (nada, poco, bastante, mucho) y por qué». Ningún código lee esa respuesta (lo busqué en `modulos/`, `web/public/` y la plantilla), así que el cambio de escala de la encuesta no rompe nada. 2026-2 conserva su archivo en R2.
- `tutoria.md`: no revelar números que el correo ocultó.
- `correo_ajuste.md`: nuevo, sin la etiqueta `NOTA FINAL` (2.4).

### Sábana (`modulos/sabana.py`)

- `:27-36`: columnas nuevas `Logro`, `NotaDelModelo` (de `correccion`, o de `evaluacion` en filas viejas), `NotaEnviada`, `Editada`, `RevisadoPor`, `CorregidoPor` (modelo o docente), `ModoRevision`, `FechaFeedback`, `Descartada`, `EscalaNota` (la escala con que se calculó la `Nota` vigente, de `Versiones` o del último `recalculo`) y `Recalculada` (sí/no).
- `:55-62`: hoy guarda solo el último `envio`, `evaluacion` y `ajuste`; suma `correccion`, `descarte` y `recalculo`, y toma la primera `respuesta` sin `Detalle=duplicado`. Sin `recalculo`, tras `datos.escala` la `Nota` cambiaría, `AjusteManual` diría «no» y nada explicaría la diferencia con `NotaEnviada`.
- `:102-107`: estados «por revisar» y «descartada».
- `:116-134`: tokens desde `correccion` y, si no hay, desde `evaluacion`.

### Streamlit (`app/`)

Se congela en la fase 1 (decisión 7): `app/pages/1_Tests_Semanales.py:63-92` corre `modulos.tests.evaluar` directo y se saltaría la revisión. El resto de Streamlit no sigue la escala ni los estados nuevos, y queda escrito así: `app/main.py:104`, `:226`, `:274`, `:359` fijan los ejes en `[1.0, 7.0]`, y `app/pages/3_Datos_y_Configuracion.py:405-429` edita `NOTA_MIN`/`NOTA_MAX` del `.env` local, que son de Tareas. `app/main.py` muestra arriba «Streamlit muestra notas en escala 1–7 y no conoce la revisión; la fuente es el sitio». No se congela entero porque sigue siendo la vista local de los semestres viejos, que no cambian.

### Pruebas

Cada prueba va en la fase que cambia su código (entre corchetes). Las nuevas en Python se agregan a `ARCHIVOS` de `pruebas/todas.py:10-12`; las de Node se llaman desde `pruebas/web.py`, como `probar-preguntas.mjs` (`:259-266`).

Cambian:

- `pruebas/comun.py:142`: respuesta falsa en los dos formatos [4].
- `pruebas/e2e_tests_semanales.py:56-73`: envío en el mismo trabajo solo en automático [3]. `:83-104`: parcha `modulos.tests.evaluar.enviar_correo`; al mudarse el envío a `modulos/revision/enviar.py` el parche deja de interceptar, el correo cae en el SMTP falso de `pruebas/comun.py:96-100` y la prueba falla con `cuerpos` vacío; el parche pasa a `modulos.revision.enviar.enviar_correo` [3]. `:575-604`: marcar leídos y candidatos cambian con los pasos 1 y 4 de 2.2 [1 y 3].
- `pruebas/e2e_tareas.py:55-70`: parcha `_corregir_una` y cuenta dos `evaluacion`; en `revisar` hay `correccion` y ninguna `evaluacion` hasta `tareas.feedback` [3].
- `pruebas/motor.py:103-201`: 1–999, alias `semana`, ítem `\d{1,3}` [2]; `avisar` exige `prueba: false` y `flujo: "test"`; `sin_modelo` agrega `--revisar` [3].
- `pruebas/web.py:209-253` y `web/scripts/probar-preguntas.mjs:29-92`: columnas opcionales, `Instancia`, archivo vacío, id siguiente con `notas.csv` [2].
- `pruebas/sabana.py:29`: `int(f["Item"])` se queda (ids enteros); cambian las columnas esperadas [3].
- `pruebas/limpieza_correos.py:21`: suma un caso con la frase nueva sin quitar el de la vieja [2].
- `pruebas/reportes.py:123-128`: tramos según escala [4]; pendientes separados de por revisar y descartadas [3].
- `pruebas/ajuste_notas.py:38`: rango según escala [4].
- `pruebas/app_paginas.py:143`: Streamlit congelado [1].
- `web/scripts/probar-consumo.mjs:68-88`: el ciclo con `Envio` y varias abiertas, sin perder los casos de 7 días del legado [2]. El archivo lo está tocando el otro agente; se edita después de su cambio.
- `web/scripts/probar-correos.mjs:64-66`: `evaluacionDeTexto` con JSON, además del caso con `NOTA FINAL` [4].
- `web/scripts/probar-prompts.mjs:8-9`: `NOTA FINAL` obligatoria solo en el formato viejo; un prompt JSON con `puntaje` y `originalidad` no avisa [4].

Nuevas:

- Esquema [1]: `escribir` conserva columnas desconocidas; escritura atómica (un `escribir` que falla a mitad deja el archivo anterior entero: se simula con un `DictWriter` que levanta en la fila 3); `reconstruir_estado` con `descarte`, `recalculo` y duplicados; `sincronizar_desde_log` pone al día una nota atrasada y no pisa una editada a mano; `comparar` ve `Corregido`.
- Simulaciones que no escriben [1]: cada flujo de `SIMULABLES` y los nuevos en prueba, sobre una copia de semestre; la huella de `notas.csv` y del log no cambia (3).
- Tutoría [1]: una respuesta con In-Reply-To al `MessageId` de una `evaluacion` de Tareas no entra a `_pendientes`, no registra `error` y se cuenta aparte.
- Reconocimiento por Message-ID [1]: un correo ya registrado como `respuesta` (también como duplicado) se marca leído sin correo de duplicado.
- Corte por tiempo [1]: en `pruebas/motor.py`, con `LIMITE_SEGUNDOS` chico y un script falso que recorre con `avanzar`, el aviso de cancelación llega antes del `kill`, el script para entre alumnos, `_guardar` sube lo hecho y el estado queda «fallido» con el texto del límite.
- Id que no se reutiliza [2]: borrar la última instancia en «Tabla completa» con envíos se rechaza; sin envíos, el id siguiente sigue siendo `max(preguntas, notas) + 1`.
- Escala [1 el módulo, 4 el uso]: lineal, dos tramos, inversa, redondeo, identidad 4–7 sobre todas las notas posibles del prompt viejo.
- Extractor en los dos formatos; armado del correo Python contra JS, con `NOTA FINAL` cuando se muestra la nota [4].
- `base` igual en Python y JS [3]: el mismo log leído por `decisiones.py` y por `revision.js` da el mismo `Timestamp` para cada alumno, con `\r\n` en el archivo.
- Flujo partido [3]: corregir, aprobar, enviar, repetir sin duplicar; envío fallido que se reintenta; decisión vieja (`base`) ignorada; `evaluacion` en el log antes que `Nota` en `notas.csv`.
- Cuerpo idéntico en 2026-2 [3]: con el mismo HTML del modelo, el cuerpo que arma `enviar_una` con `correo_muestra: nota` es igual byte a byte al de `_construir_cuerpo_correccion` antes del corte (se guarda como archivo de referencia en `pruebas/`, generado con el código de la fase 2).
- `sin_modelo` en automático [3]: con `configuracion.json` ausente, «Corregir yo» deja la corrección por revisar y no sale correo; una corrección `docente:*` sin decisión no sale en `tests.feedback`.
- Descarte [3]: decisión `descartada` → evento `descarte`, `Descartada` en `notas.csv`, `PorRevisar` falso, no aparece en pendientes ni en el contador.
- Cambio de `auto` a `revisar` [3]: una corrección `modo=auto` sin enviar no sale en `tests.feedback` si la configuración vigente es `revisar`.
- Tareas en `revisar` [3]: la segunda corrida de `tareas.corregir` no vuelve a llamar al modelo para quien tiene `Corregido`; `tareas.feedback` lista las notas antiguas y solo las manda con `antiguas`.
- Candidatos y chequeo [3]: un corregido sin enviar sale con `estado: "por revisar"`, desmarcado, y el chequeo lo cuenta aparte.
- Resumen [3]: no llama a `evaluar_respuesta`; recibe el texto de las correcciones guardadas y las preguntas de los dos grupos.
- Ajuste con aviso [3]: en prueba se rechaza; en real sale hilado a la última `evaluacion`, sin `NOTA FINAL`, y la insignia del historial dice que mandó correo.
- Tutoría con revisión activa [3].
- Recálculo con ajustes fijos y `recalculo` en la sábana [4]; dominio de los ejes con un ajuste bajo la mínima [4].

## 6. Cómo se ve en pantalla

**Preguntas.** La lista de tests muestra título, fecha de envío, fecha de entrega y un estado: borrador, confirmado o enviado (n alumnos). «+ Nuevo test» funciona aunque el semestre no tenga `preguntas.csv`: crea el archivo con su cabecera y el test 1. El editor de un test agrega título y fecha de envío arriba del tema. Abajo, «Confirmar test» (si está en borrador) o «Volver a borrador» (si no se ha enviado). Editar un test ya enviado muestra «Ya se envió a 52 alumnos; el cambio no les llega», y no ofrece borrarlo.

**Tests › Enviar.** El número 1–52 se reemplaza por una lista de tests con título. Uno en borrador se puede simular; el botón real dice «Confirma el test antes de enviarlo».

**Tests › Evaluar.** Arriba, «Después de corregir: (•) Enviar el feedback automáticamente ( ) Dejarlo para revisión», con el valor del semestre marcado. La simulación muestra los candidatos como hoy, con «por revisar» o «descartada» al lado de quien ya pasó por ahí, desmarcados. En modo revisión los botones dicen «Corregir con IA las N elegidas» y «Las corrijo yo», y la confirmación dice que no sale feedback todavía. En automático, el botón y la confirmación siguen como hoy.

**Tests › Revisar** (pestaña nueva, con contador). Filtros: por revisar, aprobadas, enviadas, descartadas. El grupo del alumno no aparece en la lista (ver R3). Cada tarjeta:

- Izquierda: la respuesta completa del alumno y la hora de llegada.
- Derecha: el correo tal como lo recibiría, en el mismo iframe aislado que ya usa la vista de correos (`web/public/comun.js:281-336`). «Editar» lo convierte en formulario: por pregunta, el rótulo, una lista de puntajes de la rúbrica y la justificación; originalidad; retroalimentación. Debajo, siempre visible para el docente: «Logro 83 % → nota 6,5», aunque el correo oculte la nota. En el legado: la nota y el HTML.
- Avisos: «el modelo juntó dos preguntas en un bloque», «respondió otra vez el 03/11» (con el texto de esa segunda respuesta, de la `respuesta` con `Detalle=duplicado`), «la IA volvió a corregir: revisa otra vez». En Tareas, «el modelo marcó señales de copia» con su justificación interna.
- Botones: «Aprobar», «Aprobar y enviar», «Descartar…» (pide motivo y registra el descarte con un trabajo, 2.3), «Volver a lo de la IA». Un descarte todavía no registrado ofrece «Volver a revisar». En una corrigida a mano, el formulario empieza vacío y «Aprobar» exige los puntajes completos.

Barra fija abajo: «Enviar las 23 aprobadas» con confirmación que dice a cuántos alumnos sale correo.

**Inicio.** En «Requiere atención»: «12 correcciones esperando revisión (Semana 6)», sin contar las descartadas. Un trabajo cortado por el límite de tiempo aparece entre los fallidos por repetir. El ciclo muestra cada test abierto con su título y sus fechas.

**Resultados.** Ejes y títulos con el nombre de cada test. Las notas por revisar no se cuentan como notas; aparecen en «Pendientes» como «por revisar», aparte de «sin corregir», y el número del indicador coincide con la lista que abre el clic. Las descartadas no son pendientes. La ficha muestra nota del modelo y nota enviada cuando difieren, y quién revisó. El ajuste tiene la casilla «Avisarle al alumno por correo», con vista previa del aviso; con la casilla marcada, el historial muestra el trabajo como real y con la insignia de correos.

**Configuración › Semestre** (sección nueva).

- «Después de la corrección de la IA: enviar automáticamente / revisar antes de enviar».
- «En el correo de corrección, mostrar: puntajes y nota / solo puntajes / ningún número».
- «Escala de notas»: mínima, máxima, decimales, casilla «Escala con nota de aprobación» (aprobación y exigencia %). Una tabla chica de logro → nota (0, 25, 50, 60, 75, 100 %). «Ver qué cambia» corre la simulación de `datos.escala`; «Guardar y recalcular» la corre en real después de una confirmación con el número de notas ya comunicadas que cambian; si hay alguna, la confirmación pide además escribir el id del semestre (2.5).

## 7. Fases

Cada fase se publica entera (motor, Worker, D1 y plantilla de R2 en el mismo despliegue, con permiso previo) y deja 2026-2 funcionando igual.

### 7.1 Tareas de implementación

Una tarea es un commit que deja `python pruebas/todas.py` en verde. Van en orden: cada una puede usar lo de las anteriores de su fase. Cada línea dice archivos, qué cambia y qué prueba la cubre; el detalle está en la sección que se cita. «Nueva `esquema_nuevo.py`» es un archivo de pruebas nuevo, `pruebas/esquema_nuevo.py`, que se agrega a `ARCHIVOS` de `pruebas/todas.py:9-11` en la primera tarea que lo use.

**Fase 0 (sin código).**

- 0.1 Apagar la evaluación de las 10:15 del otro PC (`PENDIENTES_PO.md:95`).
- 0.2 Esperar a que el otro agente deje en `master` sus cambios de `modulos/ia/cliente.py`, `web/public/consumo.js`, `comun.js`, `datos.js`, `app.js`, `motor/desplegar.ps1` y `web/public/_headers`, y volver a leer los números de línea de esos archivos citados aquí.
  (agregado en la comprobación) La lista se queda corta: `git diff --stat` del 02/11 muestra también sin commitear `web/src/index.ts` (saca `preciosValidos` a `precios.ts`; desde la línea 76 todo corre 13 líneas respecto de `HEAD`), `web/src/precios.ts`, `web/public/inicio.js`, `criterio.js`, `precios.js`, `estilos.css`, `modulos/config.py`, `modulos/ia/__init__.py`, `modulos/tareas/corregir.py` (`:84`), `pruebas/web.py` (+80 líneas) y `web/scripts/probar-consumo.mjs`, `probar-criterio.mjs`, `probar-precios.mjs`. La nota del inicio («los demás coinciden con `HEAD`») no vale para esos: los números de `index.ts` citados aquí (`:59-66`, `:100-110`, `:443-453`) son los del árbol de trabajo, no los de `HEAD`. La fase 1 toca `index.ts` (1.9) y `pruebas/web.py` (prueba de 1.9), así que espera a que esos dos también entren.
- 0.3 `python pruebas/todas.py` en verde como base, y guardar la salida.

**Fase 1. Esquema común.**

- 1.1 `modulos/datos/_csv.py:22-32`: `escribir` conserva las columnas del archivo que el llamador no conoce y escribe a `.tmp` + `replace` (1.4). Prueba: nueva `esquema_nuevo.py` (columna desconocida sobrevive; una excepción en la fila 3 deja el archivo anterior entero).
  (agregado en la comprobación) Orden de columnas: las del llamador primero y después las que solo tenía el archivo, como `fusionar` (`modulos/datos/log.py:338-342`). `escribir` tiene otros dos llamadores que heredan el cambio: `alumnos.guardar` (`modulos/datos/alumnos.py:30`, que usa `tests.enviar` al asignar grupos) pasa a conservar las columnas extra del `alumnos.csv` del profesor, que hoy borra; y `migracion.migrar` (`modulos/datos/migracion.py:66`, `:100`), que solo escribe archivos nuevos y no cambia. Es un cambio de comportamiento en `alumnos.csv`; la prueba lo cubre con un caso. Revisé los demás escritores de `notas.csv` y del log: solo `_csv.escribir` (vía `notas._upsert` y `sincronizar_desde_log`), `_csv.agregar`/`_ampliar_columnas` (ya conservan) y `log.fusionar` (ya conserva). Streamlit no edita `notas.csv` ni el log (`app/pages/3_Datos_y_Configuracion.py:164-177` edita `alumnos.csv` y `preguntas.csv` con pandas, que conserva columnas), la página no puede (`web/src/index.ts:100-110`) y no hay endpoint para restaurar una versión del historial. El `.tmp` que deje un corte no se sube: `_en_perfil` (`motor/trabajo.py:212-224`) solo acepta `.csv/.json/.md/.txt` en la raíz y `subir.py` lo excluye (`modulos/web/subir.py:77-80`).
- 1.2 `modulos/datos/esquema.py:23-65`: `Corregido`, `Logro`, `Descartada` en `COLUMNAS_NOTAS`; `correccion`, `descarte`, `recalculo` en `EVENTOS`; `Puntajes`, `Logro` en `COLUMNAS_LOG`; `ajuste` en `DEL_AGENTE`. `modulos/datos/notas.py:61-62` y `:139-140`: las filas nuevas nacen con las columnas nuevas. Prueba: `esquema_nuevo.py` (registrar cada evento nuevo; un `notas.csv` viejo gana las columnas al primer `escribir`); `pruebas/e2e_tests_semanales.py` sin cambios, en verde.
- 1.3 `modulos/datos/log.py:101-118`: `fila_por_message_id(..., flujo=)`. `modulos/tests/tutoria.py:57` y `modulos/tests/evaluar.py:144` lo usan con `flujo=TESTS`; la tutoría cuenta aparte las respuestas a feedback de Tareas (1.5). Prueba: caso nuevo en `pruebas/e2e_tests_semanales.py` (respuesta a una `evaluacion` de Tareas con `MessageId`: no entra, no registra `error`).
- 1.4 `modulos/datos/notas.py`: `marcar_corregido`, `marcar_descartada`, `ya_corregido`, `por_revisar`; `registrar_nota(..., logro="")`. Prueba: `esquema_nuevo.py`.
- 1.5 `modulos/datos/log.py:64-92`: `reconstruir_estado` con `correccion`, `descarte`, `recalculo`, `historia_nota`, sin las `respuesta` de `Detalle=duplicado`. `:183-216`: `como_interacciones` toma la primera respuesta no duplicada. Prueba: `esquema_nuevo.py`.
  (agregado en la comprobación) «La primera» rompe Tareas: con segunda oportunidad hay dos `respuesta` legítimas del mismo alumno en la misma tarea (`modulos/tareas/segunda_oportunidad.py:205-210` cambia el `message_id` y `modulos/tareas/recolectar.py:57-58` registra la segunda), y `tareas.corregir` corrige la última (`modulos/tareas/corregir.py:114-116`, el dict se queda con la última). Si `como_interacciones` toma la primera, el panel de Tareas y la sábana mostrarían la respuesta que no se corrigió. Regla para los tres lectores (`reconstruir_estado`, `como_interacciones`, sábana): ignorar las `respuesta` con `Detalle=duplicado` y dejar el resto como hoy (la última en `como_interacciones` `:206-209` y en `Respondio` `:81-82`). En Tests da lo mismo que «la primera», porque desde la fase 1 las únicas `respuesta` extra son duplicados. Lo mismo vale para el texto de 1.5 y 5 › Datos que dice «la primera». Prueba: caso de Tareas con dos `respuesta` en `esquema_nuevo.py`.
- 1.6 `modulos/datos/notas.py:108-160`: `sincronizar_desde_log` llena `Corregido`, `Logro`, `Descartada` y pone al día la nota atrasada (1.5). `modulos/datos/comparar.py:99`, `:138`: columnas nuevas. Prueba: `esquema_nuevo.py` (nota atrasada se actualiza; nota editada a mano no se toca).
- 1.7 `modulos/tests/evaluar.py:214-237`, `:267-303`: `respuesta` con `MessageId` y `RespondeA`; paso 1 de 2.2 (Message-ID ya registrado → solo marcar leído); paso 3 con `ya_corregido` y registro del duplicado con `Detalle=duplicado`. Prueba: `pruebas/e2e_tests_semanales.py:575-604` adaptada, más un caso de `marcar_leidos` fallido y repetición sin correo de duplicado.
  (agregado en la comprobación) Desde esta tarea existen `respuesta` con `Detalle=duplicado`, y hay lectores que no son los de 1.5 y que se cambian aquí mismo, no en la fase 3:
  - `modulos/tests/resumen.py:16-20` arma `{correo: Respuesta}` con todas las `respuesta`; gana la última, que sería el texto del duplicado, y el resumen volvería a corregir una respuesta que no se evaluó. Filtrar `Detalle=duplicado` ya en esta tarea (la reescritura de `resumen.py` es 3.6).
  - `log.conversacion` (`modulos/datos/log.py:151-167`) mete en el historial de la tutoría todo `DEL_ALUMNO`, y `ia_prompts.responder_duda` rotula como «AYUDANTE» todo lo que no sea `repregunta` (`modulos/tests/ia_prompts.py:84-87`): el duplicado entraría al prompt como si lo hubiera escrito el ayudante. `conversacion` excluye `Detalle=duplicado`. De paso: hoy la `respuesta` original ya sale rotulada «AYUDANTE (ronda 0)»; el rótulo debería ser «ESTUDIANTE» para todo `DEL_ALUMNO`. No lo verifiqué contra salidas reales de la tutoría.
  - Llave de deduplicación: `_clave_evento` (`modulos/datos/log.py:242-255`) y `_clave_log` (`modulos/datos/comparar.py:32-35`) usan Timestamp, Flujo, Item, Correo y Evento, con la premisa de que un alumno no genera dos veces el mismo evento del mismo ítem en el mismo segundo. Un duplicado registrado en el mismo segundo que la `respuesta` de su primer correo (dos correos seguidos en la misma corrida, con el envío del duplicado fallando rápido) se perdería en `fusionar`. Sumar `MessageId` a las dos llaves; en las filas viejas vale vacío en los dos lados y no cambia nada.
  - Paso 1: la búsqueda es `fila_por_message_id(mid, eventos=("respuesta",), flujo=TESTS)`, con el filtro de 1.3. Un Message-ID vacío no calza (`_mismo_id` exige los dos, `modulos/datos/log.py:95-98`). Recorre el log entero por cada correo (`leer` relee el archivo en cada llamada, `:51-61`); con 0,9 MB y unas 50 respuestas alcanza, pero conviene leer el log una vez al empezar `evaluar.main` y armar el conjunto de Message-ID.
  - `pruebas/comun.py:125-138`: `respuestas_falsas` no trae `message_id`; los casos nuevos lo necesitan. Agregarlo como argumento opcional para no cambiar los casos que ya existen (el paso 1 no aplica sin Message-ID y siguen recibiendo el duplicado).
- 1.8 `motor/trabajo.py:336-400`: aviso de cancelación a los 22 minutos sin marcar `cancelado`; estado «fallido» con el texto del límite (2.2 › Corte por tiempo). Prueba: `pruebas/motor.py:361-364` (ya acorta `LIMITE_SEGUNDOS`) más un caso con un script que recorre con `avanzar`.
  (agregado en la comprobación) Escribir el archivo de cancelar no alcanza para que el trabajo quede «fallido»: el script para entre alumnos y sale con código 0, y `ejecutar` decide `estado` con `ok = codigo == 0 and not fallidos` (`motor/trabajo.py:509-512`), así que quedaría «terminado» y `fallidosSinResolver` no lo mostraría. Hace falta un `threading.Event` propio (por ejemplo `cerca_del_limite`) que el reloj de los 22 minutos marque junto con el archivo; `_correr` lo devuelve o lo deja en `salida`, agrega el texto del límite (el de `avanzar`, «Detenido a pedido», `modulos/progreso.py:38`, se ve igual y confunde si no va seguido del aviso) y `ejecutar` pone `estado="fallido"` cuando está marcado aunque el código sea 0. El segundo reloj se cancela en el mismo `finally` que `reloj` (`:384-388`). Para los `CORTABLES` (`:343-344`) el aviso no cambia nada: ninguno recorre con `avanzar` salvo que se cambie, y siguen cortándose a los 25.
- 1.9 Columnas del panel: `modulos/datos/reportes.py:97-114`, `web/src/index.ts:59-66` (`COLUMNAS`, `BOOLEANAS`), `web/schema.sql:14-33` con el `ALTER TABLE` comentado, `modulos/web/subir.py:55`, `:162`. Vacías por ahora, salvo `PorRevisar` y `Descartada` en falso. Prueba: `pruebas/web.py:121` (orden de `COLUMNAS` igual al de `reportes.panel`) y `pruebas/reportes.py`.
  (agregado en la comprobación) El `ALTER TABLE` de 1.8 está escrito como una sola sentencia con cuatro `ADD COLUMN`; SQLite (D1) acepta una columna por `ALTER TABLE`. Son cuatro sentencias: `ALTER TABLE panel ADD COLUMN Logro REAL;`, `… NotaModelo REAL;`, `… PorRevisar INTEGER;`, `… Descartada INTEGER;`, y así se dejan comentadas en `web/schema.sql` junto al `CREATE TABLE`. `modulos/web/subir.py:55`, `:162` y `motor/sitio.py:112-115` mandan las filas tal cual, sin lista de columnas: no cambian, solo se verifica. El Worker inserta y lee solo sus `COLUMNAS` (`web/src/index.ts:180-191`, `:208-212`): con el motor nuevo y el Worker viejo las claves extra se ignoran; con el Worker nuevo y D1 sin `ALTER`, fallan tanto `subirPanel` como `leerPanel` (Resultados no carga). `PorRevisar` y `Descartada` en Python son `bool`, como las demás de `BOOLEANAS`.
- 1.10 Simulaciones que no escriben: prueba nueva `pruebas/simulaciones.py` que corre en prueba los flujos de `SIMULABLES` sobre una copia de semestre y compara la huella de `notas.csv` y del log (3). Sin cambio de código si pasa; si falla, se arregla el flujo que escribe antes de seguir.
  (agregado en la comprobación) La lista de flujos sale de `simula()` y no solo de `SIMULABLES` (`web/public/comun.js:456-458`): incluye `tareas.segunda` con `paso: "enviar"` en prueba, que corre `borradores` (`motor/trabajo.py:70-77`, `modulos/tareas/segunda_oportunidad.py:181-190`). La copia de semestre tiene que traer `notas.csv`: todo `notas.leer`/`estado` llama a `migracion.asegurar` (`modulos/datos/notas.py:30`, `:43`), que en un semestre sin `notas.csv` y con el `alumnos.csv` viejo migra y escribe. Los flujos leen el buzón: la prueba usa el mismo `sin_red()` y los parches de `buscar_respuestas_semana`/`buscar_no_leidos` que `pruebas/e2e_tests_semanales.py`.
- 1.11 `modulos/escala.py` con la escala por defecto, sin consumidores. Prueba: nueva `pruebas/escala.py` (lineal, dos tramos, inversa, redondeo `ROUND_HALF_UP`, identidad 4–7).
- 1.12 Streamlit: `app/pages/1_Tests_Semanales.py:63-92` sin evaluar ni enviar; aviso arriba en `app/main.py` (5 › Streamlit). Prueba: `pruebas/app_paginas.py:143`.
- 1.13 Despliegue: `ALTER TABLE` en D1 a mano antes del Worker (R9); motor y Worker juntos.
  (agregado en la comprobación) Orden que no rompe nada en medio: primero las cuatro `ALTER TABLE` (1.9), después el motor, después el Worker. No desplegar entre las 17:30 y las 18:30 de Santiago: el cron corre `tests.tutoria` real a las 18:00 (`web/wrangler.toml:15`, `web/src/index.ts:443-453`), y un trabajo que termine con el Worker ya nuevo y D1 sin columnas sube sus archivos pero falla al subir el panel («Falló al guardar», `motor/trabajo.py:500-515`). Esa tutoría es también el primer trabajo real que va a ampliar las columnas del log de 2026-2 (`_csv.agregar` → `_ampliar_columnas`, `modulos/datos/_csv.py:80-81`) si nadie corre otro antes; es lo esperado (3), pero conviene mirar su salida al día siguiente. El 0.1 (evaluación de las 10:15 del otro PC) tiene que estar apagado antes de este paso, no solo antes de la fase 3: desde la fase 1 el código viejo de ese PC borraría `Corregido`, `Logro` y `Descartada` al escribir, y no reconoce los duplicados.

**Fase 2. Instancias.**

- 2.1 Ayudante común del id: `modulos/tests/preguntas.py:43-102` lee `Instancia` o `Semana`, id estricto 1–999, repetidos como error, archivo opcional, `titulo`, `envio`, `estado`, y qué columna usa el archivo. `modulos/tests/reconstruir.py:131` y `modulos/sabana.py:68-82` usan el ayudante. Prueba: `pruebas/web.py:209-253` y casos nuevos en `pruebas/e2e_tests_semanales.py` (archivo sin filas, id inválido, `Semana` y `Instancia` a la vez).
  (agregado en la comprobación) Tipo de los errores nuevos. `sabana._preguntas_tests` atrapa solo `FileNotFoundError` y `ValueError` (`modulos/sabana.py:72-79`); `experimento.py:415-419`, `tutoria.py:111-123` y `chequeo.py:56-65` atrapan `Exception`. Los errores nuevos («el test 5 no existe», id repetido, `Semana` e `Instancia` a la vez, id inválido) son `ValueError` o una subclase, para que `datos.sabana` no se caiga. Un error de archivo entero (las dos columnas) en la sábana deja las columnas de preguntas vacías y lo dice en la salida, en vez de abortar la sábana completa. `reconstruir.cargar_preguntas` (`modulos/tests/reconstruir.py:121-143`) hoy salta filas con `continue`; con el ayudante, el id inválido se informa y la fila se salta igual (es una herramienta de recuperación y no debe parar).
- 2.2 `motor/trabajo.py:40-44`, `:86`, `:160-171`: `_instancia` acepta `instancia` o `semana`, 1–999; ítem del ajuste `\d{1,3}`. Prueba: `pruebas/motor.py:103-201`.
  (agregado en la comprobación) Los lugares exactos: `:41-42` (`int(a.get("semana", 0))` y `1 <= s <= 52`), `:86` (ítem `\d{1,2}`), `:160` (experimento mira solo `a.get("semana") is not None`) y `:171` (tutoría mira solo `a.get("semana")`); en los dos últimos, con un trabajo que mande `instancia`, el motor ignoraría el id y correría «todas». Fuera del motor quedan topes de 52 que no se cambian: Streamlit (`app/pages/1_Tests_Semanales.py:63`, `:83`, `:102`, `:151`, `:206`); las dos primeras se retiran en 1.12 y resumen, tutoría y experimento de Streamlit quedan sin poder elegir un test mayor que 52. Se anota en el aviso de `app/main.py` de 1.12.
- 2.3 `modulos/tests/enviar.py:30-35`, `:47`, `:51-52`, `:67-69`: `{TITULO}`, texto según la columna (2.1), borrador no se envía en real. `modulos/mail/limpieza.py:243`: acepta las dos frases. Prueba: `pruebas/limpieza_correos.py:21` más el caso nuevo; caso de borrador en `pruebas/e2e_tests_semanales.py`.
  (agregado en la comprobación) `modulos/mail/limpieza.py:243` es la línea con que el alumno presenta su respuesta («mis respuestas de esta semana:»), no el texto de nuestro correo; la cita del correo original se corta por el encabezado «El … escribió:» (`:189-190`). La frase nueva «La pregunta es» no depende de esa regex. El cambio de `:243` es opcional (aceptar «mis respuestas al test:»); lo que sí conviene es el caso de `pruebas/limpieza_correos.py` con una cita sin `>` que contenga «La pregunta es:», para confirmar que se corta igual que la vieja.
- 2.4 `modulos/mail/lectura.py:52`, `:77-88`: In-Reply-To contra un `envio` de Tests de la instancia antes que el asunto. Prueba: caso nuevo en `pruebas/e2e_tests_semanales.py` (asunto cambiado, In-Reply-To correcto).
- 2.5 `web/public/comun.js`: `idDe(argumentos)` y su uso en `sobreQue`, `claveTrabajo`; `web/public/tests.js:204`, `:241-254`; `web/public/inicio.js:45`, `:131`; `web/public/probar.js:262`, `:288`. Prueba: caso nuevo en `web/scripts/probar-consumo.mjs` (`fallidosSinResolver` empareja un trabajo con `semana: 4` y otro con `instancia: 4`).
  (agregado en la comprobación) Faltan lecturas de `a.semana` en `web/public/tests.js` que no están en la lista: `:37` y `:46` (texto de las confirmaciones, diría «la semana undefined»), `:54` (`descarga` arma `resumen_semana_${a.semana}.txt`: con `instancia` el enlace apunta a `resumen_semana_undefined.txt`; además `:254` exige `t.argumentos.semana` y no mostraría el enlace), `:248` (`pedirTrabajo(..., { semana, prueba: false, solo })` al evaluar los elegidos: debe mandar `instancia`), `:353` (columna del historial `a.semana ?? "todas"`: un trabajo nuevo saldría como «todas»). Todas pasan a `idDe`.
- 2.6 `web/public/preguntas.js`: columnas opcionales, id estricto, `agregarInstancia` con `notas.csv`, sin borrar tests con envíos, «+ Nuevo test», «Confirmar test», texto del bloque según la columna. `web/public/datos.js:228-242`, `:1188-1200`: «Tabla completa» crea el archivo vacío y rechaza borrar ids con envíos. Prueba: `web/scripts/probar-preguntas.mjs:29-92` con los casos de 1.1.
  (agregado en la comprobación) `columnasFaltantes` (`web/public/preguntas.js:19-28`) exige la columna `Semana` (está en `COLUMNAS`). Con la plantilla de 2.8 (cabecera `Instancia,…`) el editor se bloquea en `:533-536` («preguntas.csv no tiene las columnas que usa este editor (Semana)… Edítalo desde Tabla completa»). Debe exigir `Instancia` o `Semana` (una de las dos) más las 14 restantes; la prueba `probar-preguntas.mjs:28` suma un archivo con `Instancia`. `numeroDe` (`:30-33`) es lo que usan `leerSemana` y `semanasDe`, y a través de ellos `ciclo.js:72`, `:90` y `app.js:162`, `:1054`: al cambiar `numeroDe` al ayudante quedan cubiertos sin tocarlos. `agregarSemana` (`:123-133`) escribe hoy el id en la columna literal `"Semana"` (`:126`); con un archivo de `Instancia` dejaría la fila nueva sin id. Usa la columna que tenga el archivo.
- 2.7 `web/public/ciclo.js:45-98`: `Envio` por instancia, varias abiertas, 7 días solo en legado. `web/public/tests.js:271`, `:313`, `web/public/probar.js:142`, `:206`: lista de tests con título; los trabajos nuevos mandan `instancia`. Prueba: `web/scripts/probar-consumo.mjs:68-88` con casos de `Envio`.
  (agregado en la comprobación) Los textos de pantalla de la decisión 9 no tienen tarea. 5 › Páginas pide «títulos de instancia en ejes y fichas» y la tarjeta de Inicio con el título, pero ninguna tarea los cubre: `web/public/inicio.js:24`, `:30` («Semana N» en la tarjeta), `web/public/tests.js:120-160` y `:210-232` (estado por pestaña, todo en «semana»), `web/public/app.js:101`, `:266`, `:586`, `:631`, `:643`, `:704`, `:728`, `:1040` (títulos de ejes y avisos «Semana»). Van en esta tarea, con el título de la instancia cuando exista y «Semana N»/«Test N» según la columna del archivo (1.1). Prueba: ninguna de lógica; revisión visual con un semestre de prueba de columna `Instancia` y con 2026-2, que debe verse igual que hoy.
- 2.8 Plantilla: `semestres/_template/tests_semanales/data/preguntas.csv` con la cabecera nueva. `modulos/web/subir.py`: opción `--plantilla` (4). Prueba: caso nuevo en `pruebas/web.py` con un sitio falso (reemplaza un distinto con su etag, no toca semestres ni reportería).

**Fase 3. Revisión.**

- 3.1 `modulos/revision/decisiones.py`: leer `revision/<id>.json`, `base` = `Timestamp` de la última `correccion`, juntar. Prueba: nueva `pruebas/revision.py` (decisión vieja ignorada) y `base` igual en Python y JS (con `revision.js` de 3.9).
- 3.2 `modulos/revision/armado.py`: armador de Tests (mueve `_construir_cuerpo_correccion` desde `modulos/tests/evaluar.py:72` sin cambios) y de Tareas (mueve `_construir_cuerpo_feedback` desde `modulos/tareas/corregir.py:93-102`). Prueba: cuerpo idéntico byte a byte contra la referencia generada en la fase 2 (3).
- 3.3 `modulos/revision/enviar.py`: `enviar_una` (log antes que `notas.csv`), descartes, selección con la configuración vigente, `docente:*` solo con decisión, modo prueba con `mostrar_correo`, `antiguas`, `sincronizar_desde_log` al empezar en real. Prueba: `pruebas/revision.py` (flujo partido, reintento, descarte, cambio de `auto` a `revisar`, `sin_modelo` en automático).
- 3.4 `modulos/tests/evaluar.py:148-372`: corte en `correccion` + `enviar_una`; `--revisar`, `--sin-modelo` (implica `--revisar`); candidatos con `estado`. Prueba: `pruebas/e2e_tests_semanales.py:56-73` y `:83-104` con el parche movido a `modulos.revision.enviar.enviar_correo`.
- 3.5 `modulos/tareas/corregir.py:105-191`: corte, `--revisar`, `ya_corregido` en pendientes y candidatos, JSON completo en `correccion.EvaluacionIA`, escala real en `Versiones`. Prueba: `pruebas/e2e_tareas.py:55-70` adaptada, más la segunda corrida sin llamar al modelo.
- 3.6 `modulos/tests/resumen.py`, `modulos/tests/ia_prompts.py:100-112`, `modulos/tests/chequeo.py:68-93` (2.8). Prueba: casos nuevos en `pruebas/e2e_tests_semanales.py` (resumen sin `evaluar_respuesta`; chequeo con por revisar).
- 3.7 `motor/trabajo.py:80-99`, `:167-200`: `tests.feedback`, `tareas.feedback` (con `_prueba`, `antiguas`), `sin_modelo`, `avisar` con `prueba is False` y `flujo: "test"`. `web/src/index.ts:70-75`: `FLUJOS`; `:100-110`: `EDITABLES` con `configuracion.json` y `revision/*.json`. Prueba: `pruebas/motor.py` y `pruebas/web.py:161-163` (FLUJOS iguales).
- 3.8 `modulos/datos/ajustar.py:28-53`: rechazo si está por revisar; `--avisar` con `correo_ajuste.md` o texto fijo, sin `NOTA FINAL`, hilado a la última `evaluacion`. Plantilla: `correo_ajuste.md`. Prueba: `pruebas/ajuste_notas.py` (aviso en real, hilado; rechazo por revisar).
- 3.9 Páginas: `web/public/revision.js` (2.9, 6), pestaña «3 · Revisar» en `web/public/tests.js`, selector y textos de Evaluar (`:40-48`), `web/public/comun.js` (`SIMULABLES`, `mandaCorreos`, `elegirCandidatos` con `estado`), `web/public/ciclo.js` e `inicio.js` con por revisar y descartadas, `web/public/app.js:1095-1123` con la casilla de aviso y `prueba: false`, Configuración › Semestre sin la escala. Prueba: `web/scripts/probar-consumo.mjs` (`mandaCorreos` e insignia de `datos.ajustar` con aviso), casos nuevos para `elegirCandidatos` y para `base` en Node.
- 3.10 `modulos/datos/agregaciones.py:90-95`, `:130-140`, `:543-548`, `modulos/datos/reportes.py`: por revisar y descartadas fuera de los pendientes; regenerar `web/public/py/`. Prueba: `pruebas/reportes.py` (indicador igual a la lista del clic).
- 3.11 `modulos/sabana.py`: columnas y eventos nuevos (5 › Sábana). `web/public/sabana.js:19`. Prueba: `pruebas/sabana.py` y `web/scripts/probar-sabana.mjs`.
- 3.12 Plantilla: `configuracion.json`, `correo_correccion.md` sin la encuesta del 1 al 7; subir con `--plantilla`. Prueba: `pruebas/web.py` (la plantilla trae `configuracion.json` válido).

**Fase 4. Escala y formato nuevo.**

- 4.1 `modulos/tests/correccion.py` y `web/public/correccion.js`: leer JSON o HTML, validar, calcular, armar según `correo_muestra` (con `NOTA FINAL` cuando se muestra la nota), `texto_docente`. `modulos/tests/evaluar.py:262` usa `correccion.leer`. Prueba: nueva `pruebas/correccion.py` y comparación Python contra JS en `pruebas/web.py`.
- 4.2 `modulos/tests/ia_prompts.py:30-60`: pide JSON cuando el prompt lo declara (después del cambio de `cliente.py`). Prueba: `pruebas/comun.py:142` con respuesta falsa en los dos formatos.
- 4.3 `modulos/datos/escala_trabajo.py` y `datos.escala` en motor y Worker; `SIMULABLES`. Prueba: `pruebas/escala.py` (recálculo con ajustes fijos, eventos `recalculo`).
- 4.4 Ejes y validación por escala: `modulos/datos/agregaciones.py:212-238`, `web/public/app.js:244-248`, `modulos/datos/ajustar.py`, `motor/trabajo.py:91-93`. Prueba: `pruebas/reportes.py:123-128`, `pruebas/ajuste_notas.py:38`, caso de un ajuste bajo la mínima.
- 4.5 Configuración › Semestre: escala con «Ver qué cambia» y la confirmación reforzada de 2.5. Prueba: caso en Node para la confirmación cuando hay notas comunicadas.
- 4.6 Revisión por pregunta en `revision.js` para el formato nuevo. Prueba: comparación Python contra JS de 4.1 con decisiones aplicadas.
- 4.7 `modulos/tests/experimento.py:95-96`, `:108-118`, `:346`, `:465`; `web/public/prompts.js:15`; `web/public/comun.js:243`. Prueba: `web/scripts/probar-prompts.mjs:8-9`, `probar-correos.mjs:64-66`, caso nuevo de `candidatas` sin `docente:*`.
- 4.8 Plantilla: `evaluar_respuesta.md` en JSON, `{ESCALA}` en `correo_pregunta.md`, `tutoria.md` que no revela; subir con `--plantilla`. Prueba: `web/scripts/probar-prompts.mjs` acepta el prompt nuevo.

### 7.2 Qué deja cada fase

**Fase 0. Preparación, sin publicar.**

- Apagar la evaluación de las 10:15 del otro PC (`PENDIENTES_PO.md:95`): evalúa con código viejo y su `_csv.escribir` borraría las columnas nuevas.
- Esperar a que entren los cambios del otro agente en `cliente.py`, `consumo.js`, `comun.js`, `datos.js`, `app.js`, `desplegar.ps1` y `_headers`, y acordar con él que los tokens pasan a `correccion` (abajo, R7).
- `python pruebas/todas.py` en verde como base.

**Fase 1. Esquema común.** Invisible para el usuario.

- Columnas y eventos nuevos (1.4, 1.5); `_csv.escribir` que conserva columnas y escribe atómico.
- `reconstruir_estado` y `sincronizar_desde_log` al día, con la regla de nota atrasada.
- Filtro de flujo en `fila_por_message_id`, antes de que Tareas guarde `MessageId`.
- Columnas nuevas del panel en D1, Worker, `reportes.panel` y `subir.py` (vacías por ahora).
- `evaluar.py` guarda `MessageId` y `RespondeA` en `respuesta`, reconoce lo ya procesado (arregla el correo de duplicado del punto 17) y registra los duplicados.
- Corte suave antes de los 25 minutos.
- Prueba de que ninguna simulación escribe tablas.
- `modulos/escala.py` con la escala por defecto, sin consumidores todavía.
- Congelar la página de Tests de Streamlit y avisar en el resto.

Publicable: sí. 2026-2 gana columnas vacías y deja de recibir duplicados cuando falla `marcar_leidos`.

**Fase 2. Instancias.**

- `preguntas.py` y `preguntas.js` con columnas opcionales, id estricto, archivo opcional, id que no se reutiliza, «+ Nuevo test», confirmar.
- Motor con `instancia` y 1–999; `idDe` en todas las lecturas del id; páginas con lista de tests en vez de 1–52; ciclo por fechas; textos (la frase nueva solo con columna `Instancia`).
- Reconocimiento por In-Reply-To antes que por asunto.
- `subir.py --plantilla` y plantilla con `preguntas.csv` vacío, subida a R2.

Publicable: sí. 2026-2 ve sus semanas como «Semana 1…N» y las envía igual, con el mismo texto. Se puede crear un semestre de prueba sin subir CSV.

**Fase 3. Revisión.**

- `modulos/revision/`, `evaluar.py` partido, `tareas/corregir.py` partido, `tests.feedback` y `tareas.feedback`, descartes.
- `configuracion.json`, `revision/*.json` en `EDITABLES`, pestaña Revisar (edición de legado: nota y HTML), «Corregir yo», Inicio.
- Resumen desde las correcciones guardadas; chequeo y candidatos con «por revisar».
- Ajuste con aviso y `correo_ajuste.md`.
- Resultados y sábana con por revisar y descartadas.

Publicable: sí. 2026-2 sigue en automático, con el mismo correo, y gana el reintento de feedback fallido. Si el equipo quiere probar la revisión en 2026-2, se enciende desde Configuración.

**Fase 4. Escala y formato nuevo.**

- `correccion.py`/`correccion.js` con JSON, `correo_muestra` aplicado al armado.
- `datos.escala` con simulación y recálculo; ejes e histograma por escala; ajuste por escala.
- Prompt nuevo en la plantilla (JSON, sin nota), `{ESCALA}` en `correo_pregunta.md`, tutoría que no revela.
- Revisión con edición por pregunta para el formato nuevo.
- Probar criterio comparando contra la nota del modelo.

Publicable: sí. 2026-2 no tiene `escala_notas.json` ni el prompt nuevo, así que nada cambia; «Cambiar la escala» aparece pero no se usa en ese semestre (2.5). El primer semestre que se cree después usa todo.

**Después (fuera de este diseño):** envío programado por `Envio` desde el cron; asunto configurable por semestre (para otros cursos); «volver a corregir con IA» a un alumno desde Revisar; crear `alumnos.csv` sin subir archivo.

## 8. Riesgos

- **R1. Pérdida de lo hecho si el motor muere entre enviar y subir.** El motor sube los CSV al final (`motor/trabajo.py:515-527`); si la instancia de Cloud Run muere a mitad, los correos salieron y el registro no. Pasa hoy igual. El reconocimiento por Message-ID evita la segunda corrección, pero no un feedback repetido en automático. El corte por tiempo, que es el caso predecible, deja de matar a mitad de un alumno (2.2 › Corte por tiempo), y `notas.csv` ya no puede quedar truncado (1.4). Lo que queda es la muerte de la instancia de Cloud Run entre `enviar_correo` y la línea del log: riesgo conocido.
- **R2. Dos docentes editando la misma instancia.** Cubierto por If-Match y reintento por alumno (1.6). Si los dos editan al mismo alumno, gana el segundo, y el `historial/` guarda el primero.
- **R3. Sesgo en el experimento.** Si el docente edita más un grupo que otro, la diferencia control/tratamiento mezcla modelo y docente. Mitigación: la lista de revisión no muestra el grupo, y la sábana separa `NotaDelModelo`, `NotaEnviada` y `Editada` para analizar con y sin ediciones.
- **R4. Números en la retroalimentación.** Con `correo_muestra: nada`, el modelo puede escribir «sacaste 2 de 3» dentro del texto. El prompt nuevo lo prohíbe; en revisión el docente lo ve; en automático puede escaparse. Se puede agregar un aviso que busque patrones como «x / 3» o «nota» en la retroalimentación.
- **R5. Recalcular notas ya comunicadas.** El alumno recibió un 6,5 y Resultados mostrará otra cosa. La simulación dice cuántas son, y el recálculo no avisa a nadie. Es lo aprobado; queda visible en el log.
- **R6. Cambio de formato del prompt a mitad de semestre.** Aunque la rúbrica sea la misma, pasar de HTML a JSON puede mover las notas del modelo. Por eso 2026-2 no cambia (decisión 5).
- **R7. Costo de API.** Los tokens pasan de `evaluacion` a `correccion`. Lo que sume costo leyendo solo `evaluacion` subestima desde la fase 3. Hay que coordinarlo con el cambio en curso de `consumo.js` y con `modulos/sabana.py:134`.
- **R8. Plantilla de R2 desalineada.** Cambiar `semestres/_template/` en el repo no llega a los semestres nuevos si no se sube, y `subir.py --archivos` no reemplaza los archivos que ya existen (`modulos/web/subir.py:101-103`). Se sube con `subir.py --plantilla` (4), que va en la lista de cada despliegue con `--simular` primero.
- **R9. D1 sin migraciones.** El `ALTER TABLE` se corre a mano antes de publicar el Worker de la fase 1; si se publica antes, `subirPanel` falla al insertar columnas que no existen.
- **R10. Tamaño del log.** Cada corrección deja dos filas con texto (`correccion` y `evaluacion`). Con JSON en `correccion` y solo el bloque enviado en `evaluacion`, estimo un 30–50 % más por semestre (2026-2 va en 0,9 MB). No lo medí. El motor baja el log en cada trabajo de tests.
- **R11. Borradores olvidados.** Una corrección que nadie revisa no vence. Inicio la muestra hasta que se apruebe o descarte; no se manda sola, tampoco si era automática y el semestre pasó a revisión (2.3).

## 9. Decisiones para el usuario

1. **Id de instancia: entero correlativo (1–999) o texto libre («4a»).** Recomiendo entero. Con texto hay que tocar unos 25 `int()`/`Number()`, el reconocimiento del asunto y las pruebas, sin ganancia visible, porque el título ya es libre.
2. **¿La confirmación bloquea el envío real?** Recomiendo sí para las instancias creadas desde la página (nacen en borrador) y no para las existentes (sin columna `Estado` cuentan como confirmadas). La simulación nunca se bloquea.
3. **Mientras una corrección espera revisión, ¿Resultados la cuenta como nota?** Recomiendo que no: la nota existe cuando sale el correo, y la propuesta se ve en Revisar y en «Pendientes» como «por revisar». Así no cambia ningún indicador ya publicado.
4. **Tutoría con revisión activa: automática o también revisada.** Recomiendo automática, como hoy. Solo responde dudas sobre feedback ya enviado, y revisarla retrasaría respuestas que hoy salen el mismo día a las 18:00. Se puede agregar después un interruptor aparte.
5. **2026-2 sigue con su prompt HTML hasta cerrar.** Recomiendo que sí: puede usar la revisión (editando nota y texto) y no cambia ninguna nota. El prompt de puntajes en JSON se estrena en el próximo semestre.
6. **Tareas conserva su escala (décimas de `escala.json` o `NOTA_MIN`–`NOTA_MAX`) y solo adopta la revisión.** Recomiendo que sí: en 2026-2 la nota de una tarea es un ajuste con signo (`modulos/tareas/reporte.py:27-30`), que no encaja en una transformación de logro.
7. **Congelar la página de Tests de Streamlit.** Recomiendo retirarle evaluar y enviar en la fase 1: corre `modulos.tests.evaluar` directo y se salta la revisión y los ids nuevos. El resto de Streamlit queda con ejes de 1 a 7 y sin los estados nuevos, con un aviso (5 › Streamlit).
8. **Qué muestra por defecto el correo de corrección en un semestre nuevo.** Recomiendo «solo puntajes por pregunta», sin nota: cumple el «idealmente no se ve la nota» del product owner y le deja al alumno saber en qué pregunta le faltó. 2026-2 sigue con «puntajes y nota». El diseño está escrito con esta opción.
   - Si se elige «puntajes y nota»: `semestres/_template/configuracion.json` lleva `"correo_muestra": "nota"`; `correo_pregunta.md` conserva la frase de la escala con `{ESCALA}`; R4 desaparece; `reconstruir` desde Gmail recupera las notas de los semestres nuevos (5 › Tests); el cambio de la encuesta de `correo_correccion.md:5` deja de ser necesario, aunque no estorba. Nada más cambia: el armado ya soporta los tres valores.
   - Si se elige «ningún número»: la plantilla lleva `"correo_muestra": "nada"`; `correo_pregunta.md` borra la frase de la escala; el aviso de R4 (buscar «x / 3» o «nota» en la retroalimentación) pasa de opcional a obligatorio, en la tarjeta de Revisar y en la salida de las automáticas, en la fase 4; el cambio de la encuesta de `correo_correccion.md:5` se vuelve imprescindible; `correo_ajuste.md` por defecto no da la nota nueva.
   - En los tres casos, el valor es por semestre y se cambia en Configuración › Semestre.
9. **Palabra genérica en la interfaz.** Recomiendo «Test» («Test 5 · Control 2a» donde haga falta el id; el título solo donde alcance). «Instancia» es correcto pero no lo usa nadie del curso. El diseño está escrito con «Test» en los textos de pantalla y «instancia» en el código.
   - Si se elige «Instancia» (u otra palabra): cambian solo textos, en femenino donde corresponda: «+ Nueva instancia», «Confirmar instancia», «Confirma la instancia antes de enviarla», «todavía no hay instancias», «la instancia 5 no existe; créala en Preguntas», el título por defecto en archivos nuevos («Instancia N», 1.1), la columna de la salida de `experimento.py` y el mensaje de «Tabla completa». No cambian columnas (`Instancia`), argumentos (`instancia`), asunto (`Módulo {id}`) ni pruebas de lógica; sí las pruebas que comparan textos (`web/scripts/probar-preguntas.mjs`).
   - Si se mantiene «Semana»: el título por defecto sigue siendo «Semana N» también en archivos nuevos, y los textos de dos instancias en la misma semana («Semana 5», «Semana 6» enviadas el mismo lunes) confunden; recomiendo no hacerlo. La frase «La pregunta de la semana es» podría quedarse en todos los semestres y 2.1 se simplifica.

## 10. Respuesta a la crítica previa

1. Id entero de 1–52 en todas partes: se adopta el entero correlativo, sube a 999 y se valida con una sola regla (1.1, 5 › Motor). Los `int()` listados quedan válidos.
2. Página y Python leen distinto un id no numérico: la misma regla estricta en los dos lados, con error visible (1.1; `preguntas.js:30-33`, `preguntas.py:53-57`).
3. Sin CSV no hay semestre: archivo opcional, «sin instancias», el editor lo crea y la plantilla lo trae vacío (1.1, fase 2).
4. La plantilla de la nube es la de R2: subida en cada fase y riesgo R8 (4, 8).
5. Ciclo con una instancia por semana: `Envio` por instancia y varias abiertas a la vez; los 7 días quedan solo para el legado (1.1, 5 › Páginas `ciclo.js`).
6. Asunto e identificación por asunto: con ids enteros el asunto sigue identificando; se agrega In-Reply-To antes que el asunto en la fase 2. El asunto configurable para otros cursos queda para después (7).
7. Máximo tres preguntas y dos grupos: se mantienen y quedan escritos como límite (1.1).
8. Otros lectores de `preguntas.csv`: se conserva el archivo y el nombre de la columna se resuelve con un ayudante común (`sabana.py`, `reconstruir.py`, `EDITABLES` sin cambio, `resumen_semana_<id>.txt` sin cambio).
9. Trabajos guardados con `semana`: el motor y la página aceptan `semana` e `instancia` (1.8, 5 › Motor y `comun.js`).
10. «Semana» en la interfaz: decisión 9; el cambio de textos va en la fase 2, separado de la lógica de revisión y escala.
11. Corregir y enviar en el mismo ciclo: se parte (2.2, 2.3). En vez de crear un evento `feedback`, `evaluacion` sigue siendo el envío y se agrega `correccion` para la propuesta, así `DEL_AGENTE`, `tutoria.py:57` y `evaluar.py:144` siguen funcionando sin cambios. Los eventos nuevos se agregan a `EVENTOS` antes de usarse (fase 1), así `log.registrar` no levanta `ValueError`.
12. Corregida y enviada son lo mismo: `Corregido` en `notas.csv` y el estado «por revisar» (1.4). Elegí no escribir `Nota` hasta el envío en vez de agregar `Feedback`; con eso las filas viejas con nota no necesitan relleno (el problema del punto 41 desaparece) y ningún lector de «hay nota» cambia. Resultados no muestra notas sin enviar (decisión 3).
13. Reconstruir desde el log ignoraría las ediciones: la nota editada queda en `evaluacion`, que `reconstruir_estado` ya toma; `recalculo` se trata como `ajuste` (1.5).
14. El envío diferido no tiene con qué hilar: `respuesta` guarda `MessageId` y `RespondeA` (1.5, fase 1).
15. Lo enviado no queda guardado: `evaluacion.EvaluacionIA` pasa a ser el bloque enviado, ya editado y sin los números ocultos; la tutoría recibe eso; la sábana suma `NotaDelModelo`, `RevisadoPor`, `FechaFeedback` (1.5, 2.6, 5 › Sábana). La plantilla envolvente se identifica por su huella en `Versiones`; no guardo el cuerpo completo para no duplicar el log.
16. Dónde se guardan las ediciones: en `revision/<id>.json`, que escribe solo la página y el trabajo solo lee (1.6). No hay un trabajo por edición. El choque con la tutoría del cron no existe porque la tutoría no toca ese archivo, y entre trabajos que escriben no hay choque porque van en la cola de uno en uno (`motor/cola.py:16-19`). Expliqué en 1.6 por qué R2 y no D1.
17. Repetir la evaluación manda duplicados: reconocimiento por Message-ID en la fase 1 (2.2, paso 1).
18. Envío cortable sin repetir: registro por alumno inmediatamente después de su correo, selección por «sin `evaluacion` posterior» (2.3).
19. Otros flujos que mandan correos: decididos uno por uno en 2.6; tutoría según la decisión 4.
20. Tareas sin salida para «no enviar»: `tareas.feedback` con el mismo módulo, y `evaluacion` de tareas con `MessageId` (2.7).
21. Ajustar nunca avisa: `--avisar` con plantilla, hilado y tutoría (2.4).
22. Ver respuestas antes del modelo ya existe: se reutilizan la simulación y `elegirCandidatos` (2.2, 6 › Evaluar).
23. Corregir el docente: `sin_modelo` y «Las corrijo yo»; `correccion` con `Modelo=docente:<correo>` y sin tokens; la sábana separa `CorregidoPor` (2.2, 5 › Sábana).
24. Dónde vive el interruptor: `configuracion.json` por semestre, con cambio por corrida (1.2).
25. Quién aprueba: cualquiera de los cinco de Access; queda `por` en la decisión y en `evaluacion.Detalle`. Los roles van con el punto 8 del product owner.
26. El prompt calcula la nota de 4 a 7: prompt nuevo en JSON sin nota y extractor doble; `experimento.py:346`, `comun.js:258`, `prompts.js:15` y el resumen aceptan los dos formatos (1.7, 5).
27. La nota va en el correo: `correo_muestra` y quita números también del HTML viejo; `{ESCALA}` en `correo_pregunta.md` (1.2, 1.7, 5 › Plantilla).
28. Sin nota en el correo, reconstruir desde Gmail no recupera notas: se acepta; desde 2026-2 la fuente es el log (5 › Tests).
29. Validaciones fijas de 1 a 7: validación por escala en `ajustar.py`, `trabajo.py`, `app.js`. `index.ts:84-85` y `datos.js:1047-1084` quedan para Tareas, que es lo único que los usa (2.4, decisión 6).
30. Escala global y sin registro por nota: `escala_notas.json` por semestre, `Logro` en notas y log, escala en `Versiones`, recálculo explícito con eventos (1.3, 2.5). Guardo `Logro` en vez de un `Puntaje` bruto porque el puntaje máximo depende de cuántos bloques devolvió el modelo; el detalle por pregunta va en `Puntajes`.
31. Gráficos fijos en 7: `NOTA_MAXIMA`, el tramo y los dominios salen de la escala; se regenera la copia de Pyodide (5 › Datos y Páginas).
32. Formato y redondeo: `decimales` en la escala, `ROUND_HALF_UP`, coma (1.3).
33. En Tareas el prompt recibe la escala: Tareas conserva su mecanismo y los nombres `NOTA_MIN`/`NOTA_MAX` no se reutilizan para tests (1.3, decisión 6).
34. Probar criterio compararía cosas distintas: se calcula con la escala del semestre y se compara contra `NotaModelo`, mostrando también la final (5 › Tests, `experimento.py:108-118`).
35. Ajustes de 2026-2 fuera del rango del modelo: no se migra 2026-2; un ajuste fuera de [mínima, máxima] queda con `Logro` vacío y fijo ante un cambio de escala (2.4, 2.5).
36. Columnas nuevas del panel: tres columnas, mismo orden en Python, Worker, tabla y `subir.py`, `ALTER TABLE` a mano, todo en el despliegue de la fase 1 (1.8, R9).
37. Pruebas que asumen el flujo actual: lista de cambios y de pruebas nuevas en 5 › Pruebas.
38. Streamlit se salta la revisión: decisión 7, en la fase 1.
39. El otro PC: fase 0, y `_csv.escribir` conserva columnas desconocidas (1.4).
40. 2026-2 en instancias: sin cambios de datos y con alias de `semana` (3).
41. 2026-2 en revisión: apagada por defecto. El relleno de `Feedback` no hace falta, porque «tiene nota» sigue significando «enviada» (punto 12). El sesgo al encenderla a mitad de semestre se trata en R3.
42. 2026-2 en escala: identidad 4–7 y prompt actual hasta cerrar (3, decisión 5).

## Anexo 19/11: fases 3 y 4

Revisado contra `master` en f0b41b0, con la fase 1 (esquema común, sin Streamlit) y la fase 2 (instancias) supuestas como hechas. Los números de línea son los de f0b41b0 y hay que volver a comprobarlos. Este anexo manda sobre las secciones 2.3, 2.7, 3.x y 4.x cuando no coinciden.

**Decisiones del orquestador (19/11), con la confianza que dio el usuario:**

- Un semestre nuevo parte con `"revision": "revisar"`. Así, el evaluar programado al Cierre no le manda feedback a nadie sin que el docente lo haya visto (R13). Tareas ya parte así (`tareas.js:46`).
- La escala tiene dos tipos: lineal y lineal con exigencia (dos tramos). El usuario los aprobó el 02/11 y de nuevo el 19/11.
- Si entra `TUTORIA_AUTOMATICA` desde el instalador, IN5162 la deja en `true`.

### 1. Tareas: se mantiene su flujo y se alinea el registro

Se mantiene lo que dejaron 5f35641 y a15cb0c:

- `feedback_<T>.csv`, con la columna `feedback_pendiente`.
- La revisión en `web/public/tareas.js:1137-1275`.
- El envío con `modulos/tareas/feedback.py`.
- El hilo con `encabezado_feedback` (`modulos/tareas/corregir.py:97-109`).

Este flujo ya se usó en la T2 y cubre lo que pedía 2.7. Migrarlo obliga a rehacer una pantalla recién estrenada, y el alumno no gana nada.

Lo que sí choca está en `corregir.py:207-215`: al corregir escribe `Nota` y un evento `evaluacion`, también con `--no-enviar`. Eso contradice la decisión 3. Además, después de la fase 1, `reconstruir_estado` y `sincronizar_desde_log` le volverían a poner la nota a quien espera revisión.

**3.5, en `corregir.py`:**

- `:142-146` y `:155-161`: los pendientes se eligen con `ya_corregido` y los candidatos llevan `estado`.
- `:206-222`: registra `correccion` (nota propuesta, comentario y JSON completo) y `marcar_corregido`. Deja de llamar a `registrar_nota`.
- `:228-240`: sin `--no-enviar`, después del envío registra `evaluacion` con el `MessageId` que devuelve `enviar_correo`, y recién entonces registra la nota.
- `:63`: anota la escala real.

**3.5b (nueva), en `feedback.py:46-106`:**

- Elige por el log: la última `correccion` que no tenga una `evaluacion` posterior. `feedback_pendiente` ya no basta.
- Al enviar, registra `evaluacion` y después la nota. La `evaluacion` lleva el MessageId, la nota y el comentario enviados, y un `Detalle` del tipo «revisado por X; nota a → b». Deja de registrar `ajuste` y `feedback`. El evento `feedback` sigue en `EVENTOS` para poder leer 2026-2.
- Al empezar, copia al CSV las correcciones que están en el log y faltan en el CSV.
- `motor/trabajo.py:225` le pasa `--por`.

**Página:**

- `tareas.js:139-166` cuenta como corregida una fila con `Corregido`.
- Cambian los textos que dicen que la nota ya quedó guardada: `tareas.js:50-55`, `:195`, `:1266-1267` y `comun.js:989-990`.

**Modo:** `configuracion.json` no aplica a Tareas. Tareas sigue con su casilla por corrida y con el `no_enviar` del envío programado (`:1065`). No se agrega «Descartar».

**Pruebas:**

- Cambian `pruebas/e2e_tareas.py:76-79` y `:136-173`.
- Caso nuevo: si el CSV dice pendiente y el log ya tiene `evaluacion`, no se reenvía.

**Salen del diseño:**

- `tareas/revision/<T>.json`, en 1.6 y en `EDITABLES`.
- En 2.3: `--flujo tarea`, el armador de Tareas y `antiguas`.
- La sección 2.7 entera.
- La parte de Tareas de 3.2, 3.3 y 3.9.
- El cambio de `no_enviar` a `revisar` (3.7).
- El caso «Tareas en revisar» de 5 › Pruebas.

`modulos/revision/` queda solo para Tests. Propuesta: separarlo en `modulos/tests/feedback.py` y `decisiones.py`, igual que en Tareas.

### 2. Fase 3, tarea por tarea

**3.1.** Solo `tests_semanales/revision/<Instancia>.json`.

**3.2.** Solo Tests. Mueve `_construir_cuerpo_correccion` y `_construir_asunto_respuesta` (`evaluar.py:72-82`). El asunto sale del mismo ayudante que usa `tests.enviar` en la fase 2.

**3.3.** `tests.feedback`, sin `--flujo` ni `antiguas`.

**3.4.** `evaluar.py:148-377`. El envío y el registro están en `:262-305`; los argumentos, en `:353-377`.

- No hay `--revisar`: el modo se lee de `configuracion.json` al momento de correr.
- La primera línea de la salida dice el modo.

**3.6.** Sin cambios.

**3.7.**

- `FLUJOS` suma solo `tests.feedback`, porque `tareas.feedback` ya existe.
- `EDITABLES` (`index.ts:100-115`) suma `configuracion.json` y `tests_semanales/revision/*.json`.

**3.8.** El aviso de ajuste lleva la nota por defecto (sección 4).

**3.9.**

- Revisar es una pestaña de Tests, entre Evaluar y Resumen. Hoy Resumen es «3 · Resumen semana» (`tests.js:50`, `:171-177`).
- `NOMBRE_FLUJO` (`comun.js:434-441`) y `SIMULABLES` (`:488-489`) suman `tests.feedback`.
- `mandaCorreos` está en `:546-549`, `elegirCandidatos` en `:952-1021` y el ajuste en `app.js:1093`.
- Las confirmaciones usan `confirmar()`.

**3.10.** Sin cambios. Tareas no entra al panel (`reportes.py:60`).

**3.11.**

- En Tareas, `NotaDelModelo` sale de `correccion`, y el `feedback` de 2026-2 cuenta como `FechaFeedback`.
- Una edición en la revisión ya no marca `AjusteManual` (`sabana.py:53-62`, `:114-152`).
- Los tokens se leen de `correccion` (`:134`).
- Las columnas nuevas llevan su explicación en `sabana.js`.

**3.12.** El `configuracion.json` de la plantilla es `{"revision": "revisar", "correo_muestra": "nota"}`. Sale el cambio de la encuesta.

**3.13 (nueva).** Evaluar programado; ver la sección 3.

**Decisión 5:**

- Salen «probar la revisión en 2026-2» (7.2) y «Cambiar la escala aparece en 2026-2».
- Configuración › Semestre muestra controles solo si el semestre tiene `configuracion.json`. Si no lo tiene, dice «usa la configuración de antes».
- La prueba de cuerpo idéntico se queda.

### 3. Instancias en la fase 3

El `tests.evaluar` programado al Cierre lleva `{instancia, prueba: false, a_las}`, sin `revisar` ni `solo`. El modo no se fija al confirmar: lo lee 3.4 al correr.

- En `revisar`, corrige y deja las propuestas. No reenvía las automáticas pendientes.
- En `auto`, corrige y envía.

La 3.13 suma tres cosas:

- El diálogo «Confirmar» dice qué va a pasar al Cierre según el modo vigente.
- Inicio muestra avisos como «12 correcciones esperando revisión (Control 2)».
- Una prueba nueva en `pruebas/motor.py`.

**Rótulos:**

- Revisar, Inicio y la ficha muestran «{Tipo} {Numero}», con el ayudante de la fase 2.
- Si el archivo tiene la columna `Semana`, muestran «Semana N».
- El id oculto solo aparece en rutas: `revision/<id>.json` y `#revisar/<id>`.
- El selector lista por Cierre las instancias que tienen algo por revisar o aprobado, por ejemplo «Control 2 · 12 por revisar · 3 aprobadas».

### 4. Correo por defecto: puntajes y nota

1. El `configuracion.json` de la plantilla lleva `"correo_muestra": "nota"`.
2. En `correo_pregunta.md:9` la frase de la escala se queda, pero «4.0 a 7.0» pasa a ser `{ESCALA}`. La llena `tests/enviar.py` a partir de `escala_notas.json`.
3. R4 deja de aplicar a un semestre nuevo y queda como opción para `puntajes` y `nada`. El prompt JSON igual prohíbe escribir notas en la retroalimentación.
4. En `correo_correccion.md:5`, la encuesta «del 1 al 7» se queda.
5. `correo_ajuste.md` dice «tu nota quedó en {NOTA}», sin `NOTA FINAL`.
6. `tutoria.md` dice «no menciones puntajes ni nota que no estén en la corrección que recibió».
7. Configuración › Semestre trae marcado «puntajes y nota», y `reconstruir` vuelve a recuperar notas desde Gmail.
8. En 4.1, `nota` es el caso principal de las pruebas que comparan Python con JS.

### 5. Fase 4

- **4.1.** Lo indicado en el punto 8 de la sección 4. `evaluacionDeTexto` está en `comun.js:274`.
- **4.2.** `json_mode=True` ya existe (`modulos/ia/cliente.py:216-219`).
- **4.3.** Sin cambios. La escala de dos tramos se queda.
- **4.4.** Sin Streamlit. `NOTA_MAXIMA` está en `agregaciones.py:214`, `dominioNotas` en `app.js:246` y la validación del motor en `motor/trabajo.py:93`.
- **4.5.** Sin cambios. Como la nota va en el correo, la confirmación reforzada va a aparecer casi siempre.
- **4.6 y 4.7.** Sin cambios.
- **4.8.** Lo de la sección 4, hecho sobre la plantilla neutra del instalador (R17).
- Streamlit sale de 5 › Streamlit, de la decisión 7 y del punto 38 de la sección 10.

### 6. Riesgos nuevos

- **R12.** `feedback_<T>.csv` lo escriben tanto la página como los trabajos. Si alguien edita mientras corre `tareas.feedback`, el CSV no se guarda por el etag y la corrida siguiente reenviaría. La 3.5b lo evita, porque decide con el log.
- **R13.** En modo `auto`, el evaluar programado manda el feedback sin que nadie lo pida. Por eso los semestres nuevos parten en `revisar`.
- **R14.** Si el corte de los 22 minutos detiene el evaluar programado, el trabajo queda fallido hasta que alguien mire Inicio. Además, nadie corrige las respuestas que llegan después del Cierre. Conviene ofrecer `tests.chequeo` en la instancia cerrada.
- **R15.** Cloud Tasks programa hasta 30 días (`index.ts:423`). Se encargó a la fase 2: el cron diario encola lo que entra en ese plazo.
- **R16.** Si el Tipo, el Número o el Tema cambian después del envío, el `Re:` no calza. Se encargó a la fase 2: se congelan desde el primer `envio`.
- **R17.** La rama del instalador reescribe prompts de la plantilla y mueve `web/schema.sql` a `web/migrations/0001_inicial.sql`. Por eso los `ALTER TABLE` de la fase 1 pasan a ser una migración.
- **R7 cambia.** El costo de cada trabajo sale de la línea «Consumo de API» de su salida (`consumo.js:13`). Solo la sábana lee tokens del log.
- **Orden de publicación.** La fase 3 tiene que estar publicada antes de la primera tarea del semestre nuevo.
