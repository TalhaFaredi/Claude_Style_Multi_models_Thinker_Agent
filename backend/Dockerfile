# Backend image: FastAPI + SQLite. Python 3.12 is required by the pinned dependencies (numpy 2.5 and others).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Shared libraries that opencv / onnxruntime (used for local OCR) load at run time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

ENV APP_ENV=production DATA_DIR=/data
RUN mkdir -p /data /backups && chown -R app:app /data /backups
USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# ONE process on purpose: live runs are kept in memory. --proxy-headers lets the app see the visitor's real IP from Caddy
# (the container is only reachable from the Caddy container, so trusting the forwarded header is safe).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-keep-alive", "65"]
