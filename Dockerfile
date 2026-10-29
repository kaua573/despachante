FROM python:3.12-slim

WORKDIR /app

# Todas as dependencias tem wheel pronto (psycopg2-binary, pillow, reportlab):
# nao precisa de compilador na imagem, o que reduz tamanho e superficie de ataque.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# O servidor nao roda como root: se algo for explorado, o estrago fica limitado.
# O usuario precisa escrever nas pastas de uploads/backups/chave dentro de /app.
RUN useradd --system --uid 10001 --no-create-home app \
    && chown -R app:app /app
USER app

ENV PYTHONUNBUFFERED=1 \
    FLASK_ENV=production

EXPOSE 8080

# $PORT e injetada automaticamente pelo Cloud Run (normalmente 8080)
CMD ["sh", "-c", "waitress-serve --host=0.0.0.0 --port=${PORT:-8080} wsgi:app"]
