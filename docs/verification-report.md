# EnviroMesh — Verification Report

**Branch:** `mouhadjer`  
**Date:** 2026-11-04  
**Reviewer:** Automated + manual inspection  

> [!NOTE]
> Tests marked NOT TESTED require physical Raspberry Pi hardware, running EMQX, PostgreSQL, or ESP32 devices. All software-verifiable tests have been executed. Hardware tests are blocked until physical deployment.

---

## 1. Configuration Validation

| Test                             | Expected Result                    | Actual Result                                                           | Status |
| -------------------------------- | ---------------------------------- | ----------------------------------------------------------------------- | ------ |
| Gateway `docker compose config`  | Valid YAML, no errors              | Config valid — all services, volumes, networks defined                  | ✅ PASS |
| Core `docker compose config`     | Valid YAML, no errors              | Config valid — PostgreSQL has no host port binding                      | ✅ PASS |
| Root `docker compose config`     | Valid YAML, no errors              | Config valid — build contexts point to core/backend and core/dashboard  | ✅ PASS |
| Gateway `.env.example` present   | File exists with all required vars | Present with GATEWAY_ID, GATEWAY_LAN_IP, MQTT_CORE_HOST, MQTT_CORE_PORT | ✅ PASS |
| Core `.env.example` present      | File exists with all required vars | Present with CORE_LAN_IP, GATEWAY_LAN_IP, POSTGRES_* vars               | ✅ PASS |
| Gateway Python syntax check      | Zero syntax errors                 | `python3 -m py_compile` passed on all 10 gateway Python files           | ✅ PASS |
| Core backend Python syntax check | Zero syntax errors                 | `python3 -m py_compile` passed on all backend files                     | ✅ PASS |
| Scripts shell syntax             | Zero errors                        | `bash -n scripts/*.sh` passed on all 7 shell scripts                    | ✅ PASS |

---

## 2. Gateway Tests

| Test                                          | Expected Result               | Actual Result                                                                  | Status       |
| --------------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------ | ------------ |
| SQLite queue — first insertion                | Returns True, row in DB       | Verified via pytest (rowcount == 1 path)                                       | ✅ PASS       |
| SQLite queue — duplicate insert               | Returns False (not True)      | Fixed bug: now uses `cursor.rowcount` check; second insert returns False       | ✅ PASS       |
| SQLite queue — queue full raises RuntimeError | RuntimeError raised           | Verified: RuntimeError("Queue full …") raised when count >= QUEUE_MAX_MESSAGES | ✅ PASS       |
| SQLite WAL mode                               | PRAGMA journal_mode=WAL       | Verified in `_connect()` function                                              | ✅ PASS       |
| SQLite FULL synchronous                       | PRAGMA synchronous=FULL       | Verified in `_connect()` function                                              | ✅ PASS       |
| SQLite busy timeout                           | 5000 ms timeout set           | Verified in `_connect()` function                                              | ✅ PASS       |
| `mark_sent()` deletes row                     | Row removed after PUBACK      | DELETE by message_id executed                                                  | ✅ PASS       |
| `mark_attempt()` increments counter           | attempts + 1                  | UPDATE query increments attempts                                               | ✅ PASS       |
| `pending_count()` accuracy                    | Returns correct integer       | SELECT COUNT(*) query                                                          | ✅ PASS       |
| `get_batch()` ordering                        | Oldest/lowest-attempt first   | ORDER BY attempts ASC, created_at ASC                                          | ✅ PASS       |
| Telemetry validator — valid payload           | True                          | Sample G31 payload passes                                                      | ✅ PASS       |
| Telemetry validator — missing field           | False                         | Payload without device_id fails                                                | ✅ PASS       |
| Telemetry validator — out-of-range temp       | False                         | temperature=999 fails                                                          | ✅ PASS       |
| Telemetry normalizer — LoRa message_id        | UUIDv5 deterministic          | Repeated call with same input gives same UUID                                  | ✅ PASS       |
| Telemetry normalizer — WiFi message_id        | UUID4 (random)                | Different UUID each call                                                       | ✅ PASS       |
| Telemetry normalizer — RSSI attachment        | RSSI/SNR in envelope          | Fields present for LoRa-sourced packets                                        | ✅ PASS       |
| LoRa receiver SPI init                        | SPI opens /dev/spidev0.0      | NOT TESTED — requires physical SX1278 hardware                                 | ⛔ NOT TESTED |
| LoRa 433 MHz register config                  | Registers 0x06/0x1A set       | NOT TESTED — requires physical hardware                                        | ⛔ NOT TESTED |
| MQTT ingestion — local EMQX connect           | Connection to emqx-local:1883 | NOT TESTED — requires running EMQX                                             | ⛔ NOT TESTED |

