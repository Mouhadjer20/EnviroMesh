"""Backend entry point for RPi 2 (Core Processing Server).

Changes from the single-Pi version:
  - MQTT subscriber now listens on enviromesh/gateway/+/telemetry
    (messages forwarded from RPi 1 gateway, already normalised).
  - LoRa receiver is NOT started here — LoRa reception runs exclusively on RPi 1.
  - Duplicate detection is handled in database_writer using the processed_messages table.

FastAPI exposes the REST API for devices, telemetry, alerts, and users, plus
WebSocket endpoints for real-time telemetry streaming to the dashboard.
"""

import logging
import os
import signal
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from services.mqtt_subscriber import MqttSubscriber
from routes import devices, telemetry, alerts, users, groups
from services.colored_logger import setup_colored_logging

log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger = setup_colored_logging(level=log_level, name="backend")

app = FastAPI(
    title="EnviroMesh API",
    description="Core server API for the Environmental Monitoring System",
    version="2.0.0",
)

app.include_router(devices.router)
app.include_router(telemetry.router)
app.include_router(groups.router)
# app.include_router(alerts.router)  # Phase 4
# app.include_router(users.router)   # Phase 4


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "component": "core-backend"}


import uvicorn


def main():
    logger.info("Starting EnviroMesh backend on RPi 2 (Core Server)")

    api_host  = os.getenv("API_HOST", "0.0.0.0")
    api_port  = int(os.getenv("API_PORT", "8000"))

    mqtt_host  = os.getenv("MQTT_HOST", "localhost")
    mqtt_port  = int(os.getenv("MQTT_PORT", "1883"))
    # In the two-Pi architecture the backend subscribes to gateway-forwarded telemetry
    mqtt_topic = os.getenv(
        "MQTT_TOPIC",
        os.getenv("TOPIC_PREFIX",
        os.getenv("TOPIC_PRIFIX", "enviromesh/gateway/+/telemetry"))
    )

    logger.info(
        "MQTT subscriber connecting to %s:%d topic=%s", mqtt_host, mqtt_port, mqtt_topic
    )

    subscriber = MqttSubscriber(mqtt_host, mqtt_port, mqtt_topic)

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        subscriber.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        subscriber.connect()
        subscriber.client.loop_start()
        logger.info("MQTT subscriber network loop running in background")
    except Exception as exc:
        logger.warning("Could not connect MQTT subscriber at startup: %s", exc)

    logger.info("Starting FastAPI server on %s:%d", api_host, api_port)
    try:
        uvicorn.run(app, host=api_host, port=api_port, log_level="info")
    finally:
        subscriber.stop()


if __name__ == "__main__":
    main()

