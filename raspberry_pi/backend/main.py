"""Backend entry point for RPi 2 (Core Processing Server).

Runs the MQTT consumer loop that bridges incoming telemetry from the
LoRa gateway / Wi-Fi nodes into validation, persistence, and alerting.

FastAPI application entry point for the EnviroMesh core server.

Hosts the REST API for devices, telemetry, alerts, and users, plus WebSocket
endpoints for real-time telemetry streaming to the dashboard.
"""

import logging
import signal
import sys

from .mqtt_consumer import MqttConsumer

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import devices, telemetry, alerts, users

app = FastAPI(
    title="EnviroMesh API",
    description="Core server API for the Environmental Monitoring System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to dashboard origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(devices.router)
app.include_router(telemetry.router)
app.include_router(alerts.router)
app.include_router(users.router)


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backend")


def main():
    logger.info("Starting EnviroMesh backend on RPi 2 (Core Server)")
    consumer = MqttConsumer()

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        consumer.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        consumer.run()
    except KeyboardInterrupt:
        consumer.stop()


if __name__ == "__main__":
    main()