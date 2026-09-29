# El motor que corre en Google Cloud Run: los flujos del curso tal cual, más el
# servidor que recibe los trabajos. Ver motor/MOTOR.md.
FROM python:3.12-slim

WORKDIR /app
COPY motor/requirements.txt motor/requirements.txt
RUN pip install --no-cache-dir -r motor/requirements.txt

COPY modulos modulos
COPY motor motor

ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Cloud Run define PORT; el servidor lo lee.
CMD ["python", "-m", "motor.servidor"]
