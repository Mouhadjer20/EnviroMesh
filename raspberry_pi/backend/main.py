"""Backend entry point for RPi (Core Processing Server).

Runs the MQTT subscriber loop that bridges incoming telemetry from the
LoRa gateway / Wi-Fi nodes into validation, persistence, and alerting.

FastAPI application entry point for the EnviroMesh core server.

Hosts the REST API for devices, telemetry, alerts, and users, plus WebSocket
endpoints for real-time telemetry streaming to the dashboard.
"""

import logging
import os
import signal
import sys

# Ensure the backend directory is on sys.path so that `services.*` and
# `routes.*` packages can be imported regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.mqtt_subscriber import MqttSubscriber

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import devices, telemetry, alerts, users

from dotenv import load_dotenv

logger = logging.getLogger("main")

load_dotenv()

#BROKER_HOST = os.getenv("EMQX_URL", os.getenv("MQTT_HOST", "localhost"))
#BROKER_PORT = int(os.getenv("MQTT_PORT", 1883))
#TOPIC_PREFIX = os.getenv("TOPIC_PRIFIX", os.getenv("TOPIC_PREFIX", "enviromesh"))
#TOPIC = f"{TOPIC_PREFIX}" #/devices/G11/telemetry

#logger.info("Enviarment %s:%d, %s", BROKER_HOST, BROKER_PORT, TOPIC)

app = FastAPI(
    title="EnviroMesh API",
    description="Core server API for the Environmental Monitoring System",
    version="1.0.0",
)

#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=["*"],  # TODO: Restrict to dashboard origin in production
#    allow_credentials=True,
#    allow_methods=["*"],
#    allow_headers=["*"],
#)

app.include_router(devices.router)
app.include_router(telemetry.router)
#app.include_router(alerts.router) # Not included
#app.include_router(users.router) # Next phase


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backend")


def main():
    logger.info("Starting EnviroMesh backend on RPi (Core Server)")
    mqtt_host = os.getenv("MQTT_HOST", os.getenv("EMQX_URL", "localhost"))
    mqtt_port = int(os.getenv("MQTT_PORT", 1883))
    mqtt_topic = os.getenv("MQTT_TOPIC", os.getenv("TOPIC_PRIFIX", "enviromesh/devices/+/telemetry"))

    logger.info("MQTT subscriber connecting to %s:%d with topic %s", mqtt_host, mqtt_port, mqtt_topic)

    subscriber = MqttSubscriber(mqtt_host, mqtt_port, mqtt_topic)

    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        subscriber.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        subscriber.run()
    except KeyboardInterrupt:
        subscriber.stop()


if __name__ == "__main__":
    main()