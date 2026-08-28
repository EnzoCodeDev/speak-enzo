# Enzo Speak — backend (alternativa con Docker)
FROM python:3.12-slim

WORKDIR /srv/enzo

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Los tokens de IA se guardan aquí: móntalo como volumen para que persistan.
VOLUME ["/srv/enzo/data"]

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
