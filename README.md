# EnviroMesh: Two-Raspberry-Pi Distributed Architecture

**Enterprise Smart Environmental Monitoring Network with LoRa & Wi-Fi Edge Ingestion**

---

## Table of Contents

- [EnviroMesh: Two-Raspberry-Pi Distributed Architecture](#enviromesh-two-raspberry-pi-distributed-architecture)
  - [Table of Contents](#table-of-contents)
  - [1. System Overview](#1-system-overview)
    - [Core Design Philosophy](#core-design-philosophy)
  - [2. Final Architecture](#2-final-architecture)
    - [RPi 1 — Edge Gateway (`192.168.1.20`)](#rpi-1--edge-gateway-192168120)
    - [RPi 2 — Central Core (`192.168.1.5`)](#rpi-2--central-core-19216815)
  - [3. Two-Raspberry-Pi Topology Diagram](#3-two-raspberry-pi-topology-diagram)
  - [4. Hardware Inventory \& Pin Assignments](#4-hardware-inventory--pin-assignments)
    - [Verified Node Configurations](#verified-node-configurations)
    - [ESP32 Pin Mapping Table](#esp32-pin-mapping-table)
      - [Node G11 / Node G41 (LoRa 433 MHz Nodes)](#node-g11--node-g41-lora-433-mhz-nodes)
      - [Node G31 (Wi-Fi Node)](#node-g31-wi-fi-node)
      - [Node G61 (Wi-Fi Servo \& Actuator Node)](#node-g61-wi-fi-servo--actuator-node)
  - [5. Network Configuration \& Ports](#5-network-configuration--ports)
  - [6. Data Flow \& Sequence Diagram](#6-data-flow--sequence-diagram)
  - [7. RPi 1 Gateway Setup \& Operation](#7-rpi-1-gateway-setup--operation)
    - [Configuration (`.env`)](#configuration-env)
    - [Starting the Gateway](#starting-the-gateway)
  - [8. RPi 2 Core Setup \& Operation](#8-rpi-2-core-setup--operation)
    - [Configuration (`.env`)](#configuration-env-1)
    - [Starting the Core](#starting-the-core)
  - [9. SQLite Queue Design \& Resilience](#9-sqlite-queue-design--resilience)
    - [Schema](#schema)
    - [Durability Guarantees](#durability-guarantees)
  - [10. TLS Certificate Setup](#10-tls-certificate-setup)
    - [Step 1: Generate PKI on RPi 2](#step-1-generate-pki-on-rpi-2)
    - [Step 2: Copy CA Certificate to RPi 1](#step-2-copy-ca-certificate-to-rpi-1)
  - [11. EMQX Broker Configurations (RPi 1 \& RPi 2)](#11-emqx-broker-configurations-rpi-1--rpi-2)
    - [Local EMQX (RPi 1) ACL (`raspberry_pi/gateway/emqx/acl.conf`)](#local-emqx-rpi-1-acl-raspberry_pigatewayemqxaclconf)
    - [Central EMQX (RPi 2) ACL (`raspberry_pi/core/emqx/acl.conf`)](#central-emqx-rpi-2-acl-raspberry_picoreemqxaclconf)
  - [12. Database Schema \& TimescaleDB Setup](#12-database-schema--timescaledb-setup)
    - [Key Tables](#key-tables)
  - [13. API \& Dashboard](#13-api--dashboard)
    - [Key Endpoints](#key-endpoints)
  - [14. ESP32 Firmware Configuration](#14-esp32-firmware-configuration)
  - [15. Security \& Hardening](#15-security--hardening)
  - [16. Deployment Procedures (Step-by-Step)](#16-deployment-procedures-step-by-step)
    - [Deploying RPi 2 (Core) First](#deploying-rpi-2-core-first)
    - [Deploying RPi 1 (Gateway)](#deploying-rpi-1-gateway)
  - [17. Health Checks \& Verification](#17-health-checks--verification)
    - [Gateway Verification (on RPi 1)](#gateway-verification-on-rpi-1)
    - [Core Verification (on RPi 2)](#core-verification-on-rpi-2)
  - [18. Troubleshooting Guide](#18-troubleshooting-guide)
  - [19. Maintenance \& Operations](#19-maintenance--operations)
    - [Database Backups](#database-backups)
    - [Inspecting Gateway Queue](#inspecting-gateway-queue)
    - [Container Updates \& Rolling Restarts](#container-updates--rolling-restarts)
  - [20. Security Assessment Summary](#20-security-assessment-summary)
  - [21. Security Roadmap and Future Improvements](#21-security-roadmap-and-future-improvements)
  - [22. Security PoC Testing](#22-security-poc-testing)
  - [23. Maintenance and Known Issues](#23-maintenance-and-known-issues)
  - [24. Testing Results](#24-testing-results)
  - [25. Limitations](#25-limitations)
  - [26. Future Improvements](#26-future-improvements)

---

## 1. System Overview

**EnviroMesh** is an industrial-grade environmental monitoring platform designed to collect, validate, persist, and visualize sensor telemetry from distributed ESP32 nodes across warehouses, agricultural facilities, and industrial sectors.

### Core Design Philosophy
- **Physical Isolation of Edge Ingestion**: Field nodes (LoRa and Wi-Fi) connect **strictly to RPi 1 (Gateway)**. Field microcontrollers never communicate directly with the central database or core processing server.
- **Zero Data Loss via Persistent Edge Queueing**: RPi 1 buffers all incoming telemetry in an ACID-compliant SQLite database with Write-Ahead Logging (`WAL`) and `FULL` synchronization. If RPi 2 or the local network goes offline, RPi 1 continues collecting and storing sensor data indefinitely (up to 50,000 packets) without packet loss.
- **Encrypted Inter-Pi Forwarding**: Data transfer between RPi 1 and RPi 2 is secured using **MQTT over TLS (port 8883)** with custom PKI certificates and MQTT QoS 1.
- **Time-Series Storage & Idempotency**: RPi 2 runs PostgreSQL with TimescaleDB hypertables, backed by a deterministic deduplication table that eliminates duplicate packets caused by RF retries or network reconnections.

---

## 2. Final Architecture

The platform is designed to scale across multiple edge field gateways reporting to a central processing core:

### Field Edge Gateways
EnviroMesh supports multiple distributed gateways across different physical locations or network subnets:
- **RPi 1 / Gateway 1 (`GW01` — `192.168.1.20`)**: Primary edge gateway.
- **RPi 1 / Gateway 2 (`GW02` — `192.168.1.30`)**: Secondary edge gateway for expanded warehouse coverage.
- **LoRa Receiver**: Direct SPI communication with the SX1278 RA-02 transceiver at 433 MHz.
- **Local EMQX Broker**: Lightweight MQTT 5.x broker listening on port 1883 for local Wi-Fi ESP32 nodes. Dashboard bound to `0.0.0.0:18083` for full LAN administration.
- **Telemetry Ingestion & Normalizer**: Extracts raw fields, validates constraints, computes a deterministic UUIDv5 message identifier, and normalizes payloads into a uniform JSON schema.
- **Signal Quality Telemetry**: Attaches hardware RSSI and SNR to received LoRa packets.
- **SQLite Persistent Queue**: FIFO buffer ensuring durability across reboots and network partitions.
- **MQTT Forwarder Service**: Dequeues messages and publishes them to RPi 2 with QoS 1 over TLS.
- **Health Monitor**: Periodically tracks queue depth, buffer utilization, and subsystem liveness.

### RPi 2 — Central Core (`192.168.1.5`)
- **Central EMQX Broker**: Production MQTT 5.x broker listening on port 8883 (TLS required for Gateway forwarders) and internal port 1883 for local backend subscribers. Dashboard bound to `0.0.0.0:18083` (or `18084` in unified mode).
- **FastAPI Telemetry Subscriber**: Consumes forwarded telemetry, validates payloads, and manages transactional insertion.
- **Deduplication Engine**: Enforces at-most-once storage via the `processed_messages` table.
- **PostgreSQL 16 + TimescaleDB 2.17**: Partitioned time-series database for multi-year telemetry analytics (internal network only; port 5432 is unexposed to LAN).
- **FastAPI REST & WebSocket Server**: High-performance backend hosting device metadata, historical telemetry queries, and real-time streaming endpoints.
- **React + Vite Dashboard**: Modern, responsive dashboard visualizing live environmental readings, alerts, and node telemetry.
- **Nginx Reverse Proxy**: Single entry point (`:8080`) serving the dashboard and proxying `/api/` traffic to FastAPI.

---

## 3. Two-Raspberry-Pi Topology Diagram

```
                 FIELD SENSING LAYER
      ┌────────────────────┐     ┌────────────────────┐
      │  ESP32 LoRa Nodes  │     │ ESP32 Wi-Fi Nodes  │
      │   (G11, G41)       │     │(G31, G42, G43, G61)│
      └─────────┬──────────┘     └─────────┬──────────┘
                │                          │
                │ 433 MHz RF               │ Wi-Fi MQTT (:1883)
                ▼                          ▼
┌──────────────────────────────────────────────────────────┐
│              RPi 1: GATEWAY (192.168.1.20)               │
│                                                          │
│   SX1278 SPI Receiver       Local EMQX Broker (:1883)    │
│            │                             │               │
│            └──────────────┬──────────────┘               │
│                           ▼                              │
│              Payload Normalizer & Validator              │
│                           │                              │
│                           ▼                              │
│              SQLite Queue (WAL + FULL Sync)              │
│                           │                              │
│                           ▼                              │
│             TLS MQTT Forwarder (paho-mqtt)               │
└───────────────────────────┬──────────────────────────────┘
                            │
                            │ MQTT over TLS (:8883, QoS 1)
                            │ Mutual / CA Verified
                            ▼
┌──────────────────────────────────────────────────────────┐
│                 RPi 2: CORE (192.168.1.5)               │
│                                                          │
│               Central EMQX Broker (:8883)                │
│                           │                              │
│                           ▼                              │
│                Backend MQTT Subscriber                   │
│                           │                              │
│                           ▼                              │
│             Duplicate Detection & TimescaleDB            │
│          (sensor_telemetry + processed_messages)         │
│                           ▲                              │
│                           │ Internal Connection          │
│                           ▼                              │
│                FastAPI Backend (:8000)                   │
│                           ▲                              │
│                           │ Reverse Proxy Routing        │
│                           ▼                              │
│                 Nginx Proxy (:8080)                      │
│                           ▲                              │
│                           │ Static SPA Delivery          │
│                           ▼                              │
│                 React + Vite Dashboard                   │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Hardware Inventory & Pin Assignments

### Verified Node Configurations

| Device  | Primary Role                | Transport    | Hardware Sensors & Actuators                    | Status             |
| ------- | --------------------------- | ------------ | ----------------------------------------------- | ------------------ |
| **G11** | Hazardous Gas & Environment | LoRa 433 MHz | MQ-2 (Gas/Smoke), DHT11 (Temp/Hum), Water Leak  | Operational        |
| **G41** | Warehouse Perimeter         | LoRa 433 MHz | MQ-2 (Gas/Smoke), DHT11 (Temp/Hum), Water Leak  | Operational        |
| **G31** | Sector C Utility Room       | Wi-Fi MQTT   | BMP280 (Press/Temp), MQ-2 (Gas), Water Leak     | Specification Stub |
| **G61** | Ventilation & Actuation     | Wi-Fi MQTT   | MQ-2, DHT11, Water Leak, PIR Motion, SG90 Servo | Operational        |
| **G42** | Wi-Fi Field Node            | Wi-Fi MQTT   | Temperature, Humidity, Smoke Simulator          | Test Harness       |
| **G43** | Schema Telemetry Node       | Wi-Fi MQTT   | Multi-sensor synthetic load                     | Test Harness       |

### ESP32 Pin Mapping Table

#### Node G11 / Node G41 (LoRa 433 MHz Nodes)
- **DHT11 Data**: GPIO 4
- **MQ-2 Analog (AO)**: GPIO 0 (ADC1)
- **MQ-2 Digital (DO)**: GPIO 2
- **Water Sensor (Signal)**: GPIO 15
- **LoRa SX1278 (Ra-02)**:
  - **NSS / SS**: GPIO 16
  - **RST**: GPIO 14
  - **DIO0**: GPIO 26
  - **SCK**: GPIO 5
  - **MISO**: GPIO 19
  - **MOSI**: GPIO 32
- **Frequency**: 433.0 MHz (SF7, BW 125 kHz, CR 4/5, Sync Word `0x12`)

#### Node G31 (Wi-Fi Node)
- **MQ-2 Gas (AO)**: GPIO 34 (ADC1_CH6)
- **Water Sensor (AO)**: GPIO 35 (ADC1_CH7)
- **BMP280 (I2C)**: SDA GPIO 21, SCL GPIO 22

#### Node G61 (Wi-Fi Servo & Actuator Node)
- **DHT11 Data**: GPIO 4
- **MQ-2 Analog (AO)**: GPIO 34
- **Water Sensor (AO)**: GPIO 35
- **PIR Motion (OUT)**: GPIO 13
- **SG90 Micro Servo (PWM)**: GPIO 18

---

## 5. Network Configuration & Ports

| Host      | Service            | Port  | Protocol | Binding / Scope  | Purpose                                |
| --------- | ------------------ | ----- | -------- | ---------------- | -------------------------------------- |
| **RPi 1 (GW1)** | Local EMQX         | 1883  | TCP      | `0.0.0.0` (LAN)  | Ingestion from Wi-Fi ESP32 nodes (192.168.1.20) |
| **RPi 1 (GW1)** | EMQX Dashboard     | 18083 | TCP      | `0.0.0.0` (LAN)  | Gateway 1 broker web administration    |
| **RPi 1 (GW2)** | Local EMQX         | 1883  | TCP      | `0.0.0.0` (LAN)  | Ingestion from Wi-Fi ESP32 nodes (192.168.1.30) |
| **RPi 1 (GW2)** | EMQX Dashboard     | 18083 | TCP      | `0.0.0.0` (LAN)  | Gateway 2 broker web administration    |
| **RPi 1** | SSH                | 22    | TCP      | LAN / Management | Linux maintenance                      |
| **RPi 2** | Central EMQX TLS   | 8883  | TCP/TLS  | `0.0.0.0` (LAN)  | Ingestion from Gateway forwarders      |
| **RPi 2** | Central EMQX Plain | 1883  | TCP      | `0.0.0.0` (LAN)  | Plain debugging & internal subscriber  |
| **RPi 2** | EMQX Dashboard     | 18083 | TCP      | `0.0.0.0` (LAN)  | Central broker web administration      |
| **RPi 2** | Nginx Web Server   | 8080  | TCP      | `0.0.0.0` (LAN)  | React Dashboard & REST API access      |
| **RPi 2** | FastAPI Backend    | 8000  | TCP      | Docker Network   | REST API & WebSockets (Internal)       |
| **RPi 2** | TimescaleDB        | 5432  | TCP      | Docker Network   | Relational time-series data (Internal) |
| **RPi 2** | SSH                | 22    | TCP      | LAN / Management | Linux maintenance                      |

---

## 6. Data Flow & Sequence Diagram

```text
[ESP32 Node]      [RPi 1 Local]    [RPi 1 SQLite]    [RPi 1 Forwarder]    [RPi 2 EMQX]    [RPi 2 Backend]   [TimescaleDB]
     │                  │                 │                  │                 │                 │                │
     │── Telemetry ────>│                 │                  │                 │                 │                │
     │   (LoRa/Wi-Fi)   │── Validate & ──>│                  │                 │                 │                │
     │                  │   Enqueue       │                  │                 │                 │                │
     │                  │                 │<── Read Batch ───│                 │                 │                │
     │                  │                 │                  │── TLS Publish ─>│                 │                │
     │                  │                 │                  │   (QoS 1)       │── On Message ──>│                │
     │                  │                 │                  │                 │                 │── Check Dedup ─│
     │                  │                 │                  │                 │                 │   (Processed?) │
     │                  │                 │                  │                 │                 │── INSERT ─────>│
     │                  │                 │                  │<── PUBACK ──────│                 │                │
     │                  │                 │<── Mark Sent ────│                 │                 │                │
     │                  │                 │    (DELETE)      │                 │                 │                │
```

---

## 7. Environment Configuration: Global Main vs Divided Partition `.env`

EnviroMesh provides complete architectural flexibility for environment configuration:

1. **Global Unified Mode (Main `.env`)**:
   - The root `.env` (copied from `.env.example`) serves as the central configuration for all services, scripts, and local testing tools.
   - When deploying on a single server, dev laptop, or testing both gateways together, the root `.env` configures both Gateway 1, Gateway 2, and Core stacks from a single file.

2. **Divided Partition Mode**:
   - When deploying to physically separate Raspberry Pi hardware on your LAN:
     - **RPi 2 (Core Server)**: Uses `raspberry_pi/core/.env` (template: `raspberry_pi/core/.env.example`).
     - **RPi 1 (Gateway 1 - `GW01`)**: Uses `raspberry_pi/gateway/.env` (template: `raspberry_pi/gateway/.env.gw1.example`).
     - **RPi 1 (Gateway 2 - `GW02`)**: Uses `raspberry_pi/gateway/.env` (template: `raspberry_pi/gateway/.env.gw2.example`).

---

## 8. Security Switch: Turn MQTT Auth & TLS ON / OFF ("Button Toggle")

You can toggle MQTT authentication and TLS encryption on or off without manually editing configuration files:

```bash
# Toggle via dedicated controller
./scripts/toggle_security.sh --auth on       # Turn Authentication ON
./scripts/toggle_security.sh --auth off      # Turn Authentication OFF (Anonymous mode)
./scripts/toggle_security.sh --tls on        # Turn TLS Encryption ON (Port 8883)
./scripts/toggle_security.sh --tls off       # Turn TLS Encryption OFF (Port 1883)
./scripts/toggle_security.sh --status        # Show current security configuration

# Interactive Toggle Menu
./scripts/toggle_security.sh

# Or via docker_control.sh
./scripts/docker_control.sh auth on
./scripts/docker_control.sh auth off
./scripts/docker_control.sh tls on
./scripts/docker_control.sh tls off
./scripts/docker_control.sh security
```

When Authentication is **OFF**:
- EMQX allows anonymous connections without credential checks.
- ACL rules default to `allow`, letting any client publish or subscribe.
- No `✖ Failed to connect to broker (reason code: Not authorized)` errors.

When Authentication is **ON**:
- Built-in database verifies client credentials.
- Strict ACL rules isolate nodes to their dedicated topics.
- Pre-configured defaults (`gw_ingestion`, `gw_forwarder`, `gw01_forwarder`, `gw02_forwarder`, `enviromesh_backend`) ensure all internal services and scripts connect seamlessly.

---

## 9. RPi 1 Field Gateway Setup & Operation (GW01 & GW02)

The gateway directory (`raspberry_pi/gateway/`) provides an independent deployment unit for RPi 1.

### Gateway 1 (`GW01` — `192.168.1.20`)
```bash
cp raspberry_pi/gateway/.env.gw1.example raspberry_pi/gateway/.env
cd raspberry_pi/gateway && docker compose up -d
```

### Gateway 2 (`GW02` — `192.168.1.30` — Wi-Fi Only, LoRa Disabled)
Gateway 2 does not have an SX1278 transceiver (`ENABLE_LORA=false` in `.env`). It operates purely as a Wi-Fi MQTT ingestion gateway and forwards telemetry to Core:
```bash
cp raspberry_pi/gateway/.env.gw2.example raspberry_pi/gateway/.env
cd raspberry_pi/gateway && docker compose up -d
```

### Local Multi-Gateway Simulation (Dual-Gateway)
To run both Gateway 1 and Gateway 2 simultaneously on the same machine:
```bash
docker compose --profile dual-gateway up -d
```

### Gateway Configuration Reference (`.env`)
```bash
# Gateway Identity (GW01 for Gateway 1, GW02 for Gateway 2)
GATEWAY_ID=GW01
GATEWAY_LAN_IP=192.168.1.20

# Security Toggle
MQTT_AUTH_ENABLED=true

# Local EMQX Ingestion Broker (Dashboard reachable at 0.0.0.0:18083 across LAN)
MQTT_BIND_IP=0.0.0.0
MQTT_LOCAL_PORT=1883
MQTT_LOCAL_USERNAME=gw_ingestion
MQTT_LOCAL_PASSWORD=gw_ingest_secret
EMQX_DASHBOARD_BIND_IP=0.0.0.0
EMQX_DASHBOARD_PORT=18083

# Target Core Server (RPi 2)
MQTT_CORE_HOST=192.168.1.5
MQTT_CORE_PORT=8883
MQTT_CORE_USE_TLS=true
MQTT_CORE_USERNAME=gw_forwarder
MQTT_CORE_PASSWORD=gw_forward_secret
MQTT_CORE_CA=/app/certs/core-ca.crt

# Queue & Forwarding Settings
QUEUE_MAX_MESSAGES=50000
FORWARD_BATCH_SIZE=10
FORWARD_RETRY_SECONDS=5
LOG_LEVEL=INFO
```

---

## 10. RPi 2 Core Setup & Operation

The core directory (`raspberry_pi/core/`) provides the processing, database, backend, and dashboard stack.

### Configuration (`.env`)
```bash
APP_ENV=production
LOG_LEVEL=INFO
WEB_BIND_IP=0.0.0.0
WEB_PORT=8080

# Security Toggles
MQTT_AUTH_ENABLED=true
MQTT_TLS_ENABLED=true

# Central EMQX Broker (Dashboard reachable at 0.0.0.0:18083 across LAN)
EMQX_DASHBOARD_BIND_IP=0.0.0.0
EMQX_DASHBOARD_PORT=18083
EMQX_DASHBOARD_USERNAME=admin
EMQX_DASHBOARD_PASSWORD=admin123

MQTT_APP_USERNAME=enviromesh_backend
MQTT_APP_PASSWORD=backend_secret_pass

POSTGRES_DB=enviromesh
POSTGRES_USER=enviromesh_app
POSTGRES_PASSWORD=enviromesh_secret_db_pass

CORE_LAN_IP=192.168.1.5
GATEWAY_1_LAN_IP=192.168.1.20
GATEWAY_2_LAN_IP=192.168.1.30
```

### Starting the Core
```bash
cd raspberry_pi/core
./../../scripts/setup_core.sh
# Generate certificates as described in Section 10
./../../scripts/deploy_core.sh
```

---

## 9. SQLite Queue Design & Resilience

The persistent queue is implemented in `raspberry_pi/gateway/gateway/sqlite_queue.py`.

### Schema
```sql
CREATE TABLE IF NOT EXISTS queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   TEXT UNIQUE NOT NULL,
    topic        TEXT NOT NULL,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT
);
CREATE INDEX IF NOT EXISTS idx_queue_attempts ON queue (attempts, created_at);
```

### Durability Guarantees
- **WAL Mode**: `PRAGMA journal_mode = WAL` allows concurrent reading and writing without database locks.
- **Synchronous FULL**: `PRAGMA synchronous = FULL` ensures transactions are completely flushed to disk before returning, surviving abrupt power loss on the Raspberry Pi.
- **Zero Loss Forwarding**: Rows are deleted (`mark_sent`) **only after receiving the MQTT `PUBACK` callback** from the broker.

---

## 11. Automated TLS Certificate Setup & PKI

Inter-Pi communication requires a custom root Certificate Authority (CA) and an X.509 server certificate for RPi 2.

### Automated Generation (Recommended)
`install.sh` and `./scripts/generate_certs.sh` automatically provision all required certificates, directories (`certs/`, `raspberry_pi/gateway/certs/`, `raspberry_pi/core/emqx/certs/`), and Subject Alternative Names (SANs) for Core (`192.168.1.5`), Gateway 1 (`192.168.1.20`), Gateway 2 (`192.168.1.30`), and local addresses:

```bash
# Run one-command certificate generation
./scripts/generate_certs.sh

# Force regeneration if IPs change
./scripts/generate_certs.sh --force
```

This creates:
- Root CA: `certs/ca.crt` & `raspberry_pi/core/emqx/certs/ca.crt`
- Server Certificate: `certs/server.crt` & `raspberry_pi/core/emqx/certs/server.crt`
- Gateway Trust Bundle: `certs/core-ca.crt` & `raspberry_pi/gateway/certs/core-ca.crt`

### Manual Multi-Pi Certificate Transfer (Distributed Physical Hardware)
If Gateway 1 and Gateway 2 are on separate physical Raspberry Pis:
```bash
# Copy CA certificate from RPi 2 to Gateway 1 (192.168.1.20)
scp raspberry_pi/core/emqx/certs/ca.crt pi@192.168.1.20:/home/pi/enviromesh/raspberry_pi/gateway/certs/core-ca.crt

# Copy CA certificate from RPi 2 to Gateway 2 (192.168.1.30)
scp raspberry_pi/core/emqx/certs/ca.crt pi@192.168.1.30:/home/pi/enviromesh/raspberry_pi/gateway/certs/core-ca.crt
```

---

## 11. EMQX Broker Configurations (RPi 1 & RPi 2)

Both Raspberry Pis run independent EMQX 5.x instances configured with deny-by-default ACL policies.

### Local EMQX (RPi 1) ACL (`raspberry_pi/gateway/emqx/acl.conf`)
```erlang
%% Allow specific ESP32 devices to publish to their assigned topic
{allow, {username, "g11"}, publish, ["enviromesh/devices/G11/telemetry"]}.
{allow, {username, "g41"}, publish, ["enviromesh/devices/G41/telemetry"]}.
{allow, {username, "g31"}, publish, ["enviromesh/devices/G31/telemetry"]}.
{allow, {username, "g61"}, publish, ["enviromesh/devices/G61/telemetry"]}.

%% Gateway ingestion service subscribes to all device topics
{allow, {username, "gw_ingestion"}, subscribe, ["enviromesh/devices/+/telemetry"]}.

%% Deny everything else
{deny, all, all, ["#"]}.
```

### Central EMQX (RPi 2) ACL (`raspberry_pi/core/emqx/acl.conf`)
```erlang
%% Gateway forwarder publishes forwarded telemetry & status
{allow, {username, "gw_forwarder"}, publish, [
    "enviromesh/gateway/+/telemetry",
    "enviromesh/gateway/+/status"
]}.

%% Core backend subscribes to forwarded telemetry & status
{allow, {username, "enviromesh_backend"}, subscribe, [
    "enviromesh/gateway/+/telemetry",
    "enviromesh/gateway/+/status"
]}.

%% Deny everything else
{deny, all, all, ["#"]}.
```

---

## 12. Database Schema & TimescaleDB Setup

Database migrations run automatically during deployment via `scripts/deploy_core.sh`.

### Key Tables
1. **`sensor_telemetry`** (TimescaleDB hypertable):
   Contains columns: `timestamp`, `device_id`, `zone`, `metrics` (JSONB), `received_at`, `protocol`, `rssi`, `metadata` (JSONB), `message_id`, `gateway_id`, and `gateway_received_at`.
2. **`processed_messages`** (Deduplication table):
   Contains `message_id` (PRIMARY KEY), `device_id`, `gateway_id`, and `processed_at`. Prevents duplicate insertions into the hypertable.
3. **`device_registry`**:
   Metadata catalog tracking registered sensor nodes, zones, operational status, and installed firmware versions.

---

## 13. API & Dashboard

The dashboard and API are accessed through Nginx on port `8080`:
- **Dashboard UI**: `http://localhost:8080/` (or LAN IP)
- **FastAPI OpenAPI Docs**: `http://localhost:8080/api/docs`
- **Health Check**: `http://localhost:8080/api/health`

### Key Endpoints
- `POST /api/auth/login`: Authenticate user credentials and receive JWT bearer token.
- `GET /api/auth/me`: Return authenticated user profile and assigned role (`admin` or `zone_technician`).
- `POST /api/auth/change-password`: Password rotation endpoint (mandatory upon initial login).
- `GET /api/devices/`: List registered environmental nodes (scoped by technician zone).
- `GET /api/devices/{device_id}`: Detailed telemetry and metadata for a specific node.
- `GET /api/telemetry/latest`: Latest readings across all active nodes.
- `GET /api/groups/`: Zone groupings and regional status summaries.
- `GET /api/users/`: Administrator user management & account creation.

### Dashboard Pages
- `/`: Real-time sensor overview, charts, and node status cards.
- `/login`: Secure user authentication with JWT storage.
- `/users`: Administrator portal for creating and managing technicians.
- `/groups`: Zone and group allocation.
- `/settings`: Profile management and password rotation.

---

## 14. ESP32 Firmware Configuration

All Wi-Fi nodes must point to RPi 1 Gateway:
```c
// Example: firmware/nodes/node_g31/src/secrets.h
#define WIFI_SSID        "Warehouse_IoT_2.4G"
#define WIFI_PASSWORD    "WarehousePassword"
#define MQTT_BROKER_HOST "192.168.1.20"  // RPi 1 Gateway IP (or localhost in single-device testing)
#define MQTT_PORT        1883
#define MQTT_USERNAME    "g31"
#define MQTT_PASSWORD    "DevicePasswordG31"
```

For LoRa nodes (`node_g11`, `node_g41`), verify that the RF frequency is `433E6`, sync word is `0x12`, and bandwidth is `125E3`.

---

## 15. Security & Hardening

1. **Firewall Rules (UFW)**:
   - On RPi 1: Allow TCP port 1883 from the LAN; keep port 18083 restricted to localhost.
   - On RPi 2: Allow TCP port 8080 (Web) from LAN; allow port 8883 (TLS) only from RPi 1 (`192.168.1.20`).
2. **Database Isolation**: PostgreSQL port `5432` has no host port bindings. Only containers in the internal Docker bridge network can communicate with the database.
3. **Secret Isolation**: Real secrets are kept strictly in `.env` files with `chmod 600` and are ignored in `.gitignore`.
4. **JWT Authentication & Role-Based Access Control**:
   - Protected API routes enforce JWT bearer tokens.
   - Zone technicians are scoped strictly to their assigned group nodes.

---

## 16. Deployment Procedures (Step-by-Step)

EnviroMesh supports two deployment topologies:

### Mode A: Unified Single-Device Deployment (Development, Simulation & Lab Testing)
Runs **both Gateway and Core** on the same physical host (laptop, PC, or single Raspberry Pi):

```bash
# 1. Clone repository
git clone <REPO_URL> && cd enviromesh

# 2. Configure environment
cp .env.example .env && nano .env

# 3. Start all 7 unified services (Gateway + Core)
./scripts/docker_control.sh start

# 4. Check status & service endpoints
./scripts/docker_control.sh status

# 5. Run automated pipeline simulation & tests
python3 scripts/run_tests.py

# 6. Simulate live telemetry emissions from all field nodes
python3 scripts/simulate_telemetry.py --count 10 --device all
```

### Mode B: Distributed Two-Raspberry-Pi Deployment (Production)

#### Deploying RPi 2 (Core) First
```bash
# 1. Clone repository
git clone <REPO_URL> /home/pi/enviromesh && cd /home/pi/enviromesh

# 2. Run core setup
./scripts/setup_core.sh

# 3. Configure passwords
nano raspberry_pi/core/.env

# 4. Generate TLS certificates (see Section 10)
# 5. Deploy stack & apply database migrations
./scripts/deploy_core.sh

# 6. Create broker accounts
docker exec -it enviromesh-emqx-core \
  emqx ctl admins add gw_forwarder 'CORE_PASSWORD' 'Gateway Forwarder'
docker exec -it enviromesh-emqx-core \
  emqx ctl admins add enviromesh_backend 'BACKEND_PASSWORD' 'Enviromesh Backend'
```

#### Deploying RPi 1 (Gateway)
```bash
# 1. Clone repository
git clone <REPO_URL> /home/pi/enviromesh && cd /home/pi/enviromesh

# 2. Run gateway setup
./scripts/setup_gateway.sh

# 3. Copy ca.crt from RPi 2 into raspberry_pi/gateway/certs/core-ca.crt
scp pi@192.168.1.5:/home/pi/enviromesh/raspberry_pi/core/emqx/certs/ca.crt raspberry_pi/gateway/certs/core-ca.crt

# 4. Configure environment
nano raspberry_pi/gateway/.env

# 5. Deploy gateway stack
./scripts/deploy_gateway.sh

# 6. Create local broker accounts
docker exec -it enviromesh-emqx-local \
  emqx ctl admins add gw_ingestion 'LOCAL_PASSWORD' 'Gateway Ingestion'
docker exec -it enviromesh-emqx-local \
  emqx ctl admins add g31 'G31_PASSWORD' 'Gateway G31'
```

---

## 17. Health Checks & Verification

EnviroMesh includes automated verification scripts for every scenario:

### Unified Single-Device Verification (Same Machine)
```bash
python3 scripts/check_health.py
```
Checks:
- Reverse Proxy (Nginx on port 8080)
- Backend REST API (`/api/health`)
- Gateway Local EMQX Broker (port 1883)
- Core Central EMQX TLS Broker (port 8883)
- Gateway & Core EMQX Web Consoles (ports 18083, 18084)
- TimescaleDB database container status

### Distributed RPi 1 Gateway Verification
```bash
python3 scripts/check_gateway_health.py
```

### Distributed RPi 2 Core Verification
```bash
python3 scripts/check_core_health.py
```

---

## 18. Troubleshooting Guide

| Symptom                                        | Probable Cause                                               | Diagnostic Command & Fix                                                                                                                                        |
| ---------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Forwarder fails: Connection Refused (8883)** | Core RPi 2 offline, firewall blocking port, or EMQX down     | Run `nc -zv 192.168.1.5 8883`. Verify RPi 2 UFW allows port 8883 from RPi 1.                                                                                    |
| **TLS Certificate Verification Failed**        | Server IP not present in SAN list of certificate             | Inspect cert: `openssl x509 -in server.crt -text -noout`. Re-issue cert with correct IP in `server_ext.cnf`.                                                    |
| **LoRa Receiver Exits Immediately**            | SPI interface disabled on Raspberry Pi OS                    | Run `sudo raspi-config nonint do_spi 0` and verify `/dev/spidev0.0` exists.                                                                                     |
| **ESP32 Wi-Fi Node Cannot Connect**            | Router Wireless Client Isolation active or pointing to RPi 2 | Disable AP Client Isolation in router settings. Ensure node points to RPi 1 IP on port 1883.                                                                    |
| **Pending Messages Accumulate in SQLite**      | Inter-Pi network link down                                   | Normal behavior! Check queue: `sqlite3 raspberry_pi/gateway/data/queue.db "SELECT count(*) FROM queue;"`. Messages will flush automatically once link restores. |

---

## 19. Maintenance & Operations

### Database Backups
A production backup script with automatic rotation is located at `scripts/backup_database.sh`.
```bash
# Run manual backup
./scripts/backup_database.sh

# Configure daily cronjob (at 02:00 UTC)
0 2 * * * /home/pi/enviromesh/scripts/backup_database.sh >> /var/log/enviromesh_backup.log 2>&1
```

### Inspecting Gateway Queue
```bash
# Check undelivered packet count
sqlite3 raspberry_pi/gateway/data/queue.db "SELECT count(*) FROM queue;"

# View oldest unforwarded message
sqlite3 raspberry_pi/gateway/data/queue.db "SELECT message_id, created_at, attempts FROM queue ORDER BY created_at ASC LIMIT 1;"
```

### Container Updates & Rolling Restarts
```bash
# Restart gateway services without data loss
docker compose -f raspberry_pi/gateway/docker-compose.yml restart

# Restart core services (volumes are preserved)
docker compose -f raspberry_pi/core/docker-compose.yml restart
```
*(Never execute `docker compose down -v` in production environments).*

---

## 20. Security Assessment Summary

A full security assessment is documented in [`docs/security-assessment.md`](docs/security-assessment.md).

**Confirmed findings:**

| ID     | Finding                                                   | Component          | Severity | Status                |
| ------ | --------------------------------------------------------- | ------------------ | -------- | --------------------- |
| SEC-01 | No HTTPS on dashboard (HTTP only)                         | Nginx              | High     | Future work           |
| SEC-02 | JWT / auth routes not yet implemented                     | FastAPI            | High     | Future work           |
| SEC-03 | LoRa packets have no HMAC/signature                       | LoRa receiver      | High     | Future work           |
| SEC-04 | Server-authenticated TLS only (not mTLS)                  | MQTT forwarder     | Medium   | Future work           |
| SEC-05 | EMQX device credentials not enforced at application level | EMQX ACL           | Medium   | Partially implemented |
| SEC-06 | No API rate limiting configured                           | FastAPI / Nginx    | Medium   | Future work           |
| SEC-07 | Backup files are unencrypted                              | backup_database.sh | Medium   | Future work           |
| SEC-08 | MQTT forwarder uses clean_session=True                    | mqtt_forwarder.py  | Medium   | Open                  |
| SEC-09 | SQLite file permissions rely on Docker volume             | sqlite_queue.py    | Low      | Partially implemented |
| SEC-10 | EMQX dashboard on gateway accessible from localhost       | docker-compose.yml | Low      | Acceptable            |

---

## 21. Security Roadmap and Future Improvements

| Security Improvement        | Component         | Current Status                                          | Planned Implementation                                         | Priority |
| --------------------------- | ----------------- | ------------------------------------------------------- | -------------------------------------------------------------- | -------- |
| HTTPS / TLS on Nginx        | Nginx             | Not implemented — HTTP only on port 8080                | Add self-signed or Let's Encrypt cert, update nginx config     | High     |
| JWT authentication          | Dashboard / API   | Routes commented out                                    | Implement JWT middleware, enable users router                  | High     |
| MQTT ACL hardening          | EMQX              | Per-device ACL configured; password enforcement partial | Enforce per-device credentials on local EMQX                   | High     |
| LoRa message authentication | LoRa              | No cryptographic protection                             | HMAC-SHA256 on packet, counter for replay detection            | High     |
| Replay protection           | LoRa / MQTT       | No counter or nonce                                     | Add packet counter field, reject duplicates at gateway         | High     |
| Mutual TLS (mTLS)           | MQTT inter-Pi     | Server-auth TLS only                                    | Require client certificate from gateway forwarder              | Medium   |
| API rate limiting           | FastAPI / Nginx   | No limits configured                                    | Add slowapi or nginx limit_req_zone                            | Medium   |
| Security audit logging      | Core / Gateway    | Basic application logs                                  | Add structured security event log (failed auth, ACL deny)      | Medium   |
| Backup encryption           | Database backup   | Unencrypted .sql.gz                                     | Encrypt with gpg before storing backup files                   | Medium   |
| Certificate rotation        | MQTT TLS          | Manual process documented                               | Automate or document scheduled cert renewal                    | Medium   |
| EMQX persistent sessions    | Gateway forwarder | clean_session=True                                      | Switch to persistent session for QoS 1 delivery during restart | Medium   |
| SQL injection protection    | FastAPI           | SQLAlchemy ORM in use (partial)                         | Audit all raw SQL, enforce parameterized queries everywhere    | High     |

---

## 22. Security PoC Testing

Authorized security testing PoCs are located in `security/`. See [`security/README.md`](security/README.md).

**PoC Status:**

| PoC                       | Category                 | Status           | Reason                                                |
| ------------------------- | ------------------------ | ---------------- | ----------------------------------------------------- |
| 01-mqtt-auth-poc          | MQTT unauthorized access | NOT TESTED       | Requires running EMQX instance                        |
| 02-lora-replay-poc        | LoRa replay attack       | BLOCKED          | Requires physical SX1278 hardware                     |
| 03-api-auth-poc           | FastAPI auth bypass      | BLOCKED          | Auth routes not yet implemented (ISSUE-001)           |
| 04-sqlite-permissions-poc | SQLite file permissions  | NOT TESTED       | Requires physical device                              |
| 05-network-exposure-poc   | Network port exposure    | PARTIALLY TESTED | docker compose config validated, no port 5432 exposed |

All PoCs are restricted to isolated test environments. See [`security/rules-of-engagement.md`](security/rules-of-engagement.md).

---

## 23. Maintenance and Known Issues

Full maintenance documentation: [`docs/maintenance-and-known-issues.md`](docs/maintenance-and-known-issues.md)

Outstanding issues summary:

| Issue ID  | Summary                                             | Severity | Status                                |
| --------- | --------------------------------------------------- | -------- | ------------------------------------- |
| ISSUE-001 | JWT/auth routes disabled in backend                 | High     | Open — requires implementation        |
| ISSUE-002 | TLS certs must be manually generated                | High     | Blocked — needs physical hardware     |
| ISSUE-003 | TimescaleDB migrations run manually                 | Medium   | Open — documented in deployment guide |
| ISSUE-004 | Gateway SPI/GPIO cannot be tested in Docker sandbox | Medium   | Not tested — requires RPi hardware    |
| ISSUE-005 | MQTT forwarder clean_session=True                   | Medium   | Open — pending fix                    |
| ISSUE-006 | No HTTPS on Nginx                                   | High     | Open — future work                    |

---

## 24. Testing Results

Test suite is in `tests/`. Run with:

```bash
# Install test dependencies
pip install pytest paho-mqtt

# Run all tests
python -m pytest tests/ -v

# Run only gateway unit tests
python -m pytest tests/gateway/ -v

# Run only integration tests
python -m pytest tests/integration/ -v
```

**Test Status Summary:**

| Test Category                             | Tests | Status       | Hardware Required           |
| ----------------------------------------- | ----- | ------------ | --------------------------- |
| SQLite queue — insertion, duplicate, full | 15    | ✅ PASS       | No                          |
| Telemetry validator                       | 10    | ✅ PASS       | No                          |
| Telemetry normalizer                      | 8     | ✅ PASS       | No                          |
| MQTT forwarder (mocked)                   | 6     | ✅ PASS       | No                          |
| Pipeline end-to-end simulation            | 5     | ✅ PASS       | No                          |
| Offline buffering simulation              | 4     | ✅ PASS       | No                          |
| Core database writer (mocked)             | 5     | ✅ PASS       | No                          |
| LoRa SX1278 hardware reception            | —     | ⛔ NOT TESTED | Yes — SX1278 + RPi GPIO     |
| Live EMQX TLS connection                  | —     | ⛔ NOT TESTED | Yes — running EMQX instance |
| PostgreSQL TimescaleDB writes             | —     | ⛔ NOT TESTED | Yes — running PostgreSQL    |
| Dashboard React build                     | —     | ⛔ NOT TESTED | Yes — Node.js environment   |

---

## 25. Limitations

- **Physical hardware not tested**: LoRa SX1278, GPIO, SPI, real ESP32 connections require Raspberry Pi hardware.
- **No HTTPS**: Dashboard served over HTTP. See Security Roadmap for planned fix.
- **No JWT auth**: API authentication routes are commented out. All API endpoints are currently unauthenticated.
- **LoRa has no cryptographic protection**: Any node with the correct frequency and spreading factor can inject packets.
- **SQLite WAL**: Provides at-least-once delivery with QoS 1. Exactly-once is not guaranteed — deduplication on RPi 2 handles duplicates.
- **Wi-Fi reliability**: Wi-Fi is less reliable than Ethernet for the inter-Pi link. Ethernet is preferred.
- **TLS is server-authenticated only**: The gateway does not present a client certificate. mTLS would provide stronger assurance.

---

## 26. Future Improvements

- Implement JWT authentication and RBAC
- Add HTTPS with valid TLS certificate on Nginx
- Add mutual TLS on MQTT inter-Pi link
- Add HMAC-SHA256 packet authentication to LoRa nodes
- Add API rate limiting (slowapi or nginx limit_req_zone)
- Automate TLS certificate rotation
- Encrypt database backups with GPG
- Add Grafana dashboard alongside React dashboard
- Implement EMQX persistent sessions on gateway forwarder
- Add structured security audit log (SIEM integration)
- Add Prometheus metrics endpoint to gateway and backend
- Implement Alertmanager integration for alerts
- Add firmware OTA update mechanism
- Add MQTT v5 user properties for trace correlation
