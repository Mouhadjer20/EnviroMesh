
-- =========================================================
-- DATABASE 2: TIME-SERIES TELEMETRY
-- Requires TimescaleDB to be installed.
-- =========================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;


-- 1. High-frequency sensor telemetry
CREATE TABLE IF NOT EXISTS sensor_telemetry (
    timestamp TIMESTAMPTZ NOT NULL,
    device_id VARCHAR(3) NOT NULL,
    zone VARCHAR(255),
    metrics JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Optional transport / data-quality metadata
    protocol VARCHAR(20),
    rssi INTEGER,
    metadata JSONB,

    CONSTRAINT chk_telemetry_metrics_object
        CHECK (jsonb_typeof(metrics) = 'object')
);


-- Convert the table into a time-partitioned hypertable.
-- Use this syntax with TimescaleDB versions that support
-- CREATE TABLE ... WITH (tsdb.hypertable).
-- For older versions, use create_hypertable() instead.

SELECT create_hypertable(
    'sensor_telemetry',
    by_range('timestamp'),
    if_not_exists => TRUE
);


-- Query recent readings for a particular device.
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
    ON sensor_telemetry (device_id, timestamp DESC);


-- Query telemetry by zone and time.
CREATE INDEX IF NOT EXISTS idx_telemetry_zone_time
    ON sensor_telemetry (zone, timestamp DESC);


-- Optional: raw packets for diagnostics and traceability.
CREATE TABLE IF NOT EXISTS raw_sensor_packets (
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    device_id VARCHAR(3),
    protocol VARCHAR(20) NOT NULL,
    payload BYTEA NOT NULL,
    parsed BOOLEAN NOT NULL DEFAULT FALSE,
    parse_error TEXT,
    metadata JSONB
);

SELECT create_hypertable(
    'raw_sensor_packets',
    by_range('received_at'),
    if_not_exists => TRUE
);

/*

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

*/