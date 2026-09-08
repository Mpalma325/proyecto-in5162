# Módulo `datos`

Las tablas del semestre. Sabe leer y escribir CSV, y nada más.

## Las tres tablas

Viven en la raíz del semestre (`semestres/<id>/`), no dentro de
`tests_semanales/` o `tareas/`: ahora son compartidas y la columna `Flujo`
distingue de cuál viene cada fila.

| Archivo | Qué es | Cómo se usa |
|---|---|---|
| `alumnos.csv` | Quiénes son | Casi no cambia. Refleja lo que sube el profesor; el sistema solo agrega el grupo. |
| `notas.csv` | En qué van | Se lee y escribe todo el tiempo. Es lo que se edita a mano para corregir notas. |
| `log_envios.csv` | Qué pasó | **Append-only.** El flujo solo escribe; se lee para reconstruir o investigar. |

## Qué hace y qué no

**Sí:** leer y escribir esas tres tablas, y responder preguntas de dominio
(`pendientes_de_envio`, `ya_evaluado`, `grupo_de`). También las agregaciones de
la reportería, en `reportes.py`.

**No:** mandar correos, llamar a la IA, saber qué es una pauta o un prompt. Si
una función de acá necesita eso, va en el flujo que la llama.

## Importaciones permitidas

Librería estándar y `modulos.semestre` (que resuelve dónde están los archivos).
**No importa `mail` ni `ia`**: quien orquesta los tres es el flujo (`tests`,
`tareas`), no este módulo. Tampoco pandas: la reportería devuelve listas de
diccionarios y quien quiera un DataFrame lo arma en la app, que es donde pandas
ya vive. Así estas agregaciones sirven igual desde un script o un servidor.

## Los eventos del log

`envio`, `respuesta`, `evaluacion`, `repregunta`, `tutoria` y `error`. Los dos
del medio son el ciclo normal; `repregunta` y `tutoria` son las vueltas de
conversación cuando el alumno pregunta sobre su corrección.

`Ronda` vale 0 en el ciclo normal y 1..N en cada vuelta de tutoría. `MessageId`
es el id del mensaje que produjo el evento y `RespondeA` el del mensaje al que
contesta: con esos dos se encadena la conversación y se distingue una
repregunta de una respuesta atrasada.

Cuando el esquema crece, los archivos que ya existen se amplían solos la
primera vez que se les escribe (`_csv._ampliar_columnas`), conservando las
filas. Sin eso las filas nuevas quedarían corridas contra la cabecera vieja.

## La reportería

Todo sale de `reportes.panel()`: una fila por (alumno, ítem). El resto
—`por_item`, `por_grupo`, `por_alumno`, `ficha`, las distribuciones— son cortes
de esa misma tabla, así que una métrica se calcula en un solo lugar.

Dos cosas que hay que respetar al tocarla:

- Las notas vienen en formato chileno con coma (`"6,5"`). Pasa por
  `nota_a_float`; `float()` directo las convierte en nada.
- `Enviado` y `Respondio` mezclan fecha ISO y el literal `"SI"`, según los haya
  escrito el flujo o la migración. Solo se mira si están vacíos o no.

El panel infiere el envío cuando hay respuesta o nota. Sin eso la tasa de
respuesta pasaba de 100% en las semanas enviadas desde otro equipo, donde el
evento de envío no quedó registrado.

### La originalidad

El modelo la escribe en texto libre y el prompt le pide una de cinco
categorías, de "Muy Baja" a "Muy Alta". `nivel_originalidad()` las lleva a la
escala 1–5, que es lo que permite promediarlas y correlacionarlas con la nota;
la etiqueta original se conserva para mostrarla tal como vino.

Lo que no calza con ninguna de las cinco devuelve `None` y queda fuera de los
promedios. Pasa: en 2025-2 hay seis casillas con `-` y en 2026-1 hay tres donde
la extracción se comió un pedazo de la retroalimentación. Siguen apareciendo en
las tablas, con nivel vacío.

`correlacion_originalidad_nota()` es un Pearson entre el nivel y la nota. Como
la originalidad es ordinal y toma cinco valores, por ese lado equivale a una
correlación de rangos: dice la dirección y la fuerza, y no se puede leer como
una regresión. Con menos de tres pares, o si todas las casillas cayeron en la
misma categoría, devuelve `R` en `None` antes que un número sin sentido.

## Cómo se usa

```python
from modulos import datos

datos.alumnos.correos()                                   # ["ana@x.cl", ...]
datos.alumnos.asignar_grupos_faltantes(semilla=19)         # solo a los que no tienen

faltan = datos.notas.pendientes_de_envio(correos, datos.TESTS, "3")
datos.notas.marcar_enviado(correo, datos.TESTS, "3")
datos.notas.registrar_nota(correo, datos.TESTS, "3", "6,5", "Baja")
datos.notas.ya_evaluado(correo, datos.TESTS, "3")

datos.log.registrar("envio", datos.TESTS, "3", correo, MessageId=mid)
```

## Por qué el log es append-only

Cada fila es un **evento** (`envio`, `respuesta`, `evaluacion`, `error`), no una
interacción. Un mismo alumno en una misma semana deja varias filas.

Eso evita tener que editar algo ya escrito, que es lo que se rompe cuando dos
personas operan el curso desde equipos distintos: para juntar dos logs basta
concatenarlos y deduplicar. Con un archivo que se reescribe, gana el último que
guarda y se pierde lo del otro.

Ya pasó: en 2026-2 la Semana 3 quedó evaluada en un equipo y sin registro de
envío en el otro, porque el estado vivía en un CSV que cada uno reescribía.

Cuando eso pasa, `notas.sincronizar_desde_log()` completa la tabla de estado con
lo que el log tenga y a ella le falte:

```bash
python -m modulos.tests.reconstruir --solo-estado --simular   # dice cuanto
python -m modulos.tests.reconstruir --solo-estado             # lo aplica
```

**Solo agrega.** Crea la fila que falte y llena el campo vacío; no borra ninguna
fila ni pisa un valor ya escrito. Las dos razones: `notas.csv` también se edita a
mano cuando el equipo docente corrige una nota, y los semestres que vienen del
esquema viejo tienen filas anteriores al log, que el log no conoce y que un
volcado completo borraría.

## `interacciones.csv` ya no se mantiene

Antes se guardaba aparte una tabla con la pregunta, la respuesta y la
evaluación juntas. Ahora esa vista **se deriva del log**:

```python
datos.log.como_interacciones()            # en memoria
datos.log.exportar_interacciones()        # a un CSV, cuando se necesite
```

Se verificó contra los archivos que existían: 511, 457 y 80 filas
respectivamente, sin una sola diferencia. Mantenerla como archivo propio
significaba tener dos fuentes del mismo dato, que es exactamente lo que se
desalinea con el tiempo.

## Cuidado

`log.registrar()` **nunca lanza excepción** hacia el flujo: si el log falla, el
correo ya salió y perder el envío sería peor que perder la traza. Avisa por
pantalla y sigue. No cambies eso sin pensarlo.

`asignar_grupos_faltantes()` solo toca a quien no tiene grupo. El grupo de un
alumno no cambia nunca una vez puesto, porque define qué versión de pregunta le
tocó y de eso depende el estudio de impacto.
