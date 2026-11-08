# EnviroMesh — Automation, Simulation & Helper Scripts

This directory contains command-line utilities, test harnesses, and simulators designed to streamline development, testing, deployment, and monitoring across all layers of the EnviroMesh platform.

---

## Table of Contents

- [Script Overview](#script-overview)
- [1. Single-Device Development & Simulation (Core + Gateway)](#1-single-device-development--simulation-core--gateway)
- [2. Automated Testing & Pipeline Simulation](#2-automated-testing--pipeline-simulation)
- [3. Simulating Field Sensor Telemetry](#3-simulating-field-sensor-telemetry)
- [4. LoRa Packet Ingestion Testing](#4-lora-packet-ingestion-testing)
- [5. System Health Diagnostics](#5-system-health-diagnostics)
- [6. Database Management (PostgreSQL & TimescaleDB)](#6-database-management-postgresql--timescaledb)
- [7. Two-Raspberry-Pi Distributed Deployment Scripts](#7-two-raspberry-pi-distributed-deployment-scripts)
- [Requirements](#requirements)

---

## Script Overview

| Script | Mode | Description |
|---|---|---|
| [`run_tests.py`](run_tests.py) | **Test Runner** | Automated runner for syntax verification, end-to-end pipeline simulations, simulator checks, and unit tests. |
| [`simulate_pipeline.py`](simulate_pipeline.py) | **Simulator** | Hardware-free pipeline test: Field Nodes -> Gateway Validation/Normalization -> SQLite WAL Queue -> Network Recovery -> Core Deduplication. |
| [`simulate_telemetry.py`](simulate_telemetry.py) | **Simulator** | Synthetic telemetry generator for field nodes (`G11`, `G41`, `G31`, `G61`) over MQTT. Supports anomaly injection (gas leak, fire, water leak). |
| [`lora_packet_inject.py`](lora_packet_inject.py) | **Test Harness** | LoRa pipeline test harness; validates raw & parsed LoRa packets without physical SX1278 hardware. |
| [`docker_control.sh`](docker_control.sh) | **Unified Stack** | Controls the unified single-device Docker Compose stack (Gateway + Core: `emqx-local`, `gateway`, `emqx-core`, `timescaledb`, `backend`, `dashboard`, `nginx`). |
| [`check_health.py`](check_health.py) | **Diagnostics** | Unified health diagnostic tool checking all single-device endpoints (Nginx, FastAPI, Gateway EMQX, Core EMQX, TimescaleDB). |
| [`mqtt_monitor.py`](mqtt_monitor.py) | **Monitor** | Real-time terminal dashboard subscribing to MQTT topics (`enviromesh/#`), displaying live formatted readings. |
| [`db_manage.sh`](db_manage.sh) | **Database** | PostgreSQL & TimescaleDB manager: migrations, reference data seeding, verification queries, interactive shell. |
| [`backup_database.sh`](backup_database.sh) | **Maintenance** | Creates timestamped and rotated PostgreSQL backups. |
| [`setup_gateway.sh`](setup_gateway.sh) | **2-Pi Setup** | Configures RPi 1 Gateway environment, permissions, and service dependencies. |
| [`setup_core.sh`](setup_core.sh) | **2-Pi Setup** | Configures RPi 2 Core environment, database directories, and permissions. |
| [`deploy_gateway.sh`](deploy_gateway.sh) | **2-Pi Deploy** | Deploys RPi 1 Gateway services via Docker Compose. |
| [`deploy_core.sh`](deploy_core.sh) | **2-Pi Deploy** | Deploys RPi 2 Core services via Docker Compose with zero-loss volume persistence. |
| [`check_gateway_health.py`](check_gateway_health.py) | **2-Pi Health** | Dedicated health check for RPi 1 Gateway (local broker, queue depth, forwarder state). |
| [`check_core_health.py`](check_core_health.py) | **2-Pi Health** | Dedicated health check for RPi 2 Core (central broker, TLS, TimescaleDB, API). |

---

## 1. Single-Device Development & Simulation (Core + Gateway)

Run both Gateway and Core together on a single machine (laptop, PC, or single Raspberry Pi):

```bash
# 1. Start all 7 microservices in background
./scripts/docker_control.sh start

# 2. Check service status, ports, and health
./scripts/docker_control.sh status

# 3. View live logs across services (or specify one: backend, gateway, emqx-local)
./scripts/docker_control.sh logs gateway

# 4. Stop containers
./scripts/docker_control.sh stop
```

---

## 2. Automated Testing & Pipeline Simulation

Verify all components and test the complete end-to-end data flow with zero external dependencies:

```bash
# Run the complete test and simulation suite:
python3 scripts/run_tests.py

# Run only the end-to-end pipeline simulation (Gateway SQLite queue + Core deduplication):
python3 scripts/simulate_pipeline.py
```

---

## 3. Simulating Field Sensor Telemetry

Simulate field nodes transmitting realistic sensor data to Gateway EMQX (port 1883):

```bash
# Simulate G11 node emitting every 2 seconds (infinite loop)
python3 scripts/simulate_telemetry.py --device G11 --interval 2.0

# Simulate all 4 devices cycling periodically (10 messages total)
python3 scripts/simulate_telemetry.py --device all --count 10

# Simulate an emergency gas leak anomaly
python3 scripts/simulate_telemetry.py --device G11 --anomaly gas_leak

# Simulate water leak detection
python3 scripts/simulate_telemetry.py --device G41 --anomaly water_leak

# Print JSON payloads to stdout without publishing to MQTT
python3 scripts/simulate_telemetry.py --device G31 --print-only
```

---

## 4. LoRa Packet Ingestion Testing

Test the LoRa processing pipeline without physical SX1278 hardware:

```bash
# Inject a valid G11 LoRa packet
python3 scripts/lora_packet_inject.py --device G11 --gas 55.4 --temp 24.1

# Inject an invalid JSON payload to verify error handling and raw logging
python3 scripts/lora_packet_inject.py --corrupt-json
```

---

## 5. System Health Diagnostics

Verify all single-device service endpoints in a single command with ANSI colored status indicators:

```bash
python3 scripts/check_health.py
```

Outputs the detected LAN IP and checks:
- **Nginx Reverse Proxy** (`http://localhost:8080`)
- **FastAPI REST API** (`http://localhost:8080/api/health`)
- **Gateway Local EMQX Broker** (port 1883)
- **Core Central EMQX Broker** (port 8883)
- **Gateway & Core Web Consoles** (ports 18083, 18084)
- **TimescaleDB Database** (PostgreSQL container connection)

---

## 6. Database Management (PostgreSQL & TimescaleDB)

Manage migrations, seed data, and query verification directly:

```bash
# Initialize complete database (extensions + migrations + seed + verification)
./scripts/db_manage.sh init

# Run migrations (including registry, telemetry, metadata, active users, password rotation)
./scripts/db_manage.sh migrate

# Seed accounts and device registry
./scripts/db_manage.sh seed

# Show current table row counts
./scripts/db_manage.sh status

# Open interactive psql shell
./scripts/db_manage.sh shell
```

---

## 7. Two-Raspberry-Pi Distributed Deployment Scripts

When deploying across two separate physical Raspberry Pis:

### On RPi 1 (Edge Gateway):
```bash
./scripts/setup_gateway.sh
./scripts/deploy_gateway.sh
python3 scripts/check_gateway_health.py
```

### On RPi 2 (Central Core):
```bash
./scripts/setup_core.sh
./scripts/deploy_core.sh
python3 scripts/check_core_health.py
```

---

## Requirements

- Python 3.10+ (with `paho-mqtt`, `psycopg2-binary`, `python-dotenv`)
- Docker Engine & Docker Compose v2 (for containerized execution)
