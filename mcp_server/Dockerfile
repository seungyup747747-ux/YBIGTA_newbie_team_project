FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY mcp_server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && addgroup --system mcp \
    && adduser --system --ingroup mcp --no-create-home mcp

COPY --chown=mcp:mcp mcp_server /app/mcp_server
COPY --chown=mcp:mcp collector/__init__.py /app/collector/__init__.py
COPY --chown=mcp:mcp collector/locations.py /app/collector/locations.py

USER mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["uvicorn", "mcp_server.http_app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