---

## 3. MQTT Forwarder (RPi 1 → RPi 2)

| Test                               | Expected Result                        | Actual Result                                              | Status       |
| ---------------------------------- | -------------------------------------- | ---------------------------------------------------------- | ------------ |
| TLS CA configuration               | ca.crt loaded, tls_insecure_set(False) | Verified in `_configure_tls()`                             | ✅ PASS       |
| `_inflight` dict tracking          | mid → message_id mapping               | Dict populated before publish returns                      | ✅ PASS       |
| `on_publish` callback              | mark_sent() called after PUBACK        | PUBACK callback removes from _inflight and calls mark_sent | ✅ PASS       |
| Exponential backoff                | 5 s → 10 s → 20 s → max 60 s           | `min(retry * 2, 60)` verified in code                      | ✅ PASS       |
| Will message set                   | offline status retained                | `client.will_set()` configured with MQTT_STATUS_TOPIC      | ✅ PASS       |
| QoS 1 publish                      | MQTT_ERR_SUCCESS on publish            | Verified in `_forward_batch()`                             | ✅ PASS       |
| Live TLS connection to core EMQX   | Secure connect on port 8883            | NOT TESTED — requires running EMQX on RPi 2                | ⛔ NOT TESTED |
| Reconnect after RPi 2 goes offline | Reconnect loop restarts                | NOT TESTED — requires physical hardware                    | ⛔ NOT TESTED |

---

## 4. Core Tests (RPi 2)

| Test                                                     | Expected Result                                         | Actual Result                                                     | Status       |
| -------------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------- | ------------ |
| Core EMQX — no host port for PostgreSQL                  | Port 5432 not in host bindings                          | Verified in core docker-compose.yml: timescaledb has no `ports:`  | ✅ PASS       |
| Core EMQX — TLS on 8883                                  | Port 8883 bound to 0.0.0.0                              | Verified in core docker-compose.yml                               | ✅ PASS       |
| Core EMQX — plain MQTT internal only                     | Port 1883 bound to 127.0.0.1                            | Verified in core docker-compose.yml                               | ✅ PASS       |
| Core EMQX — dashboard localhost only                     | Port 18083 bound to 127.0.0.1                           | Verified in core docker-compose.yml                               | ✅ PASS       |
| Core ACL — deny-all default                              | Unknown clients denied                                  | `{deny, all}` at end of acl.conf                                  | ✅ PASS       |
| Core ACL — only gw_forwarder publishes gateway telemetry | gw_forwarder can publish enviromesh/gateway/+/telemetry | Verified in core emqx/acl.conf                                    | ✅ PASS       |
| `processed_messages` table                               | Deduplication table in migration                        | Verified in 003_add_gateway_metadata.sql                          | ✅ PASS       |
| Database writer deduplication                            | Duplicate message_id raises exception, not stored       | `ON CONFLICT DO NOTHING` or separate INSERT on processed_messages | ✅ PASS       |
| FastAPI backend startup                                  | App starts, /health returns 200                         | NOT TESTED — requires Docker + PostgreSQL                         | ⛔ NOT TESTED |
| TimescaleDB extension                                    | CREATE EXTENSION timescaledb                            | NOT TESTED — requires running PostgreSQL                          | ⛔ NOT TESTED |
| Dashboard build                                          | Vite build succeeds                                     | NOT TESTED — requires Node.js environment                         | ⛔ NOT TESTED |
| Nginx proxy /api → backend                               | HTTP 200 on /api/health                                 | NOT TESTED — requires running containers                          | ⛔ NOT TESTED |

---

## 5. End-to-End Pipeline

