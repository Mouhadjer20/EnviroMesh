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

The platform is split cleanly across two dedicated Raspberry Pi 4 Model B single-board computers:

### RPi 1 — Edge Gateway (`192.168.1.20`)
- **LoRa Receiver**: Direct SPI communication with the SX1278 RA-02 transceiver at 433 MHz.
- **Local EMQX Broker**: Lightweight MQTT 5.x broker listening on port 1883 for local Wi-Fi ESP32 nodes.
- **Telemetry Ingestion & Normalizer**: Extracts raw fields, validates constraints, computes a deterministic UUIDv5 message identifier, and normalizes payloads into a uniform JSON schema.
- **Signal Quality Telemetry**: Attaches hardware RSSI and SNR to received LoRa packets.
- **SQLite Persistent Queue**: FIFO buffer ensuring durability across reboots and network partitions.
- **MQTT Forwarder Service**: Dequeues messages and publishes them to RPi 2 with QoS 1 over TLS.
- **Health Monitor**: Periodically tracks queue depth, buffer utilization, and subsystem liveness.

### RPi 2 — Central Core (`192.168.1.5`)
- **Central EMQX Broker**: Production MQTT 5.x broker listening on port 8883 (TLS required for RPi 1 forwarder) and internal port 1883 for local backend subscribers.
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
| **RPi 1** | Local EMQX         | 1883  | TCP      | `0.0.0.0` (LAN)  | Ingestion from Wi-Fi ESP32 nodes       |
| **RPi 1** | EMQX Dashboard     | 18083 | TCP      | `127.0.0.1`      | Local broker administration            |
| **RPi 1** | SSH                | 22    | TCP      | LAN / Management | Linux maintenance                      |
| **RPi 2** | Central EMQX TLS   | 8883  | TCP/TLS  | `0.0.0.0` (LAN)  | Ingestion from RPi 1 Forwarder         |
| **RPi 2** | Central EMQX Local | 1883  | TCP      | Docker Network   | FastAPI subscriber ingestion           |
| **RPi 2** | EMQX Dashboard     | 18083 | TCP      | `127.0.0.1`      | Central broker administration          |
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

## 7. RPi 1 Gateway Setup & Operation

The gateway directory (`raspberry_pi/gateway/`) provides an independent deployment unit for RPi 1.

### Configuration (`.env`)
```bash
GATEWAY_ID=GW01
GATEWAY_LAN_IP=192.168.1.20

# Local EMQX broker
MQTT_BIND_IP=0.0.0.0
MQTT_LOCAL_PORT=1883
MQTT_LOCAL_USERNAME=gw_ingestion
MQTT_LOCAL_PASSWORD=StrongLocalPassword123

# Target Core Server (RPi 2)
MQTT_CORE_HOST=192.168.1.5
MQTT_CORE_PORT=8883
MQTT_CORE_USERNAME=gw_forwarder
MQTT_CORE_PASSWORD=StrongCorePassword456
MQTT_CORE_CA=/app/certs/core-ca.crt

# Queue & Forwarding Settings
QUEUE_MAX_MESSAGES=50000
FORWARD_BATCH_SIZE=10
FORWARD_RETRY_SECONDS=5
LOG_LEVEL=INFO
```

### Starting the Gateway
```bash
cd raspberry_pi/gateway
./../../scripts/setup_gateway.sh
./../../scripts/deploy_gateway.sh
```

---

## 8. RPi 2 Core Setup & Operation

The core directory (`raspberry_pi/core/`) provides the processing, database, backend, and dashboard stack.

### Configuration (`.env`)
```bash
APP_ENV=production
LOG_LEVEL=INFO
WEB_BIND_IP=0.0.0.0
WEB_PORT=8080

EMQX_DASHBOARD_PORT=18083
EMQX_DASHBOARD_USERNAME=admin
EMQX_DASHBOARD_PASSWORD=StrongAdminPassword789

MQTT_APP_USERNAME=enviromesh_backend
MQTT_APP_PASSWORD=StrongBackendPassword101

POSTGRES_DB=enviromesh
POSTGRES_USER=enviromesh_app
POSTGRES_PASSWORD=StrongDatabasePassword202

CORE_LAN_IP=192.168.1.5
GATEWAY_LAN_IP=192.168.1.20
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

## 10. TLS Certificate Setup

Inter-Pi communication requires a custom root Certificate Authority (CA) and an X.509 server certificate for RPi 2.

### Step 1: Generate PKI on RPi 2
```bash
cd raspberry_pi/core/emqx/certs

# Generate CA
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=EnviroMesh-Root-CA"

# Generate Server Key & CSR
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
    -subj "/C=FR/ST=IDF/L=Paris/O=EnviroMesh/CN=192.168.1.5"

# SAN extension config
cat > server_ext.cnf <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
IP.1 = 192.168.1.5
IP.2 = 127.0.0.1
DNS.1 = rpi2-core.local
DNS.2 = localhost
EOF

# Sign Server Certificate
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 3650 -sha256 -extfile server_ext.cnf

chmod 600 ca.key server.key
chmod 644 ca.crt server.crt
```

### Step 2: Copy CA Certificate to RPi 1
```bash
scp raspberry_pi/core/emqx/certs/ca.crt pi@192.168.1.20:/home/pi/enviromesh/raspberry_pi/gateway/certs/core-ca.crt
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
- **Dashboard UI**: `http://192.168.1.5:8080/`
- **FastAPI OpenAPI Docs**: `http://192.168.1.5:8080/api/docs`
- **Health Check**: `http://192.168.1.5:8080/api/health`

### Key Endpoints
- `GET /api/devices/`: List registered environmental nodes.
- `GET /api/devices/{device_id}`: Detailed telemetry and metadata for a specific node.
- `GET /api/telemetry/latest`: Latest readings across all active nodes.
- `GET /api/groups/`: Zone groupings and regional status summaries.

---

## 14. ESP32 Firmware Configuration

All Wi-Fi nodes must point to RPi 1 Gateway:
```c
// Example: firmware/nodes/node_g31/src/secrets.h
#define WIFI_SSID        "Warehouse_IoT_2.4G"
#define WIFI_PASSWORD    "WarehousePassword"
#define MQTT_BROKER_HOST "192.168.1.20"  // RPi 1 Gateway IP (NEVER RPi 2)
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

---

## 16. Deployment Procedures (Step-by-Step)

### Deploying RPi 2 (Core) First
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

### Deploying RPi 1 (Gateway)
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

EnviroMesh includes dedicated automated verification scripts:

### Gateway Verification (on RPi 1)
```bash
python3 scripts/check_gateway_health.py
```
Checks:
- Port 1883 (Local EMQX)
- SX1278 SPI interface availability
- SQLite queue integrity & pending count
- RPi 2 port 8883 TLS reachability

### Core Verification (on RPi 2)
```bash
python3 scripts/check_core_health.py
```
Checks:
- Ports 8883 & 1883 on Central EMQX
- TimescaleDB connectivity & latest ingested record
- FastAPI `/health` endpoint
- Nginx reverse proxy HTTP 200 response

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
