"""TimescaleDB / PostgreSQL writer for RPi 2 (Core Processing Server).

Extended from the single-Pi version to support:
  - Duplicate detection via the processed_messages table (message_id PRIMARY KEY).
  - Storage of gateway metadata: message_id, gateway_id, gateway_received_at.
  - Transactional insert — both sensor_telemetry and processed_messages are
    written in a single transaction so a process crash cannot leave an unrecorded
    insertion in one table.

The gateway normalises every message before forwarding, so the payload arriving
here always contains the message_id, gateway_id, and gateway_received_at fields.
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
        self.host     = host     or os.getenv("DB_HOST", "localhost")
        self.port     = int(port or os.getenv("DB_PORT", "5432"))
        self.dbname   = dbname   or os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "enviromesh"))
        self.user     = user     or os.getenv("DB_USER", os.getenv("POSTGRES_USER", "enviromesh_app"))
        self.password = password or os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
        self.conn     = None

    def connect(self) -> bool:
        try:
            self.conn = psycopg2.connect(
                host=self.host, port=self.port,
                dbname=self.dbname, user=self.user, password=self.password,
            )
            # autocommit=False so we can use explicit transactions for dedup
            self.conn.autocommit = False
            logger.info(
                "Connected to TimescaleDB %s:%d/%s", self.host, self.port, self.dbname
            )
            return True
        except psycopg2.Error as exc:
            logger.error("Failed to connect to TimescaleDB: %s", exc)
            self.conn = None
            return False

    def _ensure_connection(self) -> bool:
        """Reconnect if the connection was lost."""
        if self.conn is not None:
            try:
                # Lightweight liveness check
                self.conn.cursor().execute("SELECT 1")
                return True
            except psycopg2.Error:
                self.conn = None
        return self.connect()

    def write_telemetry(self, telemetry: dict):
        """Insert a validated telemetry reading with duplicate detection.

        If *message_id* is present and already exists in processed_messages,
        the insertion is silently skipped (idempotent).

        Both sensor_telemetry and processed_messages are updated in a single
        transaction.
        """
        if not self._ensure_connection():
            logger.debug("TimescaleDB not connected; skipping telemetry write")
            return

        message_id         = telemetry.get("message_id")
        gateway_id         = telemetry.get("gateway_id")
        gateway_received_at = telemetry.get("gateway_received_at")
        device_id          = telemetry.get("device_id")
        now                = datetime.now(timezone.utc)

        try:
            with self.conn.cursor() as cur:
                # --- Duplicate detection -----------------------------------
                if message_id:
                    cur.execute(
                        "SELECT 1 FROM processed_messages WHERE message_id = %s",
                        (message_id,),
                    )
                    if cur.fetchone():
                        logger.debug(
                            "Duplicate message_id=%s for device=%s — skipping",
                            message_id, device_id,
                        )
                        self.conn.rollback()
                        return

                # --- Insert telemetry -------------------------------------
                cur.execute(
                    """
                    INSERT INTO sensor_telemetry
                        (timestamp, device_id, zone, metrics, received_at, protocol,
                         rssi, metadata, message_id, gateway_id, gateway_received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        telemetry.get("timestamp") or now,
                        device_id,
                        telemetry.get("zone"),
                        Json(telemetry.get("metrics", {})),
                        now,
                        telemetry.get("protocol"),
                        telemetry.get("rssi_dbm") or telemetry.get("rssi"),
                        Json({
                            k: v for k, v in telemetry.items()
                            if k not in {
                                "timestamp", "device_id", "zone", "metrics",
                                "protocol", "rssi_dbm", "rssi", "message_id",
                                "gateway_id", "gateway_received_at",
                            }
                        }),
                        message_id,
                        gateway_id,
                        gateway_received_at,
                    ),
                )

                # --- Record in dedup table --------------------------------
                if message_id:
                    cur.execute(
                        """
                        INSERT INTO processed_messages
                            (message_id, device_id, gateway_id, processed_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (message_id) DO NOTHING
                        """,
                        (message_id, device_id, gateway_id, now),
                    )

            self.conn.commit()
            logger.debug(
                "Inserted telemetry: device=%s message_id=%s",
                device_id, message_id or "N/A",
            )

        except psycopg2.Error as exc:
            logger.error("Failed to write telemetry: %s", exc)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def write_raw_packet(self, device_id: str, protocol: str, payload, parsed: bool):
        """Insert a raw sensor packet for diagnostics and traceability."""
        if not self._ensure_connection():
            return
        clean_device_id = device_id[:3] if device_id else None
        clean_protocol  = (protocol[:20] if protocol else "unknown")
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw_sensor_packets
                        (device_id, protocol, payload, parsed, received_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        clean_device_id,
                        clean_protocol,
                        psycopg2.Binary(payload)
                        if isinstance(payload, (bytes, bytearray))
                        else payload,
                        parsed,
                        datetime.now(timezone.utc),
                    ),
                )
            self.conn.commit()
        except psycopg2.Error as exc:
            logger.error("Failed to write raw packet: %s", exc)
            try:
                self.conn.rollback()
            except Exception:
                pass

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except psycopg2.Error as exc:
                logger.warning("Error closing connection: %s", exc)
            self.conn = None
            logger.info("TimescaleDB connection closed")


# Module-level writer for backward-compatible function API
_writer = TimescaleDBWriter()


def write_telemetry(telemetry: dict):
    """Write a validated (and deduplicated) telemetry reading to TimescaleDB."""
    if _writer.conn is None:
        _writer.connect()
    _writer.write_telemetry(telemetry)


def write_raw_packet(device_id: str, protocol: str, payload: bytes, parsed: bool):
    """Write a raw sensor packet for diagnostics and traceability."""
    if _writer.conn is None:
        _writer.connect()
    _writer.write_raw_packet(device_id, protocol, payload, parsed)
