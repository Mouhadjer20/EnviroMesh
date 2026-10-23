"""Packet decoder for RPi 1 (LoRa Gateway).

Parses raw LoRa bytes from ESP32 nodes into structured JSON telemetry,
appending metadata (group_code, firmware_version, RSSI, SNR).
"""

import json
import logging

logger = logging.getLogger("packet_decoder")


def decode(raw_bytes: bytes) -> dict:
    """Decode a raw LoRa frame into a telemetry dict.

    Expected payload (example):
    {
        "device_id": "G11",
        "metrics": {"gas_ppm": 145.2, "temperature_c": 26.4, ...}
    }
    """
    # TODO: Implement LoRa frame parsing / AES-128 decryption
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Failed to decode packet: %s", exc)
        payload = {}

    payload["received_at"] = None  # TODO: set timestamp
    payload["protocol"] = "LoRa"
    return payload


def enrich(telemetry: dict, rssi: int, snr: float) -> dict:
    """Add radio metadata to a decoded telemetry payload."""
    telemetry["rssi"] = rssi
    telemetry["snr"] = snr
    telemetry["metadata"] = telemetry.get("metadata", {})
    # TODO: resolve group_code from device_id via registry
    return telemetry