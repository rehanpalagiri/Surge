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
# The in-memory constraint that pinned this to 1 is LIFTED: both throttle counters
# (services/throttle.py → rate_limit_hits table) and presigned-upload ownership
# (routers/analyze.py → pending_uploads table) now live in the shared DB, so limits
# and upload keys hold across workers and replicas.
#
# Still defaults to 1 deliberately. Before raising it, mind the DB connection math:
# total connections = WEB_CONCURRENCY * (pool_size + max_overflow) from
# database.py (currently 20 per worker) and MUST stay under Neon's max_connections
# for the plan — verify that number first. Also note DB-backed throttling adds load
# to the primary DB (the measured bottleneck); for serious scale, move the throttle
# to Redis (see services/throttle.py). A single worker's throughput is capped by one
# event loop, so horizontal scaling is the real lever once that's saturated.
ENV WEB_CONCURRENCY=1

# Use shell form so $PORT / $WEB_CONCURRENCY are expanded at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY}
