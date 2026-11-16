"""Telemetry validator for the EnviroMesh Gateway (RPi 1).

Adapted from raspberry_pi/backend/services/telemetry_validator.py.

Validates raw ESP32 payloads before they are enqueued for forwarding.
The validator intentionally accepts boolean fields (gas_alert, smoke_detected,
water_leak_detected, motion_detected) without numeric range checking.

Metric numeric ranges mirror the central validator so that the gateway can
drop obviously bad readings early and reduce unnecessary forwarding load.
"""

import logging
import math
import re

logger = logging.getLogger("gateway.telemetry_validator")

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
MAX_METRICS = 64
MAX_METRIC_NAME_LENGTH = 64
MAX_METRIC_STRING_LENGTH = 128

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
}


def validate(telemetry: dict) -> bool:
    """Return True if *telemetry* is structurally valid and in-range.

    Accepts both flat payloads and the normalised gateway envelope.
    """
    if not isinstance(telemetry, dict):
        logger.warning("Validation failed: payload is not a dict")
        return False

    device_id = telemetry.get("device_id")
    if not isinstance(device_id, str) or not DEVICE_ID_PATTERN.fullmatch(device_id):
        logger.warning("Validation failed: missing or invalid device_id")
        return False

    metadata = telemetry.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        logger.warning("Validation failed: 'metadata' is not a dict for device %s", device_id)
        return False

    metrics = telemetry.get("metrics")
    if metrics is None:
        # Accept payloads without metrics (e.g. status-only messages)
        return True
    if not isinstance(metrics, dict):
        logger.warning("Validation failed: 'metrics' is not a dict for device %s", device_id)
        return False
    if len(metrics) > MAX_METRICS:
        logger.warning("Validation failed: too many metrics for device %s", device_id)
        return False

    for key, value in metrics.items():
        if not isinstance(key, str) or not key or len(key) > MAX_METRIC_NAME_LENGTH:
            logger.warning("Validation failed: invalid metric name for device %s", device_id)
            return False
        if value is None:
            continue  # null metrics are acceptable (sensor not fitted / read error)
        if key in BOOLEAN_METRICS:
            if not isinstance(value, bool):
                logger.warning("Metric '%s' must be a boolean for device %s", key, device_id)
                return False
            continue
        if key == "motion_detected":
            # Firmware versions emit either JSON booleans or 0/1 integers.
            if not isinstance(value, bool) and (
                not isinstance(value, int) or value not in (0, 1)
            ):
                logger.warning("Metric '%s' must be boolean or 0/1 for device %s", key, device_id)
                return False
            continue
        if key in METRIC_RANGES:
            low, high = METRIC_RANGES[key]
            if isinstance(value, bool) or (
                isinstance(value, str) and len(value) > MAX_METRIC_STRING_LENGTH
            ):
                logger.warning("Metric '%s' has invalid numeric value for device %s", key, device_id)
                return False
            try:
                num = float(value)
            except (ValueError, TypeError, OverflowError):
                logger.warning(
                    "Metric '%s' has non-numeric value '%s' for device %s",
                    key, value, device_id,
                )
                return False
            if not math.isfinite(num):
                logger.warning("Metric '%s' is not finite for device %s", key, device_id)
                return False
            if not (low <= num <= high):
                logger.warning(
                    "Metric '%s'=%s out of range [%s, %s] for device %s",
                    key, value, low, high, device_id,
                )
                return False
        elif not isinstance(value, (str, int, float, bool)):
            logger.warning("Custom metric '%s' must be a scalar for device %s", key, device_id)
            return False
        elif isinstance(value, str) and len(value) > MAX_METRIC_STRING_LENGTH:
            logger.warning("Custom metric '%s' is too long for device %s", key, device_id)
            return False
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                logger.warning("Custom metric '%s' is not finite for device %s", key, device_id)
                return False

    return True
