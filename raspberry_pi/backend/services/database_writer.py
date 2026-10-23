"""Database writer for RPi 2 (Core Processing Server).

Inserts validated telemetry into the PostgreSQL / TimescaleDB sensor_telemetry
hypertable and raw_sensor_packets table.
"""

import logging

logger = logging.getLogger("database_writer")


def write_telemetry(telemetry: dict):
    """Write a validated telemetry reading to TimescaleDB."""
    # TODO: INSERT INTO sensor_telemetry (timestamp, device_id, zone, metrics, protocol, rssi, metadata)
    logger.debug("Writing telemetry to DB: %s", telemetry)


def write_raw_packet(device_id: str, protocol: str, payload: bytes, parsed: bool):
    """Write a raw sensor packet for diagnostics and traceability."""
    # TODO: INSERT INTO raw_sensor_packets (device_id, protocol, payload, parsed)
    logger.debug("Writing raw packet: device=%s protocol=%s parsed=%s", device_id, protocol, parsed)