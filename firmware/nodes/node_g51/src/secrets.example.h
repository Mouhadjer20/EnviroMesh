// Copy this file to "secrets.h" (in the same folder) and enter your Wi-Fi & MQTT settings.
// The ESP32 only supports 2.4 GHz networks.
// IMPORTANT: In the EnviroMesh architecture, Wi-Fi nodes must connect to RPi 1 Gateway
// (NOT RPi 2 Core). Telemetry is forwarded from the gateway to the core automatically.

#pragma once

// Wi-Fi credentials
#define WIFI_SSID         "REPLACE_WITH_WIFI_SSID"
#define WIFI_PASSWORD     "REPLACE_WITH_WIFI_PASSWORD"

// MQTT broker settings (RPi 1 Gateway IP on local LAN, e.g., 192.168.1.20 or localhost)
#define MQTT_BROKER_HOST  "192.168.1.20"
#define MQTT_PORT         1883
#define MQTT_USERNAME     "g51"
#define MQTT_PASSWORD     "REPLACE_WITH_G51_PASSWORD"

// EnviroMesh Node Identification
#define DEVICE_ID         "G51"
#define GROUP_CODE        "G5"
#define DEVICE_ZONE       "Sector_B_Storage"
#define MQTT_TOPIC_DATA   "enviromesh/devices/G51/telemetry"
#define MQTT_TOPIC_STATUS "enviromesh/devices/G51/status"

