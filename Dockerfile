# El motor que corre en Google Cloud Run: los flujos del curso tal cual, más el
# servidor que recibe los trabajos. Ver motor/MOTOR.md.
FROM python:3.12-slim

WORKDIR /app
COPY motor/requirements.txt motor/requirements.txt
RUN pip install --no-cache-dir -r motor/requirements.txt

COPY modulos modulos
COPY motor motor

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Hora de Chile, como en el PC. Sin esto el log mezclaba horas en UTC (nube) y
# en -03:00 (PC), y lo que se ordena por fecha quedaba desordenado.
# bsdtar (libarchive-tools) abre los .rar que la página sube sin abrir: el
# navegador no los lee (modulos/tareas/desempacar.py).
RUN apt-get update && apt-get install -y --no-install-recommends tzdata libarchive-tools \
    && rm -rf /var/lib/apt/lists/*
ENV TZ=America/Santiago
# Cloud Run define PORT; el servidor lo lee.
CMD ["python", "-m", "motor.servidor"]
