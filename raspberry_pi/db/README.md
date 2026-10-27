# Database Layer — EnviroMesh Persistence Engine

This directory contains the database artifacts for the EnviroMesh platform: relational schema migrations, time-series hypertables, seed data, and verification suites.

The system implements a **polyglot persistence architecture** hosted on PostgreSQL 16 with the TimescaleDB extension:

| Layer | Engine | Purpose | Key Tables |
|---|---|---|---|
| **Control Plane & Registry** | **PostgreSQL 16** + `pgcrypto` | Relational metadata, user accounts, groups, devices, sensors, RBAC | `groups`, `users`, `sensors`, `devices`, `sensor_devices` |
| **Telemetry Plane** | **TimescaleDB 2.17** | High-velocity time-partitioned sensor readings & raw diagnostic frames | `sensor_telemetry`, `raw_sensor_packets` |

---

## Table of Contents

- [1. Directory Layout](#1-directory-layout)
- [2. Managing the Database with Helper Scripts](#2-managing-the-database-with-helper-scripts)
- [3. Schema Specifications](#3-schema-specifications)
  - [3.1. Relational Registry](#31-relational-registry-migration001_create_registrysql)
  - [3.2. Time-Series Telemetry](#32-time-series-telemetry-migration001_create_telemetrysql)
- [4. Seed Data & Reference Accounts](#4-seed-data--reference-accounts-seed001_seed_registrysql)
- [5. Implementation Roadmap (Future Database Phases)](#5-implementation-roadmap-future-database-phases)
  - [Phase 4: Alerts Schema & Event Auditing](#phase-4-alerts-schema--event-auditing)
  - [Phase 4: TimescaleDB Downsampling & Continuous Aggregates](#phase-4-timescaledb-downsampling--continuous-aggregates)
  - [Phase 5: Retention Policies & Archiving](#phase-5-retention-policies--archiving)
- [6. Related Documentation](#6-related-documentation)

---

## 1. Directory Layout

```
raspberry_pi/db/
├── migration/
│   ├── 001_create_registry.sql   # Relational control plane schema (UUIDs, bcrypt, constraints)
│   └── 001_create_telemetry.sql  # TimescaleDB hypertables, partitions, and composite indexes
├── seed/
│   ├── 001_seed_registry.sql     # Seed data: groups G1–G7, 20+ student technician accounts, devices
│   └── 001_verify_seed_registry.sql # Automated sanity checks and topology report
└── README.md                     # This documentation file
```

---

## 2. Managing the Database with Helper Scripts

We provide an automated management utility: [`../../scripts/db_manage.sh`](../../scripts/db_manage.sh).

```bash
# Complete automated setup (extensions + migrations + seed + verification + status)
./scripts/db_manage.sh init

# Apply only schema migrations
./scripts/db_manage.sh migrate

# Load student technicians, sensors, and device assignments
./scripts/db_manage.sh seed

# Run verification queries and output database topology
./scripts/db_manage.sh verify

# View current row counts across all tables and hypertables
./scripts/db_manage.sh status

# Open an interactive psql session in the database container
./scripts/db_manage.sh shell

# Reset all tables and re-apply from scratch (destructive!)
./scripts/db_manage.sh reset
```

---

## 3. Schema Specifications

### 3.1. Relational Registry (`migration/001_create_registry.sql`)

1. **`groups`**: Student and hardware group identifiers (`G1` through `G7`).
   - Check constraint: `group_code ~ '^G[1-9]$'`.
2. **`users`**: Platform user accounts.
   - Roles: `'admin'`, `'zone_technician'`.
   - Passwords: Encrypted using bcrypt via `pgcrypto` (`crypt(password, gen_salt('bf'))`).
   - `group_id`: Foreign key referencing `groups.id`.
3. **`sensors`**: Canonical hardware catalog.
   - Catalog entries: `MQ-2`, `DHT11`, `Water Sensor`, `BMP280`, `PIR`.
4. **`devices`**: Physical edge nodes.
   - Device IDs enforce naming regex: `device_id ~ '^G[1-9][1-9]$'` (e.g. `G11`, `G41`, `G31`, `G61`).
   - Stores deployment zone and geographic coordinates (`latitude`, `longitude`).
5. **`sensor_devices`**: Many-to-many link between hardware sensors and physical devices.
   - Enforces unique assignment: `UNIQUE (sensor_id, device_id)`.
   - Status tracking: `'active'`, `'inactive'`, `'maintenance'`.
   - `configuration`: JSONB column defining measurement capabilities (e.g. `{"measurement": "gas_and_smoke"}`).

### 3.2. Time-Series Telemetry (`migration/001_create_telemetry.sql`)

1. **`sensor_telemetry`** (Hypertable):
   - Partitioned by range on `timestamp` (`SELECT create_hypertable('sensor_telemetry', by_range('timestamp'))`).
   - Stores device identifier, deployment zone, `metrics` JSONB document, protocol, reception timestamp, and RSSI.
   - Composite indexes:
     - `idx_telemetry_device_time` on `(device_id, timestamp DESC)` for fast device trendlines.
     - `idx_telemetry_zone_time` on `(zone, timestamp DESC)` for zone-wide technician dashboards.
2. **`raw_sensor_packets`** (Hypertable):
   - Partitioned on `received_at`.
   - Stores the exact `BYTEA` payload of every frame received over LoRa or MQTT before decoding.
   - Enforces column bounds: `device_id VARCHAR(3)` and `protocol VARCHAR(20)`. The backend `database_writer` defensively clamps incoming fields to prevent database write failures.
   - Maintains traceability: `parsed` boolean flag and `parse_error` diagnostic string.

---

## 4. Seed Data & Reference Accounts (`seed/001_seed_registry.sql`)

- **Default User Password:** **`password123`** (hashed with bcrypt via `pgcrypto`).
- **Technician Accounts:** 20+ accounts provisioned for university student technicians with email format `<student_code>@etu.uni-usto.dz`.
- **Pre-configured Devices:**
  - `G11`: Sector A Warehouse (LoRa — Group 1) ➔ MQ-2, DHT11, Water Sensor.
  - `G41`: Sector B Warehouse (LoRa — Group 4) ➔ MQ-2, DHT11, Water Sensor.
  - `G31`: Sector C Utility Room (Wi-Fi — Group 3) ➔ BMP280, MQ-2, Water Sensor.
  - `G61`: Sector A Valve (Wi-Fi — Group 6) ➔ MQ-2, DHT11, Water Sensor, PIR Motion, SG90 Servo.
  - `G42` & `G43`: Test nodes configured in Group 4 for MQTT harness simulation.

---

## 5. Implementation Roadmap (Future Database Phases)

### Phase 4: Alerts Schema & Event Auditing
- [ ] Create `002_create_alerts.sql` migration:
  ```sql
  CREATE TABLE IF NOT EXISTS alerts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      device_id VARCHAR(3) REFERENCES devices(device_id) ON DELETE CASCADE,
      zone VARCHAR(255) NOT NULL,
      alert_type VARCHAR(50) NOT NULL, -- 'GAS_LEAK', 'WATER_LEAK', 'HIGH_TEMP'
      severity VARCHAR(20) NOT NULL DEFAULT 'WARNING', -- 'INFO', 'WARNING', 'CRITICAL'
      message TEXT NOT NULL,
      metric_value DOUBLE PRECISION,
      threshold_value DOUBLE PRECISION,
      acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
      acknowledged_by UUID REFERENCES users(id),
      acknowledged_at TIMESTAMPTZ
  );
  ```

### Phase 4: TimescaleDB Downsampling & Continuous Aggregates
- [ ] Create materialized continuous aggregates for 1-minute and 1-hour downsampling:
  ```sql
  CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_hourly
  WITH (timescaledb.continuous) AS
  SELECT
      time_bucket('1 hour', timestamp) AS bucket,
      device_id,
      AVG((metrics->>'temperature_c')::numeric) AS avg_temp,
      MAX((metrics->>'temperature_c')::numeric) AS max_temp,
      AVG((metrics->>'gas_ppm')::numeric) AS avg_gas,
      MAX((metrics->>'gas_ppm')::numeric) AS max_gas
  FROM sensor_telemetry
  GROUP BY bucket, device_id;
  ```

### Phase 5: Retention Policies & Archiving
- [ ] Configure automatic data tiering:
  ```sql
  SELECT add_retention_policy('sensor_telemetry', INTERVAL '90 days');
  SELECT add_retention_policy('raw_sensor_packets', INTERVAL '14 days');
  ```

---

## 6. Related Documentation

- Project Root Architecture: [README.md](../../README.md)
- Raspberry Pi Overview: [raspberry_pi/README.md](../README.md)
- Backend Ingestion: [backend/README.md](../backend/README.md)
- Automation Scripts: [scripts/README.md](../../scripts/README.md)
