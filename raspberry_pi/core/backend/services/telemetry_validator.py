"""Telemetry validation for RPi (Core Processing Server).

Validates incoming telemetry payloads against schema and range constraints
before they are written to TimescaleDB.
"""

import logging
import math
import re

logger = logging.getLogger("telemetry_validator")

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
MAX_METRICS = 64
MAX_METRIC_NAME_LENGTH = 64
MAX_METRIC_STRING_LENGTH = 128

# Expected metric keys and their valid ranges
METRIC_RANGES = {
    "gas_ppm": (0, 10000),
    "gas_adc_raw": (0, 4095),
    "water_adc_raw": (0, 4095),
    "temperature_c": (-40, 85),
    "humidity": (0, 100),
    "humidity_pct": (0, 100),
    "pressure_hpa": (300, 1100),
    "water_leak": (0, 1),
    "motion_detected": (0, 1),
}


def validate(telemetry: dict) -> bool:
    """Return True if the telemetry payload is valid, False otherwise."""
    if not isinstance(telemetry, dict):
        logger.warning("Invalid telemetry: not a dict")
        return False

    device_id = telemetry.get("device_id")
    if not isinstance(device_id, str) or not DEVICE_ID_PATTERN.fullmatch(device_id):
        logger.warning("Invalid telemetry: missing or invalid device_id")
        return False

    metrics = telemetry.get("metrics", {})
    if not isinstance(metrics, dict):
        logger.warning("Invalid telemetry: metrics is not a dict")
        return False
    if len(metrics) > MAX_METRICS:
        logger.warning("Invalid telemetry: too many metrics")
        return False

    for metric, value in metrics.items():
        if (
            not isinstance(metric, str)
            or not metric
            or len(metric) > MAX_METRIC_NAME_LENGTH
        ):
            logger.warning("Invalid telemetry: invalid metric name")
            return False
        if value is None:
            continue
        if metric == "motion_detected":
            if not isinstance(value, bool) and (
                not isinstance(value, int) or value not in (0, 1)
            ):
                logger.warning("Metric %s must be boolean or 0/1", metric)
                return False
            continue
        if metric in METRIC_RANGES:
            low, high = METRIC_RANGES[metric]
            if isinstance(value, bool) or (
                isinstance(value, str) and len(value) > MAX_METRIC_STRING_LENGTH
            ):
                logger.warning("Metric %s has invalid numeric value", metric)
                return False
            try:
                numeric_val = float(value)
            except (ValueError, TypeError, OverflowError):
                logger.warning("Metric %s has non-numeric value: %s", metric, value                )
                return False
            if not math.isfinite(numeric_val):
                logger.warning("Metric %s is not finite", metric                )
                return False
            if not math.isfinite(numeric_val):
                logger.warning("Metric %s is not finite", metric)
                return False
            if not (low <= numeric_val <= high):
                logger.warning(
                    "Metric %s out of range: %s (expected %s-%s)",
                    metric,
                    value,
                    low,
                    high,
                )
                return False
        elif not isinstance(value, (str, int, float, bool)):
            logger.warning("Custom metric %s must be a scalar", metric)
            return False
        elif isinstance(value, str) and len(value) > MAX_METRIC_STRING_LENGTH:
            logger.warning("Custom metric %s is too long", metric)
            return False
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                logger.warning("Custom metric %s is not finite", metric)
                return False

    return True