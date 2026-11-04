"""
test_sqlite_queue.py
====================
Tests for raspberry_pi/gateway/gateway/sqlite_queue.py

Key design notes
----------------
* ``sqlite_queue._DB_PATH`` is set at **module import time** from
  ``config.SQLITE_PATH``.  We therefore patch ``sqlite_queue._DB_PATH``
  directly (and ``config.SQLITE_PATH`` for consistency) in every test so
  each test gets an isolated temp file.
* No real hardware or network is involved.
"""

import sqlite3
import time

import pytest

from gateway import config, sqlite_queue


# ---------------------------------------------------------------------------
# Helper: re-point the queue module to a temp DB and initialise it
# ---------------------------------------------------------------------------

def _init(temp_db, monkeypatch):
    """Redirect sqlite_queue to *temp_db* and create the schema."""
    monkeypatch.setattr(sqlite_queue, "_DB_PATH", temp_db)
    monkeypatch.setattr(config, "SQLITE_PATH", temp_db)
    sqlite_queue.init_db()


# ===========================================================================
# init_db
# ===========================================================================

class TestInitDb:
    def test_creates_queue_table(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        with sqlite3.connect(temp_db) as conn:
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "queue" in tables

    def test_creates_index(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        with sqlite3.connect(temp_db) as conn:
            indexes = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        assert "idx_queue_attempts" in indexes

    def test_idempotent_double_call(self, temp_db, monkeypatch):
        """Calling init_db twice must not raise."""
        _init(temp_db, monkeypatch)
        sqlite_queue.init_db()   # second call — CREATE TABLE IF NOT EXISTS

    def test_wal_mode_active(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        with sqlite3.connect(temp_db) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# ===========================================================================
# enqueue
# ===========================================================================

class TestEnqueue:
    def test_returns_true_on_first_insert(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        result = sqlite_queue.enqueue("msg-001", "topic/x", '{"v":1}')
        assert result is True

    def test_returns_false_on_duplicate(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        r1 = sqlite_queue.enqueue("msg-dup", "topic/x", '{"v":1}')
        r2 = sqlite_queue.enqueue("msg-dup", "topic/x", '{"v":1}')
        assert r1 is True
        assert r2 is False

    def test_duplicate_different_payload_still_false(self, temp_db, monkeypatch):
        """The uniqueness constraint is on message_id, not on payload."""
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-uid", "topic/x", '{"v":1}')
        result = sqlite_queue.enqueue("msg-uid", "topic/x", '{"v":999}')
        assert result is False

    def test_different_message_ids_both_inserted(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        r1 = sqlite_queue.enqueue("msg-A", "t", "{}")
        r2 = sqlite_queue.enqueue("msg-B", "t", "{}")
        assert r1 is True
        assert r2 is True

    def test_raises_runtime_error_when_full(self, temp_db, monkeypatch):
        monkeypatch.setattr(sqlite_queue, "_DB_PATH", temp_db)
        monkeypatch.setattr(config, "SQLITE_PATH", temp_db)
        monkeypatch.setattr(config, "QUEUE_MAX_MESSAGES", 2)
        sqlite_queue.init_db()
        sqlite_queue.enqueue("msg-001", "t", "{}")
        sqlite_queue.enqueue("msg-002", "t", "{}")
        with pytest.raises(RuntimeError, match="Queue full"):
            sqlite_queue.enqueue("msg-003", "t", "{}")

    def test_queue_full_message_contains_count(self, temp_db, monkeypatch):
        monkeypatch.setattr(sqlite_queue, "_DB_PATH", temp_db)
        monkeypatch.setattr(config, "SQLITE_PATH", temp_db)
        monkeypatch.setattr(config, "QUEUE_MAX_MESSAGES", 1)
        sqlite_queue.init_db()
        sqlite_queue.enqueue("msg-001", "t", "{}")
        with pytest.raises(RuntimeError, match="1"):
            sqlite_queue.enqueue("msg-002", "t", "{}")

    def test_stores_correct_payload(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        payload = '{"sensor":"dht22","val":25.5}'
        sqlite_queue.enqueue("msg-payload", "myTopic", payload)
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM queue WHERE message_id='msg-payload'"
            ).fetchone()
        assert row["payload"] == payload
        assert row["topic"]   == "myTopic"


# ===========================================================================
# pending_count
# ===========================================================================

class TestPendingCount:
    def test_empty_queue_returns_zero(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        assert sqlite_queue.pending_count() == 0

    def test_count_increases_with_enqueue(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("m1", "t", "{}")
        sqlite_queue.enqueue("m2", "t", "{}")
        assert sqlite_queue.pending_count() == 2

    def test_count_does_not_increase_on_duplicate(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("m-dup", "t", "{}")
        sqlite_queue.enqueue("m-dup", "t", "{}")
        assert sqlite_queue.pending_count() == 1


# ===========================================================================
# mark_sent
# ===========================================================================

class TestMarkSent:
    def test_deletes_row(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-del", "t", "{}")
        assert sqlite_queue.pending_count() == 1
        sqlite_queue.mark_sent("msg-del")
        assert sqlite_queue.pending_count() == 0

    def test_mark_sent_nonexistent_is_noop(self, temp_db, monkeypatch):
        """Deleting a non-existent message_id must not raise."""
        _init(temp_db, monkeypatch)
        sqlite_queue.mark_sent("does-not-exist")  # should not raise

    def test_mark_sent_only_removes_target(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("keep", "t", "{}")
        sqlite_queue.enqueue("remove", "t", "{}")
        sqlite_queue.mark_sent("remove")
        assert sqlite_queue.pending_count() == 1
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT message_id FROM queue"
            ).fetchone()
        assert row["message_id"] == "keep"


# ===========================================================================
# mark_attempt
# ===========================================================================

class TestMarkAttempt:
    def test_increments_attempts_counter(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-retry", "t", "{}")
        sqlite_queue.mark_attempt("msg-retry")
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT attempts FROM queue WHERE message_id='msg-retry'"
            ).fetchone()
        assert row["attempts"] == 1

    def test_increments_twice(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-r2", "t", "{}")
        sqlite_queue.mark_attempt("msg-r2")
        sqlite_queue.mark_attempt("msg-r2")
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT attempts FROM queue WHERE message_id='msg-r2'"
            ).fetchone()
        assert row["attempts"] == 2

    def test_sets_last_attempt_timestamp(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-ts", "t", "{}")
        sqlite_queue.mark_attempt("msg-ts")
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT last_attempt FROM queue WHERE message_id='msg-ts'"
            ).fetchone()
        assert row["last_attempt"] is not None


# ===========================================================================
# get_batch
# ===========================================================================

class TestGetBatch:
    def test_returns_oldest_first(self, temp_db, monkeypatch):
        """Messages with fewer attempts and earlier created_at come first."""
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("first",  "t", '{"seq":1}')
        time.sleep(0.01)
        sqlite_queue.enqueue("second", "t", '{"seq":2}')
        time.sleep(0.01)
        sqlite_queue.enqueue("third",  "t", '{"seq":3}')
        batch = sqlite_queue.get_batch(batch_size=3)
        ids = [row["message_id"] for row in batch]
        assert ids == ["first", "second", "third"]

    def test_respects_batch_size(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        for i in range(10):
            sqlite_queue.enqueue(f"m{i:03d}", "t", "{}")
        batch = sqlite_queue.get_batch(batch_size=4)
        assert len(batch) == 4

    def test_empty_queue_returns_empty_list(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        batch = sqlite_queue.get_batch()
        assert batch == []

    def test_rows_contain_expected_fields(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("msg-fields", "myTopic", '{"k":"v"}')
        row = sqlite_queue.get_batch(batch_size=1)[0]
        assert row["message_id"] == "msg-fields"
        assert row["topic"]      == "myTopic"
        assert row["payload"]    == '{"k":"v"}'
        assert row["attempts"]   == 0

    def test_higher_attempt_messages_come_last(self, temp_db, monkeypatch):
        """After marking_attempt, the retried message should sort behind new ones."""
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("early",  "t", "{}")
        sqlite_queue.enqueue("recent", "t", "{}")
        sqlite_queue.mark_attempt("early")
        batch = sqlite_queue.get_batch(batch_size=2)
        ids = [row["message_id"] for row in batch]
        # 'recent' has 0 attempts → comes before 'early' (1 attempt)
        assert ids[0] == "recent"


# ===========================================================================
# Persistence across process restart (temp file survives reimport)
# ===========================================================================

class TestPersistence:
    def test_data_survives_reconnect(self, temp_db, monkeypatch):
        """Data written to the SQLite file is readable after a new connection."""
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("persist-me", "t", '{"x":42}')

        # Simulate "process restart" by opening a brand-new connection
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT payload FROM queue WHERE message_id='persist-me'"
            ).fetchone()
        assert row is not None
        assert '"x":42' in row["payload"]

    def test_wal_mode_survives_reconnect(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        with sqlite3.connect(temp_db) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

