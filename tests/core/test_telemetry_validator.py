import pytest

from services.telemetry_validator import validate


@pytest.mark.parametrize(
    "telemetry",
    [
        {"device_id": "G31/other"},
        {"device_id": "G" + "1" * 32},
        {"device_id": "G31", "metrics": {"temperature_c": True}},
        {"device_id": "G31", "metrics": {"temperature_c": float("nan")}},
        {"device_id": "G31", "metrics": {"temperature_c": float("inf")}},
        {"device_id": "G31", "metrics": {"temperature_c": 10 ** 400}},
        {"device_id": "G31", "metrics": {"custom_sensor": 10 ** 400}},
        {"device_id": "G31", "metrics": {"motion_detected": 2}},
        {"device_id": "G31", "metrics": {"custom_sensor": {"value": 1}}},
        {"device_id": "G31", "metrics": {f"custom_{i}": i for i in range(65)}},
        {"device_id": "G31", "metrics": {1: 2}},
    ],
)
def test_rejects_malformed_or_unsafe_telemetry(telemetry):
    assert validate(telemetry) is False


@pytest.mark.parametrize(
    "telemetry",
    [
        {"device_id": "G31", "metrics": {"temperature_c": 22.5}},
        {"device_id": "G11", "metrics": {"humidity_pct": "55.0"}},
        {"device_id": "G43", "metrics": {"motion_detected": 0}},
        {"device_id": "G31", "metrics": {"custom_sensor": 9999}},
    ],
)
def test_accepts_valid_telemetry(telemetry):
    assert validate(telemetry) is True
