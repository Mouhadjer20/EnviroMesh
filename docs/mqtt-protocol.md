# MQTT Protocol & Topic Design

EnviroMesh employs two separate, non-clustered EMQX brokers with strict topic namespaces and role-based ACLs.

---

## 1. Topic Hierarchy

### Layer 1: ESP32 Nodes → RPi 1 (Local Broker)

Wi-Fi ESP32 nodes publish to their dedicated topic:
```
enviromesh/devices/{device_id}/telemetry
```
Examples:
- `enviromesh/devices/G31/telemetry`
- `enviromesh/devices/G61/telemetry`
- `enviromesh/devices/G42/telemetry`
- `enviromesh/devices/G43/telemetry`

### Layer 2: RPi 1 (Gateway) → RPi 2 (Core Broker)

The Gateway forwarder batches and publishes normalized packets to:
```
enviromesh/gateway/{gateway_id}/telemetry
```
Example:
- `enviromesh/gateway/GW01/telemetry`

Gateway status and heartbeat (using MQTT LWT — Last Will & Testament):
```
enviromesh/gateway/{gateway_id}/status
```
Example:
- `enviromesh/gateway/GW01/status` (Payload: `{"gateway_id": "GW01", "status": "online", "queue_pending": 0}`)

---

## 2. Telemetry Envelopes

### Raw ESP32 Payload (Example G31 Wi-Fi)

```json
{
  "device_id": "G31",
  "zone": "Sector_C_Utility_Room",
  "protocol": "Wi-Fi",
  "metrics": {
    "gas_adc_raw": 320,
    "water_adc_raw": 0,
    "temperature_c": 21.8,
    "pressure_hpa": 1012.3
  },
  "metadata": {
    "group_code": "G3",
    "firmware_version": "1.0.0",
    "sequence": 142
  }
}
```

### Normalized Gateway Envelope (Transmitted to RPi 2)

```json
{
  "message_id": "c1f7a49a-65b1-4f93-bcf7-0d5885c3db11",
  "timestamp": null,
  "device_id": "G31",
  "group_code": "G3",
  "zone": "Sector_C_Utility_Room",
  "protocol": "wi-fi",
  "gateway_id": "GW01",
  "gateway_received_at": "2026-11-02T18:30:15.123456+00:00",
  "ingress_topic": "enviromesh/devices/G31/telemetry",
  "metrics": {
    "gas_adc_raw": 320,
    "water_adc_raw": 0,
    "temperature_c": 21.8,
    "pressure_hpa": 1012.3
  },
  "device_metadata": {
    "group_code": "G3",
    "firmware_version": "1.0.0",
    "sequence": 142
  }
}
```

For LoRa nodes, `rssi_dbm` and `snr_db` are also attached.

---

## 3. Quality of Service (QoS) Policy

- **ESP32 → RPi 1**: QoS 0 or QoS 1. Low overhead on resource-constrained microcontrollers.
- **RPi 1 → RPi 2**: **Strictly QoS 1**. Guarantees that every message is acknowledged by Core EMQX. The SQLite queue retains the record until PUBACK is received.
- **RPi 2 Backend Subscriber**: QoS 1. Ensures no dropped messages during backend service restarts.

