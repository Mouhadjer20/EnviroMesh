"""MQTT consumer for RPi 2 (Core Processing Server).

Subscribes to device telemetry topics from RPi 1 gateway and Wi-Fi nodes,
then routes each message through validation, database writing, and alerting.
"""

import logging

logger = logging.getLogger("mqtt_consumer")


class MqttConsumer:
    def __init__(self, host="localhost", port=1883):
        self.host = host
        self.port = port
        self.running = False

    def run(self):
        """Connect, subscribe, and loop forever."""
        self.running = True
        logger.info("MQTT consumer running on %s:%d", self.host, self.port)
        # TODO: subscribe to "enviromesh/devices/+/telemetry"
        while self.running:
            pass  # TODO: replace with client.loop_forever()

    def stop(self):
        self.running = False
        logger.info("MQTT consumer stopped")

    def on_message(self, topic: str, payload: dict):
        """Handle an incoming telemetry message."""
        # TODO: extract device_id from topic, then:
        #   1. telemetry_validator.validate(payload)
        #   2. database_writer.write(payload)
        #   3. check thresholds and emit alerts
        logger.info("Message on %s: %s", topic, payload)