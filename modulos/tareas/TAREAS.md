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

## Los cuatro pasos

| Archivo | Qué hace |
|---|---|
| `generar.py` | Lee los HTML y genera pregunta + pauta por integrante |
| `enviar.py` | Manda cada pregunta a su alumno |
| `recolectar.py` | Busca las respuestas en el buzón, por Message-ID |
| `corregir.py` | Corrige y manda el feedback |

Auxiliares: `limpieza_html.py` (extrae secciones del entregable),
`alumnos.py` (empareja nombres del HTML con correos del roster),
`storage.py` (el `feedback_T*.csv`), `ia_prompts.py`, `config.py`.

## Cómo se ejecuta

Desde la raíz del proyecto:

```
python -m modulos.tareas.generar T1
python -m modulos.tareas.enviar T1
python -m modulos.tareas.recolectar T1
python -m modulos.tareas.corregir T1
```

## Cuidado

**`paso2` y `paso4` mandan correos reales.** Ambos aceptan `--dry-run`.

El emparejamiento de nombres del paso 1 usa similitud de texto y **se equivoca**
con nombres parecidos: ya pasó con dos alumnos que compartían el primer nombre.
Cuando no encuentra coincidencia clara lo deja en blanco y hay que resolverlo a
mano en el CSV antes del paso 2. No conviene bajarle el umbral para que "acierte
más": es peor mandarle la pregunta al alumno equivocado que dejarla pendiente.
