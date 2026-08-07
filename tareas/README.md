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

Todo el estado del pipeline vive en `data/salidas/feedback_<TAREA>.csv`, dentro de la carpeta del semestre activo (`semestres/<id>/tareas/data/`).

## Uso

Operado desde la interfaz: `streamlit run app/main.py` → **Tareas**.

Cada paso tiene un modo prueba que no envía emails ni llama a GPT, activado por defecto.

## Datos necesarios

Se cargan desde **Datos y Configuración → Datos del curso** en la UI (ver [`docs/GUIA_INICIO.md`](../docs/GUIA_INICIO.md)); en disco viven en `semestres/<id>/tareas/`:

- `data/alumnos.csv` — padrón con columnas `nombre`, `correo` (ver plantilla en `semestres/_template/`)
- `data/entregas/` — HTMLs descargados desde U-Cursos; se pueden subir como `.zip` desde la sección **Entregas (Tareas)**
- `.env` (en la raíz de `tareas/`, global para todos los semestres) — credenciales (ver `.env.example`); se configuran desde la UI en **Datos y Configuración → Parámetros de la revisión**

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

- El paso 1 resuelve nombres contra `alumnos.csv` con fuzzy matching (≥82% similitud). Los que no matchean quedan con correo vacío; editarlos en **Datos y Configuración → Feedback Tareas** antes de enviar.
- El paso 3 identifica respuestas por el header `In-Reply-To`. Asumiendo que los alumnos responderán el correo que se les envía y no escribirán uno nuevo.
- Los prompts se editan directamente en `prompts/*.md` (dentro del semestre activo), o desde la UI en **Datos y Configuración**.
