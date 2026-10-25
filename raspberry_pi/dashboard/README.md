# Dashboard — EnviroMesh Web Frontend

The dashboard is the user-facing web interface for the **EnviroMesh** environmental monitoring platform. It provides real-time visualization of environmental telemetry, device status summaries, emergency alerts, and actuator controls, filtered by **Role-Based Access Control (RBAC)**.

---

## 1. Role in the Architecture

The dashboard is served by Nginx and exposed through the central **EnviroMesh Gateway Reverse Proxy** on port **`8080`**:

```
Browser Client (Technician / Admin)
        │
        │ HTTP / HTTPS (Port 8080)
        v
+-------------------------------------------------------+
|                 Nginx Reverse Proxy                   |
|               (enviromesh-nginx:8080)                 |
+---------------------------+---------------------------+
                            |
           +----------------+----------------+
           | /                               | /api/
           v                                 v
+-----------------------+         +---------------------+
|  Dashboard Frontend   |         |   FastAPI Backend   |
| (enviromesh-dashboard)|         | (enviromesh-backend)|
|  Port 80 (Internal)   |         | Port 8000 (Internal)|
+-----------------------+         +---------------------+
```

- Requests to `http://localhost:8080/` load the web dashboard static assets.
- Requests to `http://localhost:8080/api/` are transparently routed to the FastAPI backend.

---

## 2. Directory Layout & Current Implementation

```
raspberry_pi/dashboard/
├── Dockerfile           # Nginx alpine image serving static assets from /usr/share/nginx/html
├── index.html           # Current single-page status interface (Phase 1–2 placeholder)
└── README.md            # This documentation file
```

### Current Status (`index.html`)
The current `index.html` provides:
- Clean, responsive CSS layout.
- High-level metric cards (**Devices Online**, **Gas PPM**, **Temperature °C**, **Humidity %**).
- Quick architectural links to API, MQTT, TimescaleDB, and EMQX.
- Direct alignment with the Docker Compose setup.

---

## 3. Implementation Roadmap (Phase 4: Dashboard & UI)

The full dashboard experience is scheduled for **Phase 4: Dashboard & Security Layer**:

### 1. Authentication & Session Management
- [ ] **Login Screen:** Email and password login form.
- [ ] **JWT Storage:** Securely store access tokens and decode user claims:
  - Technician role (`zone_technician`): automatically restrict views to assigned zone (e.g. *Sector A Warehouse*).
  - Admin role (`admin`): full global visibility across all sectors and devices (`G11`, `G41`, `G31`, `G61`).

### 2. Live Telemetry & Dynamic Charts
- [ ] **Real-Time Data Feed:** Connect to the backend via WebSocket (`/ws/telemetry`) or poll `/api/telemetry/{id}/latest` every 2 seconds.
- [ ] **Interactive Visualizations:** Integrate Chart.js or Apache ECharts for:
  - Multi-line temperature & relative humidity history.
  - Gas concentration (LPG-equivalent ppm) with threshold danger zone highlight (> 2000 ppm).
  - Barometric pressure trendline (Node G31 BMP280).
  - Water leak detection indicator with audio/visual strobe alert.

### 3. Actuator Control & Remote Triggering
- [ ] **Node G61 Servo Actuation Panel:**
  - Slider or preset buttons for valve opening angle ($0^\circ$ closed, $90^\circ$ half, $180^\circ$ open).
  - Feedback status indicator displaying `servo_current_angle_deg`.
  - Manual override toggle requiring confirmation.

### 4. Video Subsystem Integration (Phase 5)
- [ ] Embedded HLS / WebRTC video player consuming low-latency streams from the MediaMTX video proxy (when ESP32-CAM nodes are deployed).

---

## 4. Building & Running

### Running in Docker
The dashboard starts automatically when launching the EnviroMesh stack:
```bash
./scripts/docker_control.sh start
```
Access the dashboard in your browser: **`http://localhost:8080`**.

### Local Frontend Development
When building a custom React / Vue / Vite application:
1. Initialize the project inside `raspberry_pi/dashboard/`.
2. Configure build output to `dist/` or `build/`.
3. Update `raspberry_pi/dashboard/Dockerfile` to copy compiled assets into `/usr/share/nginx/html`.
4. Rebuild the container:
   ```bash
   ./scripts/docker_control.sh build
   ```

---

## 5. Related Documentation

- Project Root Architecture: [README.md](../../README.md)
- Raspberry Pi Core Server: [raspberry_pi/README.md](../README.md)
- Backend API Specification: [backend/README.md](../backend/README.md)
- Automation Scripts: [scripts/README.md](../../scripts/README.md)
