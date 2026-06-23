# ── Stage 1: Build Next.js frontend ──────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# System tools needed by ping/traceroute checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    traceroute \
    && rm -rf /var/lib/apt/lists/*

# Install Python package
COPY pyproject.toml .
COPY nethealth/ ./nethealth/
RUN pip install --no-cache-dir .

# Copy built frontend into location api.py expects
COPY --from=frontend-builder /build/frontend/out ./frontend/out

EXPOSE 8000

CMD ["uvicorn", "nethealth.api:app", "--host", "0.0.0.0", "--port", "8000"]
