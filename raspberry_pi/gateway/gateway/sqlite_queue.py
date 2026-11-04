"""SQLite persistent offline queue for the EnviroMesh Gateway.

Messages written to this queue survive process restarts and power-cuts
(WAL + FULL synchronous).  The forwarder only deletes a message *after*
receiving the MQTT PUBACK from RPi 2, guaranteeing at-least-once delivery.

Schema
------
queue(
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   TEXT UNIQUE NOT NULL,   -- stable UUID, prevents double-enqueue
    topic        TEXT NOT NULL,
    payload      TEXT NOT NULL,          -- JSON string
    created_at   TEXT NOT NULL,          -- ISO 8601 UTC
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT                    -- ISO 8601 UTC or NULL
)
"""

import sqlite3
import time
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from .logger import get_logger
from . import config

logger = get_logger("sqlite_queue")

# Fail fast if the parent directory is not writable rather than silently
# dropping data later.
_DB_PATH: str = config.SQLITE_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the queue table if it does not exist."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queue (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id   TEXT UNIQUE NOT NULL,
                topic        TEXT NOT NULL,
                payload      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                attempts     INTEGER NOT NULL DEFAULT 0,
                last_attempt TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_attempts ON queue (attempts, created_at)"
        )
    logger.info("SQLite queue initialised at %s", _DB_PATH)


def enqueue(message_id: str, topic: str, payload: str) -> bool:
    """Insert a message into the queue.

    Returns True if inserted, False if the message_id already exists
    (idempotent — safe to call on retransmitted LoRa packets).

    Raises RuntimeError if the queue is full (> QUEUE_MAX_MESSAGES).
    """
    count = pending_count()
    if count >= config.QUEUE_MAX_MESSAGES:
        raise RuntimeError(
            f"Queue full ({count} messages). Cannot enqueue {message_id}."
        )

    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO queue (message_id, topic, payload, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (message_id, topic, payload, now),
            )
        return True
    except sqlite3.IntegrityError:
        logger.debug("Duplicate enqueue ignored: %s", message_id)
        return False


def get_batch(batch_size: int = None) -> List[sqlite3.Row]:
    """Return up to *batch_size* oldest pending messages (lowest attempt count)."""
    size = batch_size or config.FORWARD_BATCH_SIZE
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, message_id, topic, payload, attempts
            FROM   queue
            ORDER  BY attempts ASC, created_at ASC
            LIMIT  ?
            """,
            (size,),
        ).fetchall()
    return rows


def mark_sent(message_id: str) -> None:
    """Delete a successfully forwarded message from the queue."""
    with _connect() as conn:
        conn.execute("DELETE FROM queue WHERE message_id = ?", (message_id,))
    logger.debug("Dequeued (ACK): %s", message_id)


def mark_attempt(message_id: str) -> None:
    """Increment the attempt counter after a failed publish."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE queue
            SET    attempts     = attempts + 1,
                   last_attempt = ?
            WHERE  message_id   = ?
            """,
            (now, message_id),
        )


def pending_count() -> int:
    """Return the total number of messages waiting to be forwarded."""
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) FROM queue").fetchone()
    return row[0] if row else 0


def oldest_pending_age_s() -> Optional[float]:
    """Return the age in seconds of the oldest undelivered message, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT created_at FROM queue ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    try:
        ts = datetime.fromisoformat(row["created_at"])
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return None

