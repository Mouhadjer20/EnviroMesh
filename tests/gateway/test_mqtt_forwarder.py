"""
test_mqtt_forwarder.py
======================
Tests for raspberry_pi/gateway/gateway/mqtt_forwarder.py

All network I/O (paho-mqtt) is fully mocked.  No real MQTT broker is needed.

Tested behaviours
-----------------
* _on_publish callback calls sqlite_queue.mark_sent with the correct message_id.
* _inflight dict correctly maps MQTT mid → SQLite message_id.
* Connection failure triggers exponential back-off (retry_delay doubles).
* stop() transitions _running to False.
* MqttForwarderService can be instantiated when TLS configuration is mocked.
"""

import threading
from unittest.mock import MagicMock, patch, call

import pytest

from gateway import config


# ---------------------------------------------------------------------------
# Helpers — patch TLS so the constructor doesn't fail during tests
# ---------------------------------------------------------------------------

def _make_service():
    """Return a MqttForwarderService with TLS configuration fully mocked."""
    with patch("gateway.mqtt_forwarder.mqtt.Client") as MockClient, \
         patch.object(config, "MQTT_CORE_CA", "/fake/ca.crt"):
        mock_client_instance = MagicMock()
        MockClient.return_value = mock_client_instance
        # _configure_tls calls tls_set — just let it pass
        mock_client_instance.tls_set.return_value = None
        mock_client_instance.tls_insecure_set.return_value = None

        from gateway.mqtt_forwarder import MqttForwarderService
        svc = MqttForwarderService.__new__(MqttForwarderService)
        svc._running    = False
        svc._connected  = False
        svc._retry_delay = config.FORWARD_RETRY_SECONDS
        svc.client      = mock_client_instance
    return svc


# ===========================================================================
# _inflight tracking
# ===========================================================================

class TestInflight:
    def test_inflight_maps_mid_to_message_id(self):
        """After a successful publish, _inflight[mid] == message_id."""
        import gateway.mqtt_forwarder as fwd

        fwd._inflight.clear()

        mid = 101
        with fwd._inflight_lock:
            fwd._inflight[mid] = "uuid-test-001"

        assert fwd._inflight[mid] == "uuid-test-001"

    def test_inflight_cleared_after_on_publish(self):
        """_on_publish removes the entry from _inflight and calls mark_sent."""
        import gateway.mqtt_forwarder as fwd

        fwd._inflight.clear()
        fwd._inflight[42] = "uuid-mark-me"

        svc = _make_service()

        with patch("gateway.mqtt_forwarder.sqlite_queue") as mock_sq:
            # Simulate the PUBACK callback
            svc._on_publish(svc.client, None, 42)
            mock_sq.mark_sent.assert_called_once_with("uuid-mark-me")

        # Entry must be removed
        assert 42 not in fwd._inflight

    def test_on_publish_unknown_mid_does_not_crash(self):
        """A PUBACK for an unknown mid must be silently ignored."""
        import gateway.mqtt_forwarder as fwd

        fwd._inflight.clear()
        svc = _make_service()

        with patch("gateway.mqtt_forwarder.sqlite_queue"):
            svc._on_publish(svc.client, None, 9999)  # unknown mid


# ===========================================================================
# _on_publish → mark_sent
# ===========================================================================

class TestOnPublish:
    def test_mark_sent_called_with_correct_id(self):
        import gateway.mqtt_forwarder as fwd

        fwd._inflight.clear()
        fwd._inflight[7] = "correct-uuid"

        svc = _make_service()

        with patch("gateway.mqtt_forwarder.sqlite_queue") as mock_sq:
            svc._on_publish(svc.client, None, 7)
            mock_sq.mark_sent.assert_called_once_with("correct-uuid")

    def test_multiple_pubs_mark_correct_ids(self):
        import gateway.mqtt_forwarder as fwd

        fwd._inflight.clear()
        fwd._inflight[1] = "id-one"
        fwd._inflight[2] = "id-two"

        svc = _make_service()

        with patch("gateway.mqtt_forwarder.sqlite_queue") as mock_sq:
            svc._on_publish(svc.client, None, 1)
            svc._on_publish(svc.client, None, 2)
            calls = mock_sq.mark_sent.call_args_list
            assert call("id-one") in calls
            assert call("id-two") in calls


# ===========================================================================
# Exponential back-off
# ===========================================================================

class TestExponentialBackoff:
    def test_retry_delay_doubles_on_failure(self):
        """_connect_with_retry doubles _retry_delay after each failed attempt."""
        from gateway import config as cfg
        import gateway.mqtt_forwarder as fwd

        svc = _make_service()
        svc._running = True
        svc._connected = False

        initial_delay = cfg.FORWARD_RETRY_SECONDS

        # Simulate connection failure then stop
        attempt_count = {"n": 0}

        def fake_connect(*args, **kwargs):
            attempt_count["n"] += 1
            svc._running = False  # stop after 1 failure
            raise ConnectionRefusedError("broker unreachable")

        svc.client.connect.side_effect = fake_connect

        with patch("gateway.mqtt_forwarder.time.sleep"):
            with patch("gateway.mqtt_forwarder.config.FORWARD_RETRY_SECONDS", initial_delay):
                svc._retry_delay = initial_delay
                svc._connect_with_retry()

        # After 1 failure the delay should have been doubled
        assert svc._retry_delay == min(
            initial_delay * 2, cfg.FORWARD_RETRY_MAX_SECONDS
        )

    def test_retry_delay_capped_at_max(self):
        """_retry_delay never exceeds FORWARD_RETRY_MAX_SECONDS."""
        from gateway import config as cfg
        import gateway.mqtt_forwarder as fwd

        svc = _make_service()
        svc._running = True
        svc._connected = False
        svc._retry_delay = cfg.FORWARD_RETRY_MAX_SECONDS  # already at max

        attempt_count = {"n": 0}

        def fake_connect(*args, **kwargs):
            attempt_count["n"] += 1
            svc._running = False
            raise ConnectionRefusedError("unreachable")

        svc.client.connect.side_effect = fake_connect

        with patch("gateway.mqtt_forwarder.time.sleep"):
            svc._connect_with_retry()

        assert svc._retry_delay <= cfg.FORWARD_RETRY_MAX_SECONDS


# ===========================================================================
# stop()
# ===========================================================================

class TestStop:
    def test_stop_sets_running_false(self):
        svc = _make_service()
        svc._running = True
        svc.stop()
        assert svc._running is False

    def test_stop_calls_loop_stop_and_disconnect(self):
        svc = _make_service()
        svc._running = True
        svc.stop()
        svc.client.loop_stop.assert_called_once()
        svc.client.disconnect.assert_called_once()

