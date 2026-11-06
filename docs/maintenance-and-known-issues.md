# EnviroMesh — Maintenance & Known Issues Guide

> [!NOTE]
> This document records operational procedures, discovered issues, and known limitations in the
> EnviroMesh Two-Raspberry-Pi deployment.
> Status values: **Open** / **Fixed** / **Mitigated** / **Blocked** / **Accepted**.

---

## 1. Discovered Issues and Known Limitations

| Issue ID | Component | Severity | Error / Symptom | Root Cause | Affected File | Required Modification | Fix Implemented | Verification | Manual Action | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **ISSUE-001** | FastAPI Core Backend | High | Authentication routes disabled; all endpoints unauthenticated | JWT auth logic not finished in prototype | `raspberry_pi/core/backend/main.py` | Implement JWT verification and scope data queries to the signed-in user's group | Implemented on `feature/user-management`; users/auth routers enabled, group-scoped device/telemetry queries, initial admin bootstrap and password rotation added | Build + API integration tests pending | Apply migrations 004/005, configure `JWT_SECRET`, bootstrap an admin, and deploy | Mitigated in branch; deployment verification required |
| **ISSUE-002** | Gateway & Core TLS | High | Forwarder fails to connect to port 8883 with SSL error | TLS CA / Server certificates not generated yet | `raspberry_pi/core/emqx/certs/` & `raspberry_pi/gateway/certs/core-ca.crt` | Generate self-signed CA and server certificates matching `CORE_LAN_IP` SAN | No | `scripts/check_gateway_health.py` | Run OpenSSL cert generation on RPi 2 and copy `ca.crt` to RPi 1 | Blocked (Requires hardware) |
| **ISSUE-003** | Core Database | Medium | Missing tables or columns on fresh deployment | TimescaleDB migrations must be applied manually | `raspberry_pi/core/database/migrations/` | Run `psql` command to apply migrations `001` and `003` | Documented in deployment guide | Database inspection | Execute migration SQL script via `deploy_core.sh` | Open |
| **ISSUE-004** | Gateway LoRa Receiver | Medium | LoRa receiver exits with SPI opening error in simulated container | SPI hardware device `/dev/spidev0.0` missing in container | `raspberry_pi/gateway/gateway/lora_receiver.py` | Add fallback / mock mode when SPI is absent; verify device on Pi OS | Documented | `py_compile` | Enable SPI interface via `raspi-config` on Raspberry Pi 1 | Not Tested (Requires hardware) |
| **ISSUE-005** | Gateway MQTT Forwarder | Medium | Potential missed messages during brief gateway restart if broker discards session | `clean_session=True` used in `MqttForwarderService` | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` | Set `clean_session=False` and manage persistent client IDs | Documented (TODO in code) | Code review | Update forwarder to persistent session when upgrading to MQTT v5 | Open |
| **ISSUE-006** | Core Reverse Proxy | High | Web dashboard & API served exclusively over cleartext HTTP on port 8080 | Nginx configuration lacks SSL directives | `raspberry_pi/core/nginx/default.conf` | Configure HTTPS server block on port 443 with TLS cert and HTTP redirection | Documented (TODO in code) | Config review | Generate domain/self-signed cert and bind port 443 in Compose | Open |

---

## 2. Operational Maintenance Procedures

### 2.1 Service Management & Restart

#### Restarting Gateway Services (RPi 1)
```bash
# Graceful restart of gateway stack (preserves SQLite queue data in volume)
docker compose -f raspberry_pi/gateway/docker-compose.yml restart

# Rebuild and restart only the gateway ingestion/forwarding Python service
docker compose -f raspberry_pi/gateway/docker-compose.yml up -d --build gateway
```

#### Restarting Core Services (RPi 2)
```bash
# Graceful restart of core stack (preserves TimescaleDB data volume)
docker compose -f raspberry_pi/core/docker-compose.yml restart

# Restart only the FastAPI backend
docker compose -f raspberry_pi/core/docker-compose.yml restart backend
```

> [!CAUTION]
> Never execute `docker compose down -v` on either Raspberry Pi. This destroys persistent volumes containing the offline queue or central historical telemetry database.

---

### 2.2 Inspecting Service Logs

```bash
# Gateway logs
docker compose -f raspberry_pi/gateway/docker-compose.yml logs -f gateway
docker compose -f raspberry_pi/gateway/docker-compose.yml logs -f emqx-local

