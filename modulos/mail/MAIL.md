# Módulo `mail`

Todo lo que toca el correo: enviar, leer el buzón y limpiar los cuerpos.

Antes esto vivía duplicado en `tests_semanales/src/correo.py` y
`tareas/src/correo.py`, con implementaciones que ya habían divergido entre sí.

## Qué hace y qué no

**Sí:** hablar SMTP e IMAP, construir el mensaje, decidir si un correo responde
a otro, y sacar del cuerpo lo que realmente escribió el alumno.

**No:** saber qué es una semana, una tarea, un alumno o una nota. No lee ni
escribe CSV, no llama a la IA, no sabe qué es un semestre. Si algo acá necesita
ese contexto, va en el módulo del flujo (`tests` o `tareas`), no acá.

## Importaciones permitidas

Solo librería estándar y `bs4`. **No importa `datos`, `ia`, `semestre`, ni nada
de `tests_semanales/` o `tareas/`.** Si aparece esa necesidad, es señal de que
la lógica va en el flujo que llama, no acá.

## Cómo se usa

Antes de nada hay que decirle de dónde saca las credenciales. No las busca solo:

```python
from modulos import mail
mail.configurar(config.cargar_correo_config)   # función -> {remitente, password}
```

### Enviar

```python
message_id = mail.enviar_correo(destinatario, asunto, cuerpo,
                                html=False, in_reply_to=None)
```

`html=False` por defecto (texto plano, como lo usa tareas). Tests pasa
`html=True`. `in_reply_to` hace que el correo salga como respuesta en el mismo
hilo. Devuelve el Message-ID, que hay que guardar para reconocer la respuesta.

### Leer

Dos formas, según cómo se envió:

```python
mail.buscar_respuestas_semana(semana)     # por asunto, no leídos  (tests)
mail.buscar_respuestas(message_ids)       # por In-Reply-To, todo el hilo con adjuntos (tareas)
mail.marcar_leidos(uids)
```

## Configuración inyectada

Igual que las credenciales, los servidores se los pasa el flujo:

```python
mail.configurar(config.cargar_correo_config, config.cargar_servidores())
```

Los valores de `credenciales.py` son solo el default de Gmail. Estaban además
escritos en `modulos/config.py`, pero solo se usaban los de acá: cambiar los
del config no tenía ningún efecto.

## Cuidado con la limpieza de cuerpos

`_limpiar_respuesta` es la parte más delicada: decide qué parte del correo
escribió el alumno y qué parte es la cita del mensaje original. Las dos
versiones anteriores tenían bugs distintos:

- La de **tareas** cortaba en el primer `\nEl `, así que mutilaba cualquier
  respuesta con una línea empezando en "El " ("El modelo final incluye...").
- La de **tests** usaba `if idx_corte < 50` para adivinar si el alumno había
  escrito arriba o abajo de la cita. Con respuestas cortas devolvía la cita, o
  directamente vacío.

La versión actual decide explícitamente: se queda con lo de **arriba** de la
cita, salvo que ahí solo haya un saludo, en cuyo caso usa lo de abajo.

**Si tocas esta función, corre antes los casos de `_limpiar_respuesta`**: son
respuestas cortas, respuestas con "El " al inicio de línea, y respuestas
escritas debajo de la cita. Es fácil arreglar un caso y romper otro.
