"""Backend entry point for RPi (Core Processing Server).

Runs the LoRa receiver (SX1278) and the MQTT subscriber (EMQX) concurrently so
that telemetry from both the LoRa gateway and Wi-Fi nodes is ingested,
validated, and persisted into TimescaleDB at the same time.

FastAPI application entry point for the EnviroMesh core server.

Hosts the REST API for devices, telemetry, alerts, and users, plus WebSocket
endpoints for real-time telemetry streaming to the dashboard.
"""

import logging
import os
import signal
import sys
import threading

# Ensure the backend directory is on sys.path so that `services.*` and
# `routes.*` packages can be imported regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.mqtt_subscriber import MqttSubscriber
from services.lora_receiver import run as lora_run

from fastapi import FastAPI

from routes import devices, telemetry, alerts, users

from dotenv import load_dotenv

logger = logging.getLogger("main")

load_dotenv()

app = FastAPI(
    title="EnviroMesh API",
    description="Core server API for the Environmental Monitoring System",
    version="1.0.0",
)

app.include_router(devices.router)
app.include_router(telemetry.router)
#app.include_router(alerts.router) # Not included
#app.include_router(users.router) # Next phase


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

from services.colored_logger import setup_colored_logging

# Configure colored logging across all backend loggers
log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger = setup_colored_logging(level=log_level, name="backend")


import uvicorn

def main():
    logger.info("Starting EnviroMesh backend on RPi (Core Server)")

    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", 8000))

    mqtt_host = os.getenv("MQTT_HOST", os.getenv("EMQX_URL", "localhost"))
    mqtt_port = int(os.getenv("MQTT_PORT", 1883))
    mqtt_topic = os.getenv("MQTT_TOPIC", os.getenv("TOPIC_PRIFIX", "enviromesh/devices/+/telemetry"))

    logger.info("MQTT subscriber connecting to %s:%d with topic %s", mqtt_host, mqtt_port, mqtt_topic)

    subscriber = MqttSubscriber(mqtt_host, mqtt_port, mqtt_topic)

    # Run the LoRa receiver in a background thread so it does not block the
    # MQTT subscriber or the FastAPI event loop.
    try:
        lora_thread = threading.Thread(target=lora_run, name="lora-receiver", daemon=True)
        lora_thread.start()
        logger.info("LoRa receiver thread started")
    except Exception as exc:
        logger.warning("Could not start LoRa receiver thread: %s", exc)

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        subscriber.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start MQTT subscriber network loop in background thread
    try:
        subscriber.connect()
        subscriber.client.loop_start()
        logger.info("MQTT subscriber network loop running in background")
    except Exception as exc:
        logger.warning("Could not connect MQTT subscriber at startup: %s", exc)

    # Start FastAPI / Uvicorn server in main thread
    logger.info("Starting FastAPI server on %s:%d", api_host, api_port)
    try:
        uvicorn.run(app, host=api_host, port=api_port, log_level="info")
    finally:
        subscriber.stop()


if __name__ == "__main__":
    main()