# EnviroMesh — Implementation Plan

> [!NOTE]
> This document tracks all implementation work across the two-Pi architecture migration.
> Status values: **COMPLETE** / **IN PROGRESS** / **PENDING** / **BLOCKED**.

---

## Overview

The project has evolved from a monolithic single-Pi prototype to a split two-Pi architecture:

- **RPi 1 (Gateway):** LoRa reception, local Wi-Fi MQTT broker (EMQX), SQLite offline queue, TLS MQTT forwarder to RPi 2.
- **RPi 2 (Core):** Central EMQX broker (TLS), TimescaleDB (PostgreSQL), FastAPI backend, React dashboard, Nginx reverse proxy.

---

## Phase 1 — Repository Migration to Two-Pi Architecture

**Status: COMPLETE**
**Commit range:** up to `3d62b24`

| Task | Status | Files | Notes |
|---|---|---|---|
| Create `raspberry_pi/gateway/` subtree | COMPLETE | `raspberry_pi/gateway/` | New directory for all RPi 1 services |
| Create `raspberry_pi/core/` subtree | COMPLETE | `raspberry_pi/core/` | New directory for all RPi 2 services |
| Remove legacy monolithic folders | COMPLETE | Root `docker-compose.yml` | Redirected to core services per commit `3d62b24` |
| Update root `.gitignore` | COMPLETE | `.gitignore` | Protects TLS certs, SQLite queue, backups — commit `55f468e` |
| Update root `README.md` | COMPLETE | `README.md` | Describes two-Pi architecture |
| Migrate backend routes to `raspberry_pi/core/backend/` | COMPLETE | `backend/routes/devices.py`, `telemetry.py`, `groups.py` | LoRa receiver removed from core backend |
| Migrate dashboard to `raspberry_pi/core/dashboard/` | COMPLETE | `raspberry_pi/core/dashboard/` | React + Vite |
| Migrate database migrations to `raspberry_pi/core/database/migrations/` | COMPLETE | `001_create_registry.sql`, `001_create_telemetry.sql`, `003_add_gateway_metadata.sql` | |

---

## Phase 2 — Gateway Implementation

**Status: COMPLETE**
**Commit range:** up to `49ec334`

| Task | Status | Files | Notes |
|---|---|---|---|
| Gateway Python package structure | COMPLETE | `raspberry_pi/gateway/gateway/` | `__init__.py`, package imports |
| `config.py` — environment variable loading | COMPLETE | `gateway/config.py` | All env vars for MQTT, SQLite, LoRa |
| `logger.py` — structured logging | COMPLETE | `gateway/logger.py` | Coloured output, log level from env |
| `sqlite_queue.py` — persistent offline queue | COMPLETE | `gateway/sqlite_queue.py` | WAL + FULL sync; `enqueue()` uses `cursor.rowcount`; `mark_sent()` on PUBACK |
| `lora_receiver.py` — SX1278 driver | COMPLETE | `gateway/lora_receiver.py` | 433 MHz, SF7, BW125, CR4/5, sync=0x12; RSSI/SNR from reg 0x1A/0x19; graceful fallback on non-RPi |
| `telemetry_validator.py` — schema validation | COMPLETE | `gateway/telemetry_validator.py` | Validates required fields before enqueue |
| `telemetry_normalizer.py` — envelope creation | COMPLETE | `gateway/telemetry_normalizer.py` | Adds `message_id` (UUID), `gateway_id`, `received_at` timestamp |
| `mqtt_ingestion.py` — local EMQX subscriber | COMPLETE | `gateway/mqtt_ingestion.py` | Subscribes to `enviromesh/devices/+/telemetry`; enqueues to SQLite |
| `mqtt_forwarder.py` — TLS forwarder to RPi 2 | COMPLETE | `gateway/mqtt_forwarder.py` | QoS 1; PUBACK-before-delete; exponential back-off 5→60 s; `_inflight` dict |
| `health_monitor.py` — health reporting | COMPLETE | `gateway/health_monitor.py` | Queue depth, forwarder status |
| `main.py` — service orchestration | COMPLETE | `gateway/main.py` | Starts LoRa, ingestion, forwarder threads |
| Gateway `Dockerfile` | COMPLETE | `raspberry_pi/gateway/Dockerfile` | Python 3.11-slim; installs spidev, paho-mqtt, etc. |
| Gateway `docker-compose.yml` | COMPLETE | `raspberry_pi/gateway/docker-compose.yml` | EMQX local + gateway service; SPI/GPIO device mapping |
| Gateway `.env.example` | COMPLETE | `raspberry_pi/gateway/.env.example` | Documented all required env vars |
| Gateway EMQX `acl.conf` | COMPLETE | `raspberry_pi/gateway/emqx/acl.conf` | Per-device publish rules; deny-all default |
| Gateway EMQX `emqx.conf` | COMPLETE | `raspberry_pi/gateway/emqx/emqx.conf` | Auth backend config |
| Gateway systemd units | COMPLETE | `raspberry_pi/gateway/systemd/enviromesh-gateway.service`, `enviromesh-lora.service` | For non-Docker deployments |
| Update firmware Wi-Fi broker endpoints to RPi 1 | COMPLETE | `firmware/nodes/node_g31/`, `node_g42/`, `node_g43/`, `node_g61_servo/` | Commit `49ec334` |

