"""Telemetry normaliser for the EnviroMesh Gateway (RPi 1).

Transforms raw ESP32 payloads (LoRa or Wi-Fi MQTT) into a uniform gateway
envelope that downstream consumers (FastAPI / TimescaleDB) can process without
knowing which transport delivered the message.

Output envelope
---------------
{
  "message_id":        "<stable UUIDv5 for LoRa / UUIDv4 for Wi-Fi>",
  "timestamp":         "<firmware UTC ISO string or null>",
  "device_id":         "G11",
  "group_code":        "G1",
  "zone":              "Sector_A_Warehouse",
  "protocol":          "lora",
  "gateway_id":        "GW01",
  "gateway_received_at": "2024-01-15T10:30:00+00:00",
  "ingress_topic":     "enviromesh/devices/G11/telemetry",
  "metrics":           { ... },
  "rssi_dbm":          -78,         # LoRa packets only
  "snr_db":            8.4          # LoRa packets only
}

message_id stability
--------------------
For LoRa packets the UUID is derived from ``device_id + seq + timestamp[:19]``
using uuid5(NAMESPACE_DNS, ...) so retransmitted packets produce the same ID and
are idempotent in the SQLite queue and in the PostgreSQL dedup table.

For Wi-Fi packets a uuid4 is generated; sequence number fallback is attempted
from ``metadata.sequence`` to improve idempotency where the firmware provides it.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from .logger import get_logger
from . import config

logger = get_logger("gateway.telemetry_normalizer")

_GATEWAY_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_DNS


def _make_message_id(device_id: str, seq: Optional[int], received_at: str) -> str:
    """Return a stable UUIDv5 for LoRa packets that carry a sequence number."""
    key = f"{device_id}:{seq}:{received_at[:19]}"
    return str(uuid.uuid5(_GATEWAY_NS, key))


def normalize(
    raw: dict,
    ingress_topic: str = "",
    rssi_dbm: Optional[float] = None,
    snr_db: Optional[float] = None,
) -> dict:
    """Produce a normalised gateway envelope from a raw ESP32 payload.

    Parameters
    ----------
    raw:          Parsed JSON dict from the ESP32 (LoRa or Wi-Fi).
    ingress_topic: MQTT topic on which the message arrived (informational).
    rssi_dbm:     Received signal strength in dBm, attached for LoRa packets.
    snr_db:       Signal-to-noise ratio in dB, attached for LoRa packets.

    Returns a new dict — the original *raw* dict is not modified.
    """
    now_utc = datetime.now(timezone.utc).isoformat()

    device_id = raw.get("device_id", "")
    protocol = (raw.get("protocol") or "unknown").lower()

    # Sequence number — LoRa firmware sends "seq"; Wi-Fi may use metadata.sequence
    seq: Optional[int] = raw.get("seq")
    if seq is None:
        metadata = raw.get("metadata") or {}
        seq = metadata.get("sequence")

    # Build stable message_id
    if seq is not None:
        message_id = _make_message_id(device_id, seq, now_utc)
    else:
        message_id = str(uuid.uuid4())

    # Firmware timestamp — preserve if present, do NOT overwrite with gateway time
    firmware_ts = raw.get("timestamp")  # may be null string or ISO string

    # group_code — present at top level in LoRa payloads; in metadata for Wi-Fi
    metadata = raw.get("metadata") or {}
    group_code = raw.get("group_code") or metadata.get("group_code", "")

    envelope = {
        "message_id":          message_id,
        "timestamp":           firmware_ts,
        "device_id":           device_id,
        "group_code":          group_code,
        "zone":                raw.get("zone", ""),
        "protocol":            protocol,
        "gateway_id":          config.GATEWAY_ID,
        "gateway_received_at": now_utc,
        "ingress_topic":       ingress_topic,
        "metrics":             raw.get("metrics", {}),
    }

    # Attach LoRa signal metadata only when the values are provided
    if rssi_dbm is not None:
        envelope["rssi_dbm"] = rssi_dbm
    if snr_db is not None:
        envelope["snr_db"] = snr_db

    # Preserve any extra metadata the firmware sent (firmware_version, uptime_ms, …)
    if metadata:
        envelope["device_metadata"] = metadata

    return envelope

