/**
 * EnviroMesh - G31 (Group 3)
 * ESP32 + BMP280 + MQ-2 + water sensor, Wi-Fi/MQTT telemetry.
 * Raw ADC readings are deliberately sent as ADC counts, not ppm or leak booleans.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <math.h>
#include <Adafruit_BMP280.h>
#include "secrets.h"  // Create from secrets.example.h; never commit this file.

constexpr char DEVICE_ID[] = "G31";
constexpr char GROUP_CODE[] = "G3";
constexpr char DEVICE_ZONE[] = "Sector_C_Utility_Room";
constexpr char MQTT_TOPIC[] = "enviromesh/devices/G31/telemetry";
constexpr char FIRMWARE_VERSION[] = "1.0.0";

// Existing Group 3 wiring: BMP280 SDA=21/SCL=22, MQ-2 AO=34, Water AO=35.
constexpr uint8_t MQ2_PIN = 34;   // ADC1: usable while Wi-Fi is active.
constexpr uint8_t WATER_PIN = 35; // ADC1: input only, usable while Wi-Fi is active.
constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;
constexpr unsigned long PUBLISH_INTERVAL_MS = 5000;
constexpr unsigned long WIFI_RETRY_INTERVAL_MS = 5000;
constexpr unsigned long MQTT_RETRY_INTERVAL_MS = 3000;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_BMP280 bmp;
bool bmpReady = false;
unsigned long lastPublish = 0;
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
uint32_t sequenceNumber = 0;

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  const unsigned long now = millis();
  if (now - lastWifiAttempt < WIFI_RETRY_INTERVAL_MS) return;
  lastWifiAttempt = now;
  Serial.printf("Connecting to Wi-Fi: %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  const unsigned long now = millis();
  if (now - lastMqttAttempt < MQTT_RETRY_INTERVAL_MS) return;
  lastMqttAttempt = now;
  String clientId = "EnviroMesh-G31-" + WiFi.macAddress();
  Serial.printf("Connecting to MQTT broker %s:%u ...\n", MQTT_BROKER_HOST, MQTT_PORT);
  bool connected;
  if (MQTT_USERNAME[0] != '\0') {
    connected = mqtt.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD);
  } else {
    connected = mqtt.connect(clientId.c_str());
  }
  Serial.println(connected ? "MQTT connected" : String("MQTT connection failed, state=") + mqtt.state());
}

void publishTelemetry() {
  const int gasAdc = analogRead(MQ2_PIN);
  const int waterAdc = analogRead(WATER_PIN);

  StaticJsonDocument<512> doc;
  doc["device_id"] = DEVICE_ID;
  doc["zone"] = DEVICE_ZONE;
  doc["protocol"] = "Wi-Fi";
  JsonObject metrics = doc.createNestedObject("metrics");
  metrics["gas_adc_raw"] = gasAdc;
  metrics["water_adc_raw"] = waterAdc;
  if (bmpReady) {
    const float temperature = bmp.readTemperature();
    const float pressure = bmp.readPressure() / 100.0F;
    if (isfinite(temperature)) metrics["temperature_c"] = roundf(temperature * 100.0F) / 100.0F;
    if (isfinite(pressure)) metrics["pressure_hpa"] = roundf(pressure * 100.0F) / 100.0F;
  } else {
    metrics["temperature_c"] = nullptr;
    metrics["pressure_hpa"] = nullptr;
  }
  JsonObject metadata = doc.createNestedObject("metadata");
  metadata["group_code"] = GROUP_CODE;
  metadata["firmware_version"] = FIRMWARE_VERSION;
  metadata["sequence"] = sequenceNumber++;
  metadata["uptime_ms"] = millis();

  char payload[512];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  if (length == 0 || length >= sizeof(payload)) {
    Serial.println("ERROR: JSON serialization failed");
    return;
  }
  const bool sent = mqtt.publish(MQTT_TOPIC, payload, false);
  Serial.printf("%s | %s\n", sent ? "PUBLISHED" : "PUBLISH FAILED", MQTT_TOPIC);
  Serial.println(payload);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  analogReadResolution(12); // ESP32 ADC values: 0..4095.
  pinMode(MQ2_PIN, INPUT);
  pinMode(WATER_PIN, INPUT);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  bmpReady = bmp.begin(0x76);
  if (!bmpReady) bmpReady = bmp.begin(0x77);
  Serial.println(bmpReady ? "BMP280 detected" : "WARNING: BMP280 not detected; raw sensor data will still publish");
  mqtt.setServer(MQTT_BROKER_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  connectWiFi();
}

void loop() {
  connectWiFi();
  if (WiFi.status() == WL_CONNECTED) {
    connectMqtt();
    mqtt.loop();
    const unsigned long now = millis();
    if (mqtt.connected() && now - lastPublish >= PUBLISH_INTERVAL_MS) {
      lastPublish = now;
      publishTelemetry();
    }
  }
  delay(10);
}
