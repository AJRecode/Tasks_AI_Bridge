# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    TASKS_BRIDGE_DEPLOYMENT=production

WORKDIR /app

RUN groupadd --system --gid 10001 appgroup \
    && useradd --system --uid 10001 --gid appgroup --create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bridge/ ./bridge/
COPY services/ ./services/
COPY mcp_server.py ./

RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

CMD ["python", "mcp_server.py"]
