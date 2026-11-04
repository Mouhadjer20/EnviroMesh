# EnviroMesh — Architecture Report

**Version:** 2.0  
**Branch:** `mouhadjer`  
**Date:** 2026-11-04  

---

## 1. What Changed and Why

EnviroMesh was migrated from a **single-Raspberry-Pi** architecture (all components on one device) to a **two-Raspberry-Pi** architecture with a dedicated edge gateway and a central processing server.

### Motivations

| Problem with Single-Pi                                       | Solution in Two-Pi Architecture                                 |
| ------------------------------------------------------------ | --------------------------------------------------------------- |
| LoRa reception and central dashboard competed for CPU/memory | LoRa and MQTT ingestion isolated on RPi 1                       |
| System reboot or update interrupts data collection           | RPi 1 continues collecting even if RPi 2 is rebooted            |
| No offline buffering — data lost during maintenance          | SQLite WAL queue on RPi 1 survives power cuts and RPi 2 outages |
| PostgreSQL, EMQX, FastAPI, and LoRa all on one device        | Each device has a focused, maintainable responsibility          |
| No TLS between MQTT clients and broker                       | TLS on port 8883 for inter-Pi MQTT forwarding                   |
| No duplicate detection                                       | `processed_messages` table ensures at-most-once storage         |

---

## 2. Component Responsibilities

### RPi 1 — Gateway (`raspberry_pi/gateway/`)

| Component            | File                              | Responsibility                                                                     |
| -------------------- | --------------------------------- | ---------------------------------------------------------------------------------- |
| Local EMQX           | `emqx/emqx.conf`, `emqx/acl.conf` | Receives WiFi ESP32 MQTT telemetry; per-device ACLs                                |
| LoRa receiver        | `gateway/lora_receiver.py`        | SX1278 SPI, 433 MHz, SF7, BW125; extracts RSSI/SNR                                 |
| Telemetry validator  | `gateway/telemetry_validator.py`  | Range checks; rejects malformed or out-of-range packets                            |
| Telemetry normalizer | `gateway/telemetry_normalizer.py` | Adds message_id (UUIDv5 for LoRa, UUID4 for WiFi), gateway_id, gateway_received_at |
| SQLite queue         | `gateway/sqlite_queue.py`         | WAL+FULL sync persistent buffer; enqueue/get_batch/mark_sent/mark_attempt          |
| MQTT ingestion       | `gateway/mqtt_ingestion.py`       | Subscribes to local EMQX; validates, normalizes, enqueues WiFi telemetry           |
| MQTT forwarder       | `gateway/mqtt_forwarder.py`       | Dequeues batches, publishes QoS 1 to core EMQX over TLS; deletes only on PUBACK    |
| Health monitor       | `gateway/health_monitor.py`       | Tracks queue depth, oldest message age, forwarder state                            |
| Config               | `gateway/config.py`               | 100% environment-variable driven; no hardcoded IPs/passwords                       |

### RPi 2 — Core (`raspberry_pi/core/`)

| Component       | Location                              | Responsibility                                                        |
| --------------- | ------------------------------------- | --------------------------------------------------------------------- |
| Central EMQX    | `emqx/`                               | TLS on 8883; receives forwarded telemetry from RPi 1                  |
| TimescaleDB     | `database/migrations/`                | Hypertable on `telemetry`; `processed_messages` for deduplication     |
| FastAPI backend | `backend/`                            | MQTT subscriber; database writer; REST API; WebSocket                 |
| MQTT subscriber | `backend/services/mqtt_subscriber.py` | Subscribes to `enviromesh/gateway/+/telemetry`                        |
| Database writer | `backend/services/database_writer.py` | Transactional dedup via `processed_messages` before writing telemetry |
| React dashboard | `dashboard/`                          | Vite SPA; communicates only with FastAPI                              |
| Nginx           | `nginx/default.conf`                  | Reverse proxy; `/api` → backend:8000; `/` → dashboard                 |

---

## 3. Data Flow

```
ESP32 LoRa nodes (G11, G41)
    │  LoRa 433 MHz packets
    ▼
RPi 1 — SX1278 SPI receiver
    │  lora_receiver.py decodes packet, reads RSSI/SNR
    │  telemetry_validator.py validates ranges
    │  telemetry_normalizer.py adds message_id (UUIDv5), gateway metadata
    ▼
SQLite persistent queue (WAL + FULL sync)
    │  mqtt_forwarder.py dequeues batches (QoS 1)
    │  mark_sent() called only on PUBACK receipt
    │  Exponential backoff: 5 s → 10 s → … → 60 s max
    │  MQTT over TLS (port 8883)
    ▼
RPi 2 — Central EMQX
    │  Topic: enviromesh/gateway/+/telemetry
    ▼
FastAPI MQTT subscriber
    │  services/database_writer.py
    │  INSERT INTO processed_messages — deduplicate by message_id
    │  INSERT INTO telemetry — TimescaleDB hypertable
    ▼
PostgreSQL + TimescaleDB (internal Docker network — no LAN exposure)
    ▼
FastAPI REST API / WebSocket
    ▼
Nginx (port 8080)
    ▼
React + Vite Dashboard (browser)
```

