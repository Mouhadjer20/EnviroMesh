# Enterprise IoT Architecture: Technical Specification & Implementation Blueprint

**Project Title:** EnviroMesh

**Target Audience:** Development & Engineering Team

**Document Version:** 1.0

---

## 1. Executive Summary & System Overview

This document outlines the complete architectural blueprint for a secure, scalable, and polyglot IoT platform. The system integrates multiple communication protocols (**LoRA, Wi-Fi, BLE, Ethernet, MQTT, RTSP, HTTPS**) to handle environmental monitoring, video streaming, and local actuation, backed by a dual-database design (**SQL** for management/metadata and **NoSQL/Time-Series** for high-frequency telemetry) with strict **Role-Based Access Control (RBAC)**.

---

## 2. Hardware Topology & Communication Matrix

The network is divided into field sensor nodes, edge gateways, core servers, and user dashboards.

| Component | Hardware / Sensors | Communication Protocol | Target Destination | Role & Justification |
| --- | --- | --- | --- | --- |
| **ESP32 Node 1** (Group 1= G1) | MQ2 (Gas), DHT11 (Temp/Hum), Water sensor | LoRA (433 MHz) | RPi 1 (LoRA Gateway) | Long-range, low-power outdoor/industrial telemetry. |
| **ESP32 Node 2** (G4) | MQ2 (Gas), DHT11 (Temp/Hum), Water sensor | LoRA (433 MHz) | RPi 1 (LoRA Gateway) | Long-range, low-power outdoor/industrial telemetry. |
| **ESP32 Node 3** (G3) | BMP280, MQ-2, Water sensor | Wi-Fi (MQTT / TCP) | RPi 2 (Core Server) | Direct IP telemetry for local infrastructural nodes. |
| **ESP32 Servo Node** (G6) | MQ2 (Gas), DHT11 (Temp/Hum), Water sensor, Micro Servo 9g, RIP sensor | Wi-Fi (MQTT / TCP) | Local Operator / RPi BLE Proxy | Short-range secure valve/latch actuation. |
| **Raspberry Pi 1** | LoRA Concentrator (SX1302) | Ethernet (TCP/IP) | RPi 2 (Core Server) | Edge Gateway: translates RF LoRA frames into structured JSON/MQTT packets. |
| **Raspberry Pi 2** | Core Processing Server | HTTPS / WebSockets | User Dashboard | Core Server: hosts databases, MQTT broker, video proxy, and RBAC auth. |

---

## 3. Revised System Topology Diagram

