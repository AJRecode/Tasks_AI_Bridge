# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    TASKS_BRIDGE_DEPLOYMENT=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py bridge_diagnostics.py google_auth.py google_tasks.py \
     mcp_server.py task_services.py ./

EXPOSE 8000

CMD ["python", "mcp_server.py"]
