# EnviroMesh — Automated Test Suite

This directory contains the automated test suite for the EnviroMesh project, covering the RPi 1 Gateway edge layer, RPi 2 Core backend, and integration pipeline.

---

## Directory Organization

```text
tests/
├── conftest.py                       # Global test fixtures (mock DB, sample sensor payloads)
├── gateway/
│   ├── test_sqlite_queue.py          # SQLite WAL queue operations, rowcount deduplication, buffer capacity
│   ├── test_telemetry_validator.py   # Ingress payload bounds checking & required field validation
│   ├── test_telemetry_normalizer.py  # UUIDv5/UUID4 generation, timestamping, gateway metadata enrichment
│   └── test_mqtt_forwarder.py        # QoS 1 publishing, PUBACK tracking, exponential backoff
├── core/
│   └── test_database_writer.py       # Deduplication using processed_messages & TimescaleDB writes
├── integration/
│   ├── test_pipeline_simulation.py   # Full simulated path: ESP32 -> Gateway -> SQLite -> Core Writer
│   └── test_offline_buffering.py     # Core outage simulation: queue accumulation & recovery drain
└── README.md                         # This file
```

---

## Prerequisites

Install test dependencies into your Python virtual environment:

```bash
pip install pytest paho-mqtt
```

---

## Running Tests

### Run all tests
```bash
python3 -m pytest tests/ -v
```

### Run by component
```bash
# Gateway unit tests only
python3 -m pytest tests/gateway/ -v

# Core unit tests only
python3 -m pytest tests/core/ -v

# Integration tests only
python3 -m pytest tests/integration/ -v
```

### Run by marker
```bash
# Run only software simulation tests (excluding hardware)
python3 -m pytest tests/ -m "not hardware" -v
```

---

## Test Verification Scope

| Category | Coverage | Real Hardware Needed? |
|---|---|---|
| **SQLite Queue Logic** | Full CRUD, capacity limits, deduplication via `rowcount` | No (in-memory / temp files) |
| **Telemetry Validation** | Min/max bounds, missing keys, datatype checking | No |
| **Envelope Normalization**| Message ID hashing, metadata injection | No |
| **MQTT Forwarder Logic** | In-flight tracking, backoff delay calculation, PUBACK handling | No (mocked broker) |
| **Deduplication Engine** | `processed_messages` conflict handling | No (mocked DB connection) |
| **LoRa SX1278 SPI Radio** | Physical radio reception & signal registers | **Yes** (Requires physical Pi + SX1278) |
| **Live Network TLS** | Actual TLS handshake over Wi-Fi/Ethernet | **Yes** (Requires running EMQX brokers) |

