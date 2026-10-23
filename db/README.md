# Database Layer — Environmental Monitoring System

This folder contains the database artifacts for the EnviroMesh project: schema
migrations, seed data, and verification queries.

The system uses a **dual-database design**:

| Layer | Technology | Purpose |
|-------|------------|---------|
| Registry / Metadata | **PostgreSQL** + pgcrypto | Users, groups, sensors, devices, assignments, RBAC |
| Telemetry / Time-Series | **PostgreSQL** + **TimescaleDB** | High-frequency sensor readings, raw packets |

## Directory Layout

```
db/
├── README.md                    # This file
├── migration/
│   ├── 001_create_registry.sql  # PostgreSQL relational schema
│   └── 001_create_telemetry.sql # TimescaleDB time-series schema
└── seed/
    ├── 001_seed_registry.sql    # Reference data (groups, users, devices, sensors)
    └── 001_verify_seed_registry.sql  # Sanity-check queries after seeding
```

Migrations and seeds are numbered `001_*` and are intended to be applied in
alphabetical order within each folder:

1. `migration/001_create_registry.sql`
2. `migration/001_create_telemetry.sql`
3. `seed/001_seed_registry.sql`

## Prerequisites

- **PostgreSQL 14+**
- **pgcrypto** extension (UUID generation + bcrypt hashing)
- **TimescaleDB** extension (required by the telemetry migration)

Apply extensions before running migrations:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

## 1. Registry Migration — `001_create_registry.sql`

Creates the relational metadata schema in five tables plus supporting indexes.

### Tables

| Table | Description |
|-------|-------------|
| **groups** | Student/device groups (G1–G7). `group_code` must match `^G[1-9]$`. |
| **users** | Zone technician / admin accounts. Passwords are hashed with bcrypt via pgcrypto. |
| **sensors** | Sensor catalog (MQ-2, DHT11, Water Sensor, BMP280, PIR). |
| **devices** | Physical edge nodes (e.g. `G11`, `G41`). `device_id` must match `^G[1-9][1-9]$`. |
| **sensor_devices** | Many-to-many association between sensors and devices with JSONB configuration. |

### Key Relationships

```
users.group_id      → groups.id          (ON DELETE SET NULL)
devices.group_id    → groups.id          (ON DELETE SET NULL)
sensor_devices.sensor_id   → sensors.id     (ON DELETE CASCADE)
sensor_devices.device_id   → devices.device_id (ON DELETE CASCADE)
```

### Indexes

- `idx_users_group_id`
- `idx_devices_group_id`
- `idx_sensor_devices_device_id`
- `idx_sensor_devices_sensor_id`

## 2. Telemetry Migration — `001_create_telemetry.sql`

Creates the time-series layer on top of TimescaleDB.

### Tables

| Table | Type | Description |
|-------|------|-------------|
| **sensor_telemetry** | Hypertable (partitioned by `timestamp`) | Normalized readings: `device_id`, `zone`, `metrics` JSONB, `protocol`, `rssi`, metadata. |
| **raw_sensor_packets** | Hypertable (partitioned by `received_at`) | Raw `BYTEA` payloads for diagnostics and traceability. |

### Indexes

- `idx_telemetry_device_time` — `(device_id, timestamp DESC)`
- `idx_telemetry_zone_time` — `(zone, timestamp DESC)`

### Example telemetry payload

```json
{
  "timestamp": "2026-10-23T08:00:00Z",
  "device_id": "G11",
  "zone": "Sector_A_Warehouse",
  "metrics": {
    "gas_ppm": 145.2,
    "temperature_c": 26.4,
    "humidity": 58.1,
    "water_leak": false
  },
  "protocol": "LoRa",
  "metadata": {
    "group_code": "G1",
    "firmware_version": "1.0.0"
  }
}
```

## 3. Seed Data — `001_seed_registry.sql`

Populates the registry tables with reference data. Default user password is
**`password123`** (hashed via `crypt`/`gen_salt('bf')`). Change all default
passwords after first login.

### Seed contents

1. **Groups** — G1 through G7 (LoRa / Wi-Fi / reserved groups).
2. **Users** — 22 student accounts (`zone_technician` role), emails derived from
   student codes as `<code[11:]>@etu.uni-usto.dz`, assigned to groups G1–G7
   where known (one student, LAAZ Abdelaziz Farouk, is intentionally unassigned
   with `group_id IS NULL`).
3. **Sensors** — MQ-2, DHT11, Water Sensor, BMP280, PIR catalog entries.
4. **Devices** — G11, G41, G31, G61 with zones and coordinates.
5. **Sensor-device assignments** — 14 assignments across the four devices,
   each with a JSONB configuration describing the measurement(s).

## 4. Verification — `001_verify_seed_registry.sql`

Run after seeding to sanity-check the topology:

- Group counts and student counts per group
- Users and their group assignments (including unassigned users)
- Sensor catalog listing

## Applying the Database

Example using `psql`:

```bash
# 1. Enable required extensions
psql -U postgres -d enviromesh -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql -U postgres -d enviromesh -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 2. Apply migrations
psql -U postgres -d enviromesh -f db/migration/001_create_registry.sql
psql -U postgres -d enviromesh -f db/migration/001_create_telemetry.sql

# 3. Load seed data
psql -U postgres -d enviromesh -f db/seed/001_seed_registry.sql

# 4. Verify
psql -U postgres -d enviromesh -f db/seed/001_verify_seed_registry.sql
```

## Security Notes

- All user passwords are hashed with bcrypt (`pgcrypto`); plaintext never
  persists in the database.
- Default seed password `password123` must be changed after first login.
- Telemetry tables are hypertables; retention policies should be configured
  separately based on operational requirements (e.g. `add_retention_policy`).

## Related Documentation

- Project architecture: [`../README.md`](../README.md)
- Dashboard: [`../dashboard`](../dashboard)
