# Backend — EnviroMesh Core Processing Server

The backend is the core processing server running on the Raspberry Pi. It exposes
a **FastAPI** HTTP/WebSocket API, consumes telemetry from **MQTT (EMQX)** and
directly from the **LoRa (SX1278)** receiver, validates readings, and persists
them to **TimescaleDB**.

## Architecture

```
ESP32 Nodes (LoRa/Wi-Fi)
        │
        ├──► LoRa 433 MHz (SX1278) ──► backend/services/lora_receiver.py
        │                                        │
        │                                        ▼
        │                                   backend/services/telemetry_validator.py
        │                                   backend/services/database_writer.py
        │                                        │
        │                                        ▼
        │                                   TimescaleDB (sensor_telemetry)
        │
        └──► MQTT (EMQX) ──► backend/services/mqtt_subscriber.py
                                        │
                                        ▼
                                   backend/services/telemetry_validator.py
                                   backend/services/database_writer.py
                                        │
                                        ▼
                                   TimescaleDB (sensor_telemetry)
```

## Directory Layout

```
backend/
├── main.py                       # Entry point: FastAPI app + service loop
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Container image (python:3.11-slim)
├── .env                          # Environment variables (MQTT, DB, API)
├── routes/                       # FastAPI route modules
│   ├── __init__.py
│   ├── devices.py                # GET/POST/PUT/DELETE /devices
│   ├── telemetry.py              # GET /telemetry, GET /telemetry/{id}/latest
│   ├── alerts.py                 # GET/POST /alerts, PATCH /alerts/{id}/ack
│   └── users.py                  # User management endpoints
├── services/                     # Background services & shared helpers
│   ├── __init__.py
│   ├── mqtt_subscriber.py        # Paho-MQTT client; subscribes, validates, persists
│   ├── database_writer.py        # TimescaleDB/PostgreSQL writer (psycopg2)
│   ├── telemetry_validator.py    # Validates telemetry metrics & ranges
│   └── lora_receiver.py          # LoRa frame reception (SX1278) + validation + persistence
└── auth/                         # Authentication & RBAC
    └── README.md                 # Authentication documentation
```

## Services

| Service | File | Description |
|---------|------|-------------|
| **LoRa Receiver** | `services/lora_receiver.py` | SX1278 SPI driver; receives 433 MHz frames, parses JSON, validates with `telemetry_validator`, persists via `database_writer` |
| **MQTT Subscriber** | `services/mqtt_subscriber.py` | Paho-MQTT client; subscribes to EMQX topics, validates, persists |
| **Telemetry Validator** | `services/telemetry_validator.py` | Schema & range validation for telemetry payloads |
| **Database Writer** | `services/database_writer.py` | TimescaleDB writer (`sensor_telemetry` + `raw_sensor_packets`) |

## LoRa Receiver Flow

1. `init_lora()` configures the SX1278 (433 MHz, SF7, BW125 kHz).
2. The main loop polls `REG_IRQ_FLAGS` for `IRQ_RX_DONE`.
3. On a valid frame, `receive_packet()` reads the FIFO and returns the raw string.
4. `process_packet(raw)`:
   - Writes the **raw packet** to `raw_sensor_packets` (for diagnostics).
   - Parses JSON; if invalid, stops there.
   - Runs `validate()`; discards the reading if invalid.
   - Persists the validated reading to `sensor_telemetry` via `write_telemetry()`.

## Prerequisites

- **Raspberry Pi** with SX1278 on SPI (bus 0, device 0).
- **Python** 3.11+ with `spidev`, `RPi.GPIO`, `paho-mqtt`, `psycopg2`, `python-dotenv`.
- **PostgreSQL + TimescaleDB** extension.
- **EMQX** MQTT broker (or any MQTT 5.0 broker).

## Configuration

All settings come from the `.env` file (see the project root `README.md` for the
full variable list). Key variables:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — TimescaleDB.
- `MQTT_HOST` / `EMQX_URL`, `MQTT_PORT` — EMQX broker.

## Running

```bash
cd raspberry_pi/backend
python main.py              # Runs LoRa receiver + MQTT subscriber + FastAPI together
python -m services.lora_receiver   # LoRa gateway mode (standalone)
python -m services.mqtt_subscriber # MQTT consumer mode (standalone)
uvicorn main:app --host 0.0.0.0 --port 8000  # FastAPI only
```

`main.py` starts the LoRa receiver in a background daemon thread and runs the
MQTT subscriber in the main thread, so both communication paths ingest telemetry
concurrently.

## Related Documentation

- Project architecture: [`../../README.md`](../../README.md)
- Dashboard: [`../dashboard`](../dashboard)
- Database layer: [`../db`](../db)