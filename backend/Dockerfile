# Ask the Multiverse API (Cloud Run). The data snapshot is not baked in: at startup the app
# downloads it from gs://$MULTIVERSE_SNAPSHOT_BUCKET/$MULTIVERSE_SNAPSHOT_PREFIX/ (app/snapshot.py).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MULTIVERSE_DATA_DIR=/tmp/multiverse PORT=8080

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --uid 10001 --no-create-home app
COPY app ./app

USER app
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
