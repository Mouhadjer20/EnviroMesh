# Deployment & Operations Guide

Step-by-step instructions for deploying EnviroMesh across the two Raspberry Pis.

---

## Prerequisites

- Two Raspberry Pi 4 Model B (4GB or 8GB recommended).
- Raspberry Pi OS Lite (64-bit Debian Bookworm).
- Network: Connected to the same Wi-Fi router or switch.
- Hardware SPI enabled on RPi 1.

---

## 1. Setup & Deploy RPi 2 (Core Server) First

RPi 2 must be initialized first so that TLS certificates and the central EMQX broker are ready to receive connections.

### Step 1.1: Clone and Run Setup

On RPi 2:
```bash
git clone <REPO_URL> /home/pi/enviromesh
cd /home/pi/enviromesh

# Run environment setup
./scripts/setup_core.sh
```

### Step 1.2: Configure Environment Variables

Edit `raspberry_pi/core/.env`:
```bash
nano raspberry_pi/core/.env
```
Ensure you set strong passwords for:
- `POSTGRES_PASSWORD`
- `MQTT_APP_PASSWORD`
- `EMQX_DASHBOARD_PASSWORD`
- Set `CORE_LAN_IP=192.168.1.5` (or actual IP)

### Step 1.3: Generate TLS Certificates

Follow `docs/certificate-setup.md` to generate `ca.crt`, `server.crt`, and `server.key` in `raspberry_pi/core/emqx/certs/`.

### Step 1.4: Deploy Core Stack

```bash
./scripts/deploy_core.sh
```
This builds and starts all containers, waits for TimescaleDB, and applies SQL migrations.

### Step 1.5: Configure EMQX Broker Users

Create the gateway forwarder user and backend subscriber user in Core EMQX:
```bash
docker exec -it enviromesh-emqx-core emqx ctl admins add \
    --username gw_forwarder --password "<STRONG_PASSWORD>"

docker exec -it enviromesh-emqx-core emqx ctl admins add \
    --username enviromesh_backend --password "<MQTT_APP_PASSWORD>"
```

### Step 1.6: Verify Core Health

```bash
python3 scripts/check_core_health.py
```

---

## 2. Setup & Deploy RPi 1 (Gateway)

### Step 2.1: Clone and Run Setup

On RPi 1:
```bash
git clone <REPO_URL> /home/pi/enviromesh
cd /home/pi/enviromesh

./scripts/setup_gateway.sh
```

### Step 2.2: Copy CA Certificate from RPi 2

Copy `ca.crt` from RPi 2 into `raspberry_pi/gateway/certs/core-ca.crt`:
```bash
scp pi@192.168.1.5:/home/pi/enviromesh/raspberry_pi/core/emqx/certs/ca.crt \
    /home/pi/enviromesh/raspberry_pi/gateway/certs/core-ca.crt
```

### Step 2.3: Configure Gateway Environment

Edit `raspberry_pi/gateway/.env`:
```bash
nano raspberry_pi/gateway/.env
```
Set:
- `MQTT_CORE_HOST=192.168.1.5`
- `MQTT_CORE_PORT=8883`
- `MQTT_CORE_USERNAME=gw_forwarder`
- `MQTT_CORE_PASSWORD=<STRONG_PASSWORD>`
- `MQTT_LOCAL_PASSWORD=<LOCAL_INGESTION_PASSWORD>`

### Step 2.4: Deploy Gateway Stack

```bash
./scripts/deploy_gateway.sh
```

### Step 2.5: Configure Local EMQX Users

Create user accounts for Wi-Fi ESP32 nodes in Local EMQX:
```bash
# Ingestion service account
docker exec -it enviromesh-emqx-local emqx ctl admins add \
    --username gw_ingestion --password "<LOCAL_INGESTION_PASSWORD>"

# Device accounts
docker exec -it enviromesh-emqx-local emqx ctl admins add \
    --username g31 --password "<DEVICE_PASSWORD>"
docker exec -it enviromesh-emqx-local emqx ctl admins add \
    --username g61 --password "<DEVICE_PASSWORD>"
```

### Step 2.6: Verify Gateway Health

```bash
python3 scripts/check_gateway_health.py
```

---

## 3. Flash & Configure ESP32 Nodes

1. Configure Wi-Fi nodes (`node_g31`, `node_g61_servo`, etc.):
   - Set `MQTT_BROKER_HOST` / `MQTT_HOST` to RPi 1's IP (`192.168.1.20`).
   - Set port to `1883`.
   - Set matching credentials.
2. Power on LoRa nodes (`node_g11`, `node_g41`).
3. Observe live telemetry flowing on the dashboard at `http://192.168.1.5:8080`.

