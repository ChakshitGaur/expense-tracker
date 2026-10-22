# Production image: gunicorn serves the app, WhiteNoise serves static files,
# and the SQLite database lives on the /app/data volume.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DB_PATH=/app/data/db.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DJANGO_DEBUG=1 only for this build step, so collectstatic runs without a secret key.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data

USER app
VOLUME ["/app/data"]
EXPOSE 8000

# Apply migrations on start, then serve. DJANGO_SECRET_KEY must be set at run time.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --access-logfile -"]
