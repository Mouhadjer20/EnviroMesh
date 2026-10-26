# ---------------------------------------------------------------
# EnviroMesh Backend — RPi Core Processing Server (Python/FastAPI)
# Build context: ./raspberry_pi/backend
# ---------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for compiling hardware extensions (spidev, RPi.GPIO)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (core + optional hardware drivers)
COPY requirements.txt requirements-hardware.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user -r requirements-hardware.txt || true

# ---------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Runtime dependencies (libpq only, no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Expose FastAPI port (matches docker-compose expose: 8000)
EXPOSE 8000

# Run the backend entry point
CMD ["python", "main.py"]
