"""LoRa receiver for the EnviroMesh Gateway (RPi 1).

Adapted from raspberry_pi/backend/services/lora_receiver.py.

Key changes from the original:
- Instead of writing to TimescaleDB, validated packets are normalised and
  enqueued into the SQLite offline queue via sqlite_queue.enqueue().
- RSSI and SNR are read from the SX1278 hardware registers (0x1A / 0x19)
  and attached to the normalised envelope.
- Hardware fallback behaviour is preserved: on non-RPi platforms the function
  logs a warning and returns immediately so the rest of the gateway continues.

SX1278 configuration (mirrors node_g11 / node_g41 firmware):
  Frequency : 433 MHz
  SF        : 7
  BW        : 125 kHz
  CR        : 4/5
  Sync word : 0x12
  RESET pin : GPIO25 (BCM)
"""

import json
import logging
import os
import sys
import time
from typing import Optional

from .logger import get_logger
from .telemetry_validator import validate
from .telemetry_normalizer import normalize
from . import sqlite_queue

logger = get_logger("gateway.lora_receiver")

# ---------------------------------------------------------------------------
# SX1278 register map
# ---------------------------------------------------------------------------
RESET_PIN = int(os.getenv("LORA_RESET_PIN", "25"))

REG_FIFO              = 0x00
REG_OP_MODE           = 0x01
REG_FRF_MSB           = 0x06
REG_FRF_MID           = 0x07
REG_FRF_LSB           = 0x08
REG_FIFO_ADDR_PTR     = 0x0D
REG_FIFO_RX_BASE_ADDR = 0x0F
REG_FIFO_RX_CURRENT   = 0x10
REG_IRQ_FLAGS         = 0x12
REG_RX_NB_BYTES       = 0x13
REG_PKT_SNR_VALUE     = 0x19   # signed byte: SNR = value / 4.0 dB
REG_PKT_RSSI_VALUE    = 0x1A   # RSSI = -157 + value dBm (LF port)
REG_MODEM_CONFIG1     = 0x1D
REG_MODEM_CONFIG2     = 0x1E
REG_PREAMBLE_MSB      = 0x20
REG_PREAMBLE_LSB      = 0x21
REG_SYNC_WORD         = 0x39
REG_VERSION           = 0x42

IRQ_RX_DONE           = 0x40
IRQ_PAYLOAD_CRC_ERROR = 0x20
IRQ_RX_TIMEOUT        = 0x80

# ---------------------------------------------------------------------------
# Hardware drivers — lazy import so the gateway process survives on non-RPi
# ---------------------------------------------------------------------------
_spidev_available = False
_spidev_error     = ""
_spidev_mod       = None
GPIO              = None

try:
    import spidev as _spidev_mod
    _spidev_available = True
except Exception as _e:
    _spidev_error = str(_e)

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    try:
        import rpi_lgpio as GPIO  # RPi 5 / Debian Bookworm
    except (ImportError, RuntimeError):
        GPIO = None

spi = None


def get_spi():
    """Lazily open /dev/spidev0.0."""
    global spi, _spidev_available, _spidev_error
    if not _spidev_available or _spidev_mod is None:
        return None
    if spi is not None:
        return spi
    try:
        s = _spidev_mod.SpiDev()
        s.open(0, 0)
        s.max_speed_hz = 100_000
        s.mode = 0
        spi = s
        return spi
    except Exception as exc:
        _spidev_available = False
        _spidev_error = f"Cannot open /dev/spidev0.0: {exc}"
        logger.warning("LoRa SPI unavailable: %s", exc)
        spi = None
        return None


def read_register(reg: int) -> int:
    s = get_spi()
    if s is None:
        raise RuntimeError("SPI interface is not open")
    return s.xfer2([reg & 0x7F, 0x00])[1]


def write_register(reg: int, value: int) -> None:
    s = get_spi()
    if s is None:
        raise RuntimeError("SPI interface is not open")
    s.xfer2([reg | 0x80, value & 0xFF])


# ---------------------------------------------------------------------------
# Hardware reset
# ---------------------------------------------------------------------------

def reset_module() -> None:
    if GPIO is None:
        logger.debug("RPi.GPIO not available — skipping hardware reset pulse")
        return
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(RESET_PIN, GPIO.OUT)
        GPIO.output(RESET_PIN, GPIO.HIGH)
        time.sleep(0.02)
        GPIO.output(RESET_PIN, GPIO.LOW)
        time.sleep(0.02)
        GPIO.output(RESET_PIN, GPIO.HIGH)
        time.sleep(0.1)
    except Exception as exc:
        logger.warning("Could not toggle LoRa RESET pin: %s", exc)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_lora() -> None:
    reset_module()

    version = read_register(REG_VERSION)
    if version != 0x12:
        raise RuntimeError(f"Unexpected SX1278 version: 0x{version:02X}")

    # Enter LoRa sleep mode
    write_register(REG_OP_MODE, 0x80)
    time.sleep(0.05)
    if read_register(REG_OP_MODE) != 0x80:
        raise RuntimeError("Failed to enter LoRa sleep mode")

    # 433 MHz frequency
    write_register(REG_FRF_MSB, 0x6C)
    write_register(REG_FRF_MID, 0x40)
    write_register(REG_FRF_LSB, 0x00)

    # SF7, BW125 kHz, CR4/5, explicit header, CRC disabled
    write_register(REG_MODEM_CONFIG1, 0x72)
    write_register(REG_MODEM_CONFIG2, 0x70)

    # Preamble length = 8 symbols
    write_register(REG_PREAMBLE_MSB, 0x00)
    write_register(REG_PREAMBLE_LSB, 0x08)

    # Sync word 0x12 (LoRa private network — must match firmware)
    write_register(REG_SYNC_WORD, 0x12)

    # FIFO RX base address = 0x00
    write_register(REG_FIFO_RX_BASE_ADDR, 0x00)
    write_register(REG_FIFO_ADDR_PTR, 0x00)

    # Continuous receive mode
    write_register(REG_OP_MODE, 0x85)
    logger.info("SX1278 initialised — 433 MHz, SF7, BW125, CR4/5, sync=0x12")


