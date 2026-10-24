"""TimescaleDB / PostgreSQL writer for RPi (Core Processing Server).

Inserts validated telemetry into the sensor_telemetry hypertable and
raw sensor packets into raw_sensor_packets.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

import psycopg2
from psycopg2.extras import Json

logger = logging.getLogger("database_writer")


class TimescaleDBWriter:
    """Wrapper around psycopg2 for writing telemetry to TimescaleDB."""

    def __init__(self, host=None, port=None, dbname=None, user=None, password=None):
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = int(port or os.getenv("DB_PORT", 5432))
        self.dbname = dbname or os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "enviromesh"))
        self.user = user or os.getenv("DB_USER", os.getenv("POSTGRES_USER", "enviromesh_app"))
        self.password = password or os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
        self.conn = None

    def connect(self):
        """Connect to TimescaleDB."""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
            )
            self.conn.autocommit = True
            logger.info(
                "Connected to TimescaleDB %s:%d/%s", self.host, self.port, self.dbname
            )
            return True
        except psycopg2.Error as exc:
            logger.error("Failed to connect to TimescaleDB: %s", exc)
            self.conn = None
            return False

    def write_telemetry(self, telemetry: dict):
        """Insert a validated telemetry reading into the sensor_telemetry hypertable."""
        if self.conn is None:
            logger.debug("TimescaleDB not connected; skipping telemetry write")
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO sensor_telemetry
                        (timestamp, device_id, zone, metrics, received_at, protocol, rssi, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        telemetry.get("timestamp") or datetime.now(timezone.utc),
                        telemetry.get("device_id"),
                        telemetry.get("zone"),
                        Json(telemetry.get("metrics", {})),
                        datetime.now(timezone.utc),
                        telemetry.get("protocol"),
                        telemetry.get("rssi"),
                        Json(telemetry.get("metadata", {})),
                    ),
                )
            logger.debug(
                "Inserted telemetry for device %s", telemetry.get("device_id")
            )
        except psycopg2.Error as exc:
            logger.error("Failed to write telemetry to TimescaleDB: %s", exc)

    def write_raw_packet(self, device_id: str, protocol: str, payload, parsed: bool):
        """Insert a raw sensor packet for diagnostics and traceability."""
        if self.conn is None:
            logger.debug("TimescaleDB not connected; skipping raw packet write")
            return None
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_sensor_packets
                        (device_id, protocol, payload, parsed, received_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        device_id,
                        protocol,
                        psycopg2.Binary(payload)
                        if isinstance(payload, (bytes, bytearray))
                        else payload,
                        parsed,
                        datetime.now(timezone.utc),
                    ),
                )
            logger.debug(
                "Inserted raw packet: device=%s protocol=%s parsed=%s",
                device_id,
                protocol,
                parsed,
            )
        except psycopg2.Error as exc:
            logger.error("Failed to write raw packet to TimescaleDB: %s", exc)

    def close(self):
        """Close the TimescaleDB connection."""
        if self.conn is not None:
            try:
                self.conn.close()
            except psycopg2.Error as exc:
                logger.warning("Error closing TimescaleDB connection: %s", exc)
            self.conn = None
            logger.info("TimescaleDB connection closed")


# Module-level writer for convenience / backward-compatible function API.
_writer = TimescaleDBWriter()


def write_telemetry(telemetry: dict):
    """Write a validated telemetry reading to TimescaleDB."""
    if _writer.conn is None:
        _writer.connect()
    _writer.write_telemetry(telemetry)


def write_raw_packet(device_id: str, protocol: str, payload: bytes, parsed: bool):
    """Write a raw sensor packet for diagnostics and traceability."""
    if _writer.conn is None:
        _writer.connect()
    _writer.write_raw_packet(device_id, protocol, payload, parsed)