# Tests Semanales — Evaluación automática IN5162

Vía correo, se envian preguntas semanales a los alumnos, posteriormente se evalúan las respuestas con GPT y una pauta.

## Flujo

```
Paso 1: Enviar preguntas  →  (esperar respuestas)
                          →  Paso 2: Evaluar respuestas
                          →  Paso 3: Resumen de respuestas (opcional)
```

El estado de cada semana se escribe en `alumnos.csv` (columnas `Envío N`, `Respuesta N`, `Nota Test N`, `Originalidad N`), dentro de la carpeta del semestre activo (`semestres/<id>/tests_semanales/data/`).

## Uso

Operado desde la interfaz: `streamlit run app/main.py` → **Tests Semanales**.

Cada paso tiene un modo prueba activado por defecto que no envía emails ni guarda cambios.

## Datos necesarios

Se cargan desde **Datos y Configuración → Datos del curso** en la UI (ver [`docs/GUIA_INICIO.md`](../docs/GUIA_INICIO.md)); en disco viven en `semestres/<id>/tests_semanales/`:

- `data/alumnos.csv` — padrón con columnas `Nombre` y `Correo` (ver plantilla en `semestres/_template/`)
- `data/preguntas.csv` — preguntas y pautas por semana; columnas: `Semana`, `Tema`, `Fecha de Entrega`, `Pregunta 1–3`, `Pauta Pregunta 1–3`
- `.env` (en la raíz de `tests_semanales/`, global para todos los semestres) — credenciales (ver `.env.example`); se configuran desde la UI en **Datos y Configuración → Parámetros de la revisión**

## Comportamiento relevante

- El paso 1 salta alumnos que ya tienen `SI` en `Envío N` — es seguro de reintentar.
- El paso 2 busca correos **no leídos** con asunto `Módulo N`. Si un alumno responde dos veces, solo se procesa la primera.
- El paso 3 genera un resumen en `data/resumen_semana_N.txt` descargable desde la interfaz.
- Los prompts se editan directamente en `prompts/*.md` (dentro del semestre activo), o desde la UI en **Datos y Configuración**.
