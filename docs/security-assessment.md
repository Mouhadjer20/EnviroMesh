# EnviroMesh — Security Assessment

**Classification:** Internal — not for public distribution  
**Date:** 2026-11-04  
**Branch / Commit:** `mouhadjer` / `55f468e`  
**Assessor:** EnviroMesh security engineering team

---

## 1. Scope

This assessment covers all software components of the EnviroMesh two-Pi environmental monitoring system:

- RPi 1 Gateway Python services and Docker configuration
- RPi 2 Core services: EMQX, TimescaleDB, FastAPI, Nginx, React dashboard
- ESP32 firmware for all six sensor nodes (G11, G31, G41, G42, G43, G61)
- Operational scripts

**Out of scope:**
- Physical hardware security (enclosure, tamper protection)
- Network infrastructure outside the deployment LAN
- Third-party cloud services

---

## 2. Components Assessed

| Component | Location | Description |
|---|---|---|
| Gateway Python package | `raspberry_pi/gateway/gateway/` | LoRa reception, SQLite queue, MQTT forwarder |
| Gateway Docker config | `raspberry_pi/gateway/docker-compose.yml`, `emqx/acl.conf` | EMQX local broker, container setup |
| Core Docker config | `raspberry_pi/core/docker-compose.yml`, `emqx/acl.conf` | EMQX central, TimescaleDB, Nginx |
| Core FastAPI backend | `raspberry_pi/core/backend/main.py`, `routes/`, `services/` | REST API, MQTT subscriber, DB writer |
| Nginx reverse proxy | `raspberry_pi/core/nginx/default.conf` | HTTP proxy for dashboard and API |
| Firmware G11 | `firmware/nodes/node_g11/src/main.ino` | LoRa node: DHT11, MQ-2, water |
| Firmware G41 | `firmware/nodes/node_g41/src/main/main.ino` | LoRa node: DHT11, MQ-2, water |
| Firmware G31 | `firmware/nodes/node_g31/src/main.ino` | Wi-Fi MQTT: BMP280, MQ-2, water |
| Firmware G42 | `firmware/nodes/node_g42/src/main/main.ino` | Wi-Fi MQTT: basic sensor node |
| Firmware G43 | `firmware/nodes/node_g43/src/main.ino` | Wi-Fi MQTT: sensor node |
| Firmware G61 | `firmware/nodes/node_g61_servo/src/main.ino` | Wi-Fi MQTT + BLE + servo: MQ-2, DHT11, water, PIR |
| Operational scripts | `scripts/` | Backup, deploy, health check, simulation |

---

## 3. Assessment Methodology

1. **Static code review** — manual inspection of all Python, Arduino/C++, shell, YAML, and configuration files.
2. **Data flow tracing** — following a telemetry message from sensor firmware through LoRa / Wi-Fi → RPi 1 → SQLite → MQTT → RPi 2 → TimescaleDB → API → dashboard.
3. **ACL trace analysis** — verifying that EMQX ACL rules on both brokers enforce the intended publish/subscribe topology.
4. **Docker configuration audit** — checking port bindings, volume mounts, device mappings, and secret handling.
5. **Threat modelling** — identifying the most likely attacker capabilities in a warehouse/industrial IoT deployment.

> [!IMPORTANT]
> No live systems were attacked. No real credentials were used. All findings are based on static analysis only.

---

## 4. Findings

### FIND-001 — MQTT Authentication Bypass Risk

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Evidence** | `raspberry_pi/gateway/emqx/acl.conf`; `docker-compose.yml` lines 29–30 |
| **Status** | **Open** |

**Impact:**  
If EMQX `allow_anonymous` is not explicitly disabled and device accounts are not provisioned before first start, any client on the LAN can publish to arbitrary topics. Per-username ACL rules have no effect until the corresponding user accounts exist in the built-in database.

**Remediation:**  
Set `EMQX_ALLOW_ANONYMOUS=false` in `docker-compose.yml`. Run `scripts/provision_emqx_accounts.sh` before first use. Document as a mandatory pre-flight step.

**Status: Open** — not yet enforced in `docker-compose.yml` or setup scripts.

---

### FIND-002 — No HTTPS on Dashboard / Nginx

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Evidence** | `raspberry_pi/core/nginx/default.conf` line 10: `listen 80;` |
| **Status** | **Open (ISSUE-006)** |

**Impact:**  
All browser traffic (dashboard, REST API calls, WebSocket streams) is transmitted in plaintext. Session cookies and authentication tokens (once implemented) would be exposed to network interception on the local LAN.

**Remediation:**  
Add a `listen 443 ssl;` server block with `ssl_certificate` / `ssl_certificate_key`. Add `return 301 https://` redirect on port 80. Mount the certificate into the Nginx container.

**Status: Open** — blocked on physical TLS certificate generation (ISSUE-002).

---

### FIND-003 — LoRa Has No Authentication or Replay Protection

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Evidence** | `raspberry_pi/gateway/gateway/lora_receiver.py` `process_packet()` lines 220–266; `firmware/nodes/node_g11/src/main.ino` `sendTelemetry()` |
| **Status** | **Open** |

