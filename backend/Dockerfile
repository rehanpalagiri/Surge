# Portable container for the ViralIQ FastAPI backend.
# Works on Render, Fly.io, Railway, or any container host.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure the uploads dir exists at runtime
RUN mkdir -p uploads

# Hosts inject the port via $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# WEB_CONCURRENCY controls the number of worker processes.
#
# It defaults to 1 ON PURPOSE. Two guards keep per-process state in memory and
# would each grant the full quota if duplicated across workers:
#   • the guest analysis limit  (services/throttle.py → check_rate "guest:<ip>")
#   • the password-reset brute-force guard (same module)
# Before raising WEB_CONCURRENCY > 1 (or running multiple Railway replicas),
# move services/throttle.py to a shared store (a DB table or Redis) so the
# counters are global. Until then, one worker is the correct, safe setting.
# Under load a single worker stays error-free (see tools/stress_test.py) but
# its throughput is capped by one event loop — horizontal scaling is the lever.
ENV WEB_CONCURRENCY=1

# Use shell form so $PORT / $WEB_CONCURRENCY are expanded at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY}
