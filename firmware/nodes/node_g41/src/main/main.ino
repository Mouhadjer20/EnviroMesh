/* =============================================================================
# Firmware: ESP32 Node G41 (Group 4 - LoRa environmental node)
# Device ID: G41
# Sensors: MQ-2 (gas/smoke), DHT11 (temperature/humidity), Water leak sensor
# Communication: LoRa 433 MHz -> RPi (LoRa Gateway)
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
  StaticJsonDocument<384> doc;

  // device_id must be exactly 3 characters (e.g. "G41") to fit VARCHAR(3) in DB
  doc["device_id"] = DEVICE_ID;
  doc["zone"] = DEVICE_ZONE;
  doc["protocol"] = "lora";

  JsonObject metrics = doc.createNestedObject("metrics");

  // ADC and digital sensor values
  metrics["gas_adc_raw"] = mq2AnalogValue;
  metrics["smoke_detected"] = (mq2DigitalState == SMOKE_TRIGGER_LEVEL);

  // Send DHT readings formatted to 1 decimal place when valid
  if (dhtReadingValid) {
    metrics["temperature_c"] = serialized(String(temperature, 1));
    metrics["humidity_pct"] = serialized(String(humidity, 1));
  }

  metrics["water_leak_detected"] = (waterValue >= WATER_LEAK_THRESHOLD);

  JsonObject status = doc.createNestedObject("status");
  status["uptime_ms"] = millis();
  status["packet_counter"] = ++packetCounter;

  // SX1278 hardware FIFO is 256 bytes maximum.
  // Limiting payload buffer to 250 bytes guarantees complete packets are sent.
  char payload[250];

  size_t payloadLength = serializeJson(doc, payload, sizeof(payload));

  if (payloadLength == 0 || payloadLength >= sizeof(payload)) {
    Serial.println("ERROR: Telemetry JSON serialization failed or payload too large");
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
