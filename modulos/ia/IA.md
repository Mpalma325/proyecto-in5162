# Módulo `ia`

La conexión con el modelo de lenguaje. Antes estaba duplicada: tests lo usaba
para evaluar respuestas y generar resúmenes, tareas para generar preguntas en
JSON. La llamada era la misma en los tres casos.

## Qué hace y qué no

**Sí:** hablar con la API, aplicar el modelo y los parámetros configurados,
devolver el texto y cuántos tokens costó.

**No:** saber qué es una pregunta, una pauta o una respuesta de alumno. **Los
prompts no viven acá**, viven en el flujo que los usa (`tests`, `tareas`) y en
los `.md` de cada semestre. Si te encuentras escribiendo un prompt en este
módulo, va en otro lado.

## Importaciones permitidas

Solo librería estándar y `openai`. No importa `mail`, `datos`, `semestre` ni
nada de los flujos.

## Cómo se usa

```python
from modulos import ia
ia.configurar(config.cargar_api_key, config.MODELO, config.TEMPERATURA, config.MAX_TOKENS)

r = ia.completar(system_prompt, user_msg)
r.texto            # lo que respondió
r.meta             # {modelo, prompt_tokens, completion_tokens, total_tokens}
```

Para respuestas en JSON (lo que usa tareas):

```python
r = ia.completar(system, user, json_mode=True)
r.datos            # el texto ya parseado; falla con un error claro si no es JSON
```

`temperatura` y `max_tokens` se pueden pasar por llamada cuando difieren del
default: el resumen semanal usa 0.3 y 2000, distinto a la evaluación.

## Cuidado

`configurar()` guarda estado a nivel de módulo. Si algún día conviven dos
configuraciones distintas en el mismo proceso (dos semestres, dos modelos),
hay que pasar a instanciar un cliente en vez de usar el global.