**Impact:**  
LoRa packets (G11, G41) are plain JSON with no HMAC signature, freshness timestamp, or sequence-number authentication. An attacker within radio range can inject fabricated sensor readings or replay captured packets to mask real events (e.g., hide a gas leak by replaying normal-reading packets).

**Remediation:**  
1. Add HMAC-SHA256 keyed on a per-device shared secret to the LoRa JSON payload.  
2. Add a `ts` (UTC epoch) and/or `nonce` field.  
3. Extend `telemetry_validator.py` to verify HMAC on receipt and reject packets older than 60 s.  
4. Store shared secrets in ESP32 NVS (`Preferences`), not in firmware flash.

**Status: Open** — requires firmware update and hardware access (ISSUE-004).

---

### FIND-004 — No Rate Limiting on FastAPI or Nginx

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Evidence** | `raspberry_pi/core/backend/main.py` (no slowapi import); `nginx/default.conf` (no `limit_req`) |
| **Status** | **Open** |

**Impact:**  
No request throttling protects the API from DoS flooding or brute-force attempts on future authentication endpoints.

**Remediation:**  
Add `limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;` to the Nginx `http {}` block and `limit_req zone=api burst=40 nodelay;` in the `/api/` location block. Alternatively use `slowapi` in FastAPI.

**Status: Open** — not yet implemented.

---

### FIND-005 — JWT Authentication Not Implemented

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Evidence** | `raspberry_pi/core/backend/main.py` lines 42–43: `# app.include_router(users.router)` and `# app.include_router(alerts.router)` |
| **Status** | **Open (ISSUE-001)** |

**Impact:**  
All API endpoints (`/api/devices/`, `/api/telemetry/`, `/api/groups/`, WebSocket `/ws/`) are publicly accessible with no authentication. Any host that can reach port 8080 on RPi 2 has full read access to the system.

**Remediation:**  
Implement `python-jose` JWT token issuance in `routes/users.py`. Add `OAuth2PasswordBearer` dependency to protected routes. Re-enable the users router.

**Status: Open** — routes exist but are disabled (Phase 4 work).

---

### FIND-006 — SQLite Queue File Permissions Not Enforced

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Evidence** | `raspberry_pi/gateway/gateway/sqlite_queue.py` `_connect()` lines 35–41 — no `os.chmod` |
| **Status** | **Open** |

**Impact:**  
If another process or container mounts the same Docker volume, it can read all queued telemetry messages without restriction. File mode is determined by Docker volume defaults.

**Remediation:**  
Call `os.chmod(_DB_PATH, 0o600)` immediately after `init_db()` returns. Add equivalent enforcement in `scripts/setup_gateway.sh`.

**Status: Open** — low-risk; scheduled for Phase 4.

---

### FIND-007 — Server-Auth-Only TLS (No Mutual TLS)

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Evidence** | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` `_configure_tls()` lines 59–74 — only `ca_certs` passed |
| **Status** | **Open** |

**Impact:**  
If MQTT credentials for `gw_forwarder` are compromised, an attacker can connect to the core EMQX broker from any host. Mutual TLS would additionally require possession of the client private key.

**Remediation:**  
Generate a client certificate for the gateway forwarder. Pass `certfile` and `keyfile` to `tls_set()`. Configure core EMQX with `listener.ssl.verify = verify_peer`.

**Status: Open** — blocked on physical certificate infrastructure (ISSUE-002).

---

### FIND-008 — EMQX Dashboard Auth Not Hardened (Gateway)

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Evidence** | `raspberry_pi/gateway/docker-compose.yml` lines 34–35: `127.0.0.1:18083` |
| **Status** | **Accepted** |

**Impact:**  
Dashboard is not externally accessible (correctly bound to `127.0.0.1`). Risk is limited to local access on RPi 1. The dashboard password is set via `.env` variables.

**Remediation:**  
Document that `EMQX_DASHBOARD_BIND_IP` must remain `127.0.0.1` in production. Add validation to `setup_gateway.sh`.

**Status: Accepted** — risk is adequately controlled by localhost binding.

---

### FIND-009 — Backup Files Are Unencrypted

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Evidence** | `scripts/backup_database.sh` line 37: `pg_dump ... \| gzip > "${BACKUP_FILE}"` |
| **Status** | **Open** |

**Impact:**  
Backup files in `raspberry_pi/core/backups/` contain the full plaintext database. Theft of storage media or unauthorised file system access exposes all historical telemetry.

**Remediation:**  
Replace gzip-only pipe with `gpg --symmetric` using a securely stored passphrase file (`chmod 600`). Document decryption procedure for restore.

**Status: Open** — scheduled for Phase 4/5.

---

### FIND-010 — `clean_session=True` on MQTT Forwarder

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Evidence** | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` line 41: `clean_session=True` |
| **Status** | **Open (ISSUE-005)** |

**Impact:**  
Messages that were published (mid assigned, added to `_inflight`) but whose PUBACK was not received before a disconnect may be silently lost, breaking the at-least-once delivery guarantee for the in-flight window.

**Remediation:**  
Change to `clean_session=False`. The stable `client_id` (`gw-forwarder-{GATEWAY_ID}`) is already set, satisfying the paho requirement for persistent sessions.

