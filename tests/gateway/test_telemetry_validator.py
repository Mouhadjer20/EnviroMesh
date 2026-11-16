"""
test_telemetry_validator.py
===========================
Tests for raspberry_pi/gateway/gateway/telemetry_validator.py

The gateway validator:
  - Requires a bounded, safe ``device_id`` and valid payload structure.
  - If a ``metrics`` key is present, each metric value is range-checked
    against METRIC_RANGES or validated as a boolean/scalar custom metric.
  - Returns True / False — never raises.
"""

import pytest

from gateway.telemetry_validator import validate, METRIC_RANGES, BOOLEAN_METRICS


# ===========================================================================
# Valid payloads
# ===========================================================================

class TestValidPayloads:
    def test_minimal_payload_no_metrics(self):
        """A payload with just device_id and no metrics key is valid."""
        assert validate({"device_id": "G31"}) is True

    def test_payload_with_empty_metrics(self):
        assert validate({"device_id": "G31", "metrics": {}}) is True

    def test_wifi_typical_payload(self):
        assert validate({
            "device_id": "G31",
            "protocol":  "wifi",
            "timestamp": "2026-11-04T10:00:00Z",
            "metrics":   {"temperature_c": 22.5, "humidity": 60.0, "gas_ppm": 150},
        }) is True

    def test_lora_typical_payload(self):
        assert validate({
            "device_id": "G11",
            "protocol":  "lora",
            "seq":       42,
            "metrics":   {"temperature_c": 25.0, "humidity": 55.0},
        }) is True

    def test_temperature_at_lower_bound(self):
        """temperature_c == -40 is exactly at the minimum — must pass."""
        assert validate({"device_id": "X", "metrics": {"temperature_c": -40}}) is True

    def test_temperature_at_upper_bound(self):
        assert validate({"device_id": "X", "metrics": {"temperature_c": 85}}) is True

    def test_humidity_at_bounds(self):
        assert validate({"device_id": "X", "metrics": {"humidity": 0}})   is True
        assert validate({"device_id": "X", "metrics": {"humidity": 100}}) is True

    def test_null_metric_value_is_accepted(self):
        """None metric values (sensor not fitted) must pass."""
        assert validate({"device_id": "G31", "metrics": {"temperature_c": None}}) is True

    def test_unknown_metric_key_is_ignored(self):
        """Scalar custom metrics remain supported."""
        assert validate({"device_id": "G31", "metrics": {"custom_sensor": 9999}}) is True


# ===========================================================================
# Boolean metrics
# ===========================================================================

class TestBooleanMetrics:
    @pytest.mark.parametrize("key", list(BOOLEAN_METRICS))
    def test_boolean_true_accepted(self, key):
        assert validate({"device_id": "G31", "metrics": {key: True}}) is True

    @pytest.mark.parametrize("key", list(BOOLEAN_METRICS))
    def test_boolean_false_accepted(self, key):
        assert validate({"device_id": "G31", "metrics": {key: False}}) is True

    def test_gas_alert_true_accepted(self):
        assert validate({"device_id": "G31", "metrics": {"gas_alert": True}}) is True

    def test_smoke_detected_false_accepted(self):
        assert validate({"device_id": "G31", "metrics": {"smoke_detected": False}}) is True

    @pytest.mark.parametrize("key", list(BOOLEAN_METRICS))
    @pytest.mark.parametrize("value", ["false", 0, 1, [], {}])
    def test_boolean_metric_rejects_non_boolean_values(self, key, value):
        assert validate({"device_id": "G31", "metrics": {key: value}}) is False

    @pytest.mark.parametrize("value", [True, False, 0, 1])
    def test_motion_detected_accepts_firmware_boolean_forms(self, value):
        assert validate({"device_id": "G31", "metrics": {"motion_detected": value}}) is True

    @pytest.mark.parametrize("value", ["true", 2, -1, [], {}])
    def test_motion_detected_rejects_invalid_values(self, value):
        assert validate({"device_id": "G31", "metrics": {"motion_detected": value}}) is False


# ===========================================================================
# Missing / invalid device_id
# ===========================================================================

class TestMissingDeviceId:
    def test_missing_device_id_fails(self):
        assert validate({"metrics": {"temperature_c": 20}}) is False

    def test_empty_string_device_id_fails(self):
        assert validate({"device_id": "", "metrics": {}}) is False

    def test_numeric_device_id_fails(self):
        assert validate({"device_id": 123, "metrics": {}}) is False

    def test_none_device_id_fails(self):
        assert validate({"device_id": None}) is False

    def test_device_id_with_topic_metacharacters_fails(self):
        assert validate({"device_id": "G31/other"}) is False

    def test_overlong_device_id_fails(self):
        assert validate({"device_id": "G" + "1" * 32}) is False


# ===========================================================================
# Out-of-range metrics
# ===========================================================================

class TestOutOfRange:
    def test_temperature_too_high_fails(self):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": 86}}) is False

    def test_temperature_too_low_fails(self):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": -41}}) is False

    def test_humidity_above_100_fails(self):
        assert validate({"device_id": "G31", "metrics": {"humidity": 101}}) is False

    def test_humidity_below_0_fails(self):
        assert validate({"device_id": "G31", "metrics": {"humidity": -1}}) is False

    def test_gas_ppm_above_max_fails(self):
        assert validate({"device_id": "G31", "metrics": {"gas_ppm": 10_001}}) is False

    def test_pressure_too_low_fails(self):
        assert validate({"device_id": "G31", "metrics": {"pressure_hpa": 299}}) is False

    def test_pressure_too_high_fails(self):
        assert validate({"device_id": "G31", "metrics": {"pressure_hpa": 1_101}}) is False


# ===========================================================================
# Invalid JSON types / non-dict input
# ===========================================================================

class TestInvalidTypes:
    def test_non_dict_payload_fails(self):
        assert validate("not a dict") is False

    def test_list_payload_fails(self):
        assert validate([{"device_id": "G31"}]) is False

    def test_metrics_not_a_dict_fails(self):
        assert validate({"device_id": "G31", "metrics": [1, 2, 3]}) is False

    def test_non_numeric_metric_for_numeric_field_fails(self):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": "hot"}}) is False

    def test_non_numeric_humidity_fails(self):
        assert validate({"device_id": "G31", "metrics": {"humidity": "high"}}) is False

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numeric_metric_fails(self, value):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": value}}) is False

    def test_overflowing_numeric_metric_fails(self):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": 10 ** 400}}) is False

    def test_overflowing_custom_metric_fails(self):
        assert validate({"device_id": "G31", "metrics": {"custom_sensor": 10 ** 400}}) is False

    def test_boolean_is_not_accepted_as_numeric_metric(self):
        assert validate({"device_id": "G31", "metrics": {"temperature_c": True}}) is False

    def test_custom_metric_object_fails(self):
        assert validate({"device_id": "G31", "metrics": {"custom_sensor": {"value": 1}}}) is False

    def test_too_many_metrics_fails(self):
        metrics = {f"custom_{index}": index for index in range(65)}
        assert validate({"device_id": "G31", "metrics": metrics}) is False

    def test_non_string_metric_name_fails(self):
        assert validate({"device_id": "G31", "metrics": {1: 2}}) is False

    def test_non_dict_metadata_fails(self):
        assert validate({"device_id": "G31", "metadata": "not-an-object"}) is False
