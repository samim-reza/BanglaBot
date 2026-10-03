FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
# Generous timeout + retries: the default 15 s read timeout aborts the whole
# build on one slow PyPI response, which shows up as flaky builds on NAT'd hosts.
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/scripts /app/scripts

# Run as non-root. Fixed UID so volume ownership is predictable.
RUN groupadd -g 10001 app && useradd -r -u 10001 -g app app \
    && mkdir -p /app/.tts-cache && chown -R app:app /app
USER app

EXPOSE 8000
# Hosts like Render pass the port in $PORT; behind their HTTPS proxy, trust its
# X-Forwarded-* headers so generated URLs are https.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
