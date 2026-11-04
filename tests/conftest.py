"""
conftest.py — shared pytest fixtures for the EnviroMesh test suite.

Adds the gateway and core backend packages to sys.path so tests can
import them without installing the packages.
"""

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Path setup — make gateway and core importable from the project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_GATEWAY_PKG  = os.path.join(_PROJECT_ROOT, "raspberry_pi", "gateway")
_CORE_PKG     = os.path.join(_PROJECT_ROOT, "raspberry_pi", "core", "backend")

for _p in (_GATEWAY_PKG, _CORE_PKG):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db(tmp_path):
    """Provide a temporary SQLite database file path (unique per test)."""
    return str(tmp_path / "test_queue.db")


@pytest.fixture
def sample_wifi_payload():
    """Minimal valid Wi-Fi ESP32 payload (flat, no seq number)."""
    return {
        "device_id": "G31",
        "protocol":  "wifi",
        "timestamp": "2026-11-04T10:00:00Z",
        "metrics": {
            "temperature_c": 22.5,
            "humidity":      60.0,
            "gas_ppm":       150,
        },
    }


@pytest.fixture
def sample_lora_payload():
    """Minimal valid LoRa ESP32 payload (includes seq number)."""
    return {
        "device_id":  "G11",
        "protocol":   "lora",
        "seq":        42,
        "group_code": "G1",
        "zone":       "Sector_A_Warehouse",
        "timestamp":  "2026-11-04T10:00:00Z",
        "metrics": {
            "temperature_c": 25.0,
            "humidity":      55.0,
            "gas_ppm":       200,
        },
    }


@pytest.fixture
def valid_telemetry_dict():
    """Full normalised gateway envelope suitable for validator / writer tests."""
    return {
        "message_id":          "test-msg-001",
        "device_id":           "G31",
        "protocol":            "wifi",
        "timestamp":           "2026-11-04T10:00:00Z",
        "gateway_id":          "GW01",
        "gateway_received_at": "2026-11-04T10:00:01Z",
        "ingress_topic":       "enviromesh/devices/G31/telemetry",
        "metrics": {
            "temperature_c": 22.5,
            "humidity":      60.0,
        },
    }

