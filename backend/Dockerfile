FROM python:3.12-slim

# Create unprivileged application user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Alembic migration assets are required at startup (apply_migrations)
COPY alembic.ini ./
COPY alembic ./alembic

# Set non-root ownership
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Launch uvicorn with proxy headers enabled so rate limiter captures real remote IPs,
# plus concurrency/keep-alive caps to bound resource exhaustion
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--limit-concurrency", "200", "--timeout-keep-alive", "30"]