**Status: Open** — single-line fix identified.

---

## 5. Implemented Security Controls

The following controls are correctly implemented in the current codebase:

| Control | Implementation | Location |
|---|---|---|
| SQLite WAL + FULL synchronous mode | `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL` | `sqlite_queue.py` lines 37–38 |
| Idempotent enqueue (`cursor.rowcount`) | `INSERT OR IGNORE` + `cur.rowcount == 1` check | `sqlite_queue.py` lines 89–96 |
| PUBACK-before-delete | `mark_sent()` only called in `on_publish` callback | `mqtt_forwarder.py` lines 112–118 |
| Exponential back-off on MQTT failure | `retry_delay = min(retry_delay * 2, 60)` | `mqtt_forwarder.py` lines 146–147 |
| TLS with CA verification to core EMQX | `tls_set(ca_certs=...)` + `tls_insecure_set(False)` | `mqtt_forwarder.py` lines 61–66 |
| PostgreSQL not exposed to host | No `ports` entry for timescaledb service | `core/docker-compose.yml` lines 73 |
| Core EMQX dashboard on localhost only | `127.0.0.1:18083` binding | `core/docker-compose.yml` line 41 |
| Gateway EMQX dashboard on localhost only | `127.0.0.1:18083` binding | `gateway/docker-compose.yml` line 35 |
| ACL deny-all default on both EMQX brokers | `{deny, all, all, ["#"]}` | `core/emqx/acl.conf` line 35, `gateway/emqx/acl.conf` line 43 |
| Per-device publish restrictions (gateway) | Per-username publish ACL for G11, G31, G41, G42, G43, G61 | `gateway/emqx/acl.conf` lines 30–37 |
| Publish isolation (core) | Only `gw_forwarder` may publish; only `enviromesh_backend` may subscribe | `core/emqx/acl.conf` lines 22–32 |
| `processed_messages` deduplication | UUID-keyed dedup table in TimescaleDB | `001_create_telemetry.sql` |
| SPI/GPIO device scoped to gateway container | `devices: [/dev/spidev0.0, /dev/gpiomem]` on gateway service only | `gateway/docker-compose.yml` lines 91–93 |
| Sensitive files in `.gitignore` | `.env`, `certs/`, `queue.db`, `backups/`, `*.key` excluded | `.gitignore` commit `55f468e` |
| CRC enabled on LoRa radio | `LoRa.enableCrc()` on both G11 and G41 | `node_g11/main.ino` line 391, `node_g41/main.ino` line 250 |
| Graceful LoRa fallback on non-RPi | Returns immediately if `spidev` unavailable | `lora_receiver.py` lines 279–283 |
| Wi-Fi disabled on LoRa nodes | `WiFi.mode(WIFI_OFF)` | `node_g11/main.ino` line 371, `node_g41/main.ino` line 213 |
| Secrets in `secrets.h` excluded from git | `secrets.h` in `.gitignore`; `secrets.example.h` / `secrets.h.example` provided | All Wi-Fi firmware nodes |

---

## 6. Remaining Risks

| Risk | Severity | Likelihood | Notes |
|---|---|---|---|
| LoRa packet injection/replay | HIGH | Medium | Physical attacker within radio range; no HMAC |
| Unauthenticated API access | HIGH | High | No JWT; anyone on LAN has full read access |
| Plaintext HTTP traffic | HIGH | Medium | LAN-local risk; no HTTPS |
| In-flight message loss on reconnect | MEDIUM | Low | Rare; only during restart with QoS 1 messages in flight |
| Credential compromise → core EMQX access | MEDIUM | Low | No mutual TLS; password alone is sufficient |
| Unencrypted backup exfiltration | MEDIUM | Low | Requires physical access to RPi 2 storage |
| EMQX allow-anonymous before provisioning | MEDIUM | Medium | Mitigated by correct deployment procedure |
| SQLite readable by other processes | LOW | Low | Docker volume; no other containers share it currently |

---

## 7. Future Security Work

Listed in approximate priority order:

1. **Implement JWT authentication** (ISSUE-001) — highest impact; unblocks dashboard auth.
2. **Add HTTPS to Nginx** (ISSUE-006, FIND-002) — high impact; requires TLS certs.
3. **Add LoRa HMAC** (FIND-003) — requires firmware update; plan in `security/reports/02-lora-replay-poc.md`.
4. **Set `clean_session=False`** (ISSUE-005, FIND-010) — single-line fix.
5. **Add Nginx rate limiting** (FIND-004) — medium effort; protects future auth endpoints.
6. **Provision EMQX accounts in setup script** (FIND-001) — operational hardening.
7. **Enable mutual TLS** (FIND-007) — requires client cert generation infrastructure.
8. **Encrypt backups** (FIND-009) — operational hardening.
9. **Enforce SQLite file permissions** (FIND-006) — low effort; minor impact.
10. **Conduct live PoC testing** — all five PoC reports in `security/reports/` once hardware and running environment are available.

> [!CAUTION]
> Do not publish or share this document outside the project team. It contains details of unmitigated vulnerabilities.
