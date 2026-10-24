/**
 * @file main.ino
 * @brief EnviroMesh G11 environmental sensor node.
 *
 * Reads DHT11, MQ-2 and water sensors on an ESP-WROOM-32 and transmits
 * telemetry as JSON over a Ra-02 LoRa radio.
 */

#include <Arduino.h>
#include <SPI.h>
#include <LoRa.h>
#include <DHT.h>
#include <WiFi.h>
#include <MQUnifiedsensor.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <math.h>
#include <stdio.h>

// ---- Device identity ----

constexpr char DEVICE_ID[] = "G11";
constexpr char GROUP_CODE[] = "G1";
constexpr char DEVICE_ZONE[] = "Sector_A_Warehouse";

// ---- Sensor and radio pin assignments (GPIO numbers) ----

constexpr int DHT_PIN = 4;
constexpr int MQ2_AO_PIN = 0;
constexpr int MQ2_DO_PIN = 2;
constexpr int WATER_PIN = 15;
constexpr int LORA_SS = 16;
constexpr int LORA_RST = 14;
constexpr int LORA_DIO0 = 26;
constexpr int LORA_SCK = 5;
constexpr int LORA_MISO = 19;
constexpr int LORA_MOSI = 32;
// ---- LoRa configuration ----

constexpr long LORA_FREQUENCY = 433000000L;  ///< Carrier frequency in Hz.

constexpr int LORA_SF = 7;
constexpr long LORA_BW = 125000L;            ///< Signal bandwidth in Hz.
constexpr int LORA_CR = 5;                   ///< Coding rate denominator: 4/5.
constexpr uint8_t LORA_SYNC_WORD = 0x12;
constexpr size_t LORA_MAX_PAYLOAD = 255;     ///< Maximum payload size in bytes.

// ---- Sampling and transmission intervals (milliseconds) ----

constexpr unsigned long SENSOR_INTERVAL = 1000;
constexpr unsigned long DHT_INTERVAL = 2000;
constexpr unsigned long LORA_INTERVAL = 2000;

// ---- Detection thresholds ----

constexpr int WATER_LEAK_THRESHOLD = 1500;   ///< Wet state begins at this ADC count.
constexpr int SMOKE_TRIGGER_LEVEL = HIGH;   ///< MQ-2 DO level interpreted as detection.
constexpr float GAS_ALERT_THRESHOLD_PPM = 2000.0f;  ///< LPG-equivalent alert threshold.

// ---- MQ-2 LPG model and analog front end ----

constexpr float MQ2_SUPPLY_V = 5.0f;
constexpr float MQ2_LOAD_KOHM = 10.0f;       ///< Module load resistor; verify the fitted value.
constexpr float MQ2_DIVIDER_TOP_KOHM = 10.0f;
constexpr float MQ2_DIVIDER_BOTTOM_KOHM = 15.0f;
constexpr float MQ2_DIVIDER_GAIN = MQ2_DIVIDER_BOTTOM_KOHM /
                                  (MQ2_DIVIDER_TOP_KOHM + MQ2_DIVIDER_BOTTOM_KOHM);
constexpr float MQ2_EFFECTIVE_LOAD_KOHM =
    MQ2_LOAD_KOHM * (MQ2_DIVIDER_TOP_KOHM + MQ2_DIVIDER_BOTTOM_KOHM) /
    (MQ2_LOAD_KOHM + MQ2_DIVIDER_TOP_KOHM + MQ2_DIVIDER_BOTTOM_KOHM);
constexpr float MQ2_LPG_A = 574.25f;
constexpr float MQ2_LPG_B = -2.222f;
constexpr float MQ2_CLEAN_AIR_RATIO = 9.83f;
constexpr float MQ2_MAX_PPM = 10000.0f;
constexpr unsigned long MQ2_WARMUP_MS = 180000;
constexpr uint8_t MQ2_VOLTAGE_SAMPLES = 8;
constexpr uint8_t MQ2_CALIBRATION_SAMPLES = 10;

/** @brief Stored clean-air reference and the electrical configuration used to obtain it. */
struct MQ2Calibration {
  uint32_t version;
  float r0;
  float supplyV;
  float loadKOhm;
  float dividerGain;
};

// ---- Sensor state and scheduler timestamps ----

