# Raspberry Pi — EnviroMesh Edge Gateway & Core Server

> **Enterprise IoT Architecture** — Multi-protocol sensor ingestion (LoRa 433 MHz, Wi-Fi MQTT, ESP-NOW bridge), EMQX broker, TimescaleDB time-series storage, PostgreSQL relational registry, and FastAPI application server.  
> **Target Audience:** Embedded Systems & Platform Engineering Team  
> **Version:** 1.1

---

## Table of Contents

- [1. System Overview & Architecture](#1-system-overview--architecture)
- [2. Directory Layout](#2-directory-layout)
- [3. Hardware Wiring: SX1278 LoRa Receiver (RPi 40-Pin Header)](#3-hardware-wiring-sx1278-lora-receiver-rpi-40-pin-header)
- [4. Running the Platform](#4-running-the-platform)
  - [Option A: Using Helper Scripts (Recommended)](#option-a-using-helper-scripts-recommended)
  - [Option B: Native Docker Compose](#option-b-native-docker-compose)
- [5. Host Ports & Service Endpoints](#5-host-ports--service-endpoints)
- [6. Implementation Roadmap & Next Phases](#6-implementation-roadmap--next-phases)
  - [Phase 1: Core Infrastructure & Persistence](#phase-1-core-infrastructure--persistence-complete)
  - [Phase 2: Ingestion & Gateway Pipeline](#phase-2-ingestion--gateway-pipeline-complete)
  - [Phase 4: Application Layer, Security & Dashboard](#phase-4-application-layer-security--dashboard-in-progress)
  - [Phase 5: Hardware Field Testing & Video Subsystem](#phase-5-hardware-field-testing--video-subsystem)
- [7. Related Documentation](#7-related-documentation)

---

## 1. System Overview & Architecture

The Raspberry Pi (RPi 3 / 4 / 5) serves as the central hub of the **EnviroMesh** ecosystem, acting in two concurrent roles:

1. **LoRa Edge Gateway (Hardware Layer):** Interfaces directly via hardware SPI with an **SX1278 (433 MHz)** transceiver to capture raw RF packets broadcast by distant ESP32 field nodes (`G11`, `G41`).
2. **Core Processing Server (Application Layer):** Runs the **EMQX** MQTT broker, a **PostgreSQL + TimescaleDB** database engine, the **FastAPI** backend service daemon, an **Nginx** reverse proxy, and the **Web Dashboard**.

```
                           +================================================+
                           |           FIELD SENSORS & ACTUATORS            |
                           +================================================+
                             |                            |
                     LoRa 433 MHz                  Wi-Fi / MQTT
                    (Nodes G11, G41)              (Nodes G31, G61, G43)
                             |                            |
                             v                            v
               +---------------------------+    +---------------------------+
               | SX1278 LoRa SPI Receiver  |    | EMQX MQTT Broker (v5.8.8) |
               | (backend/services/        |    | (Port 1883 TCP)           |
               |  lora_receiver.py)        |    +-------------+-------------+
               +-------------+-------------+                  |
                             |                                |
                 Raw Frame & | De-serialized Payload          | JSON Payload
                             v                                v
               +------------------------------------------------------------+
               |              Backend Telemetry Validator                   |
               |          (services/telemetry_validator.py)                 |
               +-----------------------------+------------------------------+
                                             | Validated Reading
                                             v
               +------------------------------------------------------------+
               |                TimescaleDB Database Writer                 |
               |             (services/database_writer.py)                  |
               +-----------------------------+------------------------------+
                                             | SQL Insert / Hypertable
                                             v
               +------------------------------------------------------------+
               |              PostgreSQL 16 + TimescaleDB                   |
               |  - sensor_telemetry (time-partitioned hypertable)          |
               |  - raw_sensor_packets (raw payloads & diagnostic log)      |
               |  - groups, users, sensors, devices, sensor_devices         |
               +-----------------------------+------------------------------+
                                             ^
                                             | SQL Queries
               +-----------------------------+------------------------------+
               |               FastAPI REST & WebSocket API                 |
               |                    (backend/main.py)                       |
               +-----------------------------+------------------------------+
                                             | /api/ endpoints (Port 8000)
                                             v
               +------------------------------------------------------------+
               |              Nginx Reverse Proxy & Dashboard               |
               |       Port 8080: / -> Dashboard | /api/ -> Backend        |
               +------------------------------------------------------------+
```

---

## 2. Directory Layout

```
raspberry_pi/
├── backend/                          # FastAPI REST API & Ingestion Engine
│   ├── main.py                       # Application entry point: FastAPI + MQTT + LoRa threads
│   ├── requirements.txt              # Python runtime dependencies
│   ├── Dockerfile                    # Container image (python:3.11-slim)
│   ├── routes/                       # Modular API router endpoints
│   │   ├── __init__.py
│   │   ├── devices.py                # Device registration & inventory CRUD
│   │   ├── telemetry.py              # Time-series query endpoints
│   │   ├── alerts.py                 # Threshold alerts & acknowledgment
│   │   └── users.py                  # User accounts & RBAC management
│   ├── services/                     # Ingestion, validation & persistence services
│   │   ├── __init__.py
│   │   ├── mqtt_subscriber.py        # Paho-MQTT client for EMQX telemetry
│   │   ├── lora_receiver.py          # SX1278 hardware SPI driver & frame receiver
│   │   ├── telemetry_validator.py    # Payload schema & metric boundary validator
│   │   └── database_writer.py        # TimescaleDB connection pool & hypertable writer
│   └── auth/                         # Authentication & RBAC documentation
│       └── README.md                 # JWT & bcrypt architecture specifications
├── dashboard/                        # Web Dashboard Frontend
│   ├── index.html                    # Single-page dashboard interface
│   ├── Dockerfile                    # Nginx container hosting static assets
│   └── README.md                     # Dashboard design and roadmap
├── db/                               # Database Schemas & Seed Data
│   ├── migration/
│   │   ├── 001_create_registry.sql   # Relational schema (groups, users, sensors, devices)
│   │   └── 001_create_telemetry.sql  # TimescaleDB hypertables & indexes
│   ├── seed/
│   │   ├── 001_seed_registry.sql     # Reference seed data (student technicians & devices)
│   │   └── 001_verify_seed_registry.sql # Verification queries
│   └── README.md                     # Database setup and documentation
└── README.md                         # This file
```

---

## 3. Hardware Wiring: SX1278 LoRa Receiver (RPi 40-Pin Header)

When running as a physical LoRa concentrator, connect the SX1278 module to the Raspberry Pi GPIO header via SPI0:

| SX1278 Pin | Raspberry Pi Physical Pin | RPi GPIO / Function | Notes |
|---|---|---|---|
| **VCC (3.3V)** | Pin 1 or Pin 17 | `3.3V Power` | Do NOT use 5V (damages the SX1278) |
| **GND** | Pin 6, 9, 14, 20, or 25 | `Ground` | Common ground reference |
| **SCK** | Pin 23 | `GPIO 11 (SPI0_SCLK)` | Hardware SPI clock |
| **MISO** | Pin 21 | `GPIO 9 (SPI0_MISO)` | Master In, Slave Out |
| **MOSI** | Pin 19 | `GPIO 10 (SPI0_MOSI)`| Master Out, Slave In |
| **NSS / CS** | Pin 24 | `GPIO 8 (SPI0_CE0_N)` | Chip select line |
| **RST** | Pin 22 | `GPIO 25` | Hardware reset pin |
| **DIO0** | Pin 37 | `GPIO 26` | Packet Rx / Tx interrupt |

Enable SPI on the Raspberry Pi:
```bash
sudo raspi-config
# Navigate to: Interface Options -> SPI -> Enable -> Yes
# Verify SPI device node exists:
ls -l /dev/spidev0.*
```

---

## 4. Running the Platform

You can run the EnviroMesh stack using our automated scripts or standard Docker Compose:

### Option A: Using Helper Scripts (Recommended)
```bash
# 1. Initialize environment, permissions, and dependencies
./scripts/setup_env.sh

# 2. Launch the entire containerized stack
./scripts/docker_control.sh start

# 3. Apply database migrations and seeds
./scripts/db_manage.sh init

# 4. Verify stack health
./scripts/check_health.py

# 5. Monitor incoming telemetry in real-time
./scripts/mqtt_monitor.py
```

### Option B: Native Docker Compose
```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

---

## 5. Host Ports & Service Endpoints

| Service | Container | Host Port | Protocol | Purpose |
|---|---|---|---|---|
| **Nginx Reverse Proxy** | `enviromesh-nginx` | `8080` | HTTP | Single access point: `/` (Dashboard), `/api/` (API) |
| **FastAPI Backend** | `enviromesh-backend` | `8000` (internal) | HTTP | Direct API access (health check: `/health`) |
| **EMQX MQTT Broker** | `enviromesh-emqx` | `1883` | TCP / MQTT | Field node telemetry publishing & subscribing |
| **EMQX Admin Dashboard** | `enviromesh-emqx` | `18083` | HTTP | Broker administration console (`admin` / password) |
| **TimescaleDB** | `enviromesh-timescaledb`| `5432` | TCP / PostgreSQL| Database backend (application network) |

---

## 6. Implementation Roadmap & Next Phases

### Phase 1: Core Infrastructure & Persistence (COMPLETE)
- [x] Docker Compose stack definition (`emqx`, `timescaledb`, `backend`, `dashboard`, `nginx`).
- [x] PostgreSQL relational schema (`groups`, `users`, `sensors`, `devices`, `sensor_devices`).
- [x] TimescaleDB hypertables (`sensor_telemetry`, `raw_sensor_packets`) with optimized time/device indexes.
- [x] Automated database management scripts (`scripts/db_manage.sh`).

### Phase 2: Ingestion & Gateway Pipeline (COMPLETE)
- [x] Paho-MQTT subscriber daemon (`services/mqtt_subscriber.py`).
- [x] SX1278 SPI LoRa receiver daemon (`services/lora_receiver.py`).
- [x] Telemetry schema and metric boundary validation (`services/telemetry_validator.py`).
- [x] Concurrent multi-threaded ingestion in `main.py`.
- [x] Hardware-free telemetry simulator (`scripts/simulate_telemetry.py`).

### Phase 4: Application Layer, Security & Dashboard (IN PROGRESS)
- [ ] Connect FastAPI routes to database:
  - `routes/devices.py`: Query `devices` and `sensor_devices` tables via `psycopg2`.
  - `routes/telemetry.py`: Query `sensor_telemetry` hypertable with time filters (`start`, `end`, `limit`).
  - `routes/alerts.py`: Automatic threshold checks on ingest (gas > 2000 ppm, water leak) and alert logging.
  - `routes/users.py`: User registration, profile management, and password updates.
- [ ] Implement JWT Authentication & RBAC in `backend/auth/`:
  - Token issuance (`/auth/login`) with `role` (`admin`, `zone_technician`) and `allowed_zones`.
  - Dependency guards (`get_current_user`, `require_admin`).
- [ ] Build interactive Web Dashboard (replace placeholder in `dashboard/index.html` with responsive real-time charts via Chart.js / React and WebSocket telemetry streaming).
- [x] Configure EMQX topic-level Access Control Lists (ACLs) to enforce zone-isolated MQTT topics ([`infrastructure/emqx/acl.conf`](../infrastructure/emqx/acl.conf)).

### Phase 5: Hardware Field Testing & Video Subsystem
- [ ] Deploy MediaMTX RTSP proxy on RPi to handle video feeds from ESP32-CAM nodes.
- [ ] Install physical SX1278 module on outdoor RPi enclosure with tuned 433 MHz antenna.
- [ ] Field range testing: measure packet loss, RSSI, and SNR at distances from 50m to 1km.
- [x] Configure systemd service files ([`infrastructure/systemd/enviromesh.service`](../infrastructure/systemd/enviromesh.service) and [`infrastructure/systemd/enviromesh-lora.service`](../infrastructure/systemd/enviromesh-lora.service)) for auto-start on boot.

---

## 7. Related Documentation

- Project Root Specification: [README.md](../README.md)
- Infrastructure Layer: [infrastructure/README.md](../infrastructure/README.md)
- Firmware Documentation: [firmware/README.md](../firmware/README.md)
- Backend Deep Dive: [backend/README.md](backend/README.md)
- Database Layer: [db/README.md](db/README.md)
- Dashboard Documentation: [dashboard/README.md](dashboard/README.md)
- Automation Scripts: [scripts/README.md](../scripts/README.md)
