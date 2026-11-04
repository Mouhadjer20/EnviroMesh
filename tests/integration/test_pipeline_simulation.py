"""
test_pipeline_simulation.py
============================
End-to-end pipeline simulation: no real MQTT broker, no real hardware.

Pipeline under test
-------------------
raw ESP32 dict → validate() → normalize() → enqueue() → get_batch() → mark_sent()

Verified properties
-------------------
1. A valid telemetry payload passes through the entire pipeline.
2. A duplicate message (same message_id) is detected on the second enqueue.
3. The queue count is correct after mixed inserts and ACKs.
4. Invalid telemetry is dropped before enqueueing (validate returns False).
5. LoRa and Wi-Fi payloads both complete the pipeline successfully.
"""

import json

import pytest

from gateway import config, sqlite_queue
from gateway.telemetry_validator import validate
from gateway.telemetry_normalizer import normalize


# ---------------------------------------------------------------------------
# Shared helper: redirect queue to a temp DB and reset it
# ---------------------------------------------------------------------------

def _init_queue(temp_db, monkeypatch):
    monkeypatch.setattr(sqlite_queue, "_DB_PATH", temp_db)
    monkeypatch.setattr(config, "SQLITE_PATH",    temp_db)
    sqlite_queue.init_db()


# ===========================================================================
# Full pipeline — single message
# ===========================================================================

class TestFullPipeline:
    def test_wifi_payload_survives_pipeline(
        self, temp_db, monkeypatch, sample_wifi_payload
    ):
        _init_queue(temp_db, monkeypatch)

        # 1. Validate
        assert validate(sample_wifi_payload) is True

        # 2. Normalize
        envelope = normalize(sample_wifi_payload, ingress_topic="env/devices/G31/t")

        # 3. Enqueue
        payload_str = json.dumps(envelope)
        enqueued = sqlite_queue.enqueue(
            envelope["message_id"], config.MQTT_OUTPUT_TOPIC, payload_str
        )
        assert enqueued is True
        assert sqlite_queue.pending_count() == 1

        # 4. Get batch
        batch = sqlite_queue.get_batch(batch_size=1)
        assert len(batch) == 1
        assert batch[0]["message_id"] == envelope["message_id"]

        # 5. Mark sent (simulate PUBACK)
        sqlite_queue.mark_sent(envelope["message_id"])
        assert sqlite_queue.pending_count() == 0

    def test_lora_payload_survives_pipeline(
        self, temp_db, monkeypatch, sample_lora_payload
    ):
        _init_queue(temp_db, monkeypatch)

        assert validate(sample_lora_payload) is True
        envelope = normalize(
            sample_lora_payload,
            ingress_topic="env/devices/G11/t",
            rssi_dbm=-78.0,
            snr_db=8.4,
        )
        payload_str = json.dumps(envelope)
        enqueued = sqlite_queue.enqueue(
            envelope["message_id"], config.MQTT_OUTPUT_TOPIC, payload_str
        )
        assert enqueued is True

        batch = sqlite_queue.get_batch(batch_size=5)
        assert any(r["message_id"] == envelope["message_id"] for r in batch)

        sqlite_queue.mark_sent(envelope["message_id"])
        assert sqlite_queue.pending_count() == 0


# ===========================================================================
# Duplicate detection in pipeline
# ===========================================================================

class TestDuplicateDetection:
    def test_second_enqueue_of_same_message_returns_false(
        self, temp_db, monkeypatch, sample_lora_payload
    ):
        _init_queue(temp_db, monkeypatch)

        envelope = normalize(sample_lora_payload)
        payload_str = json.dumps(envelope)

        r1 = sqlite_queue.enqueue(
            envelope["message_id"], config.MQTT_OUTPUT_TOPIC, payload_str
        )
        r2 = sqlite_queue.enqueue(
            envelope["message_id"], config.MQTT_OUTPUT_TOPIC, payload_str
        )
        assert r1 is True
        assert r2 is False   # idempotent — same message_id

    def test_duplicate_does_not_increase_queue_count(
        self, temp_db, monkeypatch, sample_lora_payload
    ):
        _init_queue(temp_db, monkeypatch)

        envelope = normalize(sample_lora_payload)
        payload_str = json.dumps(envelope)

        sqlite_queue.enqueue(envelope["message_id"], "t", payload_str)
        sqlite_queue.enqueue(envelope["message_id"], "t", payload_str)
        assert sqlite_queue.pending_count() == 1


# ===========================================================================
# Invalid payload is dropped before enqueueing
# ===========================================================================

class TestInvalidPayloadDropped:
    def test_missing_device_id_not_enqueued(self, temp_db, monkeypatch):
        _init_queue(temp_db, monkeypatch)

        bad_payload = {"metrics": {"temperature_c": 25.0}}
        assert validate(bad_payload) is False
        # Pipeline stops here — nothing enqueued
        assert sqlite_queue.pending_count() == 0

    def test_out_of_range_temperature_not_enqueued(self, temp_db, monkeypatch):
        _init_queue(temp_db, monkeypatch)

        bad_payload = {
            "device_id": "G31",
            "metrics":   {"temperature_c": 999},  # way out of range
        }
        assert validate(bad_payload) is False
        assert sqlite_queue.pending_count() == 0


# ===========================================================================
# Multiple messages — ordering
# ===========================================================================

class TestMultipleMessages:
    def test_batch_returns_all_enqueued(self, temp_db, monkeypatch, sample_wifi_payload):
        """Enqueue 5 messages — get_batch should return all 5."""
        _init_queue(temp_db, monkeypatch)

        ids = []
        for i in range(5):
            payload = dict(sample_wifi_payload)
            payload["seq"] = i  # differentiate payloads
            env = normalize(payload)
            # Wi-Fi without seq → random UUID4; force unique IDs with explicit override
            mid = f"test-msg-{i:03d}"
            sqlite_queue.enqueue(mid, "t", json.dumps(env))
            ids.append(mid)

        batch = sqlite_queue.get_batch(batch_size=10)
        batch_ids = [r["message_id"] for r in batch]
        assert set(ids) == set(batch_ids)

    def test_mark_sent_reduces_count(self, temp_db, monkeypatch):
        _init_queue(temp_db, monkeypatch)

        for i in range(3):
            sqlite_queue.enqueue(f"msg-{i}", "t", "{}")

        sqlite_queue.mark_sent("msg-0")
        assert sqlite_queue.pending_count() == 2

        sqlite_queue.mark_sent("msg-1")
        assert sqlite_queue.pending_count() == 1

        sqlite_queue.mark_sent("msg-2")
        assert sqlite_queue.pending_count() == 0

