# Security & Hardening Guide

Security in EnviroMesh follows a defense-in-depth model across transport, brokers, database, operating systems, and applications.

---

## 1. Network Boundary Isolation

- **No Direct Field Sensor Access to Core**: ESP32 field devices (often vulnerable microcontrollers deployed in physical spaces) never connect directly to RPi 2.
- **Port Exposure**:
  - PostgreSQL port `5432` is completely unmapped from the host network.
  - EMQX Web Dashboards on both RPis are bound strictly to `127.0.0.1` (localhost only).
  - Inter-RPi communications use TLS on port `8883`.

---

## 2. MQTT Broker Authentication & Authorization (ACLs)

### Local EMQX (RPi 1)
- **Principle of Least Privilege**: Each Wi-Fi device is granted publish access only to its specific topic (`enviromesh/devices/{device_id}/telemetry`).
- Subscription is denied to all field devices to prevent one compromised sensor from intercepting readings of other nodes.
- Ingestion worker `gw_ingestion` is granted subscribe access to `enviromesh/devices/+/telemetry`.
- Catch-all rule: `{deny, all, all, ["#"]}`.

### Core EMQX (RPi 2)
- Plain TCP port 1883 is accessible only on the internal Docker network.
- Public listener is TLS-only on port 8883.
- Only the gateway forwarder (`gw_forwarder`) is authorized to publish to `enviromesh/gateway/+/telemetry`.
- The FastAPI backend (`enviromesh_backend`) is authorized to subscribe to `enviromesh/gateway/+/telemetry`.
- Direct node connection is denied.

---

## 3. Storage Security & Idempotency

- **SQLite Queue (RPi 1)**:
  - Encapsulated within the container volume.
  - Deletion only occurs on cryptographic or protocol-level verification (`PUBACK`).
- **TimescaleDB (RPi 2)**:
  - Non-root Postgres user (`enviromesh_app`) has restricted privileges.
  - Deduplication prevents replay attacks and duplicate packet injection.

---

## 4. SSH & Linux OS Hardening

1. **Disable Password Authentication**: Use SSH key-based authentication only.
2. **UFW Firewalls**: Enabled on both Raspberry Pis.
3. **Automatic Security Updates**: Configure `unattended-upgrades` on Debian/Raspberry Pi OS.
4. **Secrets Management**: Secrets are stored exclusively in `.env` files with permissions `600` and are never committed to version control.

