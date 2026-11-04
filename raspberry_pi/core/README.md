# EnviroMesh Core (RPi 2)

The Core Raspberry Pi (RPi 2) is the centralized data processing, management, and visualization layer of the EnviroMesh network.

It receives authenticated, TLS-encrypted telemetry streams from the Gateway (RPi 1), stores them in PostgreSQL/TimescaleDB, detects duplicate transmissions, and serves the REST API, WebSocket streams, and React dashboard.

## Responsibilities

1. **Central EMQX MQTT Broker**: Exposes port 8883 (TLS) for RPi 1 Gateway connections, with strict topic authorization.
2. **Database Storage**: PostgreSQL with TimescaleDB hypertable (`sensor_telemetry`), maintaining partitioned time-series sensor data.
3. **Duplicate Detection**: Uses dedicated `processed_messages` table to ensure at-most-once processing even if network retries occur.
4. **FastAPI Backend**: Provides REST endpoints (`/devices`, `/telemetry`, `/groups`) and telemetry ingestion logic.
5. **React + Vite Dashboard**: Modern UI with charts and overview widgets served via Nginx.
6. **Nginx Reverse Proxy**: Single entrypoint on port 8080 routing `/api/` to FastAPI and `/` to the dashboard frontend.

## Directory Structure

```
raspberry_pi/core/
├── docker-compose.yml       # Orchestrates EMQX, TimescaleDB, Backend, Dashboard, Nginx
├── .env.example             # Core environment template
├── emqx/
│   ├── emqx.conf            # Core EMQX configuration with TLS listener
│   ├── acl.conf             # Restricted ACL rules
│   └── certs/               # TLS certificates (ca.crt, server.crt, server.key)
├── backend/                 # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── routes/
│   └── services/
├── dashboard/               # React + Vite frontend
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
├── database/
│   ├── migrations/          # SQL schema migrations (001, 002, 003)
│   └── seeds/               # Device registry seed data
└── nginx/
    └── default.conf         # Reverse proxy configuration
```

## Quick Start

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   nano .env
   ```
2. **Generate TLS Certificates**:
   Follow instructions in `docs/certificate-setup.md` to generate CA and server certificates, placing them in `emqx/certs/`.
3. **Deploy Core Stack**:
   ```bash
   docker compose up -d --build
   ```
4. **Run Database Migrations**:
   ```bash
   docker compose exec timescaledb psql -U enviromesh_app -d enviromesh \
       -f /migrations/001_create_registry.sql \
       -f /migrations/001_create_telemetry.sql \
       -f /migrations/003_add_gateway_metadata.sql
   ```
5. **Access the Dashboard**:
   Open your browser to `http://<CORE_RPi_IP>:8080`.

