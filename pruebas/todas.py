"""Corre todas las pruebas y devuelve un código de salida distinto de cero si alguna falla."""

import pathlib
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
ARCHIVOS = ["limpieza_correos.py", "correos_en_salida.py", "versiones_prompt.py", "contexto_curso.py", "ajuste_notas.py", "esquema_nuevo.py", "escala.py", "simulaciones.py", "sabana.py", "e2e_tests_semanales.py", "e2e_tareas.py", "reportes.py", "web.py", "motor.py",
             "entregas_zip.py",
             "chequeo_tareas.py", "chequeo_correos.py", "citas_tareas.py", "segunda_oportunidad.py"]

fallaron = []
for nombre in ARCHIVOS:
    print(f"\n{'=' * 60}\n{nombre}\n{'=' * 60}")
    r = subprocess.run([sys.executable, str(AQUI / nombre)], cwd=RAIZ,
                       env={**__import__("os").environ,
                            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    if r.returncode:
        fallaron.append(nombre)

print(f"\n{'=' * 60}")
if fallaron:
    print("FALLARON: " + ", ".join(fallaron))
    sys.exit(1)
print("Todo en verde.")
