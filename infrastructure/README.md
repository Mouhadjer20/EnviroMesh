# Infrastructure — EnviroMesh Platform Configuration

This directory contains the operational and deployment configurations for the **EnviroMesh** edge gateway and core processing platform.

---

## Directory Structure

```
infrastructure/
├── nginx/
│   └── default.conf            # Nginx gateway reverse proxy configuration
├── emqx/
│   └── acl.conf                # EMQX topic-level Access Control List (ACL)
├── systemd/
│   ├── enviromesh.service      # Systemd service for auto-starting Docker Compose stack
│   └── enviromesh-lora.service # Systemd service for native LoRa receiver on Raspberry Pi
└── README.md                   # This documentation file
```

---

## 1. Nginx Reverse Proxy (`nginx/default.conf`)

Mounted as a read-only volume in [`docker-compose.yml`](../docker-compose.yml):
```yaml
volumes:
  - ./infrastructure/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
```

### Key Responsibilities:
- **Port 80 (Internal) / Port 8080 (Host):** Serves as the single unified entry point for user browsers and external clients.
- **Frontend Routing (`/`):** Proxies traffic to the dashboard container (`http://dashboard:80`).
- **Backend API Routing (`/api/`):** Strips the `/api/` prefix and forwards calls to the FastAPI backend (`http://backend:8000/`), enabling endpoints like `/api/health` ➔ `http://backend:8000/health` and `/api/devices/` ➔ `http://backend:8000/devices/`.
- **WebSocket Upgrade (`/ws/` & `/api/`):** Configured with `Upgrade` and `Connection` headers plus a 24-hour timeout (`86400s`) to support persistent real-time telemetry streaming without dropped connections.
- **Security Isolation:** Does NOT route to port `18083` (EMQX dashboard), ensuring the MQTT admin console remains accessible only from localhost or explicit administrator tunnels.

---

## 2. EMQX MQTT Authorization (`emqx/acl.conf`)

Mounted as a read-only volume in [`docker-compose.yml`](../docker-compose.yml):
```yaml
volumes:
  - ./infrastructure/emqx/acl.conf:/opt/emqx/etc/acl.conf:ro
```

### Access Control Rules:
1. **Backend Application (`enviromesh_backend`):** Granted full publish and subscribe rights (`all`) to all topics (`#`, `$SYS/#`).
2. **Local Administration (`127.0.0.1`):** Unrestricted access for local monitoring and health check scripts.
3. **Field Sensor Nodes (`G11`, `G41`, `G31`, `G61`, `G43`):**
   - Allowed to publish telemetry to `enviromesh/devices/%c/telemetry` or `enviromesh/devices/+/telemetry`.
   - Allowed to subscribe to their individual command topics: `enviromesh/devices/%c/commands/#`.
4. **Technician & Dashboard Clients:**
   - Allowed to subscribe to device telemetry feeds.
   - Allowed to publish commands to actuator nodes.
5. **Catch-All Rule:** Rejects any unauthorized topics outside the `enviromesh/#` namespace.

---

## 3. Host Systemd Services (`systemd/`)

For production deployment on an unattended **Raspberry Pi**, systemd services ensure the platform boots automatically and recovers from unexpected reboots or power interruptions.

### 3.1. Docker Compose Service (`systemd/enviromesh.service`)
Starts and monitors the 5-container Docker Compose stack on boot.

**Installation:**
```bash
# 1. Copy service file to systemd directory
sudo cp infrastructure/systemd/enviromesh.service /etc/systemd/system/

# 2. Reload systemd daemon
sudo systemctl daemon-reload

# 3. Enable auto-start on boot
sudo systemctl enable enviromesh.service

# 4. Start service immediately
sudo systemctl start enviromesh.service

# 5. Check status
sudo systemctl status enviromesh.service
```

### 3.2. Native LoRa Receiver Service (`systemd/enviromesh-lora.service`)
On a physical Raspberry Pi, the **SX1278 (433 MHz)** transceiver interfaces directly via hardware SPI (`/dev/spidev0.0`) and GPIO. This service runs the receiver daemon natively on the host OS.

**Installation:**
```bash
# 1. Ensure SPI is enabled on Raspberry Pi
sudo raspi-config # Interface Options -> SPI -> Enable

# 2. Copy service file to systemd directory
sudo cp infrastructure/systemd/enviromesh-lora.service /etc/systemd/system/

# 3. Reload daemon & enable
sudo systemctl daemon-reload
sudo systemctl enable enviromesh-lora.service
sudo systemctl start enviromesh-lora.service

# 4. Inspect live LoRa reception logs
sudo journalctl -u enviromesh-lora.service -f
```

---

## 4. Related Documentation

- Project Root Specification: [README.md](../README.md)
- Raspberry Pi Gateway Overview: [raspberry_pi/README.md](../raspberry_pi/README.md)
- Automation & Helper Scripts: [scripts/README.md](../scripts/README.md)
