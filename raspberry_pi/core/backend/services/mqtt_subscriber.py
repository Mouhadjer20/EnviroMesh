"""MQTT subscriber for RPi 2 (Core Processing Server).

Subscribes to forwarded telemetry topics (enviromesh/gateway/+/telemetry)
from the central EMQX broker, validates each reading, and persists it to
TimescaleDB with duplicate detection via database_writer.
"""

import json
import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv
import paho.mqtt.client as mqtt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .telemetry_validator import validate  # noqa: E402
from .database_writer import write_telemetry  # noqa: E402

logger = logging.getLogger("mqtt_subscriber")

load_dotenv()

BROKER_HOST = os.getenv("MQTT_HOST", os.getenv("EMQX_URL", "localhost"))
BROKER_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_PREFIX = os.getenv(
    "MQTT_TOPIC",
    os.getenv("TOPIC_PREFIX",
    os.getenv("TOPIC_PRIFIX", "enviromesh/gateway/+/telemetry"))
)
TOPIC = TOPIC_PREFIX


class MqttSubscriber:
    """MQTT subscriber that persists validated telemetry to TimescaleDB."""

    def __init__(self, host=None, port=None, topic=None):
        self.host = host or BROKER_HOST
        self.port = port or BROKER_PORT
        self.topic = topic or TOPIC
        self._running = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "core-subscriber")
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")
        if username:
            self.client.username_pw_set(username, password or None)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("Connected to central MQTT broker %s:%d", self.host, self.port)
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

        logger.info("Received telemetry on %s from device %s", message.topic, payload.get("device_id"))

        # 1. Validate via backend validator.
        if not validate(payload):
            logger.warning("Telemetry failed validation, discarding: %s", payload)
            return

        # 2. Persist to TimescaleDB via backend database_writer (with dedup check).
        write_telemetry(payload)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self):
        """Connect to the MQTT broker."""
        self.client.connect(self.host, self.port, keepalive=60)

    def subscribe(self, topic=None):
        """Subscribe to a topic."""
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
        self.stop()
