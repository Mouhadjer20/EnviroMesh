# EnviroMesh — Automation & Helper Scripts

This directory contains command-line utilities and test harnesses designed to streamline development, testing, deployment, and monitoring across all layers of the EnviroMesh platform.

---

## Table of Contents

- [Script Overview](#script-overview)
- [1. Environment & Setup](#1-environment--setup)
- [2. Managing Docker Services](#2-managing-docker-services)
- [3. Database Management (PostgreSQL & TimescaleDB)](#3-database-management-postgresql--timescaledb)
- [4. Simulating Sensor Telemetry (Hardware-Free Testing)](#4-simulating-sensor-telemetry-hardware-free-testing)
- [5. Live MQTT Telemetry Monitor](#5-live-mqtt-telemetry-monitor)
- [6. System Health Diagnostic](#6-system-health-diagnostic)
- [7. LoRa Ingestion Pipeline Testing](#7-lora-ingestion-pipeline-testing)
- [Requirements](#requirements)

---

## Script Overview

| Script | Type | Description |
|---|---|---|
| [`setup_env.sh`](setup_env.sh) | Bash | Initializes local workspace, `.env` file, directory structure, permissions, and Python virtual environment (`.venv`). |
| [`docker_control.sh`](docker_control.sh) | Bash | Manages the Docker Compose stack (`emqx`, `timescaledb`, `backend`, `dashboard`, `nginx`) with built-in `/api/health` wait polling. |
| [`db_manage.sh`](db_manage.sh) | Bash | Controls PostgreSQL & TimescaleDB: migrations, reference data seeding, verification queries, interactive `psql` shell, and resets. |
| [`simulate_telemetry.py`](simulate_telemetry.py) | Python | Synthetic telemetry generator for field nodes (`G11`, `G41`, `G31`, `G61`) over MQTT. Supports anomaly injection (gas leak, fire, water leak). |
| [`mqtt_monitor.py`](mqtt_monitor.py) | Python | Real-time terminal dashboard subscribing to MQTT topics (`enviromesh/#`), displaying live formatted readings and alerts. |
| [`check_health.py`](check_health.py) | Python | Automated ANSI-colored diagnostic tool displaying local LAN IP and checking connectivity to Nginx, FastAPI backend, EMQX, and TimescaleDB. |
| [`lora_packet_inject.py`](lora_packet_inject.py) | Python | LoRa pipeline test harness; validates and writes raw & parsed LoRa packets to TimescaleDB without physical SX1278 hardware. |

---

## 1. Environment & Setup

Run this script first when cloning the repository or setting up a new development environment:

```bash
./scripts/setup_env.sh
```

**What it does:**
- Verifies system prerequisites (`docker`, `python3`, `git`).
- Creates `.env` from `.env.example` if it does not exist.
- Sets executable permissions on all scripts in `scripts/`.
- Prepares directories for infrastructure, backend, dashboard, and firmware.
- Creates and sets up Python virtual environment (`.venv`) with core and optional hardware dependencies.

---

## 2. Managing Docker Services

Control all five containerized microservices without needing long Docker commands:

```bash
# Start all containers in the background (polls /api/health until backend is ready)
./scripts/docker_control.sh start

# Check container status, ports, and health
./scripts/docker_control.sh status

# Follow real-time colored logs for all services (or specify one: backend, emqx, timescaledb)
./scripts/docker_control.sh logs backend

# Rebuild container images after making backend or dashboard changes
./scripts/docker_control.sh build

# Stop all containers
./scripts/docker_control.sh stop
```

---

## 3. Database Management (PostgreSQL & TimescaleDB)

Manage migrations, seed data, and query verification directly:

```bash
# 1. Initialize complete database (extensions + migrations + seed + verification)
./scripts/db_manage.sh init

# 2. Run only migrations
./scripts/db_manage.sh migrate

# 3. Seed student technician accounts and device registry
./scripts/db_manage.sh seed

# 4. Verify seeded database topology
./scripts/db_manage.sh verify

# 5. Show current table row counts
./scripts/db_manage.sh status

# 6. Open an interactive psql database shell
./scripts/db_manage.sh shell

# 7. Reset and re-apply all schemas (destructive!)
./scripts/db_manage.sh reset
```

---

## 4. Simulating Sensor Telemetry (Hardware-Free Testing)

Simulate field nodes transmitting realistic sensor data to EMQX and TimescaleDB:

```bash
# Simulate G11 node emitting every 2 seconds (infinite loop)
./scripts/simulate_telemetry.py --device G11 --interval 2.0

# Simulate all 4 devices cycling periodically (10 messages total)
./scripts/simulate_telemetry.py --device all --count 10

# Simulate an emergency gas leak anomaly
./scripts/simulate_telemetry.py --device G11 --anomaly gas_leak

# Simulate water leak detection
./scripts/simulate_telemetry.py --device G41 --anomaly water_leak

# Print JSON payloads to stdout without publishing to MQTT
./scripts/simulate_telemetry.py --device G31 --print-only
```

---

## 5. Live MQTT Telemetry Monitor

Monitor incoming telemetry on the broker live in the terminal:

```bash
# Monitor all topics (enviromesh/#)
./scripts/mqtt_monitor.py

# Monitor a specific device topic
./scripts/mqtt_monitor.py --topic "enviromesh/devices/G11/telemetry"

# Enable verbose mode to inspect raw JSON payloads
./scripts/mqtt_monitor.py -v
```

---

## 6. System Health Diagnostic

Verify all architectural layers in a single command with ANSI colored status indicators:

```bash
./scripts/check_health.py
```

Outputs the detected LAN IP (useful for connecting field nodes and laptops) and a status table covering:
- **Reverse Proxy** (Nginx on port 8080)
- **Backend REST API** (HTTP on port 8080 `/api/health`)
- **MQTT Broker** (EMQX TCP on port 1883)
- **EMQX Web Console** (port 18083)
- **TimescaleDB** (PostgreSQL connection & extension verification via `pg_isready`)

---

## 7. LoRa Ingestion Pipeline Testing

Test the backend LoRa processing pipeline (`process_packet`, `telemetry_validator`, `database_writer`) without a physical SX1278 module:

```bash
# Inject a valid G11 LoRa packet
./scripts/lora_packet_inject.py --device G11 --gas 55.4 --temp 24.1

# Inject an invalid JSON payload to verify error handling and raw logging
./scripts/lora_packet_inject.py --corrupt-json
```

---

## Requirements

All scripts run on **macOS**, **Linux** (including Raspberry Pi OS), and WSL.
Dependencies:
- Bash 4+
- Docker Engine & Docker Compose v2
- Python 3.10+ (with `paho-mqtt`, `psycopg2-binary`, `python-dotenv`)
