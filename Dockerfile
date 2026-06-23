# Mock ERP / Traceability API — FDA Recall Agent (UiPath AgentHack 2026)
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code + sample data
COPY app/ .

# Render injects PORT at runtime; default to 8080 for local/docker run
ENV PORT=8080
EXPOSE 8080

# Basic container healthcheck (Render uses its own HTTP health check too)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8080') + '/healthz', timeout=3)" || exit 1

# Use gunicorn in production; shell form so $PORT expands
CMD gunicorn -b 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 60 app:app
