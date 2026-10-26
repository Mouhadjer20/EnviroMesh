"""Telemetry validation for RPi (Core Processing Server).

Validates incoming telemetry payloads against schema and range constraints
before they are written to TimescaleDB.
"""

import logging

logger = logging.getLogger("telemetry_validator")

# Expected metric keys and their valid ranges
METRIC_RANGES = {
    "gas_ppm": (0, 10000),
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
    if not device_id:
        logger.warning("Invalid telemetry: missing device_id")
        return False

    metrics = telemetry.get("metrics", {})
    if not isinstance(metrics, dict):
        logger.warning("Invalid telemetry: metrics is not a dict")
        return False

    for metric, value in metrics.items():
        if value is None:
            continue
        if metric in METRIC_RANGES:
            low, high = METRIC_RANGES[metric]
            try:
                numeric_val = float(value)
            except (ValueError, TypeError):
                logger.warning("Metric %s has non-numeric value: %s", metric, value)
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

    return True