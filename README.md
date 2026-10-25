# Enterprise IoT Architecture: Technical Specification & Implementation Blueprint

**Project Title:** EnviroMesh

**Target Audience:** Development & Engineering Team

**Document Version:** 1.0

---

## Table of Contents

- [1. Executive Summary & System Overview](#1-executive-summary--system-overview)
- [2. Hardware Topology & Communication Matrix](#2-hardware-topology--communication-matrix)
- [3. Revised System Topology Diagram](#3-revised-system-topology-diagram)
- [4. Database Architecture (Polyglot Persistence)](#4-database-architecture-polyglot-persistence)
  - [Database 1: SQL (PostgreSQL) — Control Plane & Metadata](#database-1-sql-postgresql--control-plane--metadata)
  - [Database 2: Time-Series (TimescaleDB) — Telemetry Plane](#database-2-time-series-timescaledb--telemetry-plane)
- [5. Standardized Data Provenance & Payload Structure](#5-standardized-data-provenance--payload-structure)
  - [5.1. Standard Payload Contract](#51-standard-payload-contract)
  - [5.2. Sensor Catalog and Metric Naming](#52-sensor-catalog-and-metric-naming)
  - [5.3. Future Sensor Expansion](#53-future-sensor-expansion)
  - [5.4. TimescaleDB Integration](#54-timescaledb-integration)
  - [5.5. Data Provenance and Security Requirements](#55-data-provenance-and-security-requirements)
  - [5.6. Backend Directory Structure (Python/FastAPI)](#56-backend-directory-structure-pythonfastapi)
- [6. Security Architecture & Access Control](#6-security-architecture--access-control-next-phase-not-including-in-this-phase-of-deployment-db-and-installation-devices)
  - [A. Authentication & RBAC](#a-authentication--rbac)
  - [B. Simulated Attack Vectors & Defensive Engineering](#b-simulated-attack-vectors--defensive-engineering)
- [7. Developer Automation & Helper Scripts (`scripts/`)](#7-developer-automation--helper-scripts-scripts)
- [8. Implementation Roadmap & Phase Status](#8-implementation-roadmap--phase-status)
- [9. Quick Start Guide](#9-quick-start-guide)
- [10. Resources & References](#10-resources--references)

---

## 1. Executive Summary & System Overview

This document outlines the complete architectural blueprint for a secure, scalable, and polyglot IoT platform. The system integrates multiple communication protocols (**LoRA, Wi-Fi, BLE, Ethernet, MQTT, RTSP, HTTPS**) to handle environmental monitoring, video streaming, and local actuation, backed by a dual-database design (**SQL** for management/metadata and **NoSQL/Time-Series** for high-frequency telemetry) with strict **Role-Based Access Control (RBAC)**.

---

## 2. Hardware Topology & Communication Matrix

The network is divided into field sensor nodes, edge gateways, core servers, and user dashboards.

| Component                       | Source File / Module                                                                       | Hardware / Sensors                                   | Protocol              | Destination            | Status               |
| ------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------- | --------------------- | ---------------------- | -------------------- |
| **ESP32 Node 1 (G11)**          | [`firmware/nodes/node_g11/src/main.ino`](firmware/nodes/node_g11/src/main.ino)             | MQ-2 (LPG model + NVS $R_0$), DHT11, Water sensor    | LoRa (433 MHz)        | RPi (LoRa Gateway)     | **Production-Ready** |
| **ESP32 Node 2 (G41)**          | [`firmware/nodes/node_g41/src/main/main.ino`](firmware/nodes/node_g41/src/main/main.ino)   | MQ-2, DHT11, Water sensor                            | LoRa (433 MHz)        | RPi (LoRa Gateway)     | **Production-Ready** |
| **ESP32 Node 3 (G31)**          | [`firmware/nodes/node_g31/src/main.ini`](firmware/nodes/node_g31/src/main.ini)             | BMP280, MQ-2, Water sensor                           | Wi-Fi (MQTT / TCP)    | EMQX Broker (`:1883`)  | Phase 3.1 Stub       |
| **ESP32 Servo Node (G61)**      | [`firmware/nodes/node_g61_servo/src/main.ini`](firmware/nodes/node_g61_servo/src/main.ini) | MQ-2, DHT11, Water, PIR, 9g Micro Servo              | Wi-Fi MQTT + BLE      | EMQX + Local Operator  | Phase 3.2 Stub       |
| **Test Node G42**               | [`firmware/nodes/node_g42/src/main/main.ino`](firmware/nodes/node_g42/src/main/main.ino)   | Wi-Fi Station + PubSubClient                         | Wi-Fi (MQTT / TCP)    | EMQX Broker (`:1883`)  | Test Harness         |
| **Test Node G43**               | [`firmware/nodes/node_g43/src/main/main.ino`](firmware/nodes/node_g43/src/main/main.ino)   | Schema-Compliant Telemetry Publisher                 | Wi-Fi (MQTT / TCP)    | EMQX Broker (`:1883`)  | Test Harness         |
| **Raspberry Pi Gateway & Core** | [`raspberry_pi/`](raspberry_pi/)                                                           | SX1278 SPI, EMQX Broker, TimescaleDB, FastAPI, Nginx | HTTPS, WSS, MQTT, SPI | User Dashboard & Admin | **Core Operational** |

---

## 3. Revised System Topology Diagram

```text
        +====================================================================+
        |                              FIELD SENSORS & ACTUATORS             |
        +====================================================================+
        |                                                                    |
        |     +------------------------+      +------------------------+     |
        |     | ESP32 NODE 1 (G1)      |      | ESP32 NODE 2 (G4)      |     |
        |     |------------------------|      |------------------------|     |
        |     | MQ-2  : Gas / Smoke    |      | MQ-2  : Gas / Smoke    |     |
        |     | DHT11 : Temp / Hum     |      | DHT11 : Temp / Hum     |     |
        |     | Water : Leak Detection |      | Water : Leak Detection |     |
        |     +-----------+------------+      +-----------+------------+     |
        |                 |                               |                  |
        |                 +---------------+---------------+                  |
        |                                 |                                  |
        |                          LoRa 433 MHz                              |
        |                                 |                                  |
        |  +---------------------------+  |   +---------------------------+  |
        |  | ESP32 NODE 3 (G3)         |  |   | ESP32 SERVO NODE (G6)     |  |
        |  |---------------------------|  |   |---------------------------|  |
        |  | BMP280 : Pressure / Temp  |  |   | MQ-2    : Gas / Smoke     |  |
        |  | MQ-2   : Gas / Smoke      |  |   | DHT11   : Temp / Hum      |  |
        |  | Water  : Leak Detection   |  |   | Water   : Leak Detection  |  |
        |  |                           |  |   | PIR     : Motion Detection|  |
        |  | Wi-Fi / MQTT over TCP     |  |   | Servo   : Valve / Latch   |  |
        |  +-------------+-------------+  |   +-------------+-------------+  |
        |                |                |                 |                |
        +================|================|=================|================+
                         |                |                 |
                         | Wi-Fi /        |                 | Wi-Fi / MQTT over TCP
                         | MQTT over TCP  |                 |
                         v                v                 v
        +====================================================================+
        |                           EDGE & CORE PROCESSING LAYER             |
        +====================================================================+
        |                                                                    |
        |        +------------------------------------------------+          |
        |        | RASPBERRY PI                                   |          |
        |        | CORE PROCESSING SERVER                         |          |
        |        |------------------------------------------------|          |
        |        | MQTT Broker (EMQX)                             |          |
        |        | TimescaleDB                                    |          |
        |        | Telemetry & Provenance Storage                 |          |
        |        | MediaMTX Video Stream Proxy                    |          |
        |        | BLE-to-MQTT Bridge (if BLE is used)            |          |
        |        | Nginx Reverse Proxy                            |          |
        |        | Keycloak Authentication & RBAC                 |          |
        |        | MQTT Ingestion & Data Processing               |          |
        |        | LoRa Frame Reception                           |          |
        |        | LoRa Concentrator (SX1278)                     |          |
        |        | MQTT Ingestion & Data Processing               |          |
        |        +------------------------+-----------------------+          |
        |                                 ^                                  |
        +=================================|==================================+
                                          |
               Wi-Fi / MQTT over TCP      |
               from ESP32 Node 3 & G6     |
                                          |
                                          |
        +=====================================================================+
        |                                  VIDEO SUBSYSTEM                    |
        +=====================================================================+
        |                                                                     |
        |  +---------------------+   Wi-Fi / RTSP   +----------------------+  |
        |  | ESP32-CAM (OPTIONAL)| ---------------> | RPi: MediaMTX        |  |
        |  | Video Capture       |                  | Video Stream Proxy   |  |
        |  +---------------------+                  +-------------+--------+  |
        |                                                         |           |
        +=========================================================|===========+
                                                                  |
                                                  HTTPS / WSS     | 
                                                                  v
        +=====================================================================+
        |                           USER DASHBOARD                            |
        +=====================================================================+
        |                                                                     |
        |  +---------------------------------------------------------------+  |
        |  | Web Interface                                                 |  |
        |  |                                                               |  |
        |  | - Real-Time Sensor Telemetry                                  |  |
        |  | - Gas / Temperature / Humidity / Water / Pressure Monitoring  |  |
        |  | - Motion Detection & Actuator Status                          |  |
        |  | - Video Monitoring (if ESP32-CAM is deployed)                 |  |
        |  | - Role-Based Access Control (RBAC)                            |  |
        |  | - Zone-Scoped Access (Zone A / Zone B)                        |  |
        |  | - Alerts, Events & Historical Data                            |  |
        |  +---------------------------------------------------------------+  |
        |                                                                     |
        +=====================================================================+
```
## 4. Database Architecture (Polyglot Persistence)

To balance relational integrity with extreme write speeds, the system uses two distinct databases hosted on **Raspberry Pi**.

### Database 1: SQL (PostgreSQL) — *Control Plane & Metadata*

Stores user identities, password hashes, RBAC permissions, and the physical asset registry (mapping exact device IDs to physical zones and responsible technicians).

* **Table: `groups`**
    * `id` (UUID, primary Key)
    * `group_code` (VARCHAR(2), UNIQUE, NOT NULL — e.g., G1, G3, G4, G6)
    * `Description` (Text)

* **Table: `users`**
    * `id` (UUID, Primary Key)
    * `first_name` (VARCHAR, NOT NULL)
    * `last_name` (VARCHAR, NOT NULL)
    * `email` (VARCHAR, Unique)
    * `password` (VARCHAR, hash)
    * `group_id` (int)
    * `role` (VARCHAR: `admin`, `zone_technician`)

* **Table: `Sensors`**
    * `id` (UUID, Primary Key)
    * `name` (VARCHAR, NOT NULL)
    * `Description` (VARCHAR)

* **Table: `devices`**
    * `device_id` (VARCHAR(3), Primary Key - `<GROUPE_ID>+<INT_GENERATED>` e.g., `G1<1-9>`)
    * `zone` (VARCHAR - e.g., `Sector_A_Warehouse`)
    * `latitude` / `longitude` (FLOAT)
    * `group_id` (UUID, Foreign Key to `groups`)

* **Table: `sensor_devices`**
  * `id` (UUID, Primary Key)
  * `sensor_id` (UUID, Foreign Key referencing sensors.id, NOT NULL)
  * `device_id` (VARCHAR(3), Foreign Key referencing devices.device_id, NOT NULL)
  * `installed_at` (TIMESTAMPTZ, NOT NULL, DEFAULT CURRENT_TIMESTAMP)
  * `status` (VARCHAR, NOT NULL, DEFAULT active)
  * `configuration` (JSONB, optional — sensor-specific settings)
  * `UNIQUE(sensor_id, device_id)` — prevents duplicate sensor-device assignments

### Database 2: Time-Series (TimescaleDB) — *Telemetry Plane*

Stores high-frequency sensor readings, timestamps, and unstructured raw packets to prevent database bloat and optimize time-based queries.

* **Document / Table Schema (`sensor_telemetry`):**
* `timestamp` (DateTime, Indexed)
* `device_id` (VARCHAR)
* `zone` (VARCHAR)
* `metrics` (JSON object containing dynamic keys like `gas_ppm`, `temperature_c`, `humidity`, `water_leak`)
* `received_at` (DateTime)
* `protocol` 
* `metadata` (JSON Object containing static information about device like `group_code`, `firmware_version`, `sensor_id`, `device_id`)



---

## 5. Standardized Data Provenance & Payload Structure

Every field device must attach standardized metadata to its telemetry messages. This enables the core server to identify the originating device, its group, its deployment zone, the communication protocol, and the measurements reported by each sensor.

The system uses a **polymorphic JSON payload**: every message shares the same top-level structure, while the `metrics` object varies according to the sensor types installed on the device.

### 5.1. Standard Payload Contract

All telemetry-producing nodes should follow this structure:

```json
{
  "timestamp": "2026-10-23T08:00:00Z",
  "device_id": "G11",
  "group_code": "G1",
  "zone": "Sector_A_Warehouse",
  "protocol": "lora",
  "metrics": {
    "gas_ppm": 42.5,
    "smoke_detected": false,
    "temperature_c": 23.8,
    "humidity_pct": 55.2
  },
  "status": { // Optional (Sa9sit gpt aya madli had les informations)
    "battery_voltage": 3.72,
    "rssi_dbm": -85,
    "snr_db": 7.2
  }
}
```

**Standardization rules:**

- `timestamp`: UTC measurement time in ISO 8601 format. The ingestion service converts it to PostgreSQL `TIMESTAMPTZ`.
- `device_id`: physical device identifier referencing `devices.device_id`.
- `group_code`: group identifier referencing `groups.group_code`, such as `G1`, `G3`, `G4`, or `G6`.
- `zone`: deployment zone recorded in the device registry.
- `protocol`: actual transport, such as `lora` or `wifi_mqtt`.
- `metrics`: sensor measurements and detection states.
- `status`: optional device-health and communication diagnostics.

The server should validate the device ID, group assignment, allowed metric names, value types, timestamp, and payload size before storing the message.

The database registry remains authoritative for device ownership and location. Device-reported metadata should not override trusted registry values.

---

### 5.2. Sensor Catalog and Metric Naming

Use the `sensors` table to maintain the canonical hardware catalog. Keep the JSON metric keys consistent across firmware versions.

| Sensor catalog name | Standardized metric keys               |
| ------------------- | -------------------------------------- |
| `MQ-2`              | `gas_ppm`, `smoke_detected`            |
| `DHT11`             | `temperature_c`, `humidity_pct`        |
| `Water Sensor`      | `water_leak_detected`                  |
| `BMP280`            | `pressure_hpa`, `bmp280_temperature_c` |
| `PIR`               | `motion_detected`                      |

These are example metric conventions; your firmware must define the actual measurement semantics and units. The water sensor may provide only a wet/dry state, not a water level. The MQ-2 does not automatically provide reliable calibrated ppm values.

---

### 5.3. Future Sensor Expansion

Future projects can use the same top-level contract without changing the database table structure.

Example metric objects:

**Light sensor**
```json
{
  "ambient_light_lux": 450.0,
  "darkness_detected": false
}
```

**Flame sensor**
```json
{
  "flame_detected": true,
  "infrared_intensity_raw": 890
}
```

**Ultrasonic distance sensor**
```json
{
  "distance_cm": 125.4,
  "tank_level_pct": 75.0
}
```

These are extension examples, not sensors currently registered in the catalog. Add their canonical definitions to `sensors` and their assignments to `sensor_devices` before deployment.

---

### 5.4. TimescaleDB Integration

The standardized envelope maps to the `sensor_telemetry` table as follows:

| Payload field         | Database field                                        |
| --------------------- | ----------------------------------------------------- |
| `timestamp`           | `timestamp` (`TIMESTAMPTZ`)                           |
| `device_id`           | `device_id` (`VARCHAR(3)`)                            |
| `zone`                | `zone` (`VARCHAR`)                                    |
| `metrics`             | `metrics` (`JSONB`)                                   |
| `protocol`            | `protocol` (`VARCHAR`)                                |
| `status`              | `metadata` (`JSONB`), or a dedicated status structure |
| Server ingestion time | `received_at` (`TIMESTAMPTZ`)                         |

The `group_code` can be resolved to the relational group registry during ingestion. If you need it directly in telemetry queries, it can also be stored as denormalized metadata.

For LoRa nodes, Raspberry Pi should decode the packet and construct the standardized JSON envelope. Wi-Fi nodes can publish the same envelope directly through MQTT.

With TimescaleDB, keep the same JSON payload contract and store `metrics` as `JSONB`.

---

### 5.5. Data Provenance and Security Requirements

1. **Device registration:** Reject telemetry from unregistered device IDs.
2. **Group consistency:** Verify that the device belongs to the group associated with its registry record.
3. **Timestamp validation:** Reject malformed or implausibly future-dated timestamps; define a tolerance for clock drift.
4. **Transport integrity:** Authenticate MQTT clients and protect network connections wherever supported.
5. **Data provenance:** Record gateway reception time, packet identifiers or sequence numbers when available, and relevant radio metadata.
6. **Access control:** Enforce group- and zone-scoped authorization in the core server, not through device-supplied fields.
7. **Actuator safety:** Separate telemetry from commands and require authorization, validation, and safe-state handling.
8. **Retention:** Configure telemetry retention according to project requirements and preserve selected events when audit or incident investigations require it.

This standardized schema provides a consistent foundation for the four registered ESP32 node types, the two Raspberry Pi processing layers, and future sensor extensions.

### 5.6. Backend Directory Structure (Python/FastAPI)

The core server backend was restructured into `raspberry_pi/backend/` with a
clean separation between API routes, business services, and infrastructure.

#### 5.6.1. Python Package Layout

```
raspberry_pi/backend/
├── main.py                       # Entry point: FastAPI app + MQTT subscriber loop
├── requirements.txt              # Python runtime dependencies
├── Dockerfile                    # Container image (python:3.11-slim)
├── README.md                     # README file
├── routes/                       # FastAPI route modules (absolute imports)
│   ├── __init__.py
│   ├── devices.py                # GET/POST/PUT/DELETE /devices
│   ├── telemetry.py              # GET /telemetry, GET /telemetry/{id}/latest
│   ├── alerts.py                 # GET/POST /alerts, PATCH /alerts/{id}/ack
│   └── users.py                  # User management endpoints
│
├── auth/                         # Authentication routes
│   └── README.md                 # README file
│
└── services/                     # Business logic services
    ├── __init__.py
    ├── mqtt_subscriber.py        # Paho-MQTT client; subscribes, validates, persists
    ├── database_writer.py        # TimescaleDB/PostgreSQL writer (psycopg2)
    ├── lora_receiver.py          # LoraWAN receiver (sx1278 driver)
    └── telemetry_validator.py    # Validates telemetry metrics & ranges
```

#### 5.6.2. Running the Backend

From the `backend/` directory:
```bash
cd raspberry_pi/backend
python main.py
```

## 6. Security Architecture & Access Control (NEXT PHASE, not including in this phase of Deployment DB and installation devices)

### A. Authentication & RBAC

* **Login Portal:** Users log in with their **email and password** via a React/Grafana web frontend backed by an authentication server (Keycloak or custom JWT middleware).
* **Token Claims:** Successful authentication generates a **JSON Web Token (JWT)** containing user permissions:
```json
{
  "sub": "user_id_123",
  "email": "technician@etu.univ-usto.dz",
  "role": "zone_technician",
  "allowed_zones": ["Sector_A_Warehouse"]
}

```


* **MQTT Topic ACLs:** The MQTT broker enforces topic isolation. A technician assigned to *Sector A* can only subscribe to `factory/sector_a/#` and cannot access video or water sensor feeds from other zones.

### B. Simulated Attack Vectors & Defensive Engineering

To validate system robustness, your team should execute these simulated security drills and to make this architecture truly professional, implement and test the following security layers:
1. **Man-in-the-Middle (MitM) Sniffing:**
* *Simulation:* Use an SDR or Wi-Fi packet sniffer to capture unencrypted sensor packets.
* *Defense:* Enforce **AES-128 payload encryption** at the application layer for LoRA nodes and **TLS 1.3 / MQTT over SSL (port 8883)** for Wi-Fi nodes.


2. **Broken Object Level Authorization (BOLA):**
* *Simulation:* Intercept dashboard API requests and alter the zone ID parameter in the JWT token to view unauthorized camera streams.
* *Defense:* Implement strict server-side middleware validating that the user's `allowed_zones` claim matches the requested device's zone in PostgreSQL.


3. **BLE Replay Attack:**
* *Simulation:* Sniff BLE command packets sent to the 9g servo motor and replay them to trigger unauthorized actuation.
* *Defense:* Implement secure BLE bonding with rotating challenge-response tokens in the ESP32 firmware.

### 1. Simulated Threat: Man-in-the-Middle (MitM) / Packet Sniffing on LoRA/Wi-Fi

* **Attack Simulation:** Use an SDR (Software Defined Radio) or a Wi-Fi deauthenticator tool to capture raw unencrypted packets floating between nodes.
* **Professional Defense:**
* Implement **AES-128 payload encryption** at the application layer for all LoRA packets.
* Enforce **WPA3-Enterprise** or TLS-secured MQTT (MQTT over SSL/TLS on port 8883) between the gateways and the core server.



### 2. Simulated Threat: Unauthorized API / Dashboard Intrusion (Broken Object Level Authorization)

* **Attack Simulation:** Attempt to bypass the login portal or manipulate JWT tokens to access sensor data from restricted zones.
* **Professional Defense:**
* Enforce strict **RBAC claims inside signed JWT tokens**.
* Validate topic-level permissions on the MQTT broker (`acl.conf`) so a client connected with Zone 2 credentials cannot subscribe to Zone 1 topics.



### 3. Simulated Threat: Firmware Tampering / Physical Node Hijacking

* **Attack Simulation:** Extract the ESP32 flash memory or intercept the serial/BLE configuration interface.
* **Professional Defense:**
* Enable **ESP32 Secure Boot V2** and **Flash Encryption**.
* Require encrypted BLE pairing PINs or key exchanges before allowing the servo motor to accept motion commands.

---

## 7. Developer Automation & Helper Scripts (`scripts/`)

To streamline testing, deployment, and validation without needing manual complex commands, the project includes an automated toolchain in [`scripts/`](scripts/):

| Script                                                   | Purpose                                                                                      | Example Usage                                                 |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| [`setup_env.sh`](scripts/setup_env.sh)                   | Sets up `.env`, directory structure, permissions, and Python virtual environment             | `./scripts/setup_env.sh`                                      |
| [`docker_control.sh`](scripts/docker_control.sh)         | Controls the entire container stack (`emqx`, `timescaledb`, `backend`, `dashboard`, `nginx`) | `./scripts/docker_control.sh start`                           |
| [`db_manage.sh`](scripts/db_manage.sh)                   | Manages PostgreSQL & TimescaleDB migrations, seeds, verification, and `psql` shell           | `./scripts/db_manage.sh init`                                 |
| [`simulate_telemetry.py`](scripts/simulate_telemetry.py) | Generates and publishes synthetic sensor readings over MQTT with anomaly injection           | `./scripts/simulate_telemetry.py --device G11 --interval 2.0` |
| [`mqtt_monitor.py`](scripts/mqtt_monitor.py)             | Real-time terminal telemetry monitor subscribing to `enviromesh/#`                           | `./scripts/mqtt_monitor.py`                                   |
| [`check_health.py`](scripts/check_health.py)             | Diagnostic tool testing Nginx, FastAPI backend, EMQX broker, and TimescaleDB                 | `./scripts/check_health.py`                                   |
| [`lora_packet_inject.py`](scripts/lora_packet_inject.py) | Tests the LoRa packet processing pipeline without physical SX1278 hardware                   | `./scripts/lora_packet_inject.py --device G11`                |

Full documentation for each script is available in [`scripts/README.md`](scripts/README.md).

---

## 8. Implementation Roadmap & Phase Status

### Phase 1: Core Server & Database Setup (RPi) — [COMPLETED]
- [x] Docker Compose stack definition (`emqx`, `timescaledb`, `backend`, `dashboard`, `nginx`).
- [x] Relational metadata schema (`groups`, `users`, `sensors`, `devices`, `sensor_devices`).
- [x] TimescaleDB hypertables (`sensor_telemetry`, `raw_sensor_packets`) with optimized time/device indexes.
- [x] Seed data provisioning: groups G1–G7, 20+ student technician accounts, and 14 device-sensor assignments.

### Phase 2: Edge Gateway & Ingestion Services (RPi) — [COMPLETED]
- [x] Paho-MQTT subscriber daemon subscribing to `enviromesh/devices/+/telemetry` (`services/mqtt_subscriber.py`).
- [x] Hardware SPI LoRa frame receiver for SX1278 (`services/lora_receiver.py`).
- [x] Telemetry schema validation and range boundary checks (`services/telemetry_validator.py`).
- [x] Multi-threaded concurrent ingestion loop in `main.py`.
- [x] Reverse proxy configuration routing `/` to dashboard and `/api/` to backend (`infrastructure/nginx/default.conf`).

### Phase 3: Field Firmware Development (ESP32 Nodes) — [PARTIAL / IN PROGRESS]
- [x] **Node G11 (Group 1 LoRa):** Implemented in [`firmware/nodes/node_g11/src/main.ino`](firmware/nodes/node_g11/src/main.ino) with MQ-2 LPG regression, clean-air NVS calibration, DHT11, and Ra-02 LoRa transceiver.
- [x] **Node G41 (Group 4 LoRa):** Implemented in [`firmware/nodes/node_g41/src/main/main.ino`](firmware/nodes/node_g41/src/main/main.ino) with MQ-2, DHT11, and Water sensor.
- [x] **Test Nodes G42 & G43 (Wi-Fi MQTT):** Implemented in [`firmware/nodes/node_g42/`](firmware/nodes/node_g42/) and [`firmware/nodes/node_g43/`](firmware/nodes/node_g43/).
- [x] **ESP-NOW to LoRa Dual-Radio Bridge:** Prototyped in [`my_files/esp_now_LoRa/`](my_files/esp_now_LoRa/) and [`my_files/sensor_esp_now/`](my_files/sensor_esp_now/).
- [ ] **Node G31 (Group 3 Wi-Fi):** Finalize BMP280 barometric pressure and MQ-2 acquisition over Wi-Fi MQTT.
- [ ] **Node G61 (Group 6 Servo):** Finalize Micro Servo 9g PWM control, PIR motion interrupt, and BLE GATT server for local actuation.

### Phase 4: API Routes, Security Layer & Web Dashboard — [IN PROGRESS / UPCOMING]
- [ ] Connect FastAPI routes to database:
  - `routes/devices.py`: Query `devices` and `sensor_devices` tables.
  - `routes/telemetry.py`: Query `sensor_telemetry` hypertable (`start`, `end`, `limit`) and latest readings.
  - `routes/alerts.py`: Automatic threshold alerts (e.g. `gas_ppm > 2000` or `water_leak == 1`).
  - `routes/users.py`: User profile management.
- [ ] Implement JWT Authentication & RBAC in `backend/auth/` (email/password verification against bcrypt hashes).
- [ ] Build interactive Web Dashboard with dynamic time-series charts (Chart.js / React) and zone filtering.
- [ ] Configure EMQX topic ACLs (`acl.conf`) to enforce zone-scoped permissions.

### Phase 5: Hardware Field Testing & Video Subsystem — [UPCOMING]
- [ ] Deploy MediaMTX RTSP proxy on RPi for ESP32-CAM video capture.
- [ ] Field range testing: evaluate LoRa 433 MHz link budget, RSSI, and SNR from 100m to 1km.
- [ ] Power optimization: implement ESP32 deep-sleep cycles on battery-powered sensor nodes.
- [ ] Systemd service provisioning for unattended gateway auto-start.

---

## 9. Quick Start Guide

### Step 1: Initialize Workspace & Environment
```bash
# Clone the repository and run the setup script:
./scripts/setup_env.sh
```

### Step 2: Launch the Docker Stack
```bash
./scripts/docker_control.sh start
```

### Step 3: Initialize & Seed the Database
```bash
./scripts/db_manage.sh init
```

### Step 4: Verify Stack Health
```bash
./scripts/check_health.py
```

### Step 5: Simulate Telemetry & Monitor Live Stream
Open two terminal windows:
```bash
# Terminal 1: Monitor live MQTT traffic
./scripts/mqtt_monitor.py

# Terminal 2: Emit simulated sensor readings
./scripts/simulate_telemetry.py --device all --interval 1.5
```

Access the web interface at **`http://localhost:8080`** and the EMQX console at **`http://localhost:18083`** (`admin`).

---

## 10. Resources & References

1. [IoT Architecture Visualization](https://www.kaaiot.com/iot-knowledge-base/visualizing-iot-architecture-with-diagrams)
2. [IoT Communication Models Overview](https://www.kaaiot.com/iot-knowledge-base/iot-communication-models-overview-types-use-cases-and-implementation-strategies)
3. [TimescaleDB Documentation](https://docs.timescale.com/)
4. [EMQX 5 Broker Documentation](https://www.emqx.io/docs/en/latest/)
5. [FastAPI Documentation](https://fastapi.tiangolo.com/)
6. [Fritzing Wiring Tool](https://fritzing.org)
7. [Diagrams.net Architecture Tool](https://app.diagrams.net/)
8. [MQTT Tutorial for Beginners](https://www.youtube.com/watch?v=kuyCd53AOtg)