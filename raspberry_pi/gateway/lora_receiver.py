"""LoRa receiver daemon for RPi 1 (LoRa Gateway).

Receives raw LoRa frames from ESP32 nodes (G11, G41) via the SX1302
concentrator and forwards them to the packet decoder.
"""

import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lora_receiver")


class LoRaReceiver:
    def __init__(self, frequency=433000000, sf=7, bw=125000):
        self.frequency = frequency
        self.spreading_factor = sf
        self.bandwidth = bw
        self.running = False

    def start(self):
        """Initialize the LoRa concentrator and begin listening."""
        logger.info(
            "Starting LoRa receiver on %d Hz, SF%d, BW%d",
            self.frequency,
            self.spreading_factor,
            self.bandwidth,
        )
        self.running = True
        # TODO: Initialize SX1302 / SX1276 hardware here

    def receive(self):
        """Blocking call to receive a raw LoRa frame."""
        # TODO: Implement radio read loop
        # Returns raw bytes or None
        return None

    def stop(self):
        self.running = False
        logger.info("LoRa receiver stopped")


if __name__ == "__main__":
    receiver = LoRaReceiver()
    try:
        receiver.start()
        while receiver.running:
            frame = receiver.receive()
            if frame:
                logger.info("Received raw frame: %s", frame.hex())
            time.sleep(0.1)
    except KeyboardInterrupt:
        receiver.stop()