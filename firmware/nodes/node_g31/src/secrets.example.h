#pragma once
// Copy this file to secrets.h and fill it in locally. Do not commit secrets.h.
// In the EnviroMesh Two-Raspberry-Pi architecture, Wi-Fi nodes MUST point to
// RPi 1 (Gateway) — NEVER RPi 2 (Core).
#define WIFI_SSID "REPLACE_WITH_WIFI_NAME"
#define WIFI_PASSWORD "REPLACE_WITH_WIFI_PASSWORD"
#define MQTT_BROKER_HOST "192.168.1.20"  // IP of RPi 1 (Gateway)
#define MQTT_PORT 1883
#define MQTT_USERNAME "g31"              // Device credentials in RPi 1 local EMQX
#define MQTT_PASSWORD "REPLACE_WITH_EMQX_DEVICE_PASSWORD"
