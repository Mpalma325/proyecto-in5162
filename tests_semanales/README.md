# Tests Semanales — Evaluación automática IN5162

Vía correo, se envian preguntas semanales a los alumnos, posteriormente se evalúan las respuestas con GPT y una pauta.

## Flujo

```
Paso 1: Enviar preguntas  →  (esperar respuestas)
                          →  Paso 2: Evaluar respuestas
                          →  Paso 3: Resumen de respuestas (opcional)
```

El estado de cada semana se escribe en `data/alumnos.csv` (columnas `Envío N`, `Respuesta N`, `Nota Test N`, `Originalidad N`).

## Uso

Operado desde la interfaz: `streamlit run app/main.py` → **Tests Semanales**.

Cada paso tiene un modo prueba activado por defecto que no envía emails ni guarda cambios.

## Datos necesarios

- `data/alumnos.csv` — padrón con columnas `Nombre` y `Correo` (ver `alumnos.example.csv`)
- `data/preguntas.csv` — preguntas y pautas por semana; columnas: `Semana`, `Tema`, `Fecha de Entrega`, `Pregunta 1–3`, `Pauta Pregunta 1–3`
- `.env` — credenciales (ver `.env.example`); se configuran desde la UI en **Configuración**

## Comportamiento relevante

- El paso 1 salta alumnos que ya tienen `SI` en `Envío N` — es seguro de reintentar.
- El paso 2 busca correos **no leídos** con asunto `Módulo N`. Si un alumno responde dos veces, solo se procesa la primera.
- El paso 3 genera un resumen en `data/resumen_semana_N.txt` descargable desde la interfaz.
- Los prompts se editan directamente en `prompts/*.md`.
