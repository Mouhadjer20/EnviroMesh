# Database Schema & Migrations

The central persistent store on RPi 2 (Core) is **PostgreSQL 16** with the **TimescaleDB 2.17** extension.

---

## 1. Schema Architecture

```
                  ┌──────────────────────┐
                  │   device_registry    │
                  ├──────────────────────┤
                  │ device_id (PK)       │
                  │ group_code           │
                  │ zone                 │
                  │ protocol             │
                  │ status               │
                  └──────────┬───────────┘
                             │
                             ▼
┌─────────────────────────┐  │  ┌─────────────────────────┐
│   processed_messages    │  │  │    sensor_telemetry     │
│       (Dedup)           │  │  │      (Hypertable)       │
├─────────────────────────┤  │  ├─────────────────────────┤
│ message_id (PK)         │  │  │ timestamp (PK, Partition│
│ device_id               │  └──┼─ device_id              │
│ gateway_id              │     │ zone                    │
│ processed_at            │     │ metrics (JSONB)         │
└─────────────────────────┘     │ received_at             │
                                │ protocol                │
                                │ rssi                    │
                                │ metadata (JSONB)        │
                                │ message_id              │
                                │ gateway_id              │
                                │ gateway_received_at     │
                                └─────────────────────────┘
```

---

## 2. Table Specifications

### `sensor_telemetry` (TimescaleDB Hypertable)

Partitioned by time on `timestamp` (chunk interval: 7 days).
Stores time-series environmental measurements.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `timestamp` | TIMESTAMPTZ | NOT NULL | Sensor acquisition timestamp or gateway ingestion time |
| `device_id` | VARCHAR(20) | NOT NULL | Hardware device ID (e.g. G11, G31, G41, G61) |
| `zone` | VARCHAR(100) | | Physical deployment area |
| `metrics` | JSONB | NOT NULL | Sensor metrics object (`temperature_c`, `humidity`, etc.) |
| `received_at` | TIMESTAMPTZ | DEFAULT NOW() | Time written into TimescaleDB |
| `protocol` | VARCHAR(20) | | `lora` or `wi-fi` |
| `rssi` | REAL | | Signal strength in dBm |
| `metadata` | JSONB | | Raw device metadata and envelope diagnostics |
| `message_id` | TEXT | | Gateway-assigned stable UUID |
| `gateway_id` | VARCHAR(20) | | Receiving gateway (e.g. GW01) |
| `gateway_received_at` | TIMESTAMPTZ | | Timestamp when packet reached RPi 1 |

### `processed_messages` (Standard PostgreSQL Table)

Authoritative deduplication registry.
Because TimescaleDB hypertables do not allow unique constraints on non-partitioning columns, `processed_messages` acts as an independent dedup gate.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `message_id` | TEXT | PRIMARY KEY | Stable UUID assigned by gateway |
| `device_id` | VARCHAR(20) | NOT NULL | Device that emitted the reading |
| `gateway_id` | VARCHAR(20) | | Gateway that handled the reading |
| `processed_at` | TIMESTAMPTZ | DEFAULT NOW() | Timestamp inserted |

### `raw_sensor_packets`

Audit log table preserving raw bytes and unparsed payloads for diagnostics and radio debugging.

---

## 3. Migration Sequence

Migrations are located in `raspberry_pi/core/database/migrations/`:

1. `001_create_registry.sql`: Sets up `device_registry`, `group_registry`, and initial indices.
2. `001_create_telemetry.sql`: Creates `sensor_telemetry` hypertable and `raw_sensor_packets`.
3. `003_add_gateway_metadata.sql`: Adds `message_id`, `gateway_id`, `gateway_received_at` to `sensor_telemetry` and creates the `processed_messages` deduplication table.

