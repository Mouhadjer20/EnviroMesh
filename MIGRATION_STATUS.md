# EnviroMesh — Migration Status

> [!NOTE]
> This document tracks all file movements from the original single-Pi architecture to the two-Pi
> architecture (RPi 1 Gateway + RPi 2 Core).  
> Status values: **Migrated** / **Created new** / **Updated** / **Removed** / **Pending**.

---

## Architecture Change Summary

| Aspect | Before (Single Pi) | After (Two-Pi) |
|---|---|---|
| **LoRa reception** | `raspberry_pi/backend/services/lora_receiver.py` (direct to TimescaleDB) | `raspberry_pi/gateway/gateway/lora_receiver.py` (enqueues to SQLite) |
| **MQTT broker** | Single EMQX on RPi 1 | EMQX on RPi 1 (local, Wi-Fi nodes) + EMQX on RPi 2 (core, TLS) |
| **Data persistence** | TimescaleDB directly | SQLite offline queue → TLS forward → TimescaleDB |
| **Backend** | On same Pi as sensors | On dedicated RPi 2 |
| **Dashboard** | On same Pi as sensors | On dedicated RPi 2 |

---

## Migration Table

### Gateway Python Services (Created New on RPi 1)

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| LoRa receiver | `raspberry_pi/backend/services/lora_receiver.py` | `raspberry_pi/gateway/gateway/lora_receiver.py` | Migrated | Rewired to SQLite enqueue instead of TimescaleDB write; RSSI/SNR added |
| SQLite queue | _(did not exist)_ | `raspberry_pi/gateway/gateway/sqlite_queue.py` | Created new | WAL + FULL sync; `enqueue()` uses `cursor.rowcount`; at-least-once delivery |
| MQTT ingestion | _(did not exist)_ | `raspberry_pi/gateway/gateway/mqtt_ingestion.py` | Created new | Subscribes to local EMQX; enqueues validated packets |
| MQTT forwarder | _(did not exist)_ | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` | Created new | QoS 1 TLS forward to RPi 2; exponential back-off; PUBACK-before-delete |
| Config loader | `raspberry_pi/backend/config.py` | `raspberry_pi/gateway/gateway/config.py` | Created new | Gateway-specific env vars |
| Logger | `raspberry_pi/backend/logger.py` | `raspberry_pi/gateway/gateway/logger.py` | Migrated | Coloured structured logging |
| Telemetry validator | `raspberry_pi/backend/services/telemetry_validator.py` | `raspberry_pi/gateway/gateway/telemetry_validator.py` | Migrated | Schema validation for LoRa + Wi-Fi packets |
| Telemetry normalizer | `raspberry_pi/backend/services/telemetry_normalizer.py` | `raspberry_pi/gateway/gateway/telemetry_normalizer.py` | Migrated | Adds `message_id` UUID, `received_at`, `gateway_id` |
| Health monitor | _(did not exist)_ | `raspberry_pi/gateway/gateway/health_monitor.py` | Created new | Queue depth + forwarder status |
| Main entrypoint | `raspberry_pi/backend/main.py` | `raspberry_pi/gateway/gateway/main.py` | Migrated | Starts LoRa, ingestion, forwarder threads |

### Core Backend (Moved from `raspberry_pi/backend/` to `raspberry_pi/core/backend/`)

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| FastAPI main | `raspberry_pi/backend/main.py` | `raspberry_pi/core/backend/main.py` | Migrated | LoRa receiver removed; subscribes to gateway-forwarded topics |
| Database writer | `raspberry_pi/backend/services/database_writer.py` | `raspberry_pi/core/backend/services/database_writer.py` | Migrated | `processed_messages` dedup added |
| MQTT subscriber | `raspberry_pi/backend/services/mqtt_subscriber.py` | `raspberry_pi/core/backend/services/mqtt_subscriber.py` | Migrated | Topic changed from `enviromesh/devices/+/telemetry` to `enviromesh/gateway/+/telemetry` |
| Route: devices | `raspberry_pi/backend/routes/devices.py` | `raspberry_pi/core/backend/routes/devices.py` | Migrated | No structural changes |
| Route: telemetry | `raspberry_pi/backend/routes/telemetry.py` | `raspberry_pi/core/backend/routes/telemetry.py` | Migrated | No structural changes |
| Route: groups | `raspberry_pi/backend/routes/groups.py` | `raspberry_pi/core/backend/routes/groups.py` | Migrated | No structural changes |
| Route: alerts | `raspberry_pi/backend/routes/alerts.py` | `raspberry_pi/core/backend/routes/alerts.py` | Migrated (disabled) | Router not included pending ISSUE-001 |
| Route: users | `raspberry_pi/backend/routes/users.py` | `raspberry_pi/core/backend/routes/users.py` | Migrated (disabled) | Router not included pending ISSUE-001 |
| Colored logger | `raspberry_pi/backend/services/colored_logger.py` | `raspberry_pi/core/backend/services/colored_logger.py` | Migrated | Used in `main.py` |
| `requirements.txt` | `raspberry_pi/backend/requirements.txt` | `raspberry_pi/core/backend/requirements.txt` | Updated | LoRa/spidev deps removed; paho-mqtt retained |
| `Dockerfile` (backend) | `raspberry_pi/backend/Dockerfile` | `raspberry_pi/core/backend/Dockerfile` | Updated | Python 3.11; no spidev |

### Core Dashboard (Moved from `raspberry_pi/dashboard/` to `raspberry_pi/core/dashboard/`)

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| React app source | `raspberry_pi/dashboard/src/` | `raspberry_pi/core/dashboard/src/` | Migrated | No changes to source |
| `package.json` / `vite.config.js` | `raspberry_pi/dashboard/` | `raspberry_pi/core/dashboard/` | Migrated | Build output goes to `dist/` |
| `Dockerfile` (dashboard) | `raspberry_pi/dashboard/Dockerfile` | `raspberry_pi/core/dashboard/Dockerfile` | Migrated | Multi-stage Vite build → nginx:alpine |

### Core Database (Moved from `raspberry_pi/db/` to `raspberry_pi/core/database/`)

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| `001_create_registry.sql` | `raspberry_pi/db/migrations/` | `raspberry_pi/core/database/migrations/001_create_registry.sql` | Migrated | Unchanged |
| `001_create_telemetry.sql` | `raspberry_pi/db/migrations/` | `raspberry_pi/core/database/migrations/001_create_telemetry.sql` | Migrated | `processed_messages` table added |
| `003_add_gateway_metadata.sql` | _(did not exist)_ | `raspberry_pi/core/database/migrations/003_add_gateway_metadata.sql` | Created new | `gateway_id`, `rssi_dbm`, `snr_db` columns |

### Infrastructure

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| Nginx config | `raspberry_pi/nginx/default.conf` | `raspberry_pi/core/nginx/default.conf` | Migrated | WebSocket routes updated |
| Gateway EMQX config | _(did not exist)_ | `raspberry_pi/gateway/emqx/emqx.conf` + `acl.conf` | Created new | Local EMQX for Wi-Fi nodes |
| Core EMQX config | `raspberry_pi/emqx/emqx.conf` | `raspberry_pi/core/emqx/emqx.conf` + `acl.conf` | Migrated | TLS on 8883; deny-all ACL |
| Gateway `docker-compose.yml` | _(did not exist)_ | `raspberry_pi/gateway/docker-compose.yml` | Created new | EMQX local + gateway; SPI/GPIO device mapping |
| Core `docker-compose.yml` | `raspberry_pi/docker-compose.yml` | `raspberry_pi/core/docker-compose.yml` | Migrated | 5 services; PostgreSQL internal only |
| Root `docker-compose.yml` | `docker-compose.yml` | `docker-compose.yml` | Updated | Redirected to core services |
| Gateway systemd unit | _(did not exist)_ | `raspberry_pi/gateway/systemd/enviromesh-gateway.service` | Created new | For bare-metal deployment |
| LoRa systemd unit | `raspberry_pi/systemd/enviromesh-lora.service` | `raspberry_pi/gateway/systemd/enviromesh-lora.service` | Migrated | Updated `ExecStart` path |
| Gateway `.env.example` | _(did not exist)_ | `raspberry_pi/gateway/.env.example` | Created new | Gateway MQTT and LoRa env vars |
| Core `.env.example` | `raspberry_pi/.env.example` | `raspberry_pi/core/.env.example` | Updated | PostgreSQL, EMQX, JWT env vars |
| Root `.env.example` | `.env.example` | `.env.example` | Updated | Points to both subtree `.env` files |

### Scripts

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| `deploy_gateway.sh` | _(did not exist)_ | `scripts/deploy_gateway.sh` | Created new | Zero-loss gateway deployment |
| `deploy_core.sh` | _(did not exist)_ | `scripts/deploy_core.sh` | Created new | Core services deployment |
| `setup_gateway.sh` | _(did not exist)_ | `scripts/setup_gateway.sh` | Created new | First-time gateway setup |
| `setup_core.sh` | _(did not exist)_ | `scripts/setup_core.sh` | Created new | First-time core setup |
| `setup_env.sh` | _(did not exist)_ | `scripts/setup_env.sh` | Created new | Environment variable scaffolding |
| `backup_database.sh` | `scripts/backup_database.sh` | `scripts/backup_database.sh` | Updated | Updated paths to `raspberry_pi/core/`; 7-day retention |
| `db_manage.sh` | `scripts/db_manage.sh` | `scripts/db_manage.sh` | Updated | Updated container name references |
| `docker_control.sh` | `scripts/docker_control.sh` | `scripts/docker_control.sh` | Updated | Covers both gateway and core compose files |
| `simulate_telemetry.py` | `scripts/simulate_telemetry.py` | `scripts/simulate_telemetry.py` | Updated | Publishes to gateway EMQX (RPi 1) |
| `mqtt_monitor.py` | `scripts/mqtt_monitor.py` | `scripts/mqtt_monitor.py` | Updated | Can monitor both brokers |
| `lora_packet_inject.py` | `scripts/lora_packet_inject.py` | `scripts/lora_packet_inject.py` | Migrated | Test tool for LoRa pipeline |
| `check_gateway_health.py` | _(did not exist)_ | `scripts/check_gateway_health.py` | Created new | Checks SQLite queue, MQTT forwarder |
| `check_core_health.py` | _(did not exist)_ | `scripts/check_core_health.py` | Created new | Checks TimescaleDB, EMQX, backend |
| `check_health.py` | `scripts/check_health.py` | `scripts/check_health.py` | Updated | Calls both sub-checks |
| `scripts/README.md` | _(did not exist)_ | `scripts/README.md` | Created new | Documents all scripts |

### Documentation

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| `architecture.md` | _(did not exist)_ | `docs/architecture.md` | Created new | Two-Pi architecture diagram and data flow |
| `certificate-setup.md` | _(did not exist)_ | `docs/certificate-setup.md` | Created new | TLS cert generation procedure |
| `database-schema.md` | _(did not exist)_ | `docs/database-schema.md` | Created new | TimescaleDB schema; `processed_messages` |
| `deployment-guide.md` | `docs/deployment-guide.md` | `docs/deployment-guide.md` | Updated | Two-Pi deployment steps |
| `mqtt-protocol.md` | _(did not exist)_ | `docs/mqtt-protocol.md` | Created new | Topic hierarchy, QoS, ACL |
| `network-and-firewall.md` | _(did not exist)_ | `docs/network-and-firewall.md` | Created new | Port table, firewall rules |
| `security.md` | _(did not exist)_ | `docs/security.md` | Created new | Implemented controls |
| `troubleshooting.md` | _(did not exist)_ | `docs/troubleshooting.md` | Created new | Common failure modes |
| `security-assessment.md` | _(did not exist)_ | `docs/security-assessment.md` | Created new (this audit) | All 10 findings |
| `maintenance-and-known-issues.md` | _(did not exist)_ | `docs/maintenance-and-known-issues.md` | Created new (this audit) | 6 tracked issues + ops procedures |

### Root Files

| Existing Component | Previous Location | New Location | Status | Notes |
|---|---|---|---|---|
| `README.md` | `README.md` | `README.md` | Updated | Two-Pi quickstart |
| `docker-compose.yml` | `docker-compose.yml` | `docker-compose.yml` | Updated | Redirects to `raspberry_pi/core/docker-compose.yml` |
| `.env.example` | `.env.example` | `.env.example` | Updated | Root-level template |
| `AUDIT_REPORT.md` | _(did not exist)_ | `AUDIT_REPORT.md` | Created new (this audit) | Full audit report |
| `IMPLEMENTATION_PLAN.md` | _(did not exist)_ | `IMPLEMENTATION_PLAN.md` | Created new (this audit) | Phased plan |
| `MIGRATION_STATUS.md` | _(did not exist)_ | `MIGRATION_STATUS.md` | Created new (this audit) | This file |
| `MAINTENANCE_STATUS.md` | _(did not exist)_ | `MAINTENANCE_STATUS.md` | Created new (this audit) | Outstanding maintenance items |
| `security/README.md` | _(did not exist)_ | `security/README.md` | Created new (this audit) | Security testing scope |
| `security/rules-of-engagement.md` | _(did not exist)_ | `security/rules-of-engagement.md` | Created new (this audit) | Test constraints |
| `security/reports/0*.md` | _(did not exist)_ | `security/reports/` | Created new (this audit) | 5 PoC report templates |
