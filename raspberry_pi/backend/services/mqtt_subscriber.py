"""MQTT subscriber for RPi (LoRa Gateway).

Subscribes to decoded telemetry topics on the EMQX broker, validates each
reading with the backend telemetry validator, and persists valid readings
to the TimescaleDB database using the backend database_writer.
"""

import json
import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# Make the raspberry_pi package importable when this script is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .telemetry_validator import validate  # noqa: E402
from .database_writer import write_telemetry  # noqa: E402

logger = logging.getLogger("mqtt_subscriber")

load_dotenv()

BROKER_HOST = os.getenv("EMQX_URL", os.getenv("MQTT_HOST", "localhost"))
BROKER_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_PREFIX = os.getenv("TOPIC_PRIFIX", os.getenv("TOPIC_PREFIX", "enviromesh"))
TOPIC = f"{TOPIC_PREFIX}" #/devices/G11/telemetry


class MqttSubscriber:
    """MQTT subscriber that persists validated telemetry to TimescaleDB."""

    def __init__(self, host=None, port=None, topic=None):
        self.host = host or BROKER_HOST
        self.port = port or BROKER_PORT
        self.topic = topic or TOPIC
        self._running = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "gateway-subscriber")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("Connected to MQTT broker %s:%d", self.host, self.port)
            client.subscribe(self.topic, qos=1)
            logger.info("Subscribed to topic %s", self.topic)
        else:
            logger.error("MQTT connect failed with reason code %s", reason_code)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        logger.info("Disconnected from MQTT broker (reason: %s)", reason_code)

    def on_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Invalid JSON payload on %s: %s", message.topic, exc)
            return

        logger.info("Received telemetry on %s: %s", message.topic, payload)

        # 1. Validate via backend validator.
        if not validate(payload):
            logger.warning("Telemetry failed validation, discarding: %s", payload)
            return

        # 2. Persist to TimescaleDB via backend database_writer.
        write_telemetry(payload)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self):
        """Connect to the MQTT broker."""
        self.client.connect(self.host, self.port, keepalive=60)

    def subscribe(self, topic=None):
        """Subscribe to a topic (defaults to the configured telemetry topic)."""
        self.client.subscribe(topic or self.topic, qos=1)

    def run(self):
        """Connect, subscribe, and loop until stopped."""
        self._running = True
        self.connect()
        self.client.loop_start()
        logger.info("MQTT subscriber running. Press Ctrl+C to stop.")
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the network loop and disconnect."""
        self._running = False
        try:
            self.client.loop_stop()
        except Exception as exc:
            logger.warning("Error stopping loop: %s", exc)
        try:
            self.client.disconnect()
        except Exception as exc:
            logger.warning("Error disconnecting: %s", exc)
        logger.info("MQTT subscriber stopped")

    def disconnect(self):
        """Alias for stop() kept for lifecycle compatibility."""
        self.stop()