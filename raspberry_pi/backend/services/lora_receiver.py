"""LoRa receiver for RPi (LoRa Gateway).

Receives raw RF packets from ESP32 sensor nodes over the SX1278 (433 MHz),
parses each frame, validates it with the backend telemetry validator, and
persists valid readings plus raw packets to TimescaleDB via the backend
database_writer.
"""

import json
import logging
import os
import sys
import time

import spidev
import RPi.GPIO as GPIO

# Make the raspberry_pi package importable when this script is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .telemetry_validator import validate  # noqa: E402
from .database_writer import write_telemetry, write_raw_packet  # noqa: E402

logger = logging.getLogger("lora_receiver")

# ==================================================
# CONFIGURATION
# ==================================================

RESET_PIN = 25

REG_FIFO = 0x00
REG_OP_MODE = 0x01

REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08

REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_RX_BASE_ADDR = 0x0F
REG_FIFO_RX_CURRENT_ADDR = 0x10

REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13

REG_MODEM_CONFIG1 = 0x1D
REG_MODEM_CONFIG2 = 0x1E

REG_PREAMBLE_MSB = 0x20
REG_PREAMBLE_LSB = 0x21

REG_VERSION = 0x42

IRQ_RX_TIMEOUT = 0x80
IRQ_RX_DONE = 0x40
IRQ_PAYLOAD_CRC_ERROR = 0x20

# ==================================================
# SPI
# ==================================================

spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 100000
spi.mode = 0


def read_register(reg):
    return spi.xfer2([reg & 0x7F, 0x00])[1]


def write_register(reg, value):
    spi.xfer2([reg | 0x80, value & 0xFF])


# ==================================================
# RESET DU MODULE
# ==================================================

def reset_module():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RESET_PIN, GPIO.OUT)

    GPIO.output(RESET_PIN, GPIO.HIGH)
    time.sleep(0.02)
    GPIO.output(RESET_PIN, GPIO.LOW)
    time.sleep(0.02)
    GPIO.output(RESET_PIN, GPIO.HIGH)
    time.sleep(0.1)


# ==================================================
# INITIALISATION LORA
# ==================================================

def init_lora():
    reset_module()

    version = read_register(REG_VERSION)
    if version != 0x12:
        raise RuntimeError(
            f"Version SX1278 incorrecte : 0x{version:02X}"
        )

    # LoRa Sleep
    write_register(REG_OP_MODE, 0x80)
    time.sleep(0.05)

    if read_register(REG_OP_MODE) != 0x80:
        raise RuntimeError("Impossible d'activer le mode LoRa.")

    # Fréquence : 433 MHz
    write_register(REG_FRF_MSB, 0x6C)
    write_register(REG_FRF_MID, 0x40)
    write_register(REG_FRF_LSB, 0x00)

    # SF7, BW125 kHz, CR 4/5, en-tête explicite, CRC désactivé
    write_register(REG_MODEM_CONFIG1, 0x72)
    write_register(REG_MODEM_CONFIG2, 0x70)

    # Préambule de 8 symboles
    write_register(REG_PREAMBLE_MSB, 0x00)
    write_register(REG_PREAMBLE_LSB, 0x08)

    # Base FIFO de réception
    write_register(REG_FIFO_RX_BASE_ADDR, 0x00)

    # Effacer les interruptions en attente
    write_register(REG_IRQ_FLAGS, 0xFF)

    # Réception continue
    write_register(REG_OP_MODE, 0x85)
    time.sleep(0.05)

    if read_register(REG_OP_MODE) != 0x85:
        raise RuntimeError("Impossible d'activer la réception LoRa.")

    logger.info("Récepteur LoRa prêt à 433 MHz.")


# ==================================================
# RECEPTION DES PAQUETS
# ==================================================

def receive_packet():
    fifo_addr = read_register(REG_FIFO_RX_CURRENT_ADDR)
    write_register(REG_FIFO_ADDR_PTR, fifo_addr)

    length = read_register(REG_RX_NB_BYTES)
    data = bytearray()

    for _ in range(length):
        data.append(read_register(REG_FIFO))

    return bytes(data).decode("utf-8", errors="replace")


# ==================================================
# PROCESSING OF A RECEIVED PACKET
# ==================================================

def process_packet(raw_payload: str):
    """Validate a LoRa packet and persist it to TimescaleDB.

    The raw packet is always written for diagnostics. If the payload parses
    as valid JSON and passes the telemetry validator, the structured reading
    is also written to the sensor_telemetry hypertable.
    """
    parsed = False
    telemetry = None

    try:
        telemetry = json.loads(raw_payload)
        parsed = True
    except (json.JSONDecodeError, TypeError):
        logger.warning("LoRa packet is not valid JSON: %s", raw_payload)

    # Persist the raw packet for diagnostics / traceability.
    device_id = telemetry.get("device_id") if isinstance(telemetry, dict) else None
    write_raw_packet(device_id or "unknown", "LoRa", raw_payload.encode("utf-8"), parsed)

    if not parsed:
        return

    # 1. Validate via backend validator.
    if not validate(telemetry):
        logger.warning("LoRa telemetry failed validation, discarding: %s", telemetry)
        return

    # 2. Persist to TimescaleDB via backend database_writer.
    write_telemetry(telemetry)


# ==================================================
# BOUCLE PRINCIPALE
# ==================================================

def run():
    """Run the LoRa receive loop until interrupted.

    This is the blocking main loop: it initialises the SX1278, then polls
    ``REG_IRQ_FLAGS`` continuously, processing every received packet through
    :func:`process_packet`. Designed to be run in a background thread while
    other services (e.g. the MQTT subscriber) run in the main thread.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("Initialisation du récepteur LoRa...")
    init_lora()

    logger.info("En attente des paquets ESP32...")

    last_status = time.monotonic()

    try:
        while True:
            irq = read_register(REG_IRQ_FLAGS)

            if irq & IRQ_RX_DONE:
                if irq & IRQ_PAYLOAD_CRC_ERROR:
                    logger.error("CRC incorrect.")
                else:
                    raw = receive_packet()
                    logger.info("Reçu: %s", raw)
                    process_packet(raw)

                # Effacer les interruptions présentes
                write_register(REG_IRQ_FLAGS, irq)

                # Reprendre la réception continue
                write_register(REG_OP_MODE, 0x85)

            elif irq & IRQ_RX_TIMEOUT:
                write_register(REG_IRQ_FLAGS, IRQ_RX_TIMEOUT)
                write_register(REG_OP_MODE, 0x85)

            if time.monotonic() - last_status >= 10:
                logger.info(
                    "ÉTAT OP_MODE=0x%02X, IRQ=0x%02X",
                    read_register(REG_OP_MODE),
                    read_register(REG_IRQ_FLAGS),
                )
                last_status = time.monotonic()

            time.sleep(0.005)
    except KeyboardInterrupt:
        logger.info("Arrêt du récepteur.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.error("ERREUR: %s", e)
    finally:
        spi.close()
        GPIO.cleanup()
        logger.info("Ressources libérées.")