---

## Phase 3 — Core Implementation

**Status: COMPLETE**
**Commit:** `f392e8a`

| Task | Status | Files | Notes |
|---|---|---|---|
| Core EMQX TLS on port 8883 | COMPLETE | `raspberry_pi/core/emqx/emqx.conf`, `docker-compose.yml` | CA + server cert mount |
| Core EMQX ACL | COMPLETE | `raspberry_pi/core/emqx/acl.conf` | `gw_forwarder` publish only; `enviromesh_backend` subscribe only; deny-all |
| TimescaleDB container | COMPLETE | `raspberry_pi/core/docker-compose.yml` | No host port exposed; PostgreSQL internal only |
| `003_add_gateway_metadata.sql` migration | COMPLETE | `raspberry_pi/core/database/migrations/003_add_gateway_metadata.sql` | Adds `gateway_id`, `rssi_dbm`, `snr_db` columns |
| `processed_messages` table for dedup | COMPLETE | `001_create_telemetry.sql` | Prevents duplicate ingestion by `message_id` |
| FastAPI backend MQTT subscriber | COMPLETE | `raspberry_pi/core/backend/services/mqtt_subscriber.py` | Subscribes to `enviromesh/gateway/+/telemetry` |
| FastAPI backend database writer | COMPLETE | `raspberry_pi/core/backend/services/database_writer.py` | Writes telemetry + dedup check |
| FastAPI routes: devices, telemetry, groups | COMPLETE | `raspberry_pi/core/backend/routes/` | `devices.py`, `telemetry.py`, `groups.py` |
| FastAPI health endpoint | COMPLETE | `raspberry_pi/core/backend/main.py` line 46–49 | `GET /health` returns `{"status":"ok"}` |
| React dashboard | COMPLETE | `raspberry_pi/core/dashboard/` | Vite build; real-time WebSocket telemetry |
| Nginx reverse proxy | COMPLETE | `raspberry_pi/core/nginx/default.conf` | `/api/` → backend, `/ws/` → WebSocket, `/` → dashboard |
| Core `docker-compose.yml` | COMPLETE | `raspberry_pi/core/docker-compose.yml` | All 5 services: emqx-core, timescaledb, backend, dashboard, nginx |
| Core `.env.example` | COMPLETE | `raspberry_pi/core/.env.example` | Documented all required env vars |

---

## Phase 4 — Audit, Security Hardening, Testing

