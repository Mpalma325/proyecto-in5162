# Tareas — Feedback automatizado IN5162

Genera preguntas de comprensión personalizadas a partir de las entregas HTML de U-Cursos, las envía a los alumnos, recolecta respuestas y entrega feedback con nota usando GPT.

## Flujo

```
HTMLs de U-Cursos → Paso 1: Generar preguntas
                  → Paso 2: Enviar preguntas
                  → (esperar respuestas)
                  → Paso 3: Recolectar respuestas
                  → Paso 4: Corregir y enviar feedback
```

Todo el estado del pipeline vive en `data/salidas/feedback_<TAREA>.csv`.

## Uso

Operado desde la interfaz: `streamlit run app/main.py` → **Tareas**.

Cada paso tiene un modo prueba que no envía emails ni llama a GPT, activado por defecto.

## Datos necesarios

- `data/alumnos.csv` — padrón con columnas `nombre`, `correo` (ver `alumnos.example.csv`)
- `data/entregas/` — HTMLs descargados desde U-Cursos
- `.env` — credenciales (ver `.env.example`); se configuran desde la UI en **Configuración**

## Estructura del CSV de feedback

| Columna            | Paso | Descripción                                    |
|--------------------|------|------------------------------------------------|
| tarea              | 1    | Etiqueta de la tarea (T1, T2, etc.)           |
| grupo_archivo      | 1    | Nombre del HTML de entrada                     |
| alumno_nombre      | 1    | Nombre tal como aparece en el HTML             |
| alumno_correo      | 1    | Correo resuelto (del CSV o completado manual)  |
| pregunta           | 1    | Pregunta de comprensión generada por GPT       |
| pauta              | 1    | Pauta de corrección esperada                   |
| fecha_envio        | 2    | Timestamp del envío                            |
| message_id         | 2    | Message-ID para trackeo oculto de respuestas  |
| respuesta          | 3    | Texto de la respuesta del alumno               |
| nota               | 4    | Nota numérica asignada por GPT                 |
| comentario         | 4    | Feedback cualitativo enviado al alumno         |

## Notas de uso

- El paso 1 resuelve nombres contra `alumnos.csv` con fuzzy matching (≥82% similitud). Los que no matchean quedan con correo vacío; editarlos en **Datos → Feedback Tareas** antes de enviar.
- El paso 3 identifica respuestas por el header `In-Reply-To`. Si un alumno escribió un correo nuevo en vez de responder, hay que pegar su respuesta manualmente en el CSV.
- Los prompts se editan directamente en `prompts/*.md`.
