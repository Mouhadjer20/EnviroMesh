# Backend — EnviroMesh Core Processing Server

The EnviroMesh backend is a **FastAPI** application and concurrent ingestion daemon running on the Raspberry Pi (or containerized in Docker). It processes incoming sensor telemetry from both **MQTT (EMQX)** and an **SX1278 LoRa radio**, validates each payload, persists readings to **TimescaleDB**, and exposes REST endpoints for devices, historical telemetry, alerts, and users.

---

## Table of Contents

- [1. Architecture & Telemetry Pipeline](#1-architecture--telemetry-pipeline)
- [2. Directory Layout & Source Code Map](#2-directory-layout--source-code-map)
- [3. Services Deep Dive](#3-services-deep-dive)
  - [3.1. MQTT Subscriber](#31-mqtt-subscriber-servicesmqtt_subscriberpy)
  - [3.2. LoRa Receiver](#32-lora-receiver-serviceslora_receiverpy)
  - [3.3. Telemetry Validator](#33-telemetry-validator-servicestelemetry_validatorpy)
  - [3.4. Database Writer](#34-database-writer-servicesdatabase_writerpy)
- [4. API Routes Overview](#4-api-routes-overview)
- [5. Running the Backend](#5-running-the-backend)
  - [Method 1: Via Docker Compose (Recommended)](#method-1-via-docker-compose-recommended)
  - [Method 2: Native Local Development](#method-2-native-local-development)
- [6. Implementation Roadmap (Phase 4 Tasks)](#6-implementation-roadmap-phase-4-tasks)
  - [1. Database Query Implementation in Routes](#1-database-query-implementation-in-routes)
  - [2. Authentication & Authorization](#2-authentication--authorization-backendauth)
  - [3. Real-Time WebSocket Streaming](#3-real-time-websocket-streaming)
- [7. Related Documentation](#7-related-documentation)

---

## 1. Architecture & Telemetry Pipeline

```
ESP32 Sensor Nodes (Wi-Fi / LoRa)
        │
        ├──► LoRa 433 MHz (SX1278) ──► services/lora_receiver.py (Daemon Thread)
        │                                        │
        │                                        ├──► raw_sensor_packets (All raw bytes)
        │                                        │
        │                                        ▼
        │                                   services/telemetry_validator.py
        │                                        │ (Valid JSON & Ranges)
        │                                        ▼
        │                                   services/database_writer.py
        │                                        │
        │                                        ▼
        │                                   TimescaleDB (sensor_telemetry)
        │
        └──► Wi-Fi MQTT (EMQX) ────► services/mqtt_subscriber.py (Main Thread)
                                                 │
                                                 ▼
                                            services/telemetry_validator.py
                                                 │
                                                 ▼
                                            services/database_writer.py
                                                 │
                                                 ▼
                                            TimescaleDB (sensor_telemetry)
```

---

## 2. Directory Layout & Source Code Map

```
raspberry_pi/backend/
├── main.py                       # Application entry point: FastAPI app + threads
├── requirements.txt              # Production Python dependencies
├── Dockerfile                    # Multi-stage container build (python:3.11-slim)
├── .env                          # Local environment configuration
│
├── routes/                       # FastAPI Route Handlers
│   ├── __init__.py               # Package initializer
│   ├── devices.py                # CRUD operations for physical edge nodes
│   ├── telemetry.py              # Time-series queries and latest device readings
│   ├── alerts.py                 # Alert management & acknowledgment [Phase 4]
│   └── users.py                  # User management & technician accounts [Phase 4]
│
├── services/                     # Ingestion & Persistence Core
│   ├── __init__.py               # Package initializer
│   ├── mqtt_subscriber.py        # Paho-MQTT v2 client; subscribes, decodes, persists
│   ├── lora_receiver.py          # SX1278 SPI driver: polls IRQ, reads FIFO, persists
│   ├── telemetry_validator.py    # Enforces metric types and valid ranges
│   └── database_writer.py        # TimescaleDB hypertable writer via psycopg2
│
└── auth/                         # Authentication & RBAC Architecture
    └── README.md                 # Specifications for JWT, bcrypt, and zone-scoped claims
```

---

## 3. Services Deep Dive

### 3.1. MQTT Subscriber (`services/mqtt_subscriber.py`)
- Uses `paho-mqtt` (Callback API v2) connecting to the broker configured via `MQTT_HOST` and `MQTT_PORT`.
- Subscribes to topic pattern `enviromesh/devices/+/telemetry` (or `TOPIC_PREFIX`).
- Callback flow:
  1. Decodes incoming UTF-8 payload and parses JSON.
  2. Calls `telemetry_validator.validate(payload)`.
  3. If valid, invokes `database_writer.write_telemetry(payload)`.

### 3.2. LoRa Receiver (`services/lora_receiver.py`)
- Interfaces with the **SX1278** radio over SPI (`spidev` bus 0, device 0, max 100 kHz) and `RPi.GPIO`.
- Radio settings: Carrier `433 MHz`, SF `7`, BW `125 kHz`, CR `4/5`, explicit header, preamble 8.
- Continuous loop polls `REG_IRQ_FLAGS` for `IRQ_RX_DONE`:
  1. Reads packet bytes from `REG_FIFO`.
  2. Always writes raw payload to `raw_sensor_packets` hypertable (enables forensic diagnostics).
  3. Parses JSON and validates metrics.
  4. Persists structured data to `sensor_telemetry`.

> [!NOTE]
> `spidev` and `RPi.GPIO` require physical Raspberry Pi hardware. When developing on macOS, Windows, or cloud environments, use our test harnesses:
> - [`../../scripts/simulate_telemetry.py`](../../scripts/simulate_telemetry.py): Injects telemetry through MQTT.
> - [`../../scripts/lora_packet_inject.py`](../../scripts/lora_packet_inject.py): Tests the LoRa parser and database writer directly.

### 3.3. Telemetry Validator (`services/telemetry_validator.py`)
Rejects malformed telemetry before database insertion:
- Verifies dictionary structure and presence of `device_id`.
- Validates supported metrics against strict physical boundaries:
  - `gas_ppm`: 0 to 10,000 ppm
  - `temperature_c`: -40°C to +85°C
  - `humidity`: 0% to 100%
  - `pressure_hpa`: 300 to 1100 hPa
  - `water_leak`: 0 or 1
  - `motion_detected`: 0 or 1

### 3.4. Database Writer (`services/database_writer.py`)
- Maintains a robust connection to PostgreSQL/TimescaleDB with `autocommit = True`.
- `write_telemetry(telemetry)`: Inserts into `sensor_telemetry` (`timestamp`, `device_id`, `zone`, `metrics` JSONB, `received_at`, `protocol`, `rssi`, `metadata` JSONB).
- `write_raw_packet(device_id, protocol, payload, parsed)`: Inserts raw BYTEA payload into `raw_sensor_packets`.

---

## 4. API Routes Overview

FastAPI exposes interactive Swagger docs at `http://localhost:8080/api/docs` (or `http://localhost:8000/docs`).

| Route | Method | Description | Current Status |
|---|---|---|---|
| `/health` | `GET` | Health check endpoint returning `{"status": "ok"}` | **Active** |
| `/devices/` | `GET` | List all registered devices | Active (Stub) |
| `/devices/{id}` | `GET` | Get single device details | Active (Stub) |
| `/devices/` | `POST` | Register a new edge node | Active (Stub) |
| `/devices/{id}` | `PUT` | Update device metadata | Active (Stub) |
| `/devices/{id}` | `DELETE`| Remove a device and its sensor associations | Active (Stub) |
| `/telemetry/` | `GET` | Query time-series telemetry with time/limit filters | Active (Stub) |
| `/telemetry/{id}/latest`| `GET` | Fetch latest reading for a device | Active (Stub) |
| `/alerts/` | `GET` | List alerts (filtered by acknowledgment status) | Phase 4 |
| `/alerts/` | `POST` | Create a new alert | Phase 4 |
| `/alerts/{id}/ack` | `PATCH` | Mark alert as acknowledged | Phase 4 |
| `/users/` | `GET`, `POST` | User listing & registration (admin only) | Phase 4 |
| `/users/{id}` | `GET`, `PUT`, `DELETE` | User account lifecycle | Phase 4 |

---

## 5. Running the Backend

### Method 1: Via Docker Compose (Recommended)
```bash
# Starts EMQX, TimescaleDB, Backend, Dashboard, and Nginx together
./scripts/docker_control.sh start

# View live backend logs
./scripts/docker_control.sh logs backend
```

### Method 2: Native Local Development
```bash
cd raspberry_pi/backend

# 1. Activate Python virtual environment
source ../../.venv/bin/activate

# 2. Run the main server (starts FastAPI + MQTT subscriber loop)
python main.py

# Or run FastAPI only with hot-reloading:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 6. Implementation Roadmap (Phase 4 Tasks)

### 1. Database Query Implementation in Routes
- [ ] Connect `routes/devices.py` to `devices` and `sensor_devices` tables via `psycopg2` or `asyncpg` to return live device lists.
- [ ] Connect `routes/telemetry.py` to `sensor_telemetry` hypertable to query historical time ranges (`start`, `end`, `limit`) and latest readings.
- [ ] Connect `routes/alerts.py` to create and acknowledge threshold alerts.

### 2. Authentication & Authorization (`backend/auth/`)
- [ ] Implement bcrypt password verification against the hashed passwords in the `users` table (`password123` seed default).
- [ ] Implement JWT token issuance (`/auth/login`) with expiration (15–60 mins) and claims:
  ```json
  {
    "sub": "user_uuid",
    "email": "user@etu.uni-usto.dz",
    "role": "zone_technician",
    "group_id": "group_uuid",
    "allowed_zones": ["Sector_A_Warehouse"]
  }
  ```
- [ ] Add FastAPI dependencies: `get_current_user`, `require_admin`, and `require_zone_access`.

### 3. Real-Time WebSocket Streaming
- [ ] Add `@app.websocket("/ws/telemetry")` to broadcast incoming telemetry readings to connected web dashboards in real-time.

---

## 7. Related Documentation

- Project Root Architecture: [README.md](../../README.md)
- Raspberry Pi Overview: [raspberry_pi/README.md](../README.md)
- Database Layer: [raspberry_pi/db/README.md](../db/README.md)
- Authentication Architecture: [auth/README.md](auth/README.md)
- Automation Scripts: [scripts/README.md](../../scripts/README.md)