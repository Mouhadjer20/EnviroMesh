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
- [4. Software Dependencies & Compilation](#4-software-dependencies--compilation)
  - [Required Arduino Libraries](#required-arduino-libraries)
  - [Compilation Settings (Arduino IDE / PlatformIO)](#compilation-settings-arduino-ide--platformio)
- [5. Calibration Procedure (MQ-2 Gas Sensor)](#5-calibration-procedure-mq-2-gas-sensor)
- [6. Future Implementation Roadmap (Firmware Phases)](#6-future-implementation-roadmap-firmware-phases)
  - [Phase 3.1: Finalize Node G31](#phase-31-finalize-node-g31-group-3--wi-fi-bmp280-node)
  - [Phase 3.2: Finalize Node G61](#phase-32-finalize-node-g61-group-6--wi-fi-servo--motion-node)
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
    │       └── main.ino               # 290 lines: MQ-2, DHT11, Water, LoRa 433 MHz, JSON formatting
    ├── node_g42/                      # Group 4 — Wi-Fi MQTT Client Node [IMPLEMENTED / TEST]
    │   └── src/main/
    │       └── main.ino               # 98 lines: ESP32 Wi-Fi + PubSubClient MQTT publisher
    ├── node_g43/                      # Group 4 — Simulated Telemetry MQTT Node [IMPLEMENTED / TEST]
    │   └── src/main/
    │       └── main.ino               # 146 lines: Wi-Fi MQTT publisher with schema-compliant JSON
    ├── node_g31/                      # Group 3 — Wi-Fi Environmental Node [PHASE 3 IN PROGRESS]
    │   └── src/
    │       └── main.ini               # Specification stub: BMP280, MQ-2, Water leak, MQTT over Wi-Fi
    └── node_g61_servo/                # Group 6 — Wi-Fi Servo & Motion Node [PHASE 3 IN PROGRESS]
        └── src/
            └── main.ini               # Specification stub: MQ-2, DHT11, Water, PIR, 9g Micro Servo, BLE
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
| `node_g61_servo` | `G61`     | G6    | MQ-2, DHT11, Water, PIR Motion, Micro Servo 9g | Wi-Fi MQTT + BLE  | EMQX + Local Operator | **Phase 3.2**        |

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

### 3.3. Test Nodes G42 & G43 (`node_g42`, `node_g43`)
Wi-Fi nodes running `PubSubClient` connecting to the EMQX broker at port 1883.
- `node_g42`: Demonstrates reconnect logic, callback processing, and publishing heartbeat payloads.
- `node_g43`: Periodically generates synthetic telemetry conforming to the database schema (`gas_ppm`, `temperature_c`, `humidity`, `pressure_hpa`, `water_leak`, `motion_detected`, `group_code`, `firmware_version`) and publishes to `enviromesh/devices/G11/telemetry`.

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

## 6. Future Implementation Roadmap (Firmware Phases)

### Phase 3.1: Finalize Node G31 (Group 3 — Wi-Fi BMP280 Node)
- [ ] Connect BMP280 via I2C (`SDA = GPIO 21`, `SCL = GPIO 22`).
- [ ] Wire MQ-2 AO and Water sensor to ADC1 pins (`GPIO 32` and `GPIO 33`).
- [ ] Implement Wi-Fi auto-reconnect and MQTT client publishing to `enviromesh/devices/G31/telemetry`.
- [ ] Add barometric pressure compensation and temperature readouts.

### Phase 3.2: Finalize Node G61 (Group 6 — Wi-Fi Servo & Motion Node)
- [ ] Wire PIR sensor digital output to an interrupt-enabled GPIO (`GPIO 13`).
- [ ] Connect Micro Servo 9g signal pin to PWM GPIO (`GPIO 18`) using `ESP32Servo`.
- [ ] Subscribe to actuator command topic `enviromesh/devices/G61/commands/servo`.
- [ ] Implement local safety threshold: automatically close valve ($0^\circ$) if gas or water leak is detected.
- [ ] Implement BLE GATT service for localized manual override commands from authorized technician smartphones.

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