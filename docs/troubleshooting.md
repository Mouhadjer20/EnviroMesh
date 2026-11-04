# Troubleshooting & Diagnostics

A guide to resolving common issues in the EnviroMesh Two-Raspberry-Pi deployment.

---

## 1. Gateway (RPi 1) Issues

### Issue: "LoRa hardware not available on this platform"
- **Cause**: SPI interface disabled in Raspberry Pi OS or running in emulation on a non-RPi device.
- **Fix**: Run `sudo raspi-config nonint do_spi 0` and verify that `/dev/spidev0.0` exists. Ensure the container has `devices: - /dev/spidev0.0:/dev/spidev0.0`.

### Issue: "Cannot reach core EMQX: [Errno 111] Connection refused"
- **Causes**:
  1. RPi 2 is powered off or IP changed.
  2. Core EMQX container is restarting.
  3. UFW on RPi 2 is blocking port 8883.
- **Diagnosis**:
  ```bash
  nc -zv 192.168.1.5 8883
  ```
- **Resolution**:
  - The forwarder automatically backs off and retries up to 60s.
  - Check SQLite queue depth to verify messages are accumulating safely:
    ```bash
    sqlite3 ./EnviroMesh/raspberry_pi/gateway/data/queue.db "SELECT count(*) FROM queue;"
    ```

### Issue: "TLS verification failed: certificate verify failed"
- **Cause**: CA certificate mismatch or hostname/IP not listed in certificate Subject Alternative Names (SAN).
- **Diagnosis**:
  ```bash
  openssl s_client -connect 192.168.1.5:8883 -CAfile certs/core-ca.crt
  ```
- **Fix**: Re-generate the server certificate on RPi 2 ensuring `192.168.1.5` is listed in `server_ext.cnf`.

---

## 2. Core (RPi 2) Issues

### Issue: "TimescaleDB connection refused"
- **Cause**: Database container still initializing or unhealthy.
- **Diagnosis**:
  ```bash
  docker compose -f raspberry_pi/core/docker-compose.yml ps timescaledb
  docker compose -f raspberry_pi/core/docker-compose.yml logs timescaledb
  ```

### Issue: "Duplicate message_id ignored"
- **Cause**: Expected behavior! The gateway forwarder resent an unacknowledged message, or an ESP32 node transmitted with the same sequence number.
- **Verification**: Query `processed_messages`:
  ```bash
  docker compose -f raspberry_pi/core/docker-compose.yml exec timescaledb \
      psql -U enviromesh_app -d enviromesh -c "SELECT * FROM processed_messages ORDER BY processed_at DESC LIMIT 5;"
  ```

---

## 3. Wi-Fi ESP32 Node Issues

### Issue: ESP32 node continuously reboots or cannot connect to MQTT
- **Cause**: Node is trying to connect to RPi 2 instead of RPi 1, or client isolation is active on the router.
- **Fix**: Verify `secrets.h` points to RPi 1 (`192.168.1.20`) on port `1883`. Disable AP isolation on the Wi-Fi router.

