# EnviroMesh — Maintenance Status Overview

> [!NOTE]
> High-level tracker of outstanding operational and maintenance work for EnviroMesh.
> See [`docs/maintenance-and-known-issues.md`](docs/maintenance-and-known-issues.md) for full technical root causes and procedures.

---

## Active Issues and Maintenance Items

| Issue ID | Summary | Severity | Component | Status | Required Action |
|---|---|---|---|---|---|
| **ISSUE-001** | JWT / RBAC authentication disabled in FastAPI | High | Core Backend | **Open** | Implement JWT verification middleware and re-enable `users` and `alerts` routers in `raspberry_pi/core/backend/main.py`. |
| **ISSUE-002** | Inter-Pi MQTT TLS certificates must be generated | High | Gateway & Core TLS | **Blocked** *(Hardware)* | Generate self-signed CA and server certificate on RPi 2 matching `CORE_LAN_IP`, copy `ca.crt` to RPi 1. |
| **ISSUE-003** | TimescaleDB database schema migrations manual execution | Medium | Core Database | **Open** | Automate migration execution on container start or execute via `scripts/deploy_core.sh`. |
| **ISSUE-004** | LoRa receiver SPI interface requires physical Raspberry Pi hardware | Medium | Gateway Hardware | **Not Tested** *(Hardware)* | Test SX1278 SPI interface on real Raspberry Pi 4 hardware after enabling SPI in `raspi-config`. |
| **ISSUE-005** | Forwarder uses `clean_session=True` | Medium | Gateway Forwarder | **Open** | Migrate to persistent session (`clean_session=False`) with unique stable client ID to safeguard messages during restart. |
| **ISSUE-006** | Reverse proxy serves dashboard & API over cleartext HTTP (port 8080) | High | Core Reverse Proxy | **Open** | Add TLS certificate to Nginx and configure HTTPS server block on port 443 with HTTP-to-HTTPS redirect. |

---

## Routine Maintenance Schedule

| Frequency | Action | Target Component | Command / Script |
|---|---|---|---|
| **Daily (02:00 UTC)** | Database Backup | TimescaleDB | `scripts/backup_database.sh` |
| **Weekly** | Check SQLite Queue Size | Gateway | `sqlite3 ... "SELECT count(*) FROM queue;"` |
| **Monthly** | Review EMQX & Backend Logs | Core / Gateway | `docker compose logs --tail=100` |
| **Annual** | Rotate TLS Certificates | EMQX TLS | Follow `docs/certificate-setup.md` |

