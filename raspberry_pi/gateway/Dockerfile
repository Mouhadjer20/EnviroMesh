## EnviroMesh Gateway — RPi 1 Dockerfile
##
## Builds the Python gateway application that:
##   - Receives LoRa telemetry from SX1278 via SPI
##   - Subscribes to the local EMQX for Wi-Fi ESP32 telemetry
##   - Enqueues everything in SQLite for offline resilience
##   - Forwards to RPi 2 over MQTT/TLS
##
## NOTE: SPI and GPIO hardware access requires:
##   devices:
##     - /dev/spidev0.0:/dev/spidev0.0
##     - /dev/gpiomem:/dev/gpiomem

FROM python:3.11-slim

LABEL maintainer="EnviroMesh Project" \
      description="Gateway ingestion and forwarding service for RPi 1" \
      version="2.0.0"

WORKDIR /app

# System dependencies for spidev / RPi.GPIO compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY gateway/ /app/gateway/

# SQLite queue data directory
RUN mkdir -p /var/lib/enviromesh

# Non-root user for security (GPIO group added at runtime if needed)
RUN useradd -r -s /bin/false enviromesh && \
    chown -R enviromesh:enviromesh /var/lib/enviromesh /app
USER enviromesh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python3 -c "import sqlite3; sqlite3.connect('/var/lib/enviromesh/queue.db').execute('SELECT 1')" || exit 1

CMD ["python3", "-m", "gateway.main"]