DHT dht(DHT_PIN, DHT11);
MQUnifiedsensor mq2("ESP32", MQ2_SUPPLY_V, 12, MQ2_AO_PIN, "MQ-2");
Preferences mq2Preferences;
bool mq2StorageReady = false;
bool mq2Calibrated = false;
bool mq2WarmedUp = false;
unsigned long mq2StartedMs = 0;
float gasPpm = NAN;                         ///< LPG-equivalent estimate; NaN means unavailable.
unsigned long previousSensorMillis = 0;
unsigned long previousDHTMillis = 0;
unsigned long previousLoRaMillis = 0;
uint16_t seq = 0U;                          ///< Unsigned sequence; wraps from 65535 to zero.
int mq2DigitalState = LOW;
int waterValue = 0;
float temperature = NAN;                   ///< Last valid temperature in degrees Celsius.
float humidity = NAN;                      ///< Last valid relative humidity in percent.
bool dhtReadingValid = false;

// ---- MQ-2 voltage acquisition and calibration ----

/**
 * @brief Reconstruct the MQ-2 AO voltage from calibrated ESP32 ADC measurements.
 * @return Sensor-side voltage in volts, or NaN for an out-of-range ADC input.
 */
float readMQ2Voltage() {
  uint32_t totalMillivolts = 0;
  for (uint8_t i = 0; i < MQ2_VOLTAGE_SAMPLES; ++i) {
    const uint32_t millivolts = analogReadMilliVolts(MQ2_AO_PIN);
    if (millivolts < 100 || millivolts >= 3100) {
      return NAN;
    }
    totalMillivolts += millivolts;
    delay(2);
  }
  const float voltage = totalMillivolts /
      (1000.0f * MQ2_VOLTAGE_SAMPLES * MQ2_DIVIDER_GAIN);
  return voltage > 0.0f && voltage < MQ2_SUPPLY_V ? voltage : NAN;
}

/** @brief Configure the LPG regression and restore a compatible saved R0 reference. */
void initializeMQ2() {
  analogSetPinAttenuation(MQ2_AO_PIN, ADC_11db);
  mq2.init();
  mq2.setRegressionMethod(1);
  mq2.setA(MQ2_LPG_A);
  mq2.setB(MQ2_LPG_B);
  mq2.setRL(MQ2_EFFECTIVE_LOAD_KOHM);
  mq2StartedMs = millis();
  mq2StorageReady = mq2Preferences.begin("enviromesh-mq2", false);
  MQ2Calibration saved = {};
  if (mq2StorageReady &&
      mq2Preferences.getBytesLength("calibration") == sizeof(saved) &&
      mq2Preferences.getBytes("calibration", &saved, sizeof(saved)) == sizeof(saved) &&
      saved.version == 1 && isfinite(saved.r0) && saved.r0 > 0.0f &&
      saved.supplyV == MQ2_SUPPLY_V && saved.loadKOhm == MQ2_EFFECTIVE_LOAD_KOHM &&
      saved.dividerGain == MQ2_DIVIDER_GAIN) {
    mq2.setR0(saved.r0);
    mq2Calibrated = true;
    Serial.printf("MQ-2 calibration loaded: R0 = %.4f kOhm.\n", saved.r0);
  }
  Serial.println("MQ-2 model: LPG-equivalent ppm. Startup warm-up: 180 seconds.");
  Serial.println("After sensor conditioning, send C in clean air to calibrate and save R0.");
}

/**
 * @brief Calibrate R0 in clean air on an explicit serial command.
 * @details Acquisition pauses for approximately two seconds. A failed calibration
 *          preserves the previous reference; successful calibration is saved in NVS.
 */
void calibrateMQ2() {
  if (!mq2WarmedUp) {
    Serial.println("MQ-2 is warming up; calibration is not available yet.");
    return;
  }
  Serial.println("Calibrating MQ-2 in clean air...");
  float sumR0 = 0.0f;
  for (uint8_t i = 0; i < MQ2_CALIBRATION_SAMPLES; ++i) {
    const float voltage = readMQ2Voltage();
    if (!isfinite(voltage)) {
      Serial.println("ERROR: Invalid MQ-2 voltage; calibration cancelled.");
      return;
    }
    mq2.externalADCUpdate(voltage);
    const float candidateR0 = mq2.calibrate(MQ2_CLEAN_AIR_RATIO);
    if (!isfinite(candidateR0) || candidateR0 <= 0.0f) {
      Serial.println("ERROR: Invalid MQ-2 reference; calibration cancelled.");
      return;
    }
    sumR0 += candidateR0;
    delay(200);
  }
  const float r0 = sumR0 / MQ2_CALIBRATION_SAMPLES;
  const MQ2Calibration saved = {1, r0, MQ2_SUPPLY_V,
                                MQ2_EFFECTIVE_LOAD_KOHM, MQ2_DIVIDER_GAIN};
  mq2.setR0(r0);
  mq2Calibrated = true;
  gasPpm = NAN;
  if (!mq2StorageReady ||
      mq2Preferences.putBytes("calibration", &saved, sizeof(saved)) != sizeof(saved)) {
    Serial.println("ERROR: Calibration active but not saved; recalibrate after restart.");
  } else {
    Serial.printf("MQ-2 calibration saved: R0 = %.4f kOhm.\n", r0);
  }
}

