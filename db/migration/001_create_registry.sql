
-- =========================================================
-- ENVIRONMENTAL MONITORING SYSTEM
-- PostgreSQL database schema
-- =========================================================

-- Enable UUID generation and bcrypt password hashing.
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- 1. GROUPS
CREATE TABLE IF NOT EXISTS groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_code VARCHAR(2) UNIQUE NOT NULL,
    description TEXT,

    CONSTRAINT chk_group_code
        CHECK (group_code ~ '^G[1-9]$')
);


-- 2. USERS
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    group_id UUID REFERENCES groups(id) ON DELETE SET NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'zone_technician',

    CONSTRAINT chk_user_role
        CHECK (role IN ('admin', 'zone_technician'))
);


-- 3. SENSORS
CREATE TABLE IF NOT EXISTS sensors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255)
);


-- 4. DEVICES
CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(3) PRIMARY KEY,
    zone VARCHAR(255),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    group_id UUID REFERENCES groups(id) ON DELETE SET NULL,

    CONSTRAINT chk_device_id
        CHECK (device_id ~ '^G[1-9][1-9]$'),

    CONSTRAINT chk_latitude
        CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),

    CONSTRAINT chk_longitude
        CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);


-- 5. SENSOR-DEVICE ASSOCIATIONS
CREATE TABLE IF NOT EXISTS sensor_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sensor_id UUID NOT NULL
        REFERENCES sensors(id) ON DELETE CASCADE,
    device_id VARCHAR(3) NOT NULL
        REFERENCES devices(device_id) ON DELETE CASCADE,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    configuration JSONB,

    CONSTRAINT uq_sensor_device
        UNIQUE (sensor_id, device_id),

    CONSTRAINT chk_sensor_device_status
        CHECK (status IN ('active', 'inactive', 'maintenance'))
);


-- =========================================================
-- INDEXES
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_users_group_id
    ON users(group_id);

CREATE INDEX IF NOT EXISTS idx_devices_group_id
    ON devices(group_id);

CREATE INDEX IF NOT EXISTS idx_sensor_devices_device_id
    ON sensor_devices(device_id);

CREATE INDEX IF NOT EXISTS idx_sensor_devices_sensor_id
    ON sensor_devices(sensor_id);
