import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.runner import TAREAS_DIR, TESTS_DIR

st.title("Configuración")

ENV_PATHS = {
    "tests_semanales": TESTS_DIR / ".env",
    "tareas": TAREAS_DIR / ".env",
}


def _leer_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _escribir_env(path: Path, updates: dict) -> None:
    env = _leer_env(path)
    env.update({k: v for k, v in updates.items() if v != ""})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{k}={v}" for k, v in env.items()) + "\n",
        encoding="utf-8",
    )


# tests_semanales/.env es la fuente de verdad para las variables compartidas
env_ts = _leer_env(ENV_PATHS["tests_semanales"])
env_tar = _leer_env(ENV_PATHS["tareas"])

st.subheader("Credenciales")
st.markdown(
    "Se guardan en el `.env` de cada subproyecto. "
    "Idénticas en ambos — al guardar se escribe en los dos."
)

with st.form("form_creds"):
    api_key = st.text_input(
        "OpenAI API Key",
        value=env_ts.get("OPENAI_API_KEY", ""),
        type="password",
        placeholder="sk-proj-...",
    )
    correo = st.text_input(
        "Correo remitente",
        value=env_ts.get("CORREO_REMITENTE", ""),
        placeholder="in5162@uchile.cl",
    )
    password = st.text_input(
        "App password de Gmail (16 caracteres)",
        value=env_ts.get("CORREO_APP_PASSWORD", ""),
        type="password",
        placeholder="xxxx xxxx xxxx xxxx",
    )
    submitted_creds = st.form_submit_button("Guardar credenciales", type="primary")

if submitted_creds:
    updates = {}
    if api_key:
        updates["OPENAI_API_KEY"] = api_key
    if correo:
        updates["CORREO_REMITENTE"] = correo
    if password:
        updates["CORREO_APP_PASSWORD"] = password
    if updates:
        _escribir_env(ENV_PATHS["tests_semanales"], updates)
        _escribir_env(ENV_PATHS["tareas"], updates)
        st.success("Credenciales guardadas en ambos proyectos.")

st.divider()

st.subheader("Modelo OpenAI")
st.markdown("Aplica a ambos proyectos.")

MODELOS_CONOCIDOS = [
    "gpt-5.4-mini",   
    "gpt-5.5",        
    "gpt-5.4",        
    "gpt-5.4-nano",   
    "gpt-5-mini",     
    "gpt-4o-mini",    
    "gpt-4o",         
]
modelo_actual = env_ts.get("MODELO", "gpt-5.4-mini")

with st.form("form_modelo"):
    col1, col2 = st.columns(2)
    with col1:
        if modelo_actual in MODELOS_CONOCIDOS:
            modelo = st.selectbox(
                "Modelo",
                MODELOS_CONOCIDOS,
                index=MODELOS_CONOCIDOS.index(modelo_actual),
            )
        else:
            modelo = st.text_input("Modelo", value=modelo_actual)

        temperatura = st.slider(
            "Temperatura",
            min_value=0.0,
            max_value=1.0,
            value=float(env_ts.get("TEMPERATURA", "0.2")),
            step=0.05,
        )
    with col2:
        max_tokens = st.number_input(
            "Max tokens (evaluaciones individuales)",
            min_value=500,
            max_value=8000,
            value=int(env_ts.get("MAX_TOKENS", "3000")),
            step=100,
        )

    submitted_modelo = st.form_submit_button("Guardar configuración de modelo", type="primary")

if submitted_modelo:
    updates = {
        "MODELO": modelo,
        "TEMPERATURA": str(temperatura),
        "MAX_TOKENS": str(max_tokens),
    }
    _escribir_env(ENV_PATHS["tests_semanales"], updates)
    _escribir_env(ENV_PATHS["tareas"], updates)
    st.success("Configuración de modelo guardada en ambos proyectos.")

st.divider()

st.subheader("Escala de notas — Tareas")
st.markdown("Define el rango de notas que usa GPT para corregir.")

with st.form("form_notas"):
    col1, col2, col3 = st.columns(3)
    with col1:
        nota_min = st.number_input(
            "Nota mínima",
            min_value=1.0,
            max_value=6.9,
            value=float(env_tar.get("NOTA_MIN", "4.0")),
            step=0.1,
            format="%.1f",
        )
    with col2:
        nota_max = st.number_input(
            "Nota máxima",
            min_value=nota_min + 0.1,
            max_value=10.0,
            value=float(env_tar.get("NOTA_MAX", "7.0")),
            step=0.1,
            format="%.1f",
        )
    with col3:
        tarea_default = st.text_input(
            "Tarea por defecto",
            value=env_tar.get("TAREA_DEFAULT", "T1"),
        )

    submitted_notas = st.form_submit_button("Guardar", type="primary")

if submitted_notas:
    updates = {
        "NOTA_MIN": f"{nota_min:.1f}",
        "NOTA_MAX": f"{nota_max:.1f}",
        "TAREA_DEFAULT": tarea_default,
    }
    _escribir_env(ENV_PATHS["tareas"], updates)
    st.success("Configuración de notas guardada en Tareas.")

st.divider()

st.subheader("Grupos control/tratamiento — Tests Semanales")
st.markdown(
    "Cuando está activo, cada alumno es asignado aleatoriamente a un grupo "
    "y recibe la pregunta correspondiente."
)

with st.form("form_grupos"):
    col1, col2 = st.columns(2)
    with col1:
        grupo_activo = st.toggle(
            "Activar grupos control/tratamiento",
            value=env_ts.get("GRUPO_CONTROL_TRATAMIENTO", "true").lower() == "true",
        )
    with col2:
        grupo_seed = st.number_input(
            "Semilla aleatoria (GRUPO_SEED)",
            min_value=0,
            max_value=99999,
            value=int(env_ts.get("GRUPO_SEED", "19")),
            step=1,
            help="Cambiar la semilla reasigna los grupos.",
        )

    submitted_grupos = st.form_submit_button("Guardar", type="primary")

if submitted_grupos:
    updates = {
        "GRUPO_CONTROL_TRATAMIENTO": "true" if grupo_activo else "false",
        "GRUPO_SEED": str(grupo_seed),
    }
    _escribir_env(ENV_PATHS["tests_semanales"], updates)
    st.success("Configuración de grupos guardada en Tests Semanales.")
