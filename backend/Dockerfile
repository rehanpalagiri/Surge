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

# Use shell form so $PORT is expanded at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