```text
+==============================================================================================+
|                              FIELD SENSORS & ACTUATORS                                       |
+==============================================================================================+
|                                                                                              |
|     +------------------------+      +------------------------+                               |
|     | ESP32 NODE 1 (G1)      |      | ESP32 NODE 2 (G4)      |                               |
|     |------------------------|      |------------------------|                               |
|     | MQ-2  : Gas / Smoke    |      | MQ-2  : Gas / Smoke    |                               |
|     | DHT11 : Temp / Hum     |      | DHT11 : Temp / Hum     |                               |
|     | Water : Leak Detection |      | Water : Leak Detection |                               |
|     +-----------+------------+      +-----------+------------+                               |
|                 |                               |                                            |
|                 +---------------+---------------+                                            |
|                                 |                                                            |
|                          LoRa 433 MHz                                                        |
|                                 |                                                            |
|  +---------------------------+  |   +---------------------------+                            |
|  | ESP32 NODE 3 (G3)         |  |   | ESP32 SERVO NODE (G6)     |                            |
|  |---------------------------|  |   |---------------------------|                            |
|  | BMP280 : Pressure / Temp  |  |   | MQ-2    : Gas / Smoke     |                            |
|  | MQ-2   : Gas / Smoke      |  |   | DHT11   : Temp / Hum      |                            |
|  | Water  : Leak Detection   |  |   | Water   : Leak Detection  |                            |
|  |                           |  |   | PIR     : Motion Detection|                            |
|  | Wi-Fi / MQTT over TCP     |  |   | Servo   : Valve / Latch   |                            |
|  +-------------+-------------+  |   +-------------+-------------+                            |
|                |                |                 |                                          |
+================|================|=================|==========================================+
                 |                |                 |
                 | Wi-Fi /        |                 | Wi-Fi / MQTT over TCP
                 | MQTT over TCP  |                 |
                 v                v                 v
+==============================================================================================+
|                           EDGE & CORE PROCESSING LAYER                                       |
+==============================================================================================+
|                                                                                              |
|  +--------------------------------+      +------------------------------------------------+  |
|  | RASPBERRY PI 1                 |      | RASPBERRY PI 2                                 |  |
|  | LoRa EDGE GATEWAY              |      | CORE PROCESSING SERVER                         |  |
|  |--------------------------------|      |------------------------------------------------|  |
|  | LoRa Concentrator (SX1302)     |      | MQTT Broker (EMQX)                             |  |
|  | LoRa Frame Reception           |      | TimescaleDB                                    |  |
|  | RF-to-JSON Translation         |      | Telemetry & Provenance Storage                 |  |
|  | MQTT / TCP Forwarding          |      | MediaMTX Video Stream Proxy                    |  |
|  +----------------+---------------+      | BLE-to-MQTT Bridge (if BLE is used)            |  |
|                   |                      | Nginx Reverse Proxy                            |  |
|                   | Ethernet / TCP-IP    | Keycloak Authentication & RBAC                 |  |
|                   +--------------------->|                                                |  |
|                                          | MQTT Ingestion & Data Processing               |  |
|                                          +------------------------+-----------------------+  |
|                                                                   ^                          |
+===================================================================|==========================+
                                                                    |
                                         Wi-Fi / MQTT over TCP      |
                                         from ESP32 Node 3 & G6     |
                                                                    |
                                                                    |
+==============================================================================================+
|                                  VIDEO SUBSYSTEM                                             |
+==============================================================================================+
|                                                                                              |
|  +--------------------------+          Wi-Fi / RTSP          +----------------------------+  |
|  | ESP32-CAM (OPTIONAL)      | -----------------------------> | RPi 2: MediaMTX           |  |
|  | Video Capture             |                                | Video Stream Proxy        |  |
|  +--------------------------+                                +-------------+--------------+  |
|                                                                          |                   |
+==========================================================================|===================+
                                                                           |
                                                                           | HTTPS / WSS
                                                                           v
+==============================================================================================+
|                                   USER DASHBOARD                                             |
+==============================================================================================+
|                                                                                              |
|  +----------------------------------------------------------------------------------------+  |
|  | Web Interface                                                                          |  |
|  |                                                                                        |  |
|  | - Real-Time Sensor Telemetry                                                           |  |
|  | - Gas / Temperature / Humidity / Water / Pressure Monitoring                           |  |
|  | - Motion Detection & Actuator Status                                                   |  |
|  | - Video Monitoring (if ESP32-CAM is deployed)                                          |  |
|  | - Role-Based Access Control (RBAC)                                                     |  |
|  | - Zone-Scoped Access (Zone A / Zone B)                                                 |  |
|  | - Alerts, Events & Historical Data                                                     |  |
|  +----------------------------------------------------------------------------------------+  |
|                                                                                              |
+==============================================================================================+
```
## 4. Database Architecture (Polyglot Persistence)

To balance relational integrity with extreme write speeds, the system uses two distinct databases hosted on **Raspberry Pi 2**.

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

### Database 2: NoSQL / Time-Series (TimescaleDB / MongoDB) — *Telemetry Plane*

Stores high-frequency sensor readings, timestamps, and unstructured raw packets to prevent database bloat and optimize time-based queries.

* **Document / Table Schema (`sensor_telemetry`):**
* `timestamp` (Epoch / DateTime, Indexed)
* `device_id` (VARCHAR)
* `zone` (VARCHAR)
* `metrics` (JSON object containing dynamic keys like `gas_ppm`, `temperature_c`, `humidity`, `water_leak`)



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

### 5.2. ESP32 Node 1 — Group G1

