/* =============================================================================
# Firmware: ESP32 Node G41 (Group 4 - LoRa environmental node)
# Device ID: G41
# Sensors: MQ-2 (gas/smoke), DHT11 (temperature/humidity), Water leak sensor
# Communication: LoRa 433 MHz -> RPi 1 (LoRa Gateway)
# =============================================================================
*/

#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <WiFi.h>

// =====================================================
// ENVIROMESH DEVICE CONFIGURATION
// =====================================================
#define DEVICE_ID       "G41"
#define GROUP_CODE      "G4"
#define DEVICE_ZONE     "Sector_B_Warehouse"

// =====================================================
// SENSOR PINS
// =====================================================
#define DHTTYPE         DHT11

const int DHT_PIN       = 22;
const int MQ2_AO_PIN    = 17;  // ADC-capable GPIO
const int MQ2_DO_PIN    = 16;
const int WATER_PIN     = 34;  // ADC1, input-only is suitable

// =====================================================
// LORA PINS
// Corrected for ESP32-WROOM-32
// =====================================================
#define LORA_SS         27
#define LORA_RST        14
#define LORA_DIO0       26

#define LORA_SCK        18
#define LORA_MISO       25
#define LORA_MOSI       32

#define LORA_FREQUENCY  433E6

// =====================================================
// TIMING
// =====================================================
const unsigned long SENSOR_INTERVAL = 1000;
const unsigned long DHT_INTERVAL    = 2000;
const unsigned long LORA_INTERVAL   = 2000;

// Calibrate this threshold using your actual water sensor.
const int WATER_LEAK_THRESHOLD = 1500;

// Many MQ-2 modules signal detection HIGH, but verify yours.
const int SMOKE_TRIGGER_LEVEL = HIGH;

// =====================================================
// OBJECTS AND VARIABLES
// =====================================================
DHT dht(DHT_PIN, DHTTYPE);

int waterValue = 0;
int mq2AnalogValue = 0;
int mq2DigitalState = LOW;

float temperature = NAN;
float humidity = NAN;

bool dhtReadingValid = false;

unsigned long previousSensorMillis = 0;
unsigned long previousDHTMillis = 0;
unsigned long previousLoRaMillis = 0;

unsigned long packetCounter = 0;

// =====================================================
// READ FAST SENSORS
// =====================================================
void readFastSensors() {
  waterValue = analogRead(WATER_PIN);
  mq2AnalogValue = analogRead(MQ2_AO_PIN);
  mq2DigitalState = digitalRead(MQ2_DO_PIN);

  Serial.println("\n--- Sensor Readings ---");

  Serial.print("Water ADC: ");
  Serial.println(waterValue);

  Serial.print("MQ-2 ADC: ");
  Serial.println(mq2AnalogValue);

  Serial.print("Smoke detected: ");
  Serial.println(
    mq2DigitalState == SMOKE_TRIGGER_LEVEL ? "YES" : "NO"
  );

  Serial.print("Water leak detected: ");
  Serial.println(
    waterValue >= WATER_LEAK_THRESHOLD ? "YES" : "NO"
  );
}

// =====================================================
// READ DHT11
// =====================================================
void readDHTSensor() {
  float newTemperature = dht.readTemperature();
  float newHumidity = dht.readHumidity();

  if (isnan(newTemperature) || isnan(newHumidity)) {
    dhtReadingValid = false;
    Serial.println("ERROR: Failed to read DHT11");
    return;
  }

  temperature = newTemperature;
  humidity = newHumidity;
  dhtReadingValid = true;

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" C");

  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");
}

// =====================================================
// BUILD AND TRANSMIT ENVIROMESH TELEMETRY
// =====================================================
void sendLoRaTelemetry() {
  StaticJsonDocument<512> doc;

  // The node has no trusted UTC clock in this configuration.
  // The receiving gateway must replace null with its UTC timestamp.
  doc["timestamp"] = nullptr;

  doc["device_id"] = DEVICE_ID;
  doc["group_code"] = GROUP_CODE;
  doc["zone"] = DEVICE_ZONE;
  doc["protocol"] = "lora";

  JsonObject metrics = doc.createNestedObject("metrics");

  // MQ-2 requires calibration before reporting a meaningful ppm value.
  metrics["gas_ppm"] = nullptr;
  metrics["gas_adc_raw"] = mq2AnalogValue;

  metrics["smoke_detected"] =
      (mq2DigitalState == SMOKE_TRIGGER_LEVEL);

  if (dhtReadingValid) {
    metrics["temperature_c"] = temperature;
    metrics["humidity_pct"] = humidity;
  } else {
    metrics["temperature_c"] = nullptr;
    metrics["humidity_pct"] = nullptr;
  }

  metrics["water_leak_detected"] =
      (waterValue >= WATER_LEAK_THRESHOLD);

  JsonObject status = doc.createNestedObject("status");
  status["uptime_ms"] = millis();
  status["packet_counter"] = ++packetCounter;

  // RSSI and SNR are measured by the receiver, not this transmitter.
  // The gateway will add rssi_dbm and snr_db after reception.

  char payload[512];

  size_t payloadLength = serializeJson(doc, payload, sizeof(payload));

  if (payloadLength == 0 || payloadLength >= sizeof(payload)) {
    Serial.println("ERROR: Telemetry JSON serialization failed");
    return;
  }

  Serial.println("\n--- LoRa Transmission ---");
  Serial.print("Payload: ");
  Serial.println(payload);

  if (LoRa.beginPacket() == 0) {
    Serial.println("ERROR: LoRa transmitter is busy");
    return;
  }

  LoRa.write(
    reinterpret_cast<const uint8_t *>(payload),
    payloadLength
  );

  int result = LoRa.endPacket();

  if (result == 1) {
    Serial.println("LoRa packet transmitted successfully");
  } else {
    Serial.println("ERROR: LoRa packet transmission failed");
  }

  Serial.println("-------------------------");
}

// =====================================================
// SETUP
// =====================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  // This node communicates over LoRa; Wi-Fi is not needed.
  WiFi.mode(WIFI_OFF);

  pinMode(MQ2_DO_PIN, INPUT);

  analogReadResolution(12);

  dht.begin();

  // Initialize SPI with the selected pins.
  SPI.begin(
    LORA_SCK,
    LORA_MISO,
    LORA_MOSI,
    LORA_SS
  );

  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  Serial.println("\n==================================");
  Serial.println(" EnviroMesh - LoRa Sensor Node");
  Serial.print(" Device: ");
  Serial.println(DEVICE_ID);
  Serial.println("==================================");

  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("FATAL: LoRa initialization failed!");
    Serial.println("Check wiring, power, and module type.");

    while (true) {
      delay(1000);
    }
  }

  // Both transmitter and receiver must use matching settings.
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("LoRa initialized at 433 MHz");

  // Start first readings immediately.
  readFastSensors();
  readDHTSensor();
  sendLoRaTelemetry();

  unsigned long now = millis();
  previousSensorMillis = now;
  previousDHTMillis = now;
  previousLoRaMillis = now;
}

// =====================================================
// LOOP
// =====================================================
void loop() {
  unsigned long currentMillis = millis();

  if (currentMillis - previousSensorMillis >= SENSOR_INTERVAL) {
    previousSensorMillis = currentMillis;
    readFastSensors();
  }

  if (currentMillis - previousDHTMillis >= DHT_INTERVAL) {
    previousDHTMillis = currentMillis;
    readDHTSensor();
  }

  if (currentMillis - previousLoRaMillis >= LORA_INTERVAL) {
    previousLoRaMillis = currentMillis;
    sendLoRaTelemetry();
  }
}