**WiFi ESP32 nodes follow the same path, but entry point is local EMQX on RPi 1 instead of LoRa.**

---

## 4. MQTT Broker Architecture

The two EMQX brokers are **independent, non-clustered** brokers.

| Property     | RPi 1 Local EMQX                            | RPi 2 Central EMQX                            |
| ------------ | ------------------------------------------- | --------------------------------------------- |
| Role         | Edge ingestion                              | Centralized processing                        |
| Accepts from | Wi-Fi ESP32 nodes (port 1883)               | RPi 1 gateway forwarder (port 8883 TLS)       |
| Accepts from | Gateway Python services (internal)          | FastAPI backend subscriber (internal)         |
| TLS          | Not on inbound (LAN only)                   | TLS on 8883                                   |
| Dashboard    | 127.0.0.1:18083                             | 127.0.0.1:18083                               |
| ACL          | Per-device publish topics, deny-all default | Only gw_forwarder publishes gateway telemetry |

**Why MQTT and not HTTP?**  
MQTT is chosen for telemetry forwarding because:
- Native QoS 1 (at-least-once) with PUBACK acknowledgment
- Persistent sessions (optional) for durability across broker restarts
- Low overhead compared to HTTP for high-frequency sensor data
- Established pattern for IoT gateway-to-cloud forwarding

---

## 5. Offline Recovery Mechanism

The SQLite queue provides the core offline resilience guarantee:

1. Gateway validates and normalizes incoming telemetry
2. Message is **durably written to SQLite** (WAL + FULL synchronous) before any acknowledgment
3. MQTT forwarder publishes to core EMQX with QoS 1
4. `mark_sent()` is called **only inside `on_publish` callback** (after PUBACK)
5. If RPi 2 is unreachable: messages accumulate in SQLite (up to `QUEUE_MAX_MESSAGES = 50,000`)
6. When RPi 2 recovers: forwarder drains the queue automatically
7. Core's `processed_messages` table ensures duplicates are not stored twice

**Delivery guarantee:** At-least-once (QoS 1). Exactly-once is not provided. Deduplication handles the rare duplicate.

---

## 6. Security Architecture

### Implemented
- TLS on MQTT inter-Pi link (port 8883) with certificate verification
- EMQX ACL — per-device publish restrictions, deny-all default
- PostgreSQL has no host port binding (not accessible from LAN)
- EMQX dashboard bound to 127.0.0.1 only
- Gateway uses specific device mappings (`/dev/spidev0.0`, `/dev/gpiomem`) — no full `/dev` passthrough
- Secrets externalized in `.env` files (committed files are `.env.example` only)
- `.gitignore` protects TLS certs, `.env` files, SQLite queue files, and backups

### Not Yet Implemented (Future Work)
- HTTPS on Nginx (HTTP only on port 8080)
- JWT authentication (routes commented out in backend/main.py)
- Mutual TLS (client certificate from gateway)
- LoRa packet HMAC authentication
- API rate limiting
- Encrypted database backups
- MQTT persistent sessions on forwarder

---

## 7. Database Design

### Key Tables

**`telemetry`** (TimescaleDB hypertable, partitioned by `received_at`)
- `id`, `device_id`, `temperature`, `humidity`, `gas_level`, `water_detected`
- `received_at` — TimescaleDB partition key
- `message_id`, `gateway_id`, `gateway_received_at` — added in migration 003

**`processed_messages`** (deduplication table)
- `message_id TEXT PRIMARY KEY` — unique constraint enforces idempotent processing
- `received_at` — when the core received it
- Atomic transaction: INSERT into `processed_messages` → then INSERT into `telemetry`
- If `processed_messages` INSERT fails (duplicate), the outer transaction rolls back

**`devices`** — device registry (G11, G31, G41, G61, etc.)

### Migrations
- `001_create_registry.sql` — devices, groups, sensors tables
- `001_create_telemetry.sql` — telemetry hypertable, TimescaleDB extension
- `003_add_gateway_metadata.sql` — message_id, gateway_id columns + processed_messages table

---

## 8. ESP32 Firmware Preservation

| Device | Communication | Actual Pin Assignments                                                                                                                                     | Status    |
| ------ | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| G11    | LoRa 433 MHz  | DHT=GPIO4, MQ2_AO=GPIO0, MQ2_DO=GPIO2, WATER=GPIO15, LORA_SS=GPIO16, LORA_RST=GPIO14, LORA_DIO0=GPIO26, LORA_SCK=GPIO5, LORA_MISO=GPIO19, LORA_MOSI=GPIO32 | Preserved |
| G41    | LoRa 433 MHz  | Same pin assignments as G11                                                                                                                                | Preserved |
| G31    | Wi-Fi MQTT    | MQ2=GPIO34, WATER=GPIO35, BMP280 SDA=GPIO21, SCL=GPIO22                                                                                                    | Preserved |
| G61    | Wi-Fi MQTT    | MQ2=GPIO34, DHT=GPIO4, WATER=GPIO35, PIR=GPIO13, SERVO=GPIO18                                                                                              | Preserved |

Wi-Fi nodes' `secrets.example.h` files updated to point `MQTT_HOST` to RPi 1 IP, not RPi 2.  
LoRa packet format unchanged — no firmware modification required for LoRa nodes.

