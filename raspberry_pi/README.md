# Raspberry Pi — EnviroMesh Edge Gateway & Core Server

> **Enterprise IoT Architecture** — LoRa/Wi-Fi sensor nodes, MQTT (EMQX) messaging, TimescaleDB persistence, and FastAPI backend.  
> **Target audience:** Development & Engineering Team  
> **Project version:** 1.0

---

## 1. System Overview

The Raspberry Pi is the heart of the **EnviroMesh** system. It acts as both:

| Role | Description |
|------|-------------|
| **LoRa Edge Gateway** | Receives raw RF packets from ESP32 sensor nodes (433 MHz, SX1278) |
| **Core Processing Server** | FastAPI API, MQTT consumer, TimescaleDB persistence, alerting |

```
ESP32 Nodes (LoRa/Wi-Fi) ───► Raspberry Pi ───► Dashboard / Users
       │                            │
       │  LoRa 433 MHz              │  MQTT (EMQX)  │  HTTP/WebSocket
       ▼                            ▼               ▼
  backend/services/lora_receiver.py    backend/services/mqtt_subscriber.py  backend/main.py
  (SX1278)                             (paho-mqtt)                          (FastAPI)
                         backend/services/database_writer.py
                         (psycopg2 / TimescaleDB)
```

---

## 2. Folder Structure

```
raspberry_pi/
├── backend/                          # Core processing server (FastAPI + MQTT consumer)
│   ├── main.py                       # Entry point: FastAPI app + MQTT consumer loop
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Container image (python:3.11-slim)
│   ├── .env                          # Environment variables (MQTT, DB, API)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── devices.py                # GET/POST/PUT/DELETE /devices
│   │   ├── telemetry.py              # GET /telemetry, GET /telemetry/{id}/latest
│   │   ├── alerts.py                 # GET/POST /alerts, PATCH /alerts/{id}/ack
│   │   └── users.py                  # User management endpoints
│   └── services/
│       ├── __init__.py
│       ├── mqtt_subscriber.py        # Paho-MQTT client; subscribes, validates, persists
│       ├── database_writer.py        # TimescaleDB/PostgreSQL writer (psycopg2)
│       ├── telemetry_validator.py    # Validates telemetry metrics & ranges
│       └── lora_receiver.py          # LoRa frame reception (SX1278)
│   └── auth/                         # Authentication & RBAC (docs only)
│       └── README.md                 # Authentication documentation
├── dashboard/                        # Web dashboard frontend (static HTML)
│   ├── index.html                    # Dashboard UI
│   ├── Dockerfile                    # Nginx-based static server
│   └── README.md                     # Dashboard documentation
├── db/                               # Database migration & seed files
│   ├── README.md                     # Database documentation
│   ├── migration/
│   │   ├── 001_create_registry.sql   # PostgreSQL relational schema
│   │   └── 001_create_telemetry.sql  # TimescaleDB hypertable schema
│   └── seed/
│       ├── 001_seed_registry.sql     # Reference data (groups, users, devices, sensors)
│       └── 001_verify_seed_registry.sql
├── infrastructure/                   # Docker Compose services and config
│   ├── emqx/.gitkeep                 # MQTT broker (EMQX) container config
│   ├── nginx/default.conf            # Reverse proxy configuration
│   └── systemd/.gitkeep              # Systemd service definitions
└── README.md                         # This file
```

---

## 3. Prerequisites

| Component | Requirement |
|-----------|-------------|
| **Raspberry Pi** | RPi 3 / 4 / 5 (recommended), 4 GB RAM minimum |
| **LoRa Module** | SX1278 (433 MHz), connected via SPI |
| **MQTT Broker** | EMQX 5.x (or any MQTT 5.0 broker), port 1883 |
| **Database** | PostgreSQL + TimescaleDB extension, port 5432 |
| **Python** | 3.11+ |
| **ESP32 Nodes** | G11, G41, G61, node_g42, node_g43 (or any compatible ESP32) |

---

## 4. Environment Configuration (`.env`)

All configuration is managed through a `.env` file. Create it from the example:

```bash
cp .env.example .env
nano .env
```

### Key Configuration Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MQTT_HOST` / `EMQX_URL` | EMQX broker hostname/IP | `localhost` | ✅ |
| `MQTT_PORT` | EMQX broker port | `1883` | ✅ |
| `MQTT_TOPIC` | Telemetry topic filter | `enviromesh/devices/+/telemetry` | ⭐ |
| `MQTT_APP_USERNAME` | MQTT application username | `enviromesh_backend` | ✅ |
| `MQTT_APP_PASSWORD` | MQTT application password | *see .env.example* | ✅ |
| `DB_HOST` | TimescaleDB host | `timescaledb` (Docker) / `localhost` | ✅ |
| `DB_PORT` | TimescaleDB port | `5432` | ✅ |
| `DB_NAME` | Database name | `enviromesh` | ✅ |
| `DB_USER` | DB user | `enviromesh_app` | ✅ |
| `DB_PASSWORD` | DB password | — | ✅ |
| `API_HOST` | API bind host | `0.0.0.0` | ✅ |
| `API_PORT` | API bind port | `8000` | ✅ |

> **⚠️ Critical:** In `docker-compose.yml`, `MQTT_HOST` is set to `emqx` (the EMQX container name). In local development, override it in `.env` with your broker's IP (e.g., `192.168.43.99`).

