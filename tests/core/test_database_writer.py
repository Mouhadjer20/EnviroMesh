"""
test_database_writer.py
=======================
Tests for raspberry_pi/core/backend/services/database_writer.py

All PostgreSQL / psycopg2 interactions are fully mocked.
No live database is required.

Tested behaviours
-----------------
* connect() returns True on success, False on psycopg2.Error.
* write_telemetry() inserts into sensor_telemetry.
* write_telemetry() skips insertion when message_id already in processed_messages.
* write_telemetry() calls conn.commit() on success.
* write_telemetry() calls conn.rollback() on psycopg2 error.
* write_raw_packet() inserts a row in raw_sensor_packets.
* close() closes the connection and sets conn to None.
"""

import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# psycopg2 may not be installed in the test environment;
# provide a minimal stub so the module can be imported.
# ---------------------------------------------------------------------------
try:
    import psycopg2
except ImportError:
    # Inject a minimal mock so database_writer.py can be imported
    mock_psycopg2 = MagicMock()
    mock_psycopg2.Error = Exception
    # psycopg2.extras.Json — just return the dict as-is during tests
    mock_psycopg2.extras.Json = lambda d: d
    mock_psycopg2.Binary = lambda b: b
    sys.modules["psycopg2"]           = mock_psycopg2
    sys.modules["psycopg2.extras"]    = mock_psycopg2.extras
    sys.modules["psycopg2.errorcodes"]= MagicMock()

# Also stub dotenv if not installed
try:
    import dotenv  # noqa: F401
except ImportError:
    sys.modules["dotenv"] = MagicMock()

import psycopg2  # re-import (possibly the stub)

from services.database_writer import TimescaleDBWriter


# ---------------------------------------------------------------------------
# Shared fixture: a writer with a mocked connection
# ---------------------------------------------------------------------------

@pytest.fixture
def writer():
    """TimescaleDBWriter with a fully mocked psycopg2 connection."""
    w = TimescaleDBWriter(
        host="localhost", port=5432,
        dbname="testdb", user="test", password="test",
    )
    mock_conn = MagicMock()
    mock_conn.autocommit = False
    # cursor() returns a context manager
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)
    # fetchone returns None by default (no duplicate)
    mock_cursor.fetchone.return_value = None
    w.conn = mock_conn
    return w, mock_conn, mock_cursor


# ===========================================================================
# connect()
# ===========================================================================

class TestConnect:
    def test_connect_returns_true_on_success(self):
        w = TimescaleDBWriter(host="h", port=5432, dbname="db", user="u", password="p")
        with patch("services.database_writer.psycopg2.connect") as mock_connect:
            mock_connect.return_value = MagicMock()
            result = w.connect()
        assert result is True
        assert w.conn is not None

    def test_connect_returns_false_on_error(self):
        w = TimescaleDBWriter(host="bad", port=5432, dbname="db", user="u", password="p")
        with patch(
            "services.database_writer.psycopg2.connect",
            side_effect=psycopg2.Error("connection refused"),
        ):
            result = w.connect()
        assert result is False
        assert w.conn is None


# ===========================================================================
# write_telemetry()
# ===========================================================================

class TestWriteTelemetry:
    def test_inserts_into_sensor_telemetry(self, writer):
        w, conn, cursor = writer
        telemetry = {
            "message_id":          "uuid-001",
            "device_id":           "G31",
            "protocol":            "wifi",
            "timestamp":           "2026-11-04T10:00:00Z",
            "gateway_id":          "GW01",
            "gateway_received_at": "2026-11-04T10:00:01Z",
            "metrics":             {"temperature_c": 22.5},
        }
        w.write_telemetry(telemetry)
        # cursor.execute should have been called (at least once for telemetry insert)
        assert cursor.execute.called

    def test_commits_on_success(self, writer):
        w, conn, cursor = writer
        w.write_telemetry({"message_id": "uuid-002", "device_id": "G31", "metrics": {}})
        conn.commit.assert_called()

    def test_skips_duplicate_message_id(self, writer):
        """If processed_messages already has the message_id, insert is skipped."""
        w, conn, cursor = writer
        # Simulate: SELECT 1 FROM processed_messages returns a row
        cursor.fetchone.return_value = (1,)
        w.write_telemetry({"message_id": "dup-uuid", "device_id": "G31", "metrics": {}})
        # Must have rolled back (not committed)
        conn.rollback.assert_called()
        conn.commit.assert_not_called()

    def test_rollback_on_error(self, writer):
        """A psycopg2 error during execute triggers rollback."""
        w, conn, cursor = writer
        cursor.execute.side_effect = psycopg2.Error("insert failed")
        w.write_telemetry({"message_id": "err-uuid", "device_id": "G31", "metrics": {}})
        conn.rollback.assert_called()

    def test_no_crash_when_conn_is_none(self):
        """write_telemetry must not crash if _ensure_connection fails."""
        w = TimescaleDBWriter(host="bad", port=5432, dbname="db", user="u", password="p")
        w.conn = None
        with patch.object(w, "connect", return_value=False):
            # Should return silently without raising
            w.write_telemetry({"device_id": "G31", "metrics": {}})


# ===========================================================================
# write_raw_packet()
# ===========================================================================

class TestWriteRawPacket:
    def test_inserts_raw_packet(self, writer):
        w, conn, cursor = writer
        w.write_raw_packet("G11", "lora", b"\xDE\xAD\xBE\xEF", parsed=True)
        assert cursor.execute.called
        conn.commit.assert_called()

    def test_rollback_on_raw_packet_error(self, writer):
        w, conn, cursor = writer
        cursor.execute.side_effect = psycopg2.Error("disk full")
        w.write_raw_packet("G11", "lora", b"\x00", parsed=False)
        conn.rollback.assert_called()


# ===========================================================================
# close()
# ===========================================================================

class TestClose:
    def test_close_sets_conn_to_none(self, writer):
        w, conn, _ = writer
        w.close()
        assert w.conn is None

    def test_close_calls_conn_close(self, writer):
        w, conn, _ = writer
        w.close()
        conn.close.assert_called_once()

