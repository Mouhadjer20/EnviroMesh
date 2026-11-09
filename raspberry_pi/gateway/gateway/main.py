"""EnviroMesh Gateway main entry point (RPi 1).

Starts all gateway services concurrently:
  1. SQLite queue initialisation
  2. MQTT ingestion service  — subscribes to local EMQX, enqueues Wi-Fi telemetry
  3. LoRa receiver           — reads SX1278 SPI, enqueues LoRa telemetry
  4. MQTT forwarder          — dequeues messages and publishes to RPi 2 over TLS
  5. Health monitor          — periodic queue / status logging

All services run in daemon threads except the forwarder which runs in the main
thread (it is the primary blocking loop).
"""

import signal
import sys
import threading

from dotenv import load_dotenv

load_dotenv()  # load .env before importing config

from . import config
from .logger import configure_root, get_logger
from . import sqlite_queue
from .mqtt_ingestion import MqttIngestionService
from .mqtt_forwarder import MqttForwarderService
from .health_monitor import run as health_monitor_run

configure_root(config.LOG_LEVEL)
logger = get_logger("gateway.main")

# Lazy LoRa import — only needed on RPi hardware
_lora_run = None
try:
    from .lora_receiver import run as _lora_run
except Exception as exc:
    logger.warning("Could not import lora_receiver: %s", exc)


def main() -> None:
    logger.info(
        "Starting EnviroMesh Gateway %s (LAN IP: %s)",
        config.GATEWAY_ID, config.GATEWAY_LAN_IP,
    )

    # Initialise the SQLite queue
    sqlite_queue.init_db()

    # --- Services ---
    ingestion = MqttIngestionService()
    forwarder = MqttForwarderService()
    stop_event = threading.Event()

    # Graceful shutdown handler
    def _shutdown(signum, frame):
        logger.info("Shutdown signal received (%s)", signum)
        stop_event.set()
        ingestion.stop()
        forwarder.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    # MQTT ingestion in background thread
    ingestion_thread = threading.Thread(
        target=ingestion.start, name="mqtt-ingestion", daemon=True
    )
    ingestion_thread.start()

    # LoRa receiver in background thread (disabled on GW2 or when ENABLE_LORA=false)
    if config.ENABLE_LORA and _lora_run is not None:
        lora_thread = threading.Thread(
            target=_lora_run, name="lora-receiver", daemon=True
        )
        lora_thread.start()
        logger.info("LoRa receiver thread started")
    else:
        logger.info("LoRa receiver disabled (ENABLE_LORA=%s)", config.ENABLE_LORA)

    # Health monitor in background thread
    monitor_thread = threading.Thread(
        target=health_monitor_run,
        kwargs={"stop_event": stop_event},
        name="health-monitor",
        daemon=True,
    )
    monitor_thread.start()

    # MQTT forwarder blocks in main thread
    logger.info("Starting MQTT forwarder (blocks in main thread)")
    forwarder.run()


if __name__ == "__main__":
    main()

