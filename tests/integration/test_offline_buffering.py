"""
test_offline_buffering.py
=========================
Core outage simulation — no real MQTT broker required.

Scenario
--------
When RPi 2 (the core) is unreachable, the gateway continues to enqueue
messages in its SQLite offline queue.  When connectivity is restored and
PUBACK is received, messages are removed from the queue.

Tested behaviours
-----------------
1. Many messages enqueue successfully while the core is "down".
2. Messages remain in the queue while no ACK is received.
3. After simulated ACK (mark_sent), each message is individually removed.
4. After all ACKs, the queue is empty.
5. Queue-full RuntimeError fires when QUEUE_MAX_MESSAGES is reached.
6. Partial ACKs (some ACKed, some not) leave the right messages.
7. mark_attempt increments the retry counter but keeps the message in queue.
8. After restart (new DB connection), buffered messages are still present.
"""

import json
import sqlite3

import pytest

from gateway import config, sqlite_queue


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _init(temp_db, monkeypatch, max_messages=None):
    monkeypatch.setattr(sqlite_queue, "_DB_PATH", temp_db)
    monkeypatch.setattr(config, "SQLITE_PATH",    temp_db)
    if max_messages is not None:
        monkeypatch.setattr(config, "QUEUE_MAX_MESSAGES", max_messages)
    sqlite_queue.init_db()


def _enqueue_n(n: int, topic: str = "t") -> list:
    """Enqueue *n* messages and return their message_ids."""
    ids = []
    for i in range(n):
        mid = f"outage-msg-{i:04d}"
        sqlite_queue.enqueue(mid, topic, json.dumps({"seq": i}))
        ids.append(mid)
    return ids


# ===========================================================================
# Buffering during outage
# ===========================================================================

class TestBufferingDuringOutage:
    def test_many_messages_enqueue_during_outage(self, temp_db, monkeypatch):
        """50 messages should enqueue without error (simulating core outage)."""
        _init(temp_db, monkeypatch)
        ids = _enqueue_n(50)
        assert sqlite_queue.pending_count() == 50

    def test_messages_remain_without_ack(self, temp_db, monkeypatch):
        """Without any mark_sent call, all messages stay in the queue."""
        _init(temp_db, monkeypatch)
        _enqueue_n(10)
        # Simulate a full forward cycle that gets no ACK (no mark_sent)
        batch = sqlite_queue.get_batch(batch_size=10)
        for row in batch:
            sqlite_queue.mark_attempt(row["message_id"])
        # Messages are still there
        assert sqlite_queue.pending_count() == 10

    def test_all_messages_deleted_after_all_acks(self, temp_db, monkeypatch):
        """After simulating ACK for every message, queue must be empty."""
        _init(temp_db, monkeypatch)
        ids = _enqueue_n(20)
        for mid in ids:
            sqlite_queue.mark_sent(mid)
        assert sqlite_queue.pending_count() == 0

    def test_partial_ack_leaves_correct_messages(self, temp_db, monkeypatch):
        """ACK first 3 messages; remaining 7 must still be present."""
        _init(temp_db, monkeypatch)
        ids = _enqueue_n(10)

        acked     = ids[:3]
        remaining = ids[3:]

        for mid in acked:
            sqlite_queue.mark_sent(mid)

        assert sqlite_queue.pending_count() == 7

        # Confirm the right message_ids remain
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT message_id FROM queue ORDER BY id"
            ).fetchall()
        db_ids = [r["message_id"] for r in rows]
        assert set(db_ids) == set(remaining)


# ===========================================================================
# Queue full — outage too long
# ===========================================================================

class TestQueueFull:
    def test_raises_when_max_reached(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch, max_messages=5)
        _enqueue_n(5)
        with pytest.raises(RuntimeError, match="Queue full"):
            sqlite_queue.enqueue("overflow", "t", "{}")

    def test_queue_accepts_messages_after_ack_frees_space(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch, max_messages=3)
        ids = _enqueue_n(3)
        # ACK one → slot freed
        sqlite_queue.mark_sent(ids[0])
        # Now one more should succeed
        result = sqlite_queue.enqueue("after-ack", "t", "{}")
        assert result is True


# ===========================================================================
# Retry counter during outage
# ===========================================================================

class TestRetryCounter:
    def test_mark_attempt_keeps_message_in_queue(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("retry-me", "t", "{}")
        sqlite_queue.mark_attempt("retry-me")
        assert sqlite_queue.pending_count() == 1

    def test_mark_attempt_increments_counter_multiple_times(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("multi-retry", "t", "{}")
        for _ in range(5):
            sqlite_queue.mark_attempt("multi-retry")
        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT attempts FROM queue WHERE message_id='multi-retry'"
            ).fetchone()
        assert row["attempts"] == 5


# ===========================================================================
# Persistence — simulated restart
# ===========================================================================

class TestPersistenceAfterRestart:
    def test_messages_survive_new_connection(self, temp_db, monkeypatch):
        """Data written via sqlite_queue is still readable via a raw connection."""
        _init(temp_db, monkeypatch)
        ids = _enqueue_n(8)

        # Open a fresh connection (simulating a new process)
        with sqlite3.connect(temp_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        assert count == 8

    def test_specific_messages_readable_after_restart(self, temp_db, monkeypatch):
        _init(temp_db, monkeypatch)
        sqlite_queue.enqueue("persist-001", "t", '{"data":"important"}')

        with sqlite3.connect(temp_db) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT payload FROM queue WHERE message_id='persist-001'"
            ).fetchone()
        assert row is not None
        assert "important" in row["payload"]