**Hardware:** MQ-2, DHT11, Water Sensor  
**Communication:** LoRa at 433 MHz  
**Destination:** Raspberry Pi 1 (LoRa Gateway)  
**Device ID:** `G11` (example)

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
    "humidity_pct": 55.2,
    "water_leak_detected": false
  },
  "status": {
    "battery_voltage": 3.72,
    "rssi_dbm": -85,
    "snr_db": 7.2
  }
}
```

*Note: The gateway may need to append RSSI and SNR because these measurements are obtained by the receiving radio rather than necessarily by the transmitting ESP32.*

### 5.3. ESP32 Node 2 — Group G4

**Hardware:** MQ-2, DHT11, Water Sensor  
**Communication:** LoRa at 433 MHz  
**Destination:** Raspberry Pi 1  
**Device ID:** `G41` (example)

```json
{
  "timestamp": "2026-10-23T08:00:01Z",
  "device_id": "G41",
  "group_code": "G4",
  "zone": "Sector_B_Warehouse",
  "protocol": "lora",
  "metrics": {
    "gas_ppm": 38.1,
    "smoke_detected": false,
    "temperature_c": 24.1,
    "humidity_pct": 52.7,
    "water_leak_detected": false
  },
  "status": {
    "battery_voltage": 3.68,
    "rssi_dbm": -78,
    "snr_db": 8.4
  }
}
```

### 5.4. ESP32 Node 3 — Group G3

**Hardware:** BMP280, MQ-2, Water Sensor  
**Communication:** Wi-Fi / MQTT over TCP  
**Destination:** Raspberry Pi 2 (Core Server)  
**Device ID:** `G31` (example)

```json
{
  "timestamp": "2026-10-23T08:00:02Z",
  "device_id": "G31",
  "group_code": "G3",
  "zone": "Sector_C_Utility_Room",
  "protocol": "wifi_mqtt",
  "metrics": {
    "pressure_hpa": 1013.25,
    "bmp280_temperature_c": 24.6,
    "gas_ppm": 35.4,
    "smoke_detected": false,
    "water_leak_detected": false
  },
  "status": {
    "wifi_rssi_dbm": -62,
    "uptime_seconds": 45120
  }
}
```

*Note: BMP280 measures pressure and temperature, not humidity. MQ-2 gas readings are often raw or calibrated estimates; only label them `gas_ppm` when your calibration supports that unit.*

### 5.5. ESP32 Servo Node — Group G6

**Hardware:** MQ-2, DHT11, Water Sensor, PIR, Micro Servo 9g  
**Communication:** Wi-Fi / MQTT over TCP  
**Destination:** Raspberry Pi 2  
**Device ID:** `G61` (example)

```json
{
  "timestamp": "2026-10-23T08:00:03Z",
  "device_id": "G61",
  "group_code": "G6",
  "zone": "Sector_A_Valve",
  "protocol": "wifi_mqtt",
  "metrics": {
    "gas_ppm": 40.2,
    "smoke_detected": false,
    "temperature_c": 25.1,
    "humidity_pct": 57.0,
    "water_leak_detected": false,
    "motion_detected": true,
    "servo_current_angle_deg": 90,
    "servo_target_angle_deg": 90,
    "servo_operation_status": "position_reached"
  },
  "status": {
    "wifi_rssi_dbm": -60,
    "uptime_seconds": 45150
  }
}
```

Servo commands and acknowledgments should preferably use separate MQTT topics, rather than treating every actuator command as a sensor reading. The application should validate commands and enforce role-based permissions before allowing physical actuation.

### 5.6. Optional ESP32-CAM

The ESP32-CAM was not included in the current hardware and sensor tables. If you add it later, use a separate camera-status message and keep the video stream itself outside the telemetry database.

```json
{
  "timestamp": "2026-10-23T08:00:04Z",
  "device_id": "G62",
  "group_code": "G6",
  "zone": "Main_Gate",
  "protocol": "wifi_mqtt",
  "metrics": {
    "stream_active": true,
    "stream_id": "gate_cam",
    "resolution": "640x480",
    "fps": 15
  },
  "status": {
    "camera_state": "online"
  }
}
```

`G62` is an illustrative identifier, not an assigned device. Register it in `devices` before accepting its messages. The stream URL should be managed by the core server instead of being trusted from the camera payload.

---

### 5.7. Sensor Catalog and Metric Naming

Use the `sensors` table to maintain the canonical hardware catalog. Keep the JSON metric keys consistent across firmware versions.

| Sensor catalog name | Standardized metric keys |
|---|---|
| `MQ-2` | `gas_ppm`, `smoke_detected` |
| `DHT11` | `temperature_c`, `humidity_pct` |
| `Water Sensor` | `water_leak_detected` |
| `BMP280` | `pressure_hpa`, `bmp280_temperature_c` |
| `PIR` | `motion_detected` |

These are example metric conventions; your firmware must define the actual measurement semantics and units. The water sensor may provide only a wet/dry state, not a water level. The MQ-2 does not automatically provide reliable calibrated ppm values.

---

### 5.8. Future Sensor Expansion

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

### 5.9. TimescaleDB Integration

The standardized envelope maps to the `sensor_telemetry` table as follows:

| Payload field | Database field |
|---|---|
| `timestamp` | `timestamp` (`TIMESTAMPTZ`) |
| `device_id` | `device_id` (`VARCHAR(3)`) |
| `zone` | `zone` (`VARCHAR`) |
| `metrics` | `metrics` (`JSONB`) |
| `protocol` | `protocol` (`VARCHAR`) |
| `status` | `metadata` (`JSONB`), or a dedicated status structure |
| Server ingestion time | `received_at` (`TIMESTAMPTZ`) |

The `group_code` can be resolved to the relational group registry during ingestion. If you need it directly in telemetry queries, it can also be stored as denormalized metadata.

For LoRa nodes, Raspberry Pi 1 should decode the packet and construct the standardized JSON envelope before forwarding it to Raspberry Pi 2. Wi-Fi nodes can publish the same envelope directly through MQTT.

If you later use MongoDB, the envelope can be stored as a time-series document. With TimescaleDB, keep the same JSON payload contract and store `metrics` as `JSONB`.

---

### 5.10. Data Provenance and Security Requirements

1. **Device registration:** Reject telemetry from unregistered device IDs.
2. **Group consistency:** Verify that the device belongs to the group associated with its registry record.
3. **Timestamp validation:** Reject malformed or implausibly future-dated timestamps; define a tolerance for clock drift.
4. **Transport integrity:** Authenticate MQTT clients and protect network connections wherever supported.
5. **Data provenance:** Record gateway reception time, packet identifiers or sequence numbers when available, and relevant radio metadata.
6. **Access control:** Enforce group- and zone-scoped authorization in the core server, not through device-supplied fields.
7. **Actuator safety:** Separate telemetry from commands and require authorization, validation, and safe-state handling.
8. **Retention:** Configure telemetry retention according to project requirements and preserve selected events when audit or incident investigations require it.

This standardized schema provides a consistent foundation for the four registered ESP32 node types, the two Raspberry Pi processing layers, and future sensor extensions.
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

## 7. Implementation Roadmap for the Team

* **Phase 1: Core Server & Database Setup (RPi 2)**
* Install PostgreSQL and TimescaleDB/InfluxDB.
* Initialize tables for users, devices, and telemetry.
* Deploy an MQTT Broker (EMQX or Mosquitto).


* **Phase 2: Edge Gateway Integration (RPi 1)**
* Connect the LoRA concentrator module to RPi 1.
* Write a Python/Go daemon that receives raw LoRA packets, appends JSON metadata, and forwards them via MQTT to RPi 2.


* **Phase 3: Firmware Development (ESP32 Nodes)**
* *LoRA Nodes:* Program ESP32 + SX1276 to format JSON telemetry and transmit via LoRA.
* *Wi-Fi Nodes:* Program ESP32 water sensor to publish directly via MQTT over Wi-Fi.
* *ESP32-CAM:* Configure video streaming via RTSP using MediaMTX on RPi 2.
* *BLE Servo Node:* Implement a BLE GATT server on the ESP32 to receive encrypted rotation commands ($0^\circ$ to $180^\circ$).


* **Phase 4: Dashboard & Security Layer**
* Build the web UI with email/password login.
* Connect Grafana or a custom React dashboard to display real-time time-series charts filtered by user roles.

## 8. Start EnviroMesh

```bash
# Create your private environment file
cp .env.example .env
chmod 600 .env

# Edit passwords and network settings
nano .env

# Validate the Compose configuration
docker compose config

# Start the services
docker compose up -d

# Check service status and logs
docker compose ps
docker compose logs -f emqx timescaledb
```

## 8. Resources
1. [IoT Architecture](https://www.kaaiot.com/iot-knowledge-base/visualizing-iot-architecture-with-diagrams)
2. [IoT communication models](https://www.kaaiot.com/iot-knowledge-base/iot-communication-models-overview-types-use-cases-and-implementation-strategies)
3. [What is IoT architecture?](https://www.kaaiot.com/iot-knowledge-base/what-is-iot-architecture)
4. [Tool for esp connection PINs](https://fritzing.org)
5. [Tool for IoT Architecture](https://app.diagrams.net/)