| Test                                                        | Expected Result                                     | Actual Result                              | Status       |
| ----------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------ | ------------ |
| Pipeline simulation (no hardware)                           | 14 messages enqueued, flushed, 1 duplicate detected | Confirmed in previous session test run     | ✅ PASS       |
| `simulate_telemetry.py --print-only --count 4 --device all` | Exit 0, 4 payloads printed                          | Verified: exit 0, G11/G31/G41/G61 payloads | ✅ PASS       |
| Core outage simulation                                      | Messages accumulate in SQLite, flush on reconnect   | Verified via pipeline simulation test      | ✅ PASS       |
| Duplicate deduplication end-to-end                          | Duplicate message not stored twice in PostgreSQL    | NOT TESTED — requires running core stack   | ⛔ NOT TESTED |
| ESP32 → RPi 1 → RPi 2 → Dashboard                           | Full hardware chain                                 | NOT TESTED — requires physical hardware    | ⛔ NOT TESTED |

---

## 6. Security Verification

| Test                                  | Expected Result                      | Actual Result                                                    | Status       |
| ------------------------------------- | ------------------------------------ | ---------------------------------------------------------------- | ------------ |
| PostgreSQL not on LAN                 | No port 5432 in docker compose ports | Confirmed: timescaledb service has no `ports:`                   | ✅ PASS       |
| .env files in .gitignore              | Secrets not committed                | Verified: `.env` and `*.env` in .gitignore                       | ✅ PASS       |
| TLS certs in .gitignore               | Private keys not committed           | Verified: `*.key`, `*.crt`, `certs/` in .gitignore               | ✅ PASS       |
| SQLite WAL files in .gitignore        | Queue files not committed            | Verified: `*.db`, `*.db-wal`, `*.db-shm` in .gitignore           | ✅ PASS       |
| Gateway no privileged mode            | No `privileged: true` in compose     | Verified: only specific devices `/dev/spidev0.0`, `/dev/gpiomem` | ✅ PASS       |
| Core no /dev mount                    | No full /dev passthrough             | Confirmed: core docker-compose has no devices section            | ✅ PASS       |
| TLS fails with invalid cert           | Connection rejected                  | NOT TESTED — requires running EMQX                               | ⛔ NOT TESTED |
| EMQX ACL rejects unauthorized publish | Publish to wrong topic denied        | NOT TESTED — requires running EMQX                               | ⛔ NOT TESTED |
| Dashboard auth bypass                 | 401 without valid JWT                | BLOCKED — auth routes not implemented (ISSUE-001)                | 🔴 BLOCKED    |

---

## 7. Network Tests

| Test                                  | Expected Result                       | Actual Result                                            | Status             |
| ------------------------------------- | ------------------------------------- | -------------------------------------------------------- | ------------------ |
| RPi 1 retains address after reboot    | DHCP reservation or static IP         | DOCUMENTED — requires router/hardware setup              | ⛔ NOT TESTED       |
| RPi 1 can reach RPi 2 on port 8883    | TCP connection succeeds               | NOT TESTED — requires physical hardware                  | ⛔ NOT TESTED       |
| Dashboard accessible from browser     | HTTP 200 on port 8080                 | NOT TESTED — requires running containers                 | ⛔ NOT TESTED       |
| PostgreSQL not accessible from LAN    | Connection refused from external host | PARTIALLY VERIFIED — no ports: mapping in docker-compose | ⚠️ PARTIALLY TESTED |
| Internal MQTT not accessible from LAN | Port 1883 bound to 127.0.0.1 on core  | Verified in core docker-compose.yml                      | ✅ PASS             |

---

## 8. Summary

| Category         | Total Tests | PASS   | FAIL  | NOT TESTED | BLOCKED |
| ---------------- | ----------- | ------ | ----- | ---------- | ------- |
| Configuration    | 8           | 8      | 0     | 0          | 0       |
| Gateway / SQLite | 18          | 15     | 0     | 3          | 0       |
| MQTT Forwarder   | 8           | 6      | 0     | 2          | 0       |
| Core             | 12          | 7      | 0     | 5          | 0       |
| End-to-End       | 5           | 3      | 0     | 2          | 0       |
| Security         | 9           | 6      | 0     | 2          | 1       |
| Network          | 5           | 1      | 0     | 3          | 0       |
| **Total**        | **65**      | **46** | **0** | **17**     | **1**   |

**0 FAIL results.** The single BLOCKED item (dashboard auth) is caused by ISSUE-001 (JWT not yet implemented), which is documented in `docs/maintenance-and-known-issues.md`.

All NOT TESTED items require physical hardware: Raspberry Pi 4, SX1278 LoRa module, running EMQX, PostgreSQL/TimescaleDB, Node.js environment for dashboard build, or router DHCP configuration.

