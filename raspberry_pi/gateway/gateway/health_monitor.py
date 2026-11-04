"""Health monitor for the EnviroMesh Gateway (RPi 1).

Periodically logs queue depth, pending message age, and connection status.
Can be run in a background thread alongside the ingestion and forwarding loops.
"""

import time
import threading
from datetime import datetime, timezone

from .logger import get_logger
from . import sqlite_queue, config

logger = get_logger("gateway.health_monitor")

_INTERVAL_SECONDS = 60  # log health every minute


def _health_report() -> dict:
    """Collect current gateway health metrics."""
    pending   = sqlite_queue.pending_count()
    oldest_s  = sqlite_queue.oldest_pending_age_s()

    report = {
        "gateway_id":   config.GATEWAY_ID,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "queue_pending": pending,
        "queue_max":     config.QUEUE_MAX_MESSAGES,
        "queue_usage_pct": round(100.0 * pending / config.QUEUE_MAX_MESSAGES, 1),
        "oldest_pending_age_s": round(oldest_s, 1) if oldest_s is not None else None,
    }
    return report


def run(stop_event: threading.Event = None) -> None:
    """Run the health monitor loop until *stop_event* is set (or forever)."""
    logger.info("Health monitor started (interval=%ds)", _INTERVAL_SECONDS)
    while stop_event is None or not stop_event.is_set():
        try:
            report = _health_report()
            level = "WARNING" if report["queue_usage_pct"] > 80 else "INFO"
            getattr(logger, level.lower())(
                "Gateway health: queue=%d/%d (%.1f%%) oldest=%s",
                report["queue_pending"],
                report["queue_max"],
                report["queue_usage_pct"],
                f"{report['oldest_pending_age_s']:.0f}s"
                if report["oldest_pending_age_s"] is not None
                else "N/A",
            )
        except Exception as exc:
            logger.warning("Health monitor error: %s", exc)

        time.sleep(_INTERVAL_SECONDS)
    logger.info("Health monitor stopped")

