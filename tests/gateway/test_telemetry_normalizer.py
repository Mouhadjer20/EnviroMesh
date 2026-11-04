"""
test_telemetry_normalizer.py
============================
Tests for raspberry_pi/gateway/gateway/telemetry_normalizer.py

Key contracts verified
----------------------
* LoRa packets with a ``seq`` field get a *deterministic* UUIDv5 message_id.
* Wi-Fi packets without ``seq`` get a random UUID4 message_id.
* RSSI / SNR are attached only when provided.
* gateway_id is taken from config.GATEWAY_ID.
* gateway_received_at is a non-empty ISO timestamp string.
* The original ``raw`` dict is never mutated.
"""

import uuid
import re
from unittest.mock import patch

import pytest

from gateway.telemetry_normalizer import normalize, _make_message_id
from gateway import config


# UUID4 regex (simple check — 8-4-4-4-12 hex groups)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


# ===========================================================================
# _make_message_id (LoRa deterministic UUID)
# ===========================================================================

class TestMakeMessageId:
    def test_returns_valid_uuid_string(self):
        mid = _make_message_id("G11", 7, "2026-11-04T10:00:00+00:00")
        assert UUID_RE.match(mid)

    def test_deterministic_same_inputs(self):
        m1 = _make_message_id("G11", 7, "2026-11-04T10:00:00+00:00")
        m2 = _make_message_id("G11", 7, "2026-11-04T10:00:00+00:00")
        assert m1 == m2

    def test_different_seq_produces_different_id(self):
        m1 = _make_message_id("G11", 1, "2026-11-04T10:00:00+00:00")
        m2 = _make_message_id("G11", 2, "2026-11-04T10:00:00+00:00")
        assert m1 != m2

    def test_different_device_id_produces_different_id(self):
        m1 = _make_message_id("G11", 1, "2026-11-04T10:00:00+00:00")
        m2 = _make_message_id("G22", 1, "2026-11-04T10:00:00+00:00")
        assert m1 != m2

    def test_is_uuidv5(self):
        mid = _make_message_id("G11", 7, "2026-11-04T10:00:00+00:00")
        parsed = uuid.UUID(mid)
        assert parsed.version == 5


# ===========================================================================
# normalize — LoRa packets
# ===========================================================================

class TestNormalizeLoRa:
    def test_lora_gets_uuidv5_message_id(self, sample_lora_payload):
        env = normalize(sample_lora_payload, rssi_dbm=-78.0, snr_db=8.4)
        parsed = uuid.UUID(env["message_id"])
        assert parsed.version == 5

    def test_lora_message_id_is_deterministic(self, sample_lora_payload):
        # Two normalize calls with the same seq should yield the same message_id
        # (timestamp is truncated to [:19] in _make_message_id, so we need the
        # same wall-clock second — freeze time by patching datetime)
        from datetime import datetime, timezone
        fixed_ts = datetime(2026, 11, 4, 10, 0, 1, tzinfo=timezone.utc)
        with patch(
            "gateway.telemetry_normalizer.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_ts
            mock_dt.fromisoformat = datetime.fromisoformat
            e1 = normalize(sample_lora_payload)
            e2 = normalize(sample_lora_payload)
        assert e1["message_id"] == e2["message_id"]

    def test_rssi_attached_when_provided(self, sample_lora_payload):
        env = normalize(sample_lora_payload, rssi_dbm=-78.0, snr_db=8.4)
        assert env["rssi_dbm"] == -78.0
        assert env["snr_db"]   == 8.4

    def test_rssi_absent_when_not_provided(self, sample_lora_payload):
        env = normalize(sample_lora_payload)
        assert "rssi_dbm" not in env
        assert "snr_db"   not in env

    def test_lora_protocol_field(self, sample_lora_payload):
        env = normalize(sample_lora_payload)
        assert env["protocol"] == "lora"

    def test_group_code_preserved(self, sample_lora_payload):
        env = normalize(sample_lora_payload)
        assert env["group_code"] == "G1"

    def test_zone_preserved(self, sample_lora_payload):
        env = normalize(sample_lora_payload)
        assert env["zone"] == "Sector_A_Warehouse"


# ===========================================================================
# normalize — Wi-Fi packets
# ===========================================================================

class TestNormalizeWifi:
    def test_wifi_gets_uuid4_message_id(self, sample_wifi_payload):
        """Wi-Fi payloads have no seq → UUID4 is generated."""
        env = normalize(sample_wifi_payload)
        parsed = uuid.UUID(env["message_id"])
        assert parsed.version == 4

    def test_wifi_message_id_changes_each_call(self, sample_wifi_payload):
        e1 = normalize(sample_wifi_payload)
        e2 = normalize(sample_wifi_payload)
        # UUID4 is random — should differ (astronomically unlikely to match)
        assert e1["message_id"] != e2["message_id"]

    def test_no_rssi_on_wifi(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert "rssi_dbm" not in env
        assert "snr_db"   not in env


# ===========================================================================
# normalize — common envelope fields
# ===========================================================================

class TestNormalizeCommon:
    def test_gateway_id_set_from_config(self, sample_wifi_payload):
        with patch.object(config, "GATEWAY_ID", "GW-TEST"):
            env = normalize(sample_wifi_payload)
        assert env["gateway_id"] == "GW-TEST"

    def test_gateway_received_at_is_set(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert env["gateway_received_at"]
        # Must be parseable as ISO 8601
        from datetime import datetime
        datetime.fromisoformat(env["gateway_received_at"])

    def test_device_id_preserved(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert env["device_id"] == "G31"

    def test_firmware_timestamp_preserved(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert env["timestamp"] == "2026-11-04T10:00:00Z"

    def test_metrics_preserved(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert env["metrics"]["temperature_c"] == 22.5
        assert env["metrics"]["humidity"]      == 60.0

    def test_ingress_topic_stored(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload, ingress_topic="env/devices/G31/telemetry")
        assert env["ingress_topic"] == "env/devices/G31/telemetry"

    def test_raw_dict_not_mutated(self, sample_wifi_payload):
        original = dict(sample_wifi_payload)
        normalize(sample_wifi_payload)
        assert sample_wifi_payload == original

    def test_message_id_is_valid_uuid(self, sample_wifi_payload):
        env = normalize(sample_wifi_payload)
        assert UUID_RE.match(env["message_id"])

