FROM python:3.12-slim

WORKDIR /app

# Dependencias do sistema exigidas por reportlab/openpyxl na imagem slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

EXPOSE 8080

# $PORT e injetada automaticamente pelo Cloud Run (normalmente 8080)
CMD ["sh", "-c", "waitress-serve --host=0.0.0.0 --port=${PORT:-8080} wsgi:app"]