/** @brief Update the warm-up state and process the clean-air calibration command. */
void handleMQ2Calibration() {
  if (!mq2WarmedUp && millis() - mq2StartedMs >= MQ2_WARMUP_MS) {
    mq2WarmedUp = true;
    Serial.println(mq2Calibrated ? "MQ-2 warm-up complete; saved calibration active."
                               : "MQ-2 warm-up complete; send C in clean air to calibrate.");
  }
  if (Serial.available() > 0) {
    const int command = Serial.read();
    if (command == 'C' || command == 'c') {
      calibrateMQ2();
    }
  }
}

// ---- Sensor acquisition ----

/**
 * @brief Update LPG-equivalent concentration, digital gas detection and water ADC.
 * @details MQUnifiedsensor consumes the reconstructed sensor-side voltage.
 *          Gas concentration remains unavailable during warm-up or without R0.
 */
void readFastSensors() {
  mq2DigitalState = digitalRead(MQ2_DO_PIN);
  waterValue = analogRead(WATER_PIN);
  gasPpm = NAN;
  if (mq2WarmedUp && mq2Calibrated) {
    const float voltage = readMQ2Voltage();
    if (isfinite(voltage)) {
      mq2.externalADCUpdate(voltage);
      const float estimate = mq2.readSensor();
      if (isfinite(estimate) && estimate >= 0.0f && estimate <= MQ2_MAX_PPM) {
        gasPpm = estimate;
      } else {
        Serial.println("ERROR: MQ-2 concentration outside the supported model range.");
      }
    } else {
      Serial.println("ERROR: MQ-2 voltage outside the ADC measurement range.");
    }
  }
  Serial.printf("MQ-2 DO : %d | Water ADC : %d\n", mq2DigitalState, waterValue);
}

/**
 * @brief Read DHT11 temperature and relative humidity.
 * @details Marks the reading invalid if either measurement is NaN.
 *          Invalid readings are transmitted as JSON null values.
 */
void readDHTSensor() {
  const float newTemperature = dht.readTemperature();
  const float newHumidity = dht.readHumidity();
  dhtReadingValid = !isnan(newTemperature) && !isnan(newHumidity);
  if (!dhtReadingValid) {
    Serial.println("ERROR: Failed to read DHT11.");
    return;
  }
  temperature = newTemperature;
  humidity = newHumidity;
}

// ---- Telemetry serialization and transmission ----

/**
 * @brief Serialize current readings and transmit one LoRa packet.
 * @details The gateway supplies the UTC timestamp. gas_ppm is an LPG-equivalent
 *          estimate, or null while warming up, uncalibrated or invalid.
 *          Oversized payloads are rejected before transmission.
 *          Transmission completion does not acknowledge remote reception.
 *          The unsigned 16-bit sequence wraps naturally and resets on reboot.
 */
