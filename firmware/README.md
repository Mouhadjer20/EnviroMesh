# Firmware — EnviroMesh Field Sensor Nodes

This directory contains the embedded firmware for the ESP32 field sensor nodes, actuator controllers, and communication bridges of the **EnviroMesh** platform. Each node is an independent ESP32 firmware application that acquires environmental metrics and transmits telemetry over its assigned transport protocol (**LoRa 433 MHz**, **Wi-Fi MQTT**, or **ESP-NOW**).

---

## Table of Contents

- [1. Node Directory Layout & Implementation Status](#1-node-directory-layout--implementation-status)
- [2. Hardware Topology & Node Specifications](#2-hardware-topology--node-specifications)
- [3. Node Details & Pin Configurations](#3-node-details--pin-configurations)
  - [3.1. Node G11](#31-node-g11-node_g11srcmainino)
  - [3.2. Node G41](#32-node-g41-firmwarenodesnode_g41srcmainmainino)
  - [3.3. Test Nodes G42 & G43](#33-test-nodes-g42--g43-node_g42-node_g43)
  - [3.4. Node G61 Servo & Actuator Node](#34-node-g61-servo--actuator-node-firmwarenodesnode_g61_servosrcmainino)
- [4. Software Dependencies & Compilation](#4-software-dependencies--compilation)
  - [Required Arduino Libraries](#required-arduino-libraries)
  - [Compilation Settings (Arduino IDE / PlatformIO)](#compilation-settings-arduino-ide--platformio)
- [5. Calibration Procedure (MQ-2 Gas Sensor)](#5-calibration-procedure-mq-2-gas-sensor)
- [6. Implementation Roadmap (Firmware Phases)](#6-implementation-roadmap-firmware-phases)
  - [Phase 3.1: Finalize Node G31](#phase-31-finalize-node-g31-group-3--wi-fi-bmp280-node)
  - [Phase 3.2: Node G61 Actuation & Safety](#phase-32-node-g61-actuation--safety-group-6--wi-fi-servo--motion-node)
  - [Phase 3.3: Communications Security](#phase-33-communications-security-phase-4-integration)
  - [Phase 3.4: Low-Power Optimization](#phase-34-low-power-optimization)
- [7. Related Documentation](#7-related-documentation)

---

## 1. Node Directory Layout & Implementation Status

```
firmware/
└── nodes/
    ├── node_g11/                      # Group 1 — LoRa Environmental Node [IMPLEMENTED]
    │   └── src/
    │       └── main.ino               # 423 lines: MQ-2 (NVS calibration), DHT11, Water, Ra-02 LoRa
    ├── node_g41/                      # Group 4 — LoRa Environmental Node [IMPLEMENTED]
    │   └── src/main/
    │       └── main.ino               # 286 lines: MQ-2, DHT11, Water, LoRa 433 MHz, Compact JSON (<250B)
    ├── node_g42/                      # Group 4 — Wi-Fi MQTT Client Node [IMPLEMENTED / TEST]
    │   └── src/main/
    │       └── main.ino               # 98 lines: ESP32 Wi-Fi + PubSubClient MQTT publisher
    ├── node_g43/                      # Group 4 — Simulated Telemetry MQTT Node [IMPLEMENTED / TEST]
    │   └── src/
    │       ├── main.ino               # 105 lines: Clean single-folder layout, schema-compliant JSON
    │       └── secrets.h.example      # Wi-Fi & MQTT credentials template
    ├── node_g31/                      # Group 3 — Wi-Fi Environmental Node [PHASE 3 IN PROGRESS]
    │   └── src/
    │       └── main.ini               # Specification stub: BMP280, MQ-2, Water leak, MQTT over Wi-Fi
    └── node_g61_servo/                # Group 6 — Wi-Fi Servo & Motion Node [IMPLEMENTED]
        └── src/
            ├── main.ino               # 896 lines: MQ-2, DHT11, Water, PIR, SG90 Servo PWM, NTP UTC sync
            └── secrets.h.example      # Wi-Fi & MQTT credentials template
```

---

## 2. Hardware Topology & Node Specifications

| Node             | Device ID | Group | Sensors / Actuators                            | Primary Transport | Destination           | Status               |
| ---------------- | --------- | ----- | ---------------------------------------------- | ----------------- | --------------------- | -------------------- |
| `node_g11`       | `G11`     | G1    | MQ-2 (Gas/Smoke), DHT11 (Temp/Hum), Water Leak | LoRa 433 MHz      | RPi (LoRa Gateway)    | **Production-Ready** |
| `node_g41`       | `G41`     | G4    | MQ-2 (Gas/Smoke), DHT11 (Temp/Hum), Water Leak | LoRa 433 MHz      | RPi (LoRa Gateway)    | **Production-Ready** |
| `node_g42`       | `G42`     | G4    | Wi-Fi Station                                  | Wi-Fi / MQTT      | EMQX Broker (`:1883`) | **Test Harness**     |
| `node_g43`       | `G43`     | G4    | Synthetic Metrics                              | Wi-Fi / MQTT      | EMQX Broker (`:1883`) | **Test Harness**     |
| `node_g31`       | `G31`     | G3    | BMP280 (Pressure/Temp), MQ-2 (Gas), Water Leak | Wi-Fi / MQTT      | EMQX Broker (`:1883`) | **Phase 3.1**        |
| `node_g61_servo` | `G61`     | G6    | MQ-2, DHT11, Water, PIR Motion, Micro Servo 9g | Wi-Fi MQTT        | EMQX (`:1883`)        | **Operational**      |

---

## 3. Node Details & Pin Configurations

### 3.1. Node G11 (`node_g11/src/main.ino`)
Designed for industrial monitoring in *Sector A Warehouse*. Includes calibrated MQ-2 LPG modeling, continuous ADC sampling, and NVS flash storage of sensor baseline.

- **Sensors:**
  - **DHT11:** Data on `GPIO 4`
  - **MQ-2 AO:** `GPIO 0` (ADC2_CH1) with 10k/15k resistor divider network (`gain = 0.60`)
  - **MQ-2 DO:** `GPIO 2`
  - **Water Sensor:** `GPIO 15` (ADC2_CH3, threshold: `1500` counts)
- **Ra-02 LoRa Transceiver (SPI):**
  - `SS / NSS`: `GPIO 16`
  - `RST`: `GPIO 14`
  - `DIO0`: `GPIO 26`
  - `SCK`: `GPIO 5`
  - `MISO`: `GPIO 19`
  - `MOSI`: `GPIO 32`
- **Features:**
  - `WiFi.mode(WIFI_OFF)` to prevent Wi-Fi from conflicting with ADC2 pins.
  - 180-second warmup timer for the MQ-2 heating coil.
  - Persistent calibration: stores clean-air $R_0$ reference in non-volatile flash using the `Preferences` library (`enviromesh-mq2` namespace). Pressing `C` or `c` over the serial console in clean air triggers multi-sample calibration and auto-saves $R_0$.
  - Generates compact, standard-compliant JSON telemetry envelopes with wrapping sequence counter `seq`.

### 3.2. Node G41 (`firmware/nodes/node_g41/src/main/main.ino`)
LoRa environmental station deployed in *Sector B Warehouse*.

- **Sensors:**
  - **DHT11:** Data on `GPIO 22`
  - **MQ-2 AO:** `GPIO 17`
  - **MQ-2 DO:** `GPIO 16`
  - **Water Sensor:** `GPIO 34` (ADC1_CH6, input-only pin, threshold: `1500`)
- **LoRa Module (SPI):**
  - `SS`: `GPIO 27`
  - `RST`: `GPIO 14`
  - `DIO0`: `GPIO 26`
  - `SCK`: `GPIO 18`
  - `MISO`: `GPIO 25`
  - `MOSI`: `GPIO 32`
- **RF Parameters:** Frequency: `433E6` (433 MHz), SF: `7`, Bandwidth: `125E3` (125 kHz), Coding Rate: `4/5`, CRC: Enabled.
- **Compact LoRa Payload & Buffer Safety:**
  - **Payload Size Guarantee:** Formatted strictly under 250 bytes to respect the SX1278 hardware FIFO limit (256 bytes). This prevents over-the-air packet truncation.
  - **Memory Safety:** Direct float rounding (`round(val * 10.0) / 10.0`) eliminates temporary `String` allocations and dangling pointer memory corruption.
  - **Over-the-Air Payload Format:**
    ```json
    {
      "device_id": "G41",
      "zone": "Sector_B_Warehouse",
      "protocol": "lora",
      "metrics": {
        "gas_adc_raw": 0,
        "smoke_detected": true,
        "temperature_c": 23.6,
        "humidity_pct": 43.7,
        "water_leak_detected": false
      },
      "metadata": {
        "uptime_ms": 568,
        "packet_counter": 1
      }
    }
    ```
  - Redundant fields (`timestamp`, `group_code`) are omitted over RF to minimize transmission airtime, and are populated automatically by the Raspberry Pi gateway upon reception.

### 3.3. Test Nodes G42 & G43 (`node_g42`, `node_g43`)
Wi-Fi nodes running `PubSubClient` connecting to the EMQX broker at port 1883.
- `node_g42`: Demonstrates reconnect logic, callback processing, and publishing heartbeat payloads.
- `node_g43` ([`firmware/nodes/node_g43/src/main.ino`](nodes/node_g43/src/main.ino)): Flattened standard Arduino layout. Periodically generates synthetic telemetry conforming to the database schema (`gas_ppm`, `temperature_c`, `humidity`, `pressure_hpa`, `water_leak`, `motion_detected`, `group_code`, `firmware_version`) and publishes to `enviromesh/devices/G43/telemetry`.

### 3.4. Node G61 Servo & Actuator Node ([`firmware/nodes/node_g61_servo/src/main.ino`](nodes/node_g61_servo/src/main.ino))
High-reliability environmental monitor and automated valve shut-off actuator for *Sector A Valve*.
- **Sensors & Actuator Pinout:**
  - **MQ-2 AO:** `GPIO 34` (ADC1 input, 16x oversampling, clean-air baseline calibration)
  - **DHT11:** Data on `GPIO 4` (consecutive failure tracking with fallback)
  - **Water Leak Sensor:** `GPIO 35` (ADC1 input)
  - **PIR Motion Sensor:** `GPIO 13` (interrupt/fast polling every 50 ms with event debouncing)
  - **SG90 Micro Servo:** PWM on `GPIO 18` driven by `ESP32Servo`
- **Features:**
  - **NTP Clock Synchronization:** Acquires true UTC timestamps via network time protocol on boot.
  - **Automatic Safety Closure:** Auto-triggers emergency valve closure upon detecting high gas levels or water leaks.
  - **Command Subscription:** Subscribes to `enviromesh/devices/G61/commands/servo` for remote position adjustments (0° to 180°).

---

## 4. Software Dependencies & Compilation

### Required Arduino Libraries
Install the following libraries via the Arduino IDE Library Manager or `platformio.ini`:

1. **`LoRa` by Sandeep Mistry** (v0.8.0+) — SX127x radio driver.
2. **`DHT sensor library` by Adafruit** (v1.4.6+) + **Adafruit Unified Sensor**.
3. **`MQUnifiedsensor` by Miguel A. Califa U.** (v3.0.0+) — Gas sensor regression models.
4. **`ArduinoJson` by Benoît Blanchon** (v6.21.x or v7.x) — JSON serialization.
5. **`PubSubClient` by Nick O'Leary** (v2.8.0+) — MQTT client for Wi-Fi nodes.
6. **`Adafruit BMP280 Library`** (for Node G31).
7. **`ESP32Servo`** (for Node G61).

### Compilation Settings (Arduino IDE / PlatformIO)
- **Board:** `ESP32 Dev Module` or `NodeMCU-32S`
- **Upload Speed:** `921600` or `115200`
- **CPU Frequency:** `240MHz` (or `80MHz` for power saving)
- **Flash Frequency:** `80MHz`
- **Flash Mode:** `QIO`
- **Partition Scheme:** `Default 4MB with spiffs` or `Minimal SPIFFS (Large APPS)`

> [!WARNING]
> **ADC2 Conflict with Wi-Fi:**
> Pins on ADC2 (`GPIO 0, 2, 4, 12, 13, 14, 15, 25, 26, 27`) cannot be read with `analogRead()` while Wi-Fi is active because the Wi-Fi subsystem takes exclusive ownership of ADC2.
> - On LoRa nodes (`G11`, `G41`), Wi-Fi is turned off (`WiFi.mode(WIFI_OFF)`), so ADC2 works reliably.
> - On Wi-Fi nodes (`G31`, `G61`), analog sensor inputs must be connected to **ADC1 pins** (`GPIO 32, 33, 34, 35, 36, 39`).

---

## 5. Calibration Procedure (MQ-2 Gas Sensor)

1. **Preheating:** When powered on, allow the MQ-2 internal heater coil to warm up for at least **180 seconds** (the firmware logs progress to Serial).
2. **Clean Air Conditioning:** Place the node in an uncontaminated outdoor or clean indoor environment.
3. **Trigger Calibration:** Open the Serial Monitor at **115200 baud** and send the character `C`.
4. **Automatic Saving:** The firmware acquires 10 sequential ADC samples, calculates the clean-air baseline sensor resistance $R_0$, and writes it to ESP32 flash memory (`Preferences`). Subsequent reboots load $R_0$ automatically.

---

## 6. Implementation Roadmap (Firmware Phases)

### Phase 3.1: Finalize Node G31 (Group 3 — Wi-Fi BMP280 Node)
- [ ] Connect BMP280 via I2C (`SDA = GPIO 21`, `SCL = GPIO 22`).
- [ ] Wire MQ-2 AO and Water sensor to ADC1 pins (`GPIO 32` and `GPIO 33`).
- [ ] Implement Wi-Fi auto-reconnect and MQTT client publishing to `enviromesh/devices/G31/telemetry`.
- [ ] Add barometric pressure compensation and temperature readouts.

### Phase 3.2: Node G61 Actuation & Safety (Group 6 — Wi-Fi Servo & Motion Node) [OPERATIONAL]
- [x] Wire PIR sensor digital output to GPIO 13 with 50 ms polling and event debouncing.
- [x] Connect Micro Servo 9g signal pin to PWM GPIO 18 using `ESP32Servo`.
- [x] Subscribe to actuator command topic `enviromesh/devices/G61/commands/servo`.
- [x] Implement local safety threshold: automatically close valve ($0^\circ$) if gas or water leak is detected.
- [ ] Phase 4: Implement BLE GATT service for localized manual override commands from authorized technician smartphones.

### Phase 3.3: Communications Security (Phase 4 Integration)
- [ ] **AES-128-CBC Payload Encryption:** Encrypt LoRa JSON payloads using a pre-shared 128-bit key stored in secure flash before transmission; decrypt in `services/lora_receiver.py`.
- [ ] **MQTTS / TLS 1.3:** Configure Wi-Fi nodes to connect to EMQX port 8883 with CA certificates.
- [ ] **ESP32 Secure Boot V2 & Flash Encryption** to protect keys from physical extraction.

### Phase 3.4: Low-Power Optimization
- [ ] Implement ESP32 Deep Sleep (`esp_sleep_enable_timer_wakeup`) with 30-second cycles.
- [ ] Power down Ra-02 LoRa module (`LoRa.sleep()`) and sensor power rails between measurement cycles to allow battery/solar operation.

---

## 7. Related Documentation

- Project Root & Architecture: [README.md](../README.md)
- Raspberry Pi Core Server: [raspberry_pi/README.md](../raspberry_pi/README.md)
- Database Layer: [raspberry_pi/db/README.md](../raspberry_pi/db/README.md)
- Web Dashboard: [raspberry_pi/dashboard/README.md](../raspberry_pi/dashboard/README.md)
- Automation & Helper Scripts: [scripts/README.md](../scripts/README.md)