**Status: IN PROGRESS**

| Task | Status | Files | Notes |
|---|---|---|---|
| Static code audit of all Python services | COMPLETE | — | See `AUDIT_REPORT.md` |
| Docker configuration audit | COMPLETE | — | See `AUDIT_REPORT.md` |
| ACL trace analysis | COMPLETE | `emqx/acl.conf` (both) | See `AUDIT_REPORT.md` |
| Firmware pin mapping verification | COMPLETE | `firmware/nodes/*/src/main.ino` | Documented in audit report |
| Write security assessment | COMPLETE | `docs/security-assessment.md` | All 10 findings |
| Write security PoC plans | COMPLETE | `security/reports/0*.md` | 5 PoC reports |
| Write maintenance procedures | COMPLETE | `docs/maintenance-and-known-issues.md` | 6 tracked issues |
| Fix `clean_session=True` (FIND-010 / ISSUE-005) | OPEN | `gateway/mqtt_forwarder.py` line 41 | Change to `False` |
| Add JWT authentication (FIND-005 / ISSUE-001) | OPEN | `core/backend/main.py`, `routes/users.py` | High priority |
| Add HTTPS to Nginx (FIND-002 / ISSUE-006) | OPEN | `core/nginx/default.conf` | Blocked by TLS cert availability |
| Add rate limiting (FIND-004) | OPEN | `core/nginx/default.conf` or `backend/main.py` | Medium priority |
| Encrypt backup script output (FIND-009) | OPEN | `scripts/backup_database.sh` | Medium priority |
| Enforce SQLite file permissions (FIND-006) | OPEN | `gateway/main.py`, `scripts/setup_gateway.sh` | Low priority |
| Provision EMQX accounts in setup script (FIND-001) | OPEN | `scripts/setup_gateway.sh` | Medium priority |
| Add mutual TLS for gateway forwarder (FIND-007) | OPEN | `gateway/mqtt_forwarder.py` | Requires client cert generation |
| Add LoRa HMAC (FIND-003) | OPEN | `gateway/lora_receiver.py`, firmware G11 / G41 | Blocked by hardware access |

---

## Phase 5 — Physical Hardware Validation, TLS Deployment, Production Hardening

**Status: PENDING**

| Task | Status | Files | Notes |
|---|---|---|---|
| Provision TLS certificates on physical RPi 2 (ISSUE-002) | PENDING | `docs/certificate-setup.md` | Requires physical hardware |
| Deploy TLS certs to `raspberry_pi/core/emqx/certs/` | PENDING | `raspberry_pi/core/emqx/certs/` | Blocked by ISSUE-002 |
| Copy CA cert to `raspberry_pi/gateway/certs/core-ca.crt` | PENDING | `raspberry_pi/gateway/certs/core-ca.crt` | Blocked by ISSUE-002 |
| Run database migrations on physical TimescaleDB (ISSUE-003) | PENDING | `database/migrations/` | Requires running container |
| Test SPI/GPIO LoRa reception on physical RPi 1 (ISSUE-004) | PENDING | `gateway/lora_receiver.py` | Requires SX1278 hardware |
| Test LoRa end-to-end with G11 and G41 firmware | PENDING | — | Requires all physical hardware |
| Test Wi-Fi MQTT end-to-end with G31, G42, G43, G61 firmware | PENDING | — | Requires physical network |
| Load test TimescaleDB with high-volume telemetry | PENDING | — | Performance baseline needed |
| Final production credential rotation | PENDING | `.env` files (both RPis) | Before go-live |
| Enable automatic migration entrypoint | PENDING | `raspberry_pi/core/docker-compose.yml` | Automation of ISSUE-003 |
| Enable backup encryption | PENDING | `scripts/backup_database.sh` | After FIND-009 fix |
| Set up cron for `backup_database.sh` | PENDING | Host crontab on RPi 2 | 7-day retention already in script |
