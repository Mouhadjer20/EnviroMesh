# Dashboard — EnviroMesh Web Frontend

The dashboard is the user-facing web interface for the **EnviroMesh** environmental monitoring platform. It provides real-time visualization of environmental telemetry, device status summaries, and emergency alerts, served as a **React + Vite SPA** behind an Nginx reverse proxy.

---

## Table of Contents

- [1. Role in the Architecture](#1-role-in-the-architecture)
- [2. Directory Layout](#2-directory-layout)
- [3. Features (Current Implementation)](#3-features-current-implementation)
- [4. Environment Variables](#4-environment-variables)
- [5. Building & Running](#5-building--running)
  - [Docker (recommended)](#docker-recommended)
  - [Local Development Server](#local-development-server)
- [6. Known Limitations & Roadmap](#6-known-limitations--roadmap)
- [7. Related Documentation](#7-related-documentation)

---

## 1. Role in the Architecture

The dashboard is served by its own Nginx container and exposed through the central **EnviroMesh Gateway** reverse proxy on port **`8080`** (set by `WEB_PORT` in root `.env`, or `8081` by default):

```
Browser Client (Technician / Admin)
        │
        │ HTTP  (Port 8080 via WEB_PORT, or 8081 default)
        v
+-------------------------------------------------------+
|            Nginx Reverse Proxy (Gateway)              |
|           (enviromesh-nginx : port 80 internal)       |
+---------------------------+---------------------------+
                            │
           +----------------+----------------+
           │ /                               │ /api/
           v                                 v
+-----------------------+         +---------------------+
│  Dashboard Frontend   │         │   FastAPI Backend   │
│ (enviromesh-dashboard)│         │ (enviromesh-backend)│
│  Port 80 (internal)   │         │ Port 8000 (internal)│
+-----------------------+         +---------------------+
                                           │
                                  +--------+--------+
                                  │  TimescaleDB    │
                                  │  (port 5432)    │
                                  +-----------------+
```

- `http://<rpi-ip>:8080/` → SPA static assets (React/Vite bundle).
- `http://<rpi-ip>:8080/api/` → FastAPI backend (prefix stripped by Nginx).

---

## 2. Directory Layout

```
raspberry_pi/dashboard/
├── Dockerfile              # Multi-stage build: node:20-alpine builder → nginx:1.28-alpine
├── nginx.conf              # Nginx server block for the dashboard container (SPA fallback)
├── .dockerignore           # Excludes node_modules, dist, .env from build context
├── .env                    # Local dev overrides (not committed, see .env.example)
├── .env.example            # Template for local dev environment variables
├── .gitignore
├── index.html              # Vite entry point (loads /src/main.jsx)
├── package.json            # React 18 + React Router v6 + Recharts
├── vite.config.js          # Dev-server proxy: /api → VITE_API_PROXY
├── README.md               # This file
└── src/
    ├── main.jsx            # App entry — HashRouter wrapping <App />
    ├── App.jsx             # Shell: sidebar, topbar, theme switcher, polling
    ├── styles.css          # Global CSS variables + component styles
    ├── lib.js              # Constants, alert logic, CSV export, normalization helpers
    ├── context/
    │   └── DataContext.jsx # React context: devices, groups, latestBy, actives, readings
    ├── hooks/
    │   └── useApi.js       # Polling hook: fetch + auto-refresh every POLL_MS (5 s)
    ├── components/
    │   ├── Chart.jsx       # Recharts LineChart for the Device history page
    │   └── Stat.jsx        # Simple metric card component
    └── pages/
        ├── Overview.jsx    # KPI grid, sensor cards, trend charts, device fleet list
        ├── Device.jsx      # Per-device telemetry history, stats, CSV/JSON export
        └── Alerts.jsx      # Active alert banner + full alert history table
```

---

## 3. Features (Current Implementation)

| Feature | Status |
|---|---|
| Real-time telemetry polling (every 5 s via `/api/telemetry/`) | ✅ Done |
| KPI cards: devices online, network state, active alerts, groups | ✅ Done |
| Sensor metric cards with sparklines (gas, temp, humidity, pressure, water, smoke, motion) | ✅ Done |
| 24-hour trend charts (temperature + humidity, gas concentration) | ✅ Done |
| Device fleet list with online/alert filter | ✅ Done |
| Per-device history page with time-range selector and Recharts chart | ✅ Done |
| CSV + JSON export of telemetry history | ✅ Done |
| Alert history reconstructed from telemetry readings | ✅ Done |
| Dark / Light / Auto theme toggle (persisted in localStorage) | ✅ Done |
| Zone and group filters | ✅ Done |
| API connection status indicator | ✅ Done |
| Login / JWT authentication and forced initial password rotation | ✅ Implemented (requires migrations + bootstrap admin) |
| Role-scoped navigation, admin user management, group/device assignment | ✅ Implemented (group scope enforced by the API) |
| Profile details and password change | ✅ Implemented |
| WebSocket live telemetry (`/ws/telemetry`) | 🔲 Planned (Phase 4) |
| Actuator control panel (Node G61 servo) | 🔲 Planned (Phase 4) |
| HLS / WebRTC video stream (ESP32-CAM) | 🔲 Planned (Phase 5) |
| Persistent alert table (backend-driven) | 🔲 Planned (Phase 4) |

---

## 4. Environment Variables

The dashboard has **no runtime env vars** — it is a static SPA. The only variable affects the **Vite dev-server** (`npm run dev`) and is **not baked into the Docker image**.

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_PROXY` | `http://localhost:8080` | Dev-server proxy target for `/api/*` requests. Set to the Nginx gateway URL (root `.env` → `WEB_PORT`, default 8080). |

Copy [`.env.example`](.env.example) to `.env` before running the dev server:

```bash
cp .env.example .env
# Edit VITE_API_PROXY if your Docker stack runs on a different port or host
```

> **Docker note:** In the Docker Compose stack, Nginx routes `/api/` to the backend directly. The `VITE_API_PROXY` variable is only used when running `npm run dev` locally.

---

## 5. Building & Running

### Docker (recommended)

The dashboard container is built and started automatically by the root `docker-compose.yml`:

```bash
# From the project root
./scripts/docker_control.sh start
# or directly:
docker compose up -d --build
```

Access the dashboard: **`http://<rpi-ip>:8080`** (or `http://localhost:8080` when running locally).

To rebuild only the dashboard after a code change:

```bash
docker compose build dashboard
docker compose up -d dashboard
```

### Local Development Server

Run the Vite dev server for hot-reload development:

```bash
cd raspberry_pi/dashboard

# 1. Install dependencies
npm install

# 2. Copy and configure the env file
cp .env.example .env
# Edit VITE_API_PROXY=http://localhost:8080 (or wherever your Docker stack runs)

# 3. Start the dev server
npm run dev
# Dashboard available at http://localhost:5173
# All /api/* calls are proxied to VITE_API_PROXY
```

> **Requirement:** The Docker Compose stack (or at minimum the backend + Nginx gateway) must be running so that API calls resolve.

To build a production bundle locally:

```bash
npm run build       # output → dist/
npm run preview     # preview the built bundle at http://localhost:4173
```

---

## 6. Known Limitations & Roadmap

- **Initial setup required:** Apply migrations 004 and 005, configure a persistent `JWT_SECRET`, and create the first administrator with `python -m services.bootstrap_admin`.
- **Browser token storage:** The bearer token is kept in `sessionStorage` and sent to the API. Use HTTPS on networks that are not fully trusted; the current reverse proxy is HTTP-only.
- **Alert history is reconstructed client-side** from the last 2 000 telemetry readings. A dedicated `alerts` table and backend endpoint are planned.
- **Live surveillance** (`/ws/telemetry` WebSocket) is shown as *À venir* in the sidebar.
- **Actuators, dedicated Zones, Analytics, and Security pages** remain planned. Users, Groups, and Settings are implemented.
- **`smoke_detected`** is in the validator `METRIC_RANGES` but not in `METRIC_RANGES` on the frontend `lib.js` — no danger threshold is set for it (binary flag only).

---

## 7. Related Documentation

- Project Root Architecture: [README.md](../../README.md)
- Raspberry Pi Core Server: [raspberry_pi/core/README.md](../README.md)
- Core Reverse Proxy: [nginx/default.conf](../nginx/default.conf)
- Automation Scripts: [scripts/README.md](../../scripts/README.md)
