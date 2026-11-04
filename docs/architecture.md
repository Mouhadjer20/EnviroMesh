# EnviroMesh Architecture Specification

## 1. Architectural Philosophy

EnviroMesh adopts a decoupled, multi-tiered edge architecture designed for industrial and agricultural warehouse monitoring. It addresses real-world IoT deployment challenges:
- **Intermittent network connectivity**: The gateway must buffer data without loss during core server downtime.
- **Heterogeneous wireless transports**: Long-range LoRa 433 MHz RF and local Wi-Fi MQTT coexist seamlessly.
- **Cybersecurity & Defense-in-Depth**: Raw field sensors are completely isolated from the central database and management dashboard.

---

## 2. Two-Raspberry-Pi Separation

```
[ ESP32 LoRa Nodes ]      [ ESP32 Wi-Fi Nodes ]
 (G11, G41: 433MHz)        (G31, G42, G43, G61)
         │                          │
         │                          │ (Plain MQTT :1883)
         ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│              RPi 1 — GATEWAY (192.168.1.20)             │
│                                                         │
│  SX1278 SPI Receiver       Local EMQX Broker (:1883)    │
│           │                          │                  │
│           └───────────┬──────────────┘                  │
│                       ▼                                 │
│          Normalizer & Early Validator                   │
│                       ▼                                 │
│        Persistent SQLite Queue (WAL Full)               │
│                       ▼                                 │
│            MQTT Forwarder Service                       │
└───────────────────────┬─────────────────────────────────┘
                        │
                        │ MQTT over TLS (:8883, QoS 1)
                        ▼
┌─────────────────────────────────────────────────────────┐
│               RPi 2 — CORE (192.168.1.5)               │
│                                                         │
│              Central EMQX Broker (:8883)                │
│                       │                                 │
│                       ▼                                 │
│            FastAPI MQTT Subscriber                      │
│            (Duplicate Detection)                        │
│                       ▼                                 │
│      PostgreSQL 16 + TimescaleDB 2.17 (Internal)        │
│                       ▲                                 │
│                       │ Internal API                    │
│                       ▼                                 │
│             FastAPI Backend (:8000)                     │
│                       ▲                                 │
│                       │ Reverse Proxy                   │
│             Nginx Web Server (:8080)                    │
│                       │                                 │
│             React + Vite Dashboard                      │
└─────────────────────────────────────────────────────────┘
```

### Component Placement Summary

| Component               | Host  | Access / Exposure                                       |
| ----------------------- | ----- | ------------------------------------------------------- |
| **SX1278 Receiver**     | RPi 1 | Local SPI `/dev/spidev0.0`                              |
| **Local EMQX**          | RPi 1 | Exposed on LAN `0.0.0.0:1883` for Wi-Fi ESP32s          |
| **SQLite Queue**        | RPi 1 | Internal volume (`/var/lib/enviromesh/queue.db`)        |
| **Gateway Forwarder**   | RPi 1 | Client outbound connection to RPi 2                     |
| **Central EMQX**        | RPi 2 | Exposed on LAN `0.0.0.0:8883` (TLS only)                |
| **TimescaleDB**         | RPi 2 | **Internal Docker network only** (no host port binding) |
| **FastAPI Backend**     | RPi 2 | Internal Docker network `:8000`                         |
| **React Dashboard**     | RPi 2 | Internal Docker network `:80`                           |
| **Nginx Reverse Proxy** | RPi 2 | Exposed on LAN `0.0.0.0:8080`                           |

---

## 3. Data Pipeline & Reliability Guarantees

1. **Ingestion & Normalization**:
   - Both LoRa frames and Wi-Fi JSON are transformed into a standard JSON envelope with `message_id`, `gateway_id`, `gateway_received_at`, and signal metrics.
   - For LoRa nodes, `message_id` is a deterministic UUIDv5 derived from `device_id`, packet sequence number, and timestamp.
2. **Offline Persistence**:
   - Every normalized packet is written to SQLite with `PRAGMA journal_mode = WAL` and `PRAGMA synchronous = FULL`.
   - The queue holds up to 50,000 messages (configurable).
3. **At-Least-Once TLS Forwarding**:
   - The forwarder connects to RPi 2 over TLS using the custom CA.
   - Forwarding uses MQTT QoS 1. Messages are **only deleted** from the SQLite queue when the MQTT broker returns a `PUBACK`.
4. **Deduplication at Core**:
   - In RPi 2's backend, `database_writer.py` verifies `message_id` against the `processed_messages` table in PostgreSQL before inserting into `sensor_telemetry`.
   - If a duplicate message is received, it is discarded safely.