void sendTelemetry() {
  char temperatureJson[16] = "null";
  char humidityJson[16] = "null";
  char gasJson[16] = "null";
  if (isfinite(gasPpm)) {
    snprintf(gasJson, sizeof(gasJson), "%.1f", gasPpm);
  }
  if (dhtReadingValid) {
    snprintf(temperatureJson, sizeof(temperatureJson), "%.1f", temperature);
    snprintf(humidityJson, sizeof(humidityJson), "%.1f", humidity);
  }

  const char *waterLeakJson = waterValue >= WATER_LEAK_THRESHOLD ? "true" : "false";
  const char *smokeJson = mq2DigitalState == SMOKE_TRIGGER_LEVEL ? "true" : "false";
  const char *gasAlertJson = !isfinite(gasPpm) ? "null"
      : (gasPpm >= GAS_ALERT_THRESHOLD_PPM ? "true" : "false");

  JsonDocument doc;
  doc["timestamp"] = nullptr;
  doc["device_id"] = DEVICE_ID;
  doc["group_code"] = GROUP_CODE;
  doc["zone"] = DEVICE_ZONE;
  doc["protocol"] = "lora";

  JsonObject metrics = doc["metrics"].to<JsonObject>();
  // Insert internally formatted numbers/nulls to preserve one-decimal precision.
  metrics["gas_ppm"] = serialized(gasJson);
  if (isfinite(gasPpm)) {
    metrics["gas_alert"] = gasPpm >= GAS_ALERT_THRESHOLD_PPM;
  } else {
    metrics["gas_alert"] = nullptr;
  }
  metrics["smoke_detected"] = mq2DigitalState == SMOKE_TRIGGER_LEVEL;
  metrics["temperature_c"] = serialized(temperatureJson);
  metrics["humidity_pct"] = serialized(humidityJson);
  metrics["water_leak_detected"] = waterValue >= WATER_LEAK_THRESHOLD;
  doc["seq"] = seq;

  Serial.println("\n============== G11 READINGS ==============");
  Serial.printf("Sequence        : %u\n", static_cast<unsigned int>(seq));
  Serial.printf("Temperature (C) : %s\n", temperatureJson);
  Serial.printf("Humidity (%%)    : %s\n", humidityJson);
  Serial.printf("LPG equiv. ppm  : %s\n", gasJson);
  Serial.printf("Gas alert       : %s (threshold: %.0f ppm)\n",
                gasAlertJson, GAS_ALERT_THRESHOLD_PPM);
  Serial.printf("Smoke detected  : %s\n", smokeJson);
  Serial.printf("Water raw ADC   : %d\n", waterValue);
  Serial.printf("Water leak      : %s\n", waterLeakJson);

  const size_t length = measureJson(doc);
  if (doc.overflowed() || length == 0 || length > LORA_MAX_PAYLOAD) {
    Serial.println("ERROR: JSON allocation failed or payload too large; packet not sent.");
    return;
  }

  // serializeJson produces compact JSON; the buffer includes its string terminator.
  char payload[LORA_MAX_PAYLOAD + 1];
  if (serializeJson(doc, payload, sizeof(payload)) != length) {
    Serial.println("ERROR: Incomplete JSON serialization; packet not sent.");
    return;
  }

  Serial.printf("JSON (%u/255 bytes) : %s\n", static_cast<unsigned int>(length), payload);
  if (LoRa.beginPacket() == 0) {
    Serial.println("ERROR: LoRa transmitter unavailable.");
    return;
  }

  const size_t written = LoRa.write(
      reinterpret_cast<const uint8_t *>(payload), static_cast<size_t>(length));
  if (written != static_cast<size_t>(length)) {
    LoRa.idle();
    Serial.println("ERROR: Incomplete write; transmission cancelled.");
    return;
  }

  const int txResult = LoRa.endPacket();
  ++seq;
  if (txResult == 1) {
    Serial.println("Transmission complete (reception not confirmed).");
  } else {
    Serial.println("ERROR: LoRa transmission failed.");
  }
}

// ---- Arduino entry points ----

/**
 * @brief Initialize serial output, sensors and the LoRa radio.
 * @details Stops initialization if an analog pin is unsupported or the radio
 *          cannot start. Sends an initial sample before starting the scheduler.
 */
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("Starting EnviroMesh G1 / G11");

  if (digitalPinToAnalogChannel(MQ2_AO_PIN) < 0 ||
      digitalPinToAnalogChannel(WATER_PIN) < 0) {
    Serial.println("ERROR: MQ-2 AO or water GPIO does not support ADC on this board.");
    while (true) {
      delay(1000);
    }
  }

  // GPIO0 and GPIO15 use ADC2, which is shared with the Wi-Fi driver.
  WiFi.mode(WIFI_OFF);
  analogReadResolution(12);
  pinMode(MQ2_DO_PIN, INPUT);
  initializeMQ2();
  dht.begin();

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  if (!LoRa.begin(LORA_FREQUENCY)) {
    Serial.println("ERROR: LoRa initialization failed. Check wiring.");
    while (true) {
      delay(1000);
    }
  }

  LoRa.setSpreadingFactor(LORA_SF);
  LoRa.setSignalBandwidth(LORA_BW);
  LoRa.setCodingRate4(LORA_CR);
  LoRa.setSyncWord(LORA_SYNC_WORD);
  LoRa.setPreambleLength(8);
  LoRa.enableCrc();

  readFastSensors();
  readDHTSensor();
  sendTelemetry();
  const unsigned long now = millis();
  previousSensorMillis = now;
  previousDHTMillis = now;
  previousLoRaMillis = now;
}

/**
 * @brief Schedule sensor acquisition and periodic telemetry transmission.
 */
void loop() {
  handleMQ2Calibration();
  const unsigned long now = millis();
  // Unsigned elapsed-time subtraction supports millis() counter rollover.
  if (now - previousSensorMillis >= SENSOR_INTERVAL) {
    previousSensorMillis = now;
    readFastSensors();
  }
  if (now - previousDHTMillis >= DHT_INTERVAL) {
    previousDHTMillis = now;
    readDHTSensor();
  }
  if (now - previousLoRaMillis >= LORA_INTERVAL) {
    previousLoRaMillis = now;
    sendTelemetry();
  }
  delay(10);
}
