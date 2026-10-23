"""MQTT publisher for RPi 1 (LoRa Gateway).

Publishes decoded telemetry JSON to the EMQX broker on RPi 2 over Ethernet.
"""

import json
import logging

logger = logging.getLogger("mqtt_publisher")


class MqttPublisher:
    def __init__(self, host="localhost", port=1883, topic_prefix="enviromesh"):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self.client = None

    def connect(self):
        """Connect to the MQTT broker."""
        # TODO: Initialize paho-mqtt / asyncio MQTT client and connect
        logger.info("Connecting to MQTT broker at %s:%d", self.host, self.port)

    def publish(self, device_id: str, telemetry: dict):
        """Publish a telemetry payload for a given device."""
        topic = f"{self.topic_prefix}/devices/{device_id}/telemetry"
        payload = json.dumps(telemetry)
        # TODO: client.publish(topic, payload, qos=1)
        logger.debug("Published to %s: %s", topic, payload)

    def disconnect(self):
        """Disconnect from the broker."""
        # TODO: client.disconnect()
        logger.info("Disconnected from MQTT broker")