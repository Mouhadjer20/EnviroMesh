# EnviroMesh — Audit Report

> [!NOTE]
> This report covers the state of the codebase as of the audit date.
> Findings are graded by severity: **HIGH** / **MEDIUM** / **LOW**.
> Status labels: **Fixed** / **Mitigated** / **Open** / **Accepted**.

---

## Audit Scope

| Field | Value |
|---|---|
| **Audit date** | 2026-11-04 |
| **Branch** | `mouhadjer` |
| **HEAD commit** | `55f468e5d8e96d7f52e7912be5451558a991cb22` |
| **Commit message** | `chore(git): update gitignore to protect TLS certificates, SQLite queue files, and backups` |
| **Architecture** | Two-Raspberry-Pi split: RPi 1 (Gateway) + RPi 2 (Core) |
| **Methodology** | Manual static code review, docker-compose configuration audit, ACL trace analysis, firmware pin mapping |
| **Auditor** | EnviroMesh security engineering team |
| **Scope** | All source files under `raspberry_pi/`, `firmware/`, `scripts/`, `docs/` |

---

## Component Audit Table

| Component | Existing Implementation | Problems Identified | Required Modification | Priority |
|---|---|---|---|---|
| **Gateway Python services** | `config.py`, `main.py`, `sqlite_queue.py`, `mqtt_forwarder.py`, `mqtt_ingestion.py`, `lora_receiver.py`, `telemetry_validator.py`, `telemetry_normalizer.py`, `health_monitor.py`, `logger.py` — fully implemented; WAL+FULL sync on SQLite; `enqueue()` uses `cursor.rowcount` correctly; QoS 1 with PUBACK-before-delete; exponential back-off 5 → 60 s | LoRa packets carry no HMAC/signature (FIND-003). `clean_session=True` on MQTT forwarder (FIND-010). No explicit SQLite file permission enforcement (FIND-006). | Add HMAC-SHA256 to LoRa packet envelope (requires firmware update). Set `clean_session=False` on forwarder. Enforce `chmod 600` on `queue.db` in gateway setup script. | HIGH / MEDIUM |
| **Gateway Docker** | `docker-compose.yml`, `Dockerfile`, `.env.example`, `emqx/acl.conf`, `emqx/emqx.conf` — SPI/GPIO devices scoped to gateway container only; EMQX dashboard on `127.0.0.1:18083`; ACL deny-all default | EMQX built-in-database auth is configured but actual credentials are not pre-seeded — a device can connect with any username until accounts are created (FIND-001). Dashboard has no extra auth beyond EMQX default (FIND-008). | Document and enforce mandatory credential provisioning step before first bring-up. Consider seeding credentials at container init time. | MEDIUM / LOW |
| **Core Docker** | `raspberry_pi/core/docker-compose.yml`, `.env.example` — PostgreSQL not exposed to host (internal only). EMQX TLS on 8883. Backend subscribes to `enviromesh/gateway/+/telemetry`. | No issues with PostgreSQL exposure. Nginx serves only HTTP (FIND-002). | Add HTTPS termination to Nginx (TLS certificate + 443 listener). | HIGH |
| **Core Backend** | `main.py` — FastAPI 2.0.0; `devices`, `telemetry`, `groups` routers included; `alerts` and `users` routers commented out | JWT auth routes disabled (FIND-005). No rate limiting (FIND-004). `# app.include_router(users.router)` and `# app.include_router(alerts.router)` are both commented out in `main.py` line 42–43. | Implement JWT middleware and re-enable auth routes (ISSUE-001). Add `slowapi` or Nginx `limit_req`. | HIGH / MEDIUM |
| **Core EMQX** | `raspberry_pi/core/emqx/acl.conf` — only `gw_forwarder` may publish; only `enviromesh_backend` may subscribe; deny-all default | Server-auth-only TLS; no mutual TLS (FIND-007). | Add client certificate requirement for `gw_forwarder` connection. | MEDIUM |
| **Database** | TimescaleDB migrations in `raspberry_pi/core/database/migrations/`: `001_create_registry.sql`, `001_create_telemetry.sql`, `003_add_gateway_metadata.sql`. `processed_messages` table used for deduplication. | Migrations must be run manually (ISSUE-003). | Automate migration execution on container startup via an entrypoint script. | MEDIUM |
| **Dashboard** | React + Vite, served by nginx inside the dashboard container. Proxied through the core Nginx reverse proxy. | No HTTPS at the Nginx layer (FIND-002). No authentication gate on the dashboard URL (tied to FIND-005). | Add HTTPS + redirect HTTP → HTTPS. Enable auth guard once JWT is implemented. | HIGH |
| **Nginx** | `raspberry_pi/core/nginx/default.conf` — HTTP only on port 80 (exposed as 8080). Routes `/api/` → `backend:8000`, `/ws/` → WebSocket. | No HTTPS (FIND-002). No `limit_req` rate limiting (FIND-004). | Add TLS configuration with `ssl_certificate` / `ssl_certificate_key`. Add `limit_req_zone` for `/api/`. | HIGH / MEDIUM |
| **Firmware** | G11 (LoRa, `firmware/nodes/node_g11/`), G41 (LoRa, `firmware/nodes/node_g41/`), G31 (Wi-Fi MQTT, `firmware/nodes/node_g31/`), G42 (Wi-Fi MQTT, `firmware/nodes/node_g42/`), G43 (Wi-Fi MQTT, `firmware/nodes/node_g43/`), G61 (Wi-Fi MQTT + BLE + servo, `firmware/nodes/node_g61_servo/`) | LoRa nodes (G11, G41) transmit plain JSON with no authentication, replay protection, or HMAC (FIND-003). Wi-Fi nodes connect to RPi 1 local EMQX but rely on shared secrets in `secrets.h` files. No OTA update mechanism. | Add HMAC-SHA256 keyed on a per-device shared secret to LoRa JSON payload. Rotate `secrets.h` credentials periodically. | HIGH |
| **Scripts** | `backup_database.sh`, `deploy_core.sh`, `deploy_gateway.sh`, `docker_control.sh`, `setup_core.sh`, `setup_gateway.sh`, `setup_env.sh`, `db_manage.sh`, `simulate_telemetry.py`, `mqtt_monitor.py`, `lora_packet_inject.py`, `check_*.py` | Backup script produces unencrypted `.sql.gz` files (FIND-009). No script enforces SQLite file permissions after gateway setup. | Encrypt backups with `gpg --symmetric` or pipe through `openssl enc`. Add `chmod 600 /var/lib/enviromesh/queue.db` in gateway setup script. | MEDIUM / LOW |

---

## Findings Detail

### FIND-001 — MQTT Authentication Bypass Risk

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Status** | Open |
| **Affected file** | `raspberry_pi/gateway/emqx/acl.conf` |

**Description:**  
The gateway's local EMQX broker is configured with `built_in_database` authentication. The `acl.conf` restricts publish rights per username (G11, G41, G31, G61, G42, G43) and limits the ingestion service account to subscribe-only. However, **user accounts are not provisioned automatically**. Until `emqx ctl admins add` is run for each device, EMQX may fall back to accepting connections with any credentials or anonymous connections depending on the allow-anonymous setting, allowing a rogue device to publish to any topic.

**Evidence:**  
`docker-compose.yml` lines 29–30 set the auth mechanism but do not seed device credentials. `acl.conf` lines 30–37 define per-username topic restrictions — these only have effect if the username accounts exist.

**Impact:**  
A device on the same LAN as RPi 1 could publish telemetry under another device's username, injecting false data into the pipeline.

**Remediation:**  
1. Explicitly set `EMQX_ALLOW_ANONYMOUS=false` in gateway `docker-compose.yml`.  
2. Provide a mandatory `scripts/provision_emqx_accounts.sh` step in the deployment guide.  
3. Consider seeding accounts via EMQX bootstrap configuration rather than post-start `ctl` commands.

---

### FIND-002 — No HTTPS on Dashboard / Nginx

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Status** | Open (ISSUE-006) |
| **Affected file** | `raspberry_pi/core/nginx/default.conf` |

