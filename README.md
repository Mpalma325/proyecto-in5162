# Proyecto IN5162

Herramientas de automatización docente para el curso IN5162.

## Subproyectos

- **[tests_semanales/](tests_semanales/)** — Envío, evaluación y resumen de tests semanales via email + GPT.
- **[tareas/](tareas/)** — Generación de preguntas de comprensión, envío y corrección automática de tareas.
- **[app/](app/)** — Interfaz gráfica (`streamlit run app/main.py`).

## Setup

```bash
python -m venv venv
venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Cada subproyecto requiere su propio `.env` con `OPENAI_API_KEY`, `CORREO_REMITENTE` y `CORREO_APP_PASSWORD`. Ver `.env.example` en cada carpeta.

## Datos de semestre

Al inicio de cada semestre, cargar desde **Datos → Archivos de semestre** en la UI:

- `tests_semanales/data/alumnos.csv` — padrón con columnas `Nombre`, `Correo`
- `tests_semanales/data/preguntas.csv` — preguntas y pautas por semana (ver `preguntas.example.csv`)
- `tareas/data/alumnos.csv` — padrón con columnas `nombre`, `correo`
