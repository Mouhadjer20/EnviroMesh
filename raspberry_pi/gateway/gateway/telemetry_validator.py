"""Telemetry validator for the EnviroMesh Gateway (RPi 1).

Adapted from raspberry_pi/backend/services/telemetry_validator.py.

Validates raw ESP32 payloads before they are enqueued for forwarding.
The validator intentionally accepts boolean fields (gas_alert, smoke_detected,
water_leak_detected, motion_detected) without numeric range checking.

Metric numeric ranges mirror the central validator so that the gateway can
drop obviously bad readings early and reduce unnecessary forwarding load.
"""

import logging
from typing import Union

logger = logging.getLogger("gateway.telemetry_validator")

# Numeric metric ranges — (min_inclusive, max_inclusive)
METRIC_RANGES: dict = {
    "gas_ppm":         (0, 10_000),
    "gas_adc_raw":     (0, 4_095),
    "water_adc_raw":   (0, 4_095),
    "temperature_c":   (-40, 85),
    "humidity":        (0, 100),
    "humidity_pct":    (0, 100),
    "pressure_hpa":    (300, 1_100),
    "water_leak":      (0, 1),
    "motion_detected": (0, 1),
    # rssi / snr are metadata, not metrics — validated separately
}

# Metric keys that are boolean flags — not range-checked
BOOLEAN_METRICS = {
    "gas_alert",
    "smoke_detected",
    "water_leak_detected",
    "motion_detected",
}


def validate(telemetry: dict) -> bool:
    """Return True if *telemetry* is structurally valid and in-range.

    Accepts both flat payloads and the normalised gateway envelope.
    """
    if not isinstance(telemetry, dict):
        logger.warning("Validation failed: payload is not a dict")
        return False

    device_id = telemetry.get("device_id")
    if not device_id or not isinstance(device_id, str):
        logger.warning("Validation failed: missing or invalid device_id")
        return False

    metrics = telemetry.get("metrics")
    if metrics is None:
        # Accept payloads without metrics (e.g. status-only messages)
        return True
    if not isinstance(metrics, dict):
        logger.warning("Validation failed: 'metrics' is not a dict for device %s", device_id)
        return False

    for key, value in metrics.items():
        if value is None:
            continue  # null metrics are acceptable (sensor not fitted / read error)
        if key in BOOLEAN_METRICS:
            continue  # booleans skip numeric range check
        if key in METRIC_RANGES:
            low, high = METRIC_RANGES[key]
            try:
                num = float(value)
            except (ValueError, TypeError):
                logger.warning(
                    "Metric '%s' has non-numeric value '%s' for device %s",
                    key, value, device_id,
                )
                return False
            if not (low <= num <= high):
                logger.warning(
                    "Metric '%s'=%s out of range [%s, %s] for device %s",
                    key, value, low, high, device_id,
                )
                return False

    return True

