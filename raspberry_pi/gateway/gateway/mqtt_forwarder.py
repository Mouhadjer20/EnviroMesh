"""MQTT forwarding service for the EnviroMesh Gateway (RPi 1).

Dequeues batches of messages from the SQLite offline queue and publishes them
to RPi 2's central EMQX broker over MQTT with TLS (port 8883).

Reliability guarantees:
  - Messages are never deleted from the queue before receiving a PUBACK
    (paho mqtt QoS 1 on_publish callback).
  - Exponential back-off on connection failure (5 s → 60 s max).
  - Reconnect loop runs indefinitely so the gateway survives RPi 2 reboots.
"""

import json
import ssl
import time
import threading
from typing import Dict

import paho.mqtt.client as mqtt

from .logger import get_logger
from . import sqlite_queue, config

logger = get_logger("gateway.mqtt_forwarder")

# Map mid (MQTT message ID) → SQLite message_id so on_publish can mark_sent
_inflight: Dict[int, str] = {}
_inflight_lock = threading.Lock()


class MqttForwarderService:
    """Publish queued messages to the core EMQX broker with TLS."""

    def __init__(self) -> None:
        self._running    = False
        self._connected  = False
        self._retry_delay = config.FORWARD_RETRY_SECONDS
        # TODO(ISSUE-005): Switch to persistent session (clean_session=False) so that
        # QoS 1 messages published while the gateway is restarting are not lost.
        # Also set session_expiry_interval when upgrading to MQTT v5.
        # See: docs/maintenance-and-known-issues.md ISSUE-005
        self.client       = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"gw-forwarder-{config.GATEWAY_ID}",
            clean_session=True,
        )
        self._configure_tls()
        if config.MQTT_CORE_USERNAME:
            self.client.username_pw_set(
                config.MQTT_CORE_USERNAME, config.MQTT_CORE_PASSWORD or None
            )
        # Will message — lets RPi 2 detect gateway disconnect
        self.client.will_set(
            config.MQTT_STATUS_TOPIC,
            payload=json.dumps({"gateway_id": config.GATEWAY_ID, "status": "offline"}),
            qos=1,
            retain=True,
        )
        self.client.on_connect    = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish    = self._on_publish

    def _configure_tls(self) -> None:
        use_tls = getattr(config, "MQTT_CORE_USE_TLS", True)
        if not use_tls or config.MQTT_CORE_PORT == 1883:
            logger.info("Core MQTT TLS disabled (plain connection mode on port %d)", config.MQTT_CORE_PORT)
            return

        try:
            self.client.tls_set(
                ca_certs   = config.MQTT_CORE_CA,
                tls_version= ssl.PROTOCOL_TLS_CLIENT,
            )
            # Server name verification — must match the CN in the server cert
            self.client.tls_insecure_set(False)
            logger.info("TLS configured with CA: %s", config.MQTT_CORE_CA)
        except (FileNotFoundError, ssl.SSLError) as exc:
            logger.error(
                "TLS configuration failed: %s. "
                "Copy ca.crt to %s before starting the forwarder (or set MQTT_CORE_USE_TLS=false for local testing).",
                exc, config.MQTT_CORE_CA,
            )
            raise

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._connected  = True
            self._retry_delay = config.FORWARD_RETRY_SECONDS
            logger.info(
                "Forwarder connected to core EMQX %s:%d",
                config.MQTT_CORE_HOST, config.MQTT_CORE_PORT,
            )
            # Publish online status (retained)
            client.publish(
                config.MQTT_STATUS_TOPIC,
                payload=json.dumps({
                    "gateway_id": config.GATEWAY_ID,
                    "status": "online",
                    "queue_pending": sqlite_queue.pending_count(),
                }),
                qos=1,
                retain=True,
            )
        else:
            self._connected = False
            logger.error(
                "Forwarder connect to core EMQX failed: reason_code=%s", reason_code
            )

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        self._connected = False
        if reason_code != 0:
            logger.warning("Forwarder disconnected unexpectedly (reason=%s)", reason_code)
        else:
            logger.info("Forwarder disconnected cleanly")

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        """Called when the broker acknowledges a QoS 1 publish (PUBACK)."""
        with _inflight_lock:
            message_id = _inflight.pop(mid, None)
        if message_id:
            sqlite_queue.mark_sent(message_id)
            logger.debug("PUBACK received, dequeued message_id=%s mid=%d", message_id, mid)

    # ------------------------------------------------------------------
    # Forward loop
    # ------------------------------------------------------------------

    def _connect_with_retry(self) -> None:
        while self._running and not self._connected:
            try:
                self.client.connect(
                    config.MQTT_CORE_HOST,
                    config.MQTT_CORE_PORT,
                    keepalive=60,
                )
                self.client.loop_start()
                # Wait up to 10 s for on_connect to set _connected
                for _ in range(100):
                    if self._connected:
                        break
                    time.sleep(0.1)
                if not self._connected:
                    raise ConnectionError("Timed out waiting for on_connect")
            except Exception as exc:
                logger.warning(
                    "Cannot reach core EMQX (%s:%d): %s — retrying in %ds",
                    config.MQTT_CORE_HOST, config.MQTT_CORE_PORT,
                    exc, self._retry_delay,
                )
                time.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, config.FORWARD_RETRY_MAX_SECONDS)

    def _forward_batch(self) -> int:
        """Publish one batch of queued messages.  Returns number published."""
        rows = sqlite_queue.get_batch(config.FORWARD_BATCH_SIZE)
        published = 0
        for row in rows:
            msg_info = self.client.publish(
                row["topic"],
                payload=row["payload"],
                qos=config.MQTT_QOS,
            )
            if msg_info.rc == mqtt.MQTT_ERR_SUCCESS:
                with _inflight_lock:
                    _inflight[msg_info.mid] = row["message_id"]
                published += 1
            else:
                sqlite_queue.mark_attempt(row["message_id"])
                logger.warning(
                    "Publish failed for message_id=%s rc=%d",
                    row["message_id"], msg_info.rc,
                )
        return published

    def run(self) -> None:
        """Block and continuously forward queued messages to RPi 2."""
        self._running = True
        logger.info(
            "MQTT forwarder starting — target: %s:%d (TLS)",
            config.MQTT_CORE_HOST, config.MQTT_CORE_PORT,
        )
        while self._running:
            if not self._connected:
                self._connect_with_retry()
                continue

            pending = sqlite_queue.pending_count()
            if pending == 0:
                time.sleep(config.FORWARD_RETRY_SECONDS)
                continue

            try:
                published = self._forward_batch()
                if published > 0:
                    logger.debug("Forwarded %d/%d messages", published, pending)
            except Exception as exc:
                logger.error("Forwarding error: %s", exc)
                time.sleep(config.FORWARD_RETRY_SECONDS)

            # Small sleep to avoid busy-loop when queue drains
            time.sleep(0.1)

    def stop(self) -> None:
        """Stop the forwarding loop and disconnect cleanly."""
        self._running = False
        try:
            self.client.loop_stop()
        except Exception:
            pass
        try:
            self.client.disconnect()
        except Exception:
            pass
        logger.info("MQTT forwarder stopped")