# Core logs
docker compose -f raspberry_pi/core/docker-compose.yml logs -f backend
docker compose -f raspberry_pi/core/docker-compose.yml logs -f emqx-core
docker compose -f raspberry_pi/core/docker-compose.yml logs -f timescaledb
```

---

### 2.3 Storage and Queue Inspection

#### Monitoring SQLite Queue Size on RPi 1
```bash
# Check number of undelivered messages
sqlite3 /var/lib/docker/volumes/enviromesh-gateway_gateway_queue/_data/queue.db \
  "SELECT count(*) AS pending_count FROM queue;"

# Inspect oldest unforwarded message and attempt count
sqlite3 /var/lib/docker/volumes/enviromesh-gateway_gateway_queue/_data/queue.db \
  "SELECT message_id, attempts, created_at, last_attempt FROM queue ORDER BY attempts ASC, created_at ASC LIMIT 5;"
```

#### Monitoring PostgreSQL Storage & Telemetry Growth on RPi 2
```bash
# Connect to TimescaleDB inside container
docker exec -it enviromesh-timescaledb psql -U enviromesh_app -d enviromesh -c \
  "SELECT hypertable_name, total_bytes FROM timescaledb_information.hypertables;"

# Check total telemetry count
docker exec -it enviromesh-timescaledb psql -U enviromesh_app -d enviromesh -c \
  "SELECT count(*) FROM telemetry;"
```

---

### 2.4 Database Backup and Recovery

#### Performing Backup (RPi 2)
```bash
# Run the automated backup script
./scripts/backup_database.sh
# Stored at /var/backups/enviromesh/enviromesh_YYYYMMDD_HHMMSS.sql.gz
```

#### Restoring from Backup
```bash
# 1. Unpack backup
gunzip -c /var/backups/enviromesh/enviromesh_20261104_120000.sql.gz > /tmp/restore.sql

# 2. Restore into TimescaleDB container
docker exec -i enviromesh-timescaledb psql -U enviromesh_app -d enviromesh < /tmp/restore.sql
rm /tmp/restore.sql
```

---

### 2.5 Credential and TLS Certificate Rotation

1. **Rotate MQTT Forwarder Credentials**:
   ```bash
   # On RPi 2 Core:
   docker exec -it enviromesh-emqx-core emqx ctl admins passwd gw_forwarder 'NEW_STRONG_PASSWORD'

   # On RPi 1 Gateway:
   # Update MQTT_CORE_PASSWORD in raspberry_pi/gateway/.env
   docker compose -f raspberry_pi/gateway/docker-compose.yml restart gateway
   ```

2. **Renew TLS Certificates**:
   - Follow instructions in [`docs/certificate-setup.md`](certificate-setup.md).
   - Re-generate `server.crt` on RPi 2.
   - If CA expires, copy new `ca.crt` to `raspberry_pi/gateway/certs/core-ca.crt` and restart both stacks.

---

### 2.6 Post-Incident Disaster Recovery

#### Scenario A: Power Loss on Gateway (RPi 1)
1. RPi 1 boots up automatically via systemd service `enviromesh-gateway.service`.
2. Docker daemon starts `emqx-local` and `gateway`.
3. SQLite WAL mode recovers any in-flight uncommitted transactions cleanly.
4. Telemetry collection and forwarding resumes immediately.

#### Scenario B: Extended Core Outage (RPi 2 Offline)
1. Gateway continues ingesting LoRa and Wi-Fi sensor packets.
2. Messages accumulate in the SQLite offline queue (up to `QUEUE_MAX_MESSAGES = 50,000`).
3. Forwarder enters exponential backoff (retrying every 60s max).
4. Once RPi 2 comes back online:
   - Forwarder establishes TLS connection to RPi 2 port 8883.
   - Forwarder drains the SQLite queue batch by batch.
   - Deduplication table `processed_messages` on RPi 2 safely ignores any duplicate messages forwarded during the transition.