# ---------------------------------------------------------------------------
# RSSI / SNR helpers
# ---------------------------------------------------------------------------

def read_rssi() -> float:
    """Return the RSSI of the last received packet in dBm (LF port formula)."""
    raw = read_register(REG_PKT_RSSI_VALUE)
    return -157.0 + raw


def read_snr() -> float:
    """Return the SNR of the last received packet in dB."""
    raw = read_register(REG_PKT_SNR_VALUE)
    # The register holds a signed byte; convert from two's complement
    if raw > 127:
        raw -= 256
    return raw / 4.0


# ---------------------------------------------------------------------------
# Packet reception
# ---------------------------------------------------------------------------

def receive_packet() -> str:
    fifo_addr = read_register(REG_FIFO_RX_CURRENT)
    write_register(REG_FIFO_ADDR_PTR, fifo_addr)
    length = read_register(REG_RX_NB_BYTES)
    data = bytearray(read_register(REG_FIFO) for _ in range(length))
    return data.decode("utf-8", errors="replace")


def process_packet(raw_payload: str) -> None:
    """Validate, normalise, and enqueue a LoRa packet."""
    # Read signal quality immediately (must be read before next packet)
    try:
        rssi = read_rssi()
        snr  = read_snr()
    except Exception:
        rssi = None
        snr  = None

    try:
        telemetry = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError):
        logger.warning("LoRa packet is not valid JSON: %.120s", raw_payload)
        return

    # Normalise "status" → "metadata" (legacy firmware compat)
    if isinstance(telemetry, dict) and "status" in telemetry and "metadata" not in telemetry:
        telemetry["metadata"] = telemetry.pop("status")

    if not validate(telemetry):
        logger.warning("LoRa packet failed validation, discarding: %s", telemetry)
        return

    envelope = normalize(
        raw=telemetry,
        ingress_topic=f"lora/{telemetry.get('device_id', 'unknown')}",
        rssi_dbm=rssi,
        snr_db=snr,
    )

    import json as _json
    payload_str = _json.dumps(envelope, separators=(",", ":"))
    from . import config as _cfg
    topic = _cfg.MQTT_OUTPUT_TOPIC

    try:
        sqlite_queue.enqueue(envelope["message_id"], topic, payload_str)
        logger.info(
            "LoRa packet queued: device=%s seq=%s rssi=%s snr=%s",
            envelope.get("device_id"),
            telemetry.get("seq"),
            f"{rssi:.1f}" if rssi is not None else "N/A",
            f"{snr:.1f}" if snr is not None else "N/A",
        )
    except RuntimeError as exc:
        logger.error("Queue full — dropping LoRa packet: %s", exc)


# ---------------------------------------------------------------------------
# Main receive loop
# ---------------------------------------------------------------------------

def run() -> None:
    """Run the LoRa receive loop until interrupted.

    On non-RPi platforms or when ENABLE_LORA is false (e.g. Gateway 2), this function
    logs and returns immediately so the MQTT ingestion and forwarding services continue.
    """
    from . import config
    if not getattr(config, "ENABLE_LORA", True):
        logger.info("LoRa receiver explicitly disabled via ENABLE_LORA=false. Exiting receiver.")
        return

    if not _spidev_available or get_spi() is None:
        logger.warning(
            "LoRa hardware not available on this platform (%s) — receiver exiting.",
            _spidev_error or "SPI device not open",
        )
        return

    logger.info("Starting LoRa receiver...")
    try:
        init_lora()
    except Exception as exc:
        logger.error("LoRa init failed: %s — receiver exiting.", exc)
        return

    logger.info("Waiting for ESP32 LoRa packets on 433 MHz...")
    last_status = time.monotonic()

    try:
        while True:
            irq = read_register(REG_IRQ_FLAGS)

            if irq & IRQ_RX_DONE:
                if irq & IRQ_PAYLOAD_CRC_ERROR:
                    logger.error("CRC error in received LoRa packet")
                else:
                    raw = receive_packet()
                    logger.debug("Raw LoRa payload: %s", raw)
                    process_packet(raw)

                write_register(REG_IRQ_FLAGS, irq)          # clear IRQ flags
                write_register(REG_OP_MODE, 0x85)           # back to continuous RX

            elif irq & IRQ_RX_TIMEOUT:
                write_register(REG_IRQ_FLAGS, IRQ_RX_TIMEOUT)
                write_register(REG_OP_MODE, 0x85)

            # Periodic status log
            if time.monotonic() - last_status >= 30:
                logger.info(
                    "LoRa status: OP_MODE=0x%02X IRQ=0x%02X queue=%d",
                    read_register(REG_OP_MODE),
                    read_register(REG_IRQ_FLAGS),
                    sqlite_queue.pending_count(),
                )
                last_status = time.monotonic()

            time.sleep(0.005)

    except KeyboardInterrupt:
        logger.info("LoRa receiver stopped by keyboard interrupt")
    finally:
        if spi is not None:
            try:
                spi.close()
            except Exception:
                pass
        if GPIO is not None:
            try:
                GPIO.cleanup()
            except Exception:
                pass