**Description:**  
The Nginx reverse proxy listens only on port 80 (exposed as 8080). All dashboard traffic, REST API calls, and WebSocket streams are transmitted in plaintext over HTTP.

**Evidence:**  
`default.conf` line 10: `listen 80;` — no `listen 443 ssl;` block exists. `docker-compose.yml` line 147: `"${WEB_BIND_IP:-0.0.0.0}:${WEB_PORT:-8080}:80"`.

**Impact:**  
Credentials, session tokens, and all telemetry data returned to the browser are exposed to network interception on the local LAN. This is especially relevant on shared Wi-Fi networks and during sensor commissioning.

**Remediation:**  
1. Generate a TLS certificate (self-signed or Let's Encrypt) for RPi 2.  
2. Add `listen 443 ssl;` block to `default.conf` with `ssl_certificate` / `ssl_certificate_key`.  
3. Add `return 301 https://$host$request_uri;` redirect on port 80.  
4. Mount the certificate into the Nginx container volume.

---

### FIND-003 — LoRa Has No Authentication / Replay Protection

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Status** | Open |
| **Affected file** | `raspberry_pi/gateway/gateway/lora_receiver.py`, `firmware/nodes/node_g11/src/main.ino`, `firmware/nodes/node_g41/src/main/main.ino` |

**Description:**  
LoRa packets transmitted by G11 and G41 are plain JSON with no HMAC signature, timestamp freshness check, or sequence-number authentication. Any party within radio range with a compatible SX1278 module can inject or replay packets that pass the gateway's `validate()` / `normalize()` pipeline.

**Evidence:**  
`lora_receiver.py` `process_packet()` function (lines 220–266): validates JSON structure and schema only — no cryptographic check. `node_g11/main.ino` `sendTelemetry()` (line 265): serialises plain JSON and calls `LoRa.write()`. No HMAC field present in either firmware.

**Impact:**  
An attacker within LoRa range can replay previous telemetry packets to mask real sensor values, or inject fabricated fire/gas alerts.

**Remediation:**  
1. Add an HMAC-SHA256 field to the LoRa JSON payload using a per-device shared secret stored in ESP32 NVS.  
2. Extend `telemetry_validator.py` to verify the HMAC on receipt.  
3. Add a `nonce` or UTC timestamp field and reject packets older than 60 seconds (requires NTP on ESP32 side, or a rolling counter).

See `security/reports/02-lora-replay-poc.md` for the PoC plan.

---

### FIND-004 — No Rate Limiting on FastAPI

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Status** | Open |
| **Affected file** | `raspberry_pi/core/backend/main.py` |

**Description:**  
No `slowapi` rate limiter is configured in the FastAPI application, and no `limit_req_zone` is configured in Nginx. Any client that can reach port 8080 may issue unlimited requests to all API endpoints.

**Evidence:**  
`main.py` does not import `slowapi`. `nginx/default.conf` has no `limit_req` or `limit_req_zone` directives.

**Impact:**  
The API is vulnerable to DoS via request flooding. This also makes brute-force attacks on any authentication endpoints easier once auth is implemented.

**Remediation:**  
Option A — Nginx: add `limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;` and `limit_req zone=api burst=40 nodelay;` in the `/api/` block.  
Option B — Application: add `slowapi` and apply `@limiter.limit("20/second")` to sensitive endpoints.

---

### FIND-005 — JWT Authentication Not Implemented

| Field | Value |
|---|---|
| **Severity** | HIGH |
| **Status** | Open (ISSUE-001) |
| **Affected file** | `raspberry_pi/core/backend/main.py` lines 42–43 |

**Description:**  
The `users` and `alerts` routers are commented out in `main.py`. There is no authentication middleware, no JWT issuance endpoint, and no bearer-token validation on any existing route. All `/api/devices/`, `/api/telemetry/`, and WebSocket endpoints are publicly accessible to anyone who can reach port 8080.

**Evidence:**  
```python
# app.include_router(alerts.router)  # Phase 4
# app.include_router(users.router)   # Phase 4
```

**Impact:**  
Full read access to all telemetry, device registry, and groups data without authentication. Combined with FIND-002 (no HTTPS), data is exposed both in transit and at rest in the browser.

**Remediation:**  
1. Implement `python-jose` JWT generation in `routes/users.py`.  
2. Add `OAuth2PasswordBearer` dependency to protected routes.  
3. Re-enable `app.include_router(users.router)`.  
4. Document the token workflow in `docs/security.md`.

---

### FIND-006 — SQLite Queue File Permissions Not Enforced

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Status** | Open |
| **Affected file** | `raspberry_pi/gateway/gateway/sqlite_queue.py` |

**Description:**  
The SQLite queue database (`queue.db`) is written to a Docker volume at `/var/lib/enviromesh/queue.db`. No explicit `chmod 600` or `chown` is applied by the application or setup scripts. The file mode depends entirely on Docker volume defaults, which is typically `755` on the directory and `644` on files created by the process UID.

**Evidence:**  
`sqlite_queue.py` `_connect()` and `init_db()` (lines 35–63): no `os.chmod` call after database creation.

**Impact:**  
If another process or container mounts the same volume, it can read all queued telemetry messages without restriction.

**Remediation:**  
Add `os.chmod(_DB_PATH, 0o600)` immediately after `init_db()` returns in `main.py`. Add equivalent enforcement in `scripts/setup_gateway.sh`.

---

### FIND-007 — TLS Is Server-Auth Only (No Mutual TLS)

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Status** | Open |
| **Affected file** | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` lines 59–74 |

**Description:**  
The MQTT forwarder authenticates RPi 2's EMQX broker via CA certificate (`tls_set(ca_certs=...)`), but does not present a client certificate. The EMQX broker on RPi 2 does not require a client certificate. This means any client that obtains valid MQTT credentials can connect to core EMQX without proof of identity beyond password.

**Evidence:**  
`mqtt_forwarder.py` `_configure_tls()`: only `ca_certs` is supplied; `certfile` and `keyfile` parameters are absent.

**Impact:**  
If gateway MQTT credentials (`gw_forwarder` username + password) are compromised, an attacker can connect to the core broker from any host and publish telemetry. Mutual TLS would require possession of the client private key even if credentials are leaked.

**Remediation:**  
1. Generate a client certificate for the gateway forwarder (see `docs/certificate-setup.md`).  
2. Pass `certfile=config.MQTT_CLIENT_CERT, keyfile=config.MQTT_CLIENT_KEY` to `tls_set()`.  
3. Configure core EMQX to require client certs (`listener.ssl.verify = verify_peer`).

---

### FIND-008 — EMQX Dashboard Auth Not Hardened (Gateway)

| Field | Value |
|---|---|
| **Severity** | LOW |
| **Status** | Accepted |
| **Affected file** | `raspberry_pi/gateway/docker-compose.yml` lines 34–35 |

**Description:**  
The EMQX dashboard is bound to `127.0.0.1:18083`, which is correct. However, only the default username/password from environment variables is configured, with no IP-based allowlist or additional authentication layer.

**Evidence:**  
`docker-compose.yml` lines 27–28: `EMQX_DASHBOARD__DEFAULT_USERNAME` / `EMQX_DASHBOARD__DEFAULT_PASSWORD` from `.env`.

**Impact:**  
Low — dashboard is not externally accessible. Risk is limited to local access on RPi 1. However, a misconfiguration (e.g., binding to `0.0.0.0`) would expose the dashboard to the LAN.

**Remediation:**  
Document that `EMQX_DASHBOARD_BIND_IP` must remain `127.0.0.1` in production. Add a `.env` validation step in `setup_gateway.sh`.

---

### FIND-009 — Backup Files Are Unencrypted

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Status** | Open |
| **Affected file** | `scripts/backup_database.sh` lines 36–37 |

**Description:**  
The backup script pipes `pg_dump` output directly through `gzip` to produce `.sql.gz` files. The files are stored in `raspberry_pi/core/backups/` with no encryption. Anyone with read access to that directory (or the filesystem) can recover the full database.

**Evidence:**  
`backup_database.sh` line 37:
```bash
pg_dump ... | gzip > "${BACKUP_FILE}"
```
No `gpg`, `openssl enc`, or equivalent.

**Impact:**  
If backup storage media is stolen or if the RPi 2 filesystem is accessed without authorisation, all historical telemetry and device metadata are exposed in plaintext.

**Remediation:**  
Replace the gzip pipe with:
```bash
pg_dump ... | gzip | gpg --symmetric --batch --passphrase-file /etc/enviromesh/backup.key > "${BACKUP_FILE}.gpg"
```
Store the passphrase in a file with `chmod 600`. Document the restore procedure.

---

### FIND-010 — `clean_session=True` on MQTT Forwarder

| Field | Value |
|---|---|
| **Severity** | MEDIUM |
| **Status** | Open (ISSUE-005) |
| **Affected file** | `raspberry_pi/gateway/gateway/mqtt_forwarder.py` line 41 |

**Description:**  
The MQTT forwarder creates its paho client with `clean_session=True`. When the forwarder disconnects and reconnects, any QoS 1 messages that were in-flight but not yet acknowledged by EMQX are **not** re-queued by the broker. The gateway's SQLite queue provides durability for messages not yet published, but messages that were published (mid assigned, added to `_inflight`) but whose PUBACK was not received before a disconnect may be silently lost.

**Evidence:**  
`mqtt_forwarder.py` line 41: `clean_session=True`.  
`_inflight` dict (line 27) is in-memory only — it does not survive process restart.

**Impact:**  
During a gateway restart or momentary network interruption, in-flight messages (between `client.publish()` and PUBACK) can be lost without being re-queued in SQLite. This breaks the at-least-once guarantee for the in-flight window.

**Remediation:**  
Change to `clean_session=False` and assign a stable `client_id` (already set to `f"gw-forwarder-{config.GATEWAY_ID}"`). The broker will then re-deliver unacknowledged QoS 1 messages on reconnect. Verify that the paho reconnect flow handles the session-present flag correctly.

---

## Summary

### Fixed / Implemented Controls

The following security controls are already correctly implemented in the current codebase:

- SQLite WAL + FULL synchronous mode prevents data loss on power failure
- `enqueue()` uses `cursor.rowcount` — idempotent, no race with duplicate inserts
- QoS 1 with PUBACK-before-delete enforced via `_inflight` dict and `on_publish` callback
- Exponential back-off (5 → 60 s) on MQTT connection failure
- Core EMQX TLS on port 8883 with CA verification (`tls_insecure_set(False)`)
- PostgreSQL not exposed to host network (no `ports` entry in `docker-compose.yml`)
- Core EMQX dashboard bound to `127.0.0.1` only
- Gateway EMQX dashboard bound to `127.0.0.1` only
- ACL deny-all defaults on both gateway and core EMQX brokers
- Per-device publish restrictions on gateway EMQX ACL
- `processed_messages` table in TimescaleDB prevents duplicate ingestion
- SPI and GPIO devices scoped to gateway container only (not shared with EMQX container)
- Sensitive files (`.env`, `certs/`, `queue.db`, `backups/`) excluded via `.gitignore`

### Pending (Open Findings)

| ID | Severity | Status |
|---|---|---|
| FIND-001 | MEDIUM | Open — accounts not auto-provisioned |
| FIND-002 | HIGH | Open — no HTTPS on Nginx |
| FIND-003 | HIGH | Open — LoRa packets unauthenticated |
| FIND-004 | MEDIUM | Open — no rate limiting |
| FIND-005 | HIGH | Open — JWT not implemented |
| FIND-006 | LOW | Open — SQLite file permissions |
| FIND-007 | MEDIUM | Open — no mutual TLS |
| FIND-008 | LOW | Accepted — dashboard localhost-only |
| FIND-009 | MEDIUM | Open — unencrypted backups |
| FIND-010 | MEDIUM | Open — clean_session=True |
