"""MQTT ingestion service for the EnviroMesh Gateway (RPi 1).

Subscribes to the local EMQX broker and processes Wi-Fi ESP32 node telemetry.
Each received message is validated, normalised, and enqueued in the SQLite
offline queue for forwarding to RPi 2.

Topic pattern: enviromesh/devices/+/telemetry
"""

import json
import time

import paho.mqtt.client as mqtt

from .logger import get_logger
from .telemetry_validator import validate
from .telemetry_normalizer import normalize
from . import sqlite_queue, config

logger = get_logger("gateway.mqtt_ingestion")


class MqttIngestionService:
    """Subscribe to the local EMQX broker and enqueue validated telemetry."""

    def __init__(self) -> None:
        self._running = False
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="gw-ingestion"
        )
        if config.MQTT_LOCAL_USERNAME:
            self.client.username_pw_set(
                config.MQTT_LOCAL_USERNAME, config.MQTT_LOCAL_PASSWORD or None
            )
        self.client.on_connect    = self._on_connect
        self.client.on_message    = self._on_message
        self.client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info(
                "Connected to local EMQX %s:%d",
                config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT,
            )
            client.subscribe(config.MQTT_INPUT_TOPIC, qos=config.MQTT_QOS)
            logger.info("Subscribed to %s", config.MQTT_INPUT_TOPIC)
        else:
            logger.error("Local EMQX connect failed: reason_code=%s", reason_code)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        logger.warning("Disconnected from local EMQX (reason=%s)", reason_code)

    def _on_message(self, client, userdata, message):
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning("Invalid JSON on topic %s: %s", topic, exc)
            return

        logger.debug("Wi-Fi MQTT message on %s: %s", topic, payload)

        # Normalise "status" → "metadata"
        if isinstance(payload, dict) and "status" in payload and "metadata" not in payload:
            payload["metadata"] = payload.pop("status")

        if not validate(payload):
            logger.warning("Wi-Fi telemetry failed validation on %s, discarding", topic)
            return

        envelope = normalize(raw=payload, ingress_topic=topic)
        payload_str = json.dumps(envelope, separators=(",", ":"))
        out_topic   = config.MQTT_OUTPUT_TOPIC

        try:
            enqueued = sqlite_queue.enqueue(envelope["message_id"], out_topic, payload_str)
            if enqueued:
                logger.info(
                    "Wi-Fi telemetry queued: device=%s topic=%s",
                    envelope.get("device_id"), topic,
                )
        except RuntimeError as exc:
            logger.error("Queue full — dropping Wi-Fi telemetry from %s: %s", topic, exc)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Connect to the local EMQX broker and start the network loop."""
        self._running = True
        retry_delay = 5
        while self._running:
            try:
                self.client.connect(
                    config.MQTT_LOCAL_HOST,
                    config.MQTT_LOCAL_PORT,
                    keepalive=60,
                )
                self.client.loop_start()
                logger.info("MQTT ingestion service running")
                return
            except Exception as exc:
                logger.warning(
                    "Cannot connect to local EMQX (%s:%d): %s — retrying in %ds",
                    config.MQTT_LOCAL_HOST, config.MQTT_LOCAL_PORT, exc, retry_delay,
                )
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)

    def stop(self) -> None:
        """Stop the network loop and disconnect gracefully."""
        self._running = False
        try:
            self.client.loop_stop()
        except Exception:
            pass
        try:
            self.client.disconnect()
        except Exception:
            pass
        logger.info("MQTT ingestion service stopped")

