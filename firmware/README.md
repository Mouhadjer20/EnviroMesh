# Firmware — Environmental Monitoring System

This folder contains the embedded firmware for the ESP32 field sensor nodes of
the EnviroMesh platform. Each node is an independent ESP32 application that
reads environmental sensors and publishes telemetry over its assigned
communication protocol.

## Node Directory Layout

```
firmware/
└── nodes/
    ├── node_g11/              # Group 1 — LoRa environmental node (device G11)
    │   └── src/main.ini
    ├── node_g41/              # Group 4 — LoRa environmental node (device G41)
    │   └── src/main.ini
    ├── node_g31/              # Group 3 — Wi-Fi environmental node (device G31)
    │   └── src/main.ini
    └── node_g61_servo/        # Group 6 — Wi-Fi servo & motion node (device G61)
        └── src/main.ini
```

Each `src/main.ini` is a placeholder file containing a `# TODO: Write your code here`
marker. Replace it with the actual ESP32 firmware source (e.g. Arduino/PlatformIO
`main.cpp`, ESP-IDF `main/main.c`, or MicroPython `main.py`) as development
progresses.

## Node Summary

| Node | Device ID | Group | Sensors | Actuator | Protocol | Destination |
|------|-----------|-------|---------|----------|----------|-------------|
| `node_g11` | G11 | G1 | MQ-2 (gas/smoke), DHT11 (temp/hum), Water leak | — | LoRa 433 MHz | RPi 1 (LoRa Gateway) |
| `node_g41` | G41 | G4 | MQ-2 (gas/smoke), DHT11 (temp/hum), Water leak | — | LoRa 433 MHz | RPi 1 (LoRa Gateway) |
| `node_g31` | G31 | G3 | BMP280 (pressure/temp), MQ-2 (gas/smoke), Water leak | — | Wi-Fi (MQTT / TCP) | RPi 2 (Core Server) |
| `node_g61_servo` | G61 | G6 | MQ-2 (gas/smoke), DHT11 (temp/hum), Water leak, PIR (motion) | Micro Servo 9g | Wi-Fi (MQTT / TCP) + BLE | Local Operator / RPi BLE Proxy |

## Communication Details

- **LoRa nodes (G11, G41):** Transmit JSON telemetry via ESP32 + SX1276 on LoRa 433 MHz to RPi 1, which forwards to RPi 2 via MQTT.
- **Wi-Fi nodes (G31, G61):** Publish JSON telemetry directly via MQTT over Wi-Fi/TCP to RPi 2.
- **BLE Servo Node (G61):** Implements a BLE GATT server to receive encrypted rotation commands (0°–180°) for the micro servo.

## Security Notes

- LoRa payloads should use **AES-128** application-layer encryption.
- Wi-Fi/MQTT should use **WPA3-Enterprise** or **TLS-secured MQTT (port 8883)**.
- The servo node requires **secure BLE bonding** with rotating challenge-response tokens before accepting motion commands.
- Enable **ESP32 Secure Boot V2** and **Flash Encryption** to protect against firmware tampering.

## Implementation Roadmap (Phase 3)

Per the project README, firmware is developed in **Phase 3: Firmware Development (ESP32 Nodes)**:

1. LoRa nodes: format JSON telemetry and transmit via LoRa.
2. Wi-Fi nodes: publish telemetry directly via MQTT over Wi-Fi.
3. ESP32-CAM: video streaming via RTSP using MediaMTX on RPi 2.
4. BLE Servo Node: BLE GATT server for encrypted rotation commands.

## Related Documentation

- Project architecture & full specification: [`../README.md`](../README.md)
- Database layer: [`../db`](../db)
- Dashboard: [`../dashboard`](../dashboard)