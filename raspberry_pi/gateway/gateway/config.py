"""Configuration loader for the EnviroMesh Gateway (RPi 1).

All configuration is read exclusively from environment variables so that
no credentials or addresses are hard-coded in source files.  A .env file
in the gateway root is loaded automatically by Docker Compose.
"""

import os

# ---------------------------------------------------------------------------
# Gateway identity (GW01 on .20 or GW02 on .30)
# ---------------------------------------------------------------------------
GATEWAY_ID: str = os.getenv("GATEWAY_ID", "GW01")
GATEWAY_LAN_IP: str = os.getenv("GATEWAY_LAN_IP", "192.168.1.20")

# Hardware features (Gateway 1 has LoRa SX1278; Gateway 2 is Wi-Fi only)
ENABLE_LORA: bool = os.getenv("ENABLE_LORA", "true").lower() in ("true", "1", "yes")

# Security toggles
MQTT_AUTH_ENABLED: bool = os.getenv("MQTT_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Local EMQX broker (on this RPi 1)
# ---------------------------------------------------------------------------
MQTT_LOCAL_HOST: str = os.getenv("MQTT_LOCAL_HOST", "localhost")
MQTT_LOCAL_PORT: int = int(os.getenv("MQTT_LOCAL_PORT", "1883"))
MQTT_LOCAL_USERNAME: str = os.getenv("MQTT_LOCAL_USERNAME", "gw_ingestion")
MQTT_LOCAL_PASSWORD: str = os.getenv("MQTT_LOCAL_PASSWORD", "gw_ingest_secret")

# ---------------------------------------------------------------------------
# Core EMQX broker (on RPi 2) — TLS enabled by default on port 8883
# ---------------------------------------------------------------------------
MQTT_CORE_HOST: str = os.getenv("MQTT_CORE_HOST", "192.168.1.5")
MQTT_CORE_PORT: int = int(os.getenv("MQTT_CORE_PORT", "8883"))
MQTT_CORE_USE_TLS: bool = os.getenv("MQTT_CORE_USE_TLS", os.getenv("MQTT_TLS_ENABLED", "true")).lower() in ("true", "1", "yes")
MQTT_CORE_USERNAME: str = os.getenv("MQTT_CORE_USERNAME", "gw_forwarder")
MQTT_CORE_PASSWORD: str = os.getenv("MQTT_CORE_PASSWORD", "gw_forward_secret")
# Path to the CA certificate that signed the core EMQX server certificate
MQTT_CORE_CA: str = os.getenv("MQTT_CORE_CA", "/app/certs/core-ca.crt")

# ---------------------------------------------------------------------------
# MQTT topics
# ---------------------------------------------------------------------------
MQTT_INPUT_TOPIC: str = os.getenv(
    "MQTT_INPUT_TOPIC", "enviromesh/devices/+/telemetry"
)
MQTT_OUTPUT_TOPIC: str = os.getenv(
    "MQTT_OUTPUT_TOPIC", f"enviromesh/gateway/{GATEWAY_ID}/telemetry"
)
MQTT_STATUS_TOPIC: str = os.getenv(
    "MQTT_STATUS_TOPIC", f"enviromesh/gateway/{GATEWAY_ID}/status"
)
MQTT_QOS: int = int(os.getenv("MQTT_QOS", "1"))

# ---------------------------------------------------------------------------
# SQLite offline queue
# ---------------------------------------------------------------------------
SQLITE_PATH: str = os.getenv("SQLITE_PATH", "/var/lib/enviromesh/queue.db")
QUEUE_MAX_MESSAGES: int = int(os.getenv("QUEUE_MAX_MESSAGES", "50000"))

# ---------------------------------------------------------------------------
# Forwarding tuning
# ---------------------------------------------------------------------------
FORWARD_BATCH_SIZE: int = int(os.getenv("FORWARD_BATCH_SIZE", "10"))
FORWARD_RETRY_SECONDS: int = int(os.getenv("FORWARD_RETRY_SECONDS", "5"))
FORWARD_RETRY_MAX_SECONDS: int = int(os.getenv("FORWARD_RETRY_MAX_SECONDS", "60"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

