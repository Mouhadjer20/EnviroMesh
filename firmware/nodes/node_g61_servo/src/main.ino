/**
 * @file main.ino
 * @brief EnviroMesh G61 environmental and servo node.
 *
 * Reads MQ-2, DHT11, water and PIR sensors and drives an SG90 servo on an
 * ESP32. Telemetry is built as JSON, timestamped in UTC via NTP, and published
 * over Wi-Fi to an MQTT broker on enviromesh/devices/G61/telemetry..
 * Copy secrets.h.example to secrets.h and fill it in before compiling.
 */

#include <WiFi.h>
#include <time.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>   // PubSubClient (Nick O'Leary)    

#include "secrets.h"        // WIFI_SSID, WIFI_PASSWORD + MQTT

#if MQTT_USE_TLS
  #include <WiFiClientSecure.h>
#endif

// --- Pin Definitions ---
const int PIN_MQ2 = 34;          // Analog input for MQ-2 (AO)
const int PIN_DHT = 4;           // Digital data pin for DHT11
const int PIN_WATER = 35;        // Analog input for Water Leak Sensor (S)
const int PIN_PIR = 13;          // Digital output pin for PIR motion sensor
const int PIN_SERVO = 18;        // PWM output signal for SG90 Servo

// --- EnviroMesh Configuration (mandated values) ---
const char* DEVICE_ID  = "G61";
const char* GROUP_CODE = "G6";
const char* ZONE       = "Sector_A_Valve";
const char* PROTOCOL   = "wifi_mqtt";

// Policy for unavailable/invalid data:
//   1 = the field is present with a null value
//   0 = the field is omitted
// telemetry_validator.py calls float(value) on known metrics, so null would raise
// a TypeError there: omission (0) is the safe choice.
#define UNAVAILABLE_AS_NULL 0

// Set to 0 to disable NTP (the timestamp is then always unavailable)
#define ENABLE_NTP 1

// --- Timing configuration (milliseconds) ---
const unsigned long SENSOR_INTERVAL_MS   = 2000;    // sensor read + serial report
const unsigned long JSON_INTERVAL_MS     = 10000;   // JSON build + MQTT publish + status report
const unsigned long WIFI_RETRY_MS        = 10000;   // delay between Wi-Fi reconnection attempts
const unsigned long STARTUP_NET_WAIT_MS  = 15000;   // max wait for Wi-Fi (+ NTP) at boot
// --- PIR / motion settings ---
const unsigned long PIR_POLL_MS               = 50;    // PIR is read every 50 ms (was every 2 s)
const unsigned long MOTION_MIN_PUBLISH_GAP_MS = 2000;  // min gap between two event-triggered publications
// --- DHT11 settings ---
const int DHT_MAX_FAILS = 3;   // consecutive failed reads before the DHT11 data is declared invalid
// --- MQ-2 calibration settings ---
const unsigned long MQ2_WARMUP_MS        = 60000;   // heater warm-up before calibrating (longer = more stable)
const int           MQ2_OVERSAMPLE       = 16;      // ADC reads averaged per sample (reduces ESP32 ADC noise)
const int           MQ2_SPREAD_MAX       = 60;      // max (max-min) of averaged samples accepted as "stable" (ADC units)
const int           MQ2_CAL_ATTEMPTS     = 3;       // attempts at boot
const unsigned long MQ2_RECAL_INTERVAL_MS = 60000;  // retry interval while calibration is invalid
const unsigned long MQTT_RETRY_MIN_MS    = 5000;    // first MQTT retry delay
const unsigned long MQTT_RETRY_MAX_MS    = 60000;   // retry delay cap (exponential backoff)

// --- NTP configuration (UTC, no offset, no daylight saving) ---
const char* NTP_SERVER_1 = "pool.ntp.org";
const char* NTP_SERVER_2 = "time.google.com";

// Any time before 2026-01-01 00:00:00 UTC is considered unsynchronized
const time_t MIN_VALID_EPOCH = 1767225600;

const size_t JSON_BUF_SIZE = 512;   // serialized telemetry (about 330 bytes in practice)

const uint16_t MQTT_BUF_SIZE = 640; // PubSubClient packet buffer (topic + header + payload)

// Optional secrets.h settings with safe defaults
#ifndef MQTT_USER
  #define MQTT_USER ""
#endif
#ifndef MQTT_PASSWORD
  #define MQTT_PASSWORD ""
#endif

// --- DHT11 Configuration ---
#define DHTTYPE DHT11
DHT dht(PIN_DHT, DHTTYPE);

// --- Servo Instance ---
Servo myservo;

// --- Network objects ---
#if MQTT_USE_TLS
  WiFiClientSecure netClient;
#else
  WiFiClient netClient;
#endif
PubSubClient mqtt(netClient);

// --- Data Structure for Sensor Readings ---
struct Measurements {
    // DHT11
    float temperature;
    float humidity;
    bool dhtValid;

    // Water Sensor
    int waterRaw;
    int waterDryBaseline;
    bool waterLeakDetected;
    bool waterCalibrationValid;

    // MQ-2 Sensor
    int mq2Raw;
    int mq2Baseline;
    bool mq2Stable;
    bool smokeDetected;
    bool mq2CalibrationValid;

    // PIR Sensor
    bool motionDetected;

    // Servo SG90
    int targetAngle;
    int lastCommandedAngle;
    bool servoCommanded;   // true once a command has been sent
};

Measurements currentMeasurements;

// --- Connectivity state ---
bool wifiWasConnected = false;
unsigned long lastWifiAttemptMs = 0;
unsigned long lastSensorMs = 0;
unsigned long lastJsonMs = 0;
unsigned long mqttRetryMs = MQTT_RETRY_MIN_MS;
unsigned long lastMqttAttemptMs = 0;
bool mqttAttempted = false;
unsigned long publishCount = 0;
unsigned long publishFailCount = 0;
unsigned long lastMq2CalMs = 0;
int dhtFailCount = 0;
unsigned long lastPirPollMs = 0;
unsigned long lastMotionPublishMs = 0;
bool lastPirState = false;
bool motionLatched = false;   // true if motion was seen since the last JSON message was built

// Reused JSON document (avoids repeated allocation of the document object)
JsonDocument telemetryDoc;

// --- Function Prototypes: sensors (unchanged from previous phases) ---
void initializeSensors();
bool calibrateMQ2(int samples = 50);
bool calibrateWaterSensor();
int readMQ2();
int readMQ2Averaged();
void warmUpMQ2();
void maintainMQ2Calibration();
bool detectSmoke(int currentVal, int baseline);
bool readDHT11(float &temp, float &hum);
int readWaterSensor();
bool detectWaterLeak(int currentVal, int baseline);
bool readPIR();
void pollMotion();
void controlServo(int angle);
void collectMeasurements();
void displayMeasurements();
// --- Function Prototypes: JSON ---
bool getUtcTimestamp(char *buf, size_t len);
void markUnavailable(JsonObject obj, const char *key);
size_t buildTelemetryJSON(char *out, size_t outSize);
bool validateJsonMessage(const char *json);
void jsonCycle();
// --- Function Prototypes: connectivity ---
void connectWiFi();
void maintainWiFi();
void initializeNTP();
bool isClockSynced();
void waitForNetworkAtStartup();
void displayStatus();
// --- Function Prototypes: MQTT ---
bool mqttConfigValid();
void initializeMQTT();
bool connectMQTT();
void reconnectMQTT();
bool publishTelemetry(const char *json, size_t len);

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n[EnviroMesh] System Initialization...");

    // Initialize pins and sensor modules
    initializeSensors();

    // Startup calibration sequence (unchanged)
    warmUpMQ2();
    Serial.println("[Calibration] Starting MQ-2 calibration (ambient air)...");
    for (int attempt = 1; attempt <= MQ2_CAL_ATTEMPTS && !currentMeasurements.mq2CalibrationValid; attempt++) {
        Serial.printf("[Calibration] MQ-2 attempt %d/%d\n", attempt, MQ2_CAL_ATTEMPTS);
        currentMeasurements.mq2CalibrationValid = calibrateMQ2();
        if (!currentMeasurements.mq2CalibrationValid && attempt < MQ2_CAL_ATTEMPTS) delay(5000);
    }
    lastMq2CalMs = millis();

    Serial.println("[Calibration] Starting Water Sensor calibration (dry state)...");
    currentMeasurements.waterCalibrationValid = calibrateWaterSensor();

    // Wi-Fi (bounded wait; the loop keeps retrying afterwards)
    initializeMQTT();
    connectWiFi();
    waitForNetworkAtStartup();

    // First sensor snapshot
    collectMeasurements();

    Serial.println("[System] Initialization complete. Entering main loop.\n");
}

void loop() {
    unsigned long now = millis();

    // Keep Wi-Fi alive without blocking
    maintainWiFi();
    reconnectMQTT();
    mqtt.loop();
    maintainMQ2Calibration();
    pollMotion();   // fast PIR polling + immediate servo reaction + event-triggered publication

    // Periodic sensor acquisition and serial report
    if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
        lastSensorMs = now;
        collectMeasurements();
        displayMeasurements();
    }

    // Periodic JSON build and status report
    if (now - lastJsonMs >= JSON_INTERVAL_MS) {
        lastJsonMs = now;
        displayStatus();
        jsonCycle();
    }
}

// ==========================================
// INITIALIZATION AND CALIBRATION FUNCTIONS
// ==========================================

void initializeSensors() {
    pinMode(PIN_MQ2, INPUT);
    pinMode(PIN_WATER, INPUT);
    pinMode(PIN_PIR, INPUT);

    dht.begin();
    delay(1500);   // DHT11 needs about 1 s after power-up before the first valid read

    // Servo configuration
    myservo.setPeriodHertz(50); // Standard 50Hz servo signal
    myservo.attach(PIN_SERVO, 500, 2400);
    controlServo(0); // Initial position set to 0 degrees
}

// Averages several ADC reads to reduce the ESP32 ADC noise.
int readMQ2Averaged() {
    long sum = 0;
    for (int i = 0; i < MQ2_OVERSAMPLE; i++) {
        sum += analogRead(PIN_MQ2);
        delayMicroseconds(200);
    }
    return (int)(sum / MQ2_OVERSAMPLE);
}

// The MQ-2 heater needs time before its output settles. Calibrating right after power-up
// gives a drifting signal, so we wait first. Progress is printed every 10 s.
void warmUpMQ2() {
    Serial.printf("[Calibration] MQ-2 warm-up for %lu s (keep the sensor in clean air)...\n", MQ2_WARMUP_MS / 1000);
    unsigned long start = millis();
    unsigned long lastPrint = 0;
    while (millis() - start < MQ2_WARMUP_MS) {
        if (millis() - lastPrint >= 10000) {
            lastPrint = millis();
            Serial.printf("   warm-up %lu s / %lu s, MQ-2 raw = %d\n",
                          (millis() - start) / 1000, MQ2_WARMUP_MS / 1000, readMQ2Averaged());
        }
        delay(100);
    }
}

bool calibrateMQ2(int samples) {
    long sum = 0;
    int minVal = 4095;
    int maxVal = 0;

    // Collect samples to establish baseline readings (each sample is an average of several reads)
    for (int i = 0; i < samples; i++) {
        int val = readMQ2Averaged();
        sum += val;
        if (val < minVal) minVal = val;
        if (val > maxVal) maxVal = val;
        delay(50);
    }

    int average = sum / samples;
    int spread = maxVal - minVal;

    currentMeasurements.mq2Baseline = average;

    Serial.printf("   MQ-2 calibration data: avg=%d, min=%d, max=%d, spread=%d (limit %d)\n",
                  average, minVal, maxVal, spread, MQ2_SPREAD_MAX);

    // A reading stuck at the ADC limits means the sensor is not wired correctly
    if (average < 20 || average > 4000) {
        currentMeasurements.mq2Stable = false;
        Serial.println("-> MQ-2 Warning: value at the ADC limit. Check wiring (AO to GPIO34, VCC 5V, GND) and the voltage divider.");
        return false;
    }

    // Stability check: max spread must not exceed the tolerance
    if (spread < MQ2_SPREAD_MAX) {
        currentMeasurements.mq2Stable = true;
        Serial.printf("-> MQ-2 Calibrated successfully. Baseline (ADC): %d (Stability OK)\n", average);
        return true;
    } else {
        currentMeasurements.mq2Stable = false;
        Serial.println("-> MQ-2 Warning: unstable signal during calibration (warm-up too short, floating AO pin or noisy supply).");
        return false;
    }
}

// While the calibration is invalid, retry every MQ2_RECAL_INTERVAL_MS (the sensor keeps warming up).
void maintainMQ2Calibration() {
    if (currentMeasurements.mq2CalibrationValid) return;
    if (millis() - lastMq2CalMs < MQ2_RECAL_INTERVAL_MS) return;
    lastMq2CalMs = millis();
    Serial.println("[Calibration] MQ-2 retry (previous calibration invalid)...");
    currentMeasurements.mq2CalibrationValid = calibrateMQ2();
}

bool calibrateWaterSensor() {
    // Acquire baseline reading under dry condition
    long sum = 0;
    int samples = 20;
    for (int i = 0; i < samples; i++) {
        sum += analogRead(PIN_WATER);
        delay(20);
    }
    currentMeasurements.waterDryBaseline = sum / samples;
    Serial.printf("-> Water Sensor Calibrated. Dry Baseline (ADC): %d\n", currentMeasurements.waterDryBaseline);
    return true;
}

// ==========================================
// READING AND PROCESSING FUNCTIONS
// ==========================================

int readMQ2() {
    currentMeasurements.mq2Raw = analogRead(PIN_MQ2);
    return currentMeasurements.mq2Raw;
}

bool detectSmoke(int currentVal, int baseline) {
    // Relative detection threshold: triggers when value exceeds baseline by > 250 ADC units
    const int smokeDeltaThreshold = 250;
    if (!currentMeasurements.mq2CalibrationValid) return false;

    return (currentVal - baseline) > smokeDeltaThreshold;
}

bool readDHT11(float &temp, float &hum) {
    float h = dht.readHumidity();
    float t = dht.readTemperature(); // Celsius

    if (isnan(h) || isnan(t)) {
        return false; // Failed to read from sensor
    }
    if (h < 0.0f || h > 100.0f || t < -40.0f || t > 85.0f) {
        return false; // Implausible value (corrupted frame)
    }
    temp = t;
    hum = h;
    return true;
}

int readWaterSensor() {
    currentMeasurements.waterRaw = analogRead(PIN_WATER);
    return currentMeasurements.waterRaw;
}

bool detectWaterLeak(int currentVal, int baseline) {
    if (!currentMeasurements.waterCalibrationValid) return false;

    // Resistive sensor conductivity increases when wet, raising the ADC reading.
    // Trigger threshold set to +200 ADC units relative to dry state.
    const int waterDeltaThreshold = 200;
    return (currentVal - baseline) > waterDeltaThreshold;
}

bool readPIR() {
    // PIR sensor outputs HIGH (1) when motion is detected, LOW (0) otherwise
    return digitalRead(PIN_PIR) == HIGH;
}

// Called on every loop iteration but runs every PIR_POLL_MS.
// - updates the motion state quickly (a short pulse is no longer missed between two 2 s reports)
// - moves the servo immediately on a motion edge
// - latches motion so the next JSON reports it even if the PIR returned to LOW before publication
// - publishes right away on a motion start (rate limited), instead of waiting for the 10 s cycle
void pollMotion() {
    unsigned long now = millis();
    if (now - lastPirPollMs < PIR_POLL_MS) return;
    lastPirPollMs = now;

    bool state = readPIR();
    currentMeasurements.motionDetected = state;
    if (state) motionLatched = true;

    if (state != lastPirState) {
        lastPirState = state;
        Serial.printf("[PIR] Motion %s\n", state ? "STARTED" : "ended");
        controlServo(state ? 90 : 0);   // 90 deg upon motion, 0 deg otherwise (command only, position not verified)

        if (state && (now - lastMotionPublishMs >= MOTION_MIN_PUBLISH_GAP_MS)) {
            lastMotionPublishMs = now;
            lastJsonMs = now;   // restart the periodic cycle so we do not publish twice in a row
            jsonCycle();
        }
    }
}

void controlServo(int angle) {
    // Constrain target angle between 0 and 180 degrees
    if (angle < 0) angle = 0;
    if (angle > 180) angle = 180;

    currentMeasurements.targetAngle = angle;
    myservo.write(angle);
    currentMeasurements.lastCommandedAngle = angle; // Store last commanded angle
    currentMeasurements.servoCommanded = true;      // Command sent; actual position NOT verified
}

// ==========================================
// DATA COLLECTION AND DISPLAY
// ==========================================

void collectMeasurements() {
    // 1. DHT11 Readout
    float t = 0, h = 0;
    if (readDHT11(t, h)) {
        currentMeasurements.temperature = t;
        currentMeasurements.humidity = h;
        currentMeasurements.dhtValid = true;
        dhtFailCount = 0;
    } else {
        dhtFailCount++;
        Serial.printf("[DHT11] Read failed (%d consecutive)\n", dhtFailCount);
        // One or two isolated failures keep the previous (recent) value; after DHT_MAX_FAILS it becomes invalid
        if (dhtFailCount >= DHT_MAX_FAILS) currentMeasurements.dhtValid = false;
    }

    // 2. MQ-2 Readout
    int mq2Val = readMQ2();
    currentMeasurements.smokeDetected = detectSmoke(mq2Val, currentMeasurements.mq2Baseline);

    // 3. Water Sensor Readout
    int waterVal = readWaterSensor();
    currentMeasurements.waterLeakDetected = detectWaterLeak(waterVal, currentMeasurements.waterDryBaseline);

     // 4. PIR and servo: handled continuously by pollMotion() (called from loop())
}

void displayMeasurements() {
    Serial.println("----------------------------------------");
    Serial.println("[EnviroMesh Sensor Report]");

    // Temperature & Humidity
    if (currentMeasurements.dhtValid) {
        Serial.printf("- Temperature : %.1f °C\n", currentMeasurements.temperature);
        Serial.printf("- Humidity    : %.1f %%\n", currentMeasurements.humidity);
    } else {
        Serial.printf("- DHT11       : Read error or invalid sensor data (%d consecutive failures; check DATA on GPIO4, VCC 3V3, GND)\n", dhtFailCount);
    }

    // Motion Detection (PIR)
    Serial.printf("- Motion      : %s\n", currentMeasurements.motionDetected ? "Detected" : "Not Detected");

    // Water Leak
    if (currentMeasurements.waterCalibrationValid) {
        Serial.printf("- Water Leak  : %s (Raw: %d / Dry Ref: %d)\n",
            currentMeasurements.waterLeakDetected ? "DETECTED" : "Not Detected",
            currentMeasurements.waterRaw,
            currentMeasurements.waterDryBaseline);
    } else {
        Serial.println("- Water Leak  : Invalid Calibration");
    }

    // MQ-2 Gas / Smoke
    if (currentMeasurements.mq2CalibrationValid) {
        Serial.printf("- MQ-2 (Gas)  : Ref=%d, Raw=%d, Stability=%s, Smoke=%s\n",
            currentMeasurements.mq2Baseline,
            currentMeasurements.mq2Raw,
            currentMeasurements.mq2Stable ? "Stable" : "Unstable",
            currentMeasurements.smokeDetected ? "SMOKE ALARM" : "Normal");
    } else {
        Serial.printf("- MQ-2 (Gas)  : Calibration Unavailable (Raw=%d, retrying)\n", currentMeasurements.mq2Raw);
    }

    // Servo Motor Status
    Serial.printf("- SG90 Servo  : Target Angle = %d°, Last Commanded = %d°\n",
        currentMeasurements.targetAngle,
        currentMeasurements.lastCommandedAngle);
}

// ==========================================
// WI-FI
// ==========================================

// Starts the connection and returns immediately (non-blocking).
// The password is never printed.
void connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastWifiAttemptMs = millis();
    Serial.printf("[WiFi] Connecting to SSID \"%s\"...\n", WIFI_SSID);
}

// Called every loop: logs state changes, restarts NTP after (re)connection,
// and retries periodically while disconnected.
void maintainWiFi() {
    bool connected = (WiFi.status() == WL_CONNECTED);

    if (connected && !wifiWasConnected) {
        Serial.printf("[WiFi] Connected. IP: %s, RSSI: %d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        initializeNTP();   // (re)start SNTP: forces a fresh synchronization
    } else if (!connected && wifiWasConnected) {
        Serial.println("[WiFi] Connection lost. Sensors keep running; retrying...");
    }
    wifiWasConnected = connected;

    if (!connected && (millis() - lastWifiAttemptMs >= WIFI_RETRY_MS)) {
        lastWifiAttemptMs = millis();
        Serial.println("[WiFi] Reconnection attempt...");
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
}

// ==========================================
// NTP / TIMESTAMP
// ==========================================

// UTC with no offset and no daylight saving. SNTP then re-syncs periodically on its own.
void initializeNTP() {
#if ENABLE_NTP
    configTime(0, 0, NTP_SERVER_1, NTP_SERVER_2);
    setenv("TZ", "UTC0", 1);
    tzset();
    Serial.printf("[NTP] Synchronization requested (%s, %s)\n", NTP_SERVER_1, NTP_SERVER_2);
#endif
}

// True once the system time is a plausible, synchronized date.
bool isClockSynced() {
    return time(nullptr) >= MIN_VALID_EPOCH;
}

// Writes the ISO 8601 UTC time into buf. Returns false if the time is not reliable
// (no NTP sync: time() then returns ~0, i.e. 1970).
bool getUtcTimestamp(char *buf, size_t len) {
    time_t now = time(nullptr);
    if (now < MIN_VALID_EPOCH) return false;
    struct tm tmUtc;
    gmtime_r(&now, &tmUtc);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tmUtc);
    return true;
}

// Bounded wait at boot. If the network is slow, the loop keeps retrying.
void waitForNetworkAtStartup() {
    Serial.println("[System] Waiting for Wi-Fi (and NTP) (bounded)...");
    unsigned long start = millis();
    while (millis() - start < STARTUP_NET_WAIT_MS) {
        maintainWiFi();
        if (wifiWasConnected && (!ENABLE_NTP || isClockSynced())) break;
        delay(250);
    }
    if (!wifiWasConnected) {
        Serial.println("[System] Wi-Fi not connected yet; continuing, will keep retrying.");
    } else if (ENABLE_NTP && !isClockSynced()) {
        Serial.println("[System] Clock not synchronized yet; timestamp will be omitted until it is.");
    } else if (ENABLE_NTP) {
        char ts[25];
        getUtcTimestamp(ts, sizeof(ts));
        Serial.printf("[NTP] Clock synchronized: %s\n", ts);
    }
}

// ==========================================
// MQTT
// ==========================================

static bool isPlaceholder(const char *s) {
    return s == nullptr || s[0] == '\0' || strstr(s, "REPLACE_ME") != nullptr;
}

// Broker and topic must have been set by the user in secrets.h.
bool mqttConfigValid() {
    return !isPlaceholder(MQTT_HOST) && !isPlaceholder(MQTT_TOPIC);
}

void initializeMQTT() {
    if (!mqttConfigValid()) {
        Serial.println("[MQTT] Broker/topic still set to placeholders in secrets.h. Publishing disabled.");
        return;
    }
#if MQTT_USE_TLS
    // Certificate verification stays ENABLED: the broker's CA certificate is required.
    netClient.setCACert(MQTT_CA_CERT);
#endif
    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setBufferSize(MQTT_BUF_SIZE);
    mqtt.setSocketTimeout(3);   // seconds; limits how long a dead connection can block the loop
    mqtt.setKeepAlive(30);
}

// One connection attempt. The client ID is unique per board (device ID + MAC tail).
bool connectMQTT() {
    char clientId[48];
    uint64_t mac = ESP.getEfuseMac();
    snprintf(clientId, sizeof(clientId), "enviromesh-%s-%06X", DEVICE_ID, (uint32_t)(mac >> 24) & 0xFFFFFF);

    Serial.printf("[MQTT] Connecting to %s:%d as %s...\n", MQTT_HOST, MQTT_PORT, clientId);

    bool ok;
    if (strlen(MQTT_USER) > 0) {
        ok = mqtt.connect(clientId, MQTT_USER, MQTT_PASSWORD);
    } else {
        ok = mqtt.connect(clientId);
    }

    if (ok) {
        Serial.println("[MQTT] Connected.");
    } else {
        Serial.printf("[MQTT] Connection failed, state=%d (see PubSubClient state codes)\n", mqtt.state());
    }
    return ok;
}

// Rate-limited reconnection with exponential backoff (5 s -> 60 s). Never loops.
void reconnectMQTT() {
    if (mqtt.connected()) {
        mqttRetryMs = MQTT_RETRY_MIN_MS;
        return;
    }
    if (!mqttConfigValid() || WiFi.status() != WL_CONNECTED) return;
#if MQTT_USE_TLS
    if (!isClockSynced()) return;   // certificate validation needs a correct date
#endif
    if (mqttAttempted && (millis() - lastMqttAttemptMs < mqttRetryMs)) return;

    mqttAttempted = true;
    lastMqttAttemptMs = millis();
    if (!connectMQTT()) {
        mqttRetryMs = min(mqttRetryMs * 2, MQTT_RETRY_MAX_MS);
        Serial.printf("[MQTT] Next attempt in %lu s\n", mqttRetryMs / 1000);
    }
}

// Publishes with QoS 0 (the only QoS PubSubClient supports for publishing).
// A true return means "handed to the TCP socket", NOT "accepted/stored by the server".
bool publishTelemetry(const char *json, size_t len) {
    if (!mqttConfigValid()) {
        Serial.println("[PUBLISH] Skipped: MQTT broker/topic not configured.");
        return false;
    }
    if (!isClockSynced()) {
        Serial.println("[PUBLISH] Deferred: clock not synchronized (no valid timestamp).");
        return false;
    }
    if (!mqtt.connected()) {
        Serial.println("[PUBLISH] Skipped: MQTT not connected.");
        return false;
    }
    if (len + strlen(MQTT_TOPIC) + 10 > MQTT_BUF_SIZE) {
        Serial.println("[PUBLISH] Error: message larger than MQTT buffer.");
        return false;
    }

    bool ok = mqtt.publish(MQTT_TOPIC, json);   // retain = false
    if (ok) {
        publishCount++;
        Serial.printf("[PUBLISH] Sent %u bytes to \"%s\" (QoS 0; server acceptance NOT confirmed)\n",
                      (unsigned)len, MQTT_TOPIC);
    } else {
        publishFailCount++;
        Serial.println("[PUBLISH] Failed (publish returned false).");
    }
    return ok;
}

// ==========================================
// JSON: BUILDING, VALIDATION, DISPLAY
// ==========================================

// Represents unavailable data according to the chosen policy (null or omission)
void markUnavailable(JsonObject obj, const char *key) {
#if UNAVAILABLE_AS_NULL
    obj[key] = nullptr;
#else
    (void)obj; (void)key;   // field omitted
#endif
}

// Builds the telemetry JSON into out. Returns the length, or 0 on error.
size_t buildTelemetryJSON(char *out, size_t outSize) {
    telemetryDoc.clear();
    JsonDocument &doc = telemetryDoc;

    // Timestamp: only a real, synchronized UTC time; never a fake date
    char ts[25];
    if (getUtcTimestamp(ts, sizeof(ts))) {
        doc["timestamp"] = ts;
    } else {
#if UNAVAILABLE_AS_NULL
        doc["timestamp"] = nullptr;
#endif
    }

    doc["device_id"]  = DEVICE_ID;
    doc["group_code"] = GROUP_CODE;
    doc["zone"]       = ZONE;
    doc["protocol"]   = PROTOCOL;

    // Nested "metrics" object
    JsonObject m = doc["metrics"].to<JsonObject>();

    // MQ-2: no validated ppm conversion -> unavailable (never the raw ADC value)
    markUnavailable(m, "gas_ppm");

    if (currentMeasurements.mq2CalibrationValid) {
        m["smoke_detected"] = currentMeasurements.smokeDetected;
    } else {
        markUnavailable(m, "smoke_detected");
    }

    // DHT11: only if the current reading is valid
    if (currentMeasurements.dhtValid) {
        m["temperature_c"] = roundf(currentMeasurements.temperature * 10.0f) / 10.0f;
        m["humidity_pct"]  = roundf(currentMeasurements.humidity * 10.0f) / 10.0f;
    } else {
        markUnavailable(m, "temperature_c");
        markUnavailable(m, "humidity_pct");
    }

    // Water sensor: only valid if calibration succeeded
    if (currentMeasurements.waterCalibrationValid) {
        m["water_leak_detected"] = currentMeasurements.waterLeakDetected;
    } else {
        markUnavailable(m, "water_leak_detected");
    }

    // PIR
    m["motion_detected"] = currentMeasurements.motionDetected || motionLatched;

    // Servo: no position feedback -> "current" = last commanded angle
    m["servo_current_angle_deg"] = currentMeasurements.lastCommandedAngle;
    m["servo_target_angle_deg"]  = currentMeasurements.targetAngle;
    m["servo_operation_status"]  = currentMeasurements.servoCommanded ? "commanded" : "unknown";

    if (doc.overflowed()) return 0;
    if (measureJson(doc) >= outSize) return 0;   // would not fit (needs room for '\0')

    return serializeJson(doc, out, outSize);
}

// Local self-check: re-parses the produced JSON and verifies field names, types and
// extra fields. Does NOT replace server-side validation.
bool validateJsonMessage(const char *json) {
    JsonDocument d;
    DeserializationError err = deserializeJson(d, json);
    if (err) {
        Serial.printf("[JSON CHECK] Invalid syntax: %s\n", err.c_str());
        return false;
    }

    bool ok = true;

    // Unexpected root-level fields
    const char *rootKeys[] = {"timestamp", "device_id", "group_code", "zone", "protocol", "metrics"};
    for (JsonPair kv : d.as<JsonObject>()) {
        bool known = false;
        for (const char *k : rootKeys) if (strcmp(kv.key().c_str(), k) == 0) known = true;
        if (!known) { Serial.printf("[JSON CHECK] Unexpected root field: %s\n", kv.key().c_str()); ok = false; }
    }

    // Root field types and fixed values
    if (!d["timestamp"].isNull() && !d["timestamp"].is<const char*>()) { Serial.println("[JSON CHECK] timestamp: invalid type"); ok = false; }
    if (d["timestamp"].isNull()) Serial.println("[JSON CHECK] timestamp unavailable (time not synchronized)");
    if (strcmp(d["device_id"] | "", DEVICE_ID) != 0)   { Serial.println("[JSON CHECK] device_id mismatch");  ok = false; }
    if (strcmp(d["group_code"] | "", GROUP_CODE) != 0) { Serial.println("[JSON CHECK] group_code mismatch"); ok = false; }
    if (strcmp(d["zone"] | "", ZONE) != 0)             { Serial.println("[JSON CHECK] zone mismatch");       ok = false; }
    if (strcmp(d["protocol"] | "", PROTOCOL) != 0)     { Serial.println("[JSON CHECK] protocol mismatch");   ok = false; }

    if (!d["metrics"].is<JsonObject>()) {
        Serial.println("[JSON CHECK] metrics missing or not an object");
        return false;
    }

    // Expected type: 'n' number, 'b' boolean, 'i' integer, 's' string
    struct Rule { const char *key; char type; };
    const Rule rules[] = {
        {"gas_ppm", 'n'}, {"smoke_detected", 'b'}, {"temperature_c", 'n'}, {"humidity_pct", 'n'},
        {"water_leak_detected", 'b'}, {"motion_detected", 'b'},
        {"servo_current_angle_deg", 'i'}, {"servo_target_angle_deg", 'i'}, {"servo_operation_status", 's'}
    };

    JsonObject m = d["metrics"].as<JsonObject>();

    // Unexpected metrics fields
    for (JsonPair kv : m) {
        bool known = false;
        for (const Rule &r : rules) if (strcmp(kv.key().c_str(), r.key) == 0) known = true;
        if (!known) { Serial.printf("[JSON CHECK] Unexpected metrics field: %s\n", kv.key().c_str()); ok = false; }
    }

    // Presence and type of each expected field
    for (const Rule &r : rules) {
        JsonVariant v = m[r.key];
        if (v.isNull()) {
            Serial.printf("[JSON CHECK] %s: %s (unavailable)\n",
                          r.key, v.is<JsonVariant>() ? "null" : "absent");
            continue;
        }
        bool typeOk = (r.type == 'n' && v.is<float>()) ||
                      (r.type == 'b' && v.is<bool>()) ||
                      (r.type == 'i' && v.is<int>()) ||
                      (r.type == 's' && v.is<const char*>());
        if (!typeOk) { Serial.printf("[JSON CHECK] %s: invalid type\n", r.key); ok = false; }
    }

    return ok;
}

// One JSON cycle: build -> self-check -> display -> publish
void jsonCycle() {
    static char jsonBuf[JSON_BUF_SIZE];

    size_t len = buildTelemetryJSON(jsonBuf, sizeof(jsonBuf));
    if (len == 0) {
        Serial.println("[JSON] Build failed (overflow or buffer too small).");
        return;
    }

    motionLatched = false;   // motion seen so far is now included in this message
    bool localOk = validateJsonMessage(jsonBuf);

        Serial.println("[JSON] Generated message:");
    Serial.println(jsonBuf);
    Serial.printf("[JSON] Local self-check: %s\n", localOk ? "OK" : "FAILED");

    if (!localOk) {
        Serial.println("[PUBLISH] Skipped: local self-check failed.");
        return;
    }
    publishTelemetry(jsonBuf, len);
}

// Connectivity summary (no secrets printed)
void displayStatus() {
    Serial.println("========================================");
    Serial.println("[EnviroMesh Connectivity Status]");

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("- Wi-Fi  : Connected, IP %s, RSSI %d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.println("- Wi-Fi  : Disconnected (retrying)");
    }

    char ts[25];
    if (getUtcTimestamp(ts, sizeof(ts))) {
        Serial.printf("- Clock  : Synchronized, UTC %s\n", ts);
    } else {
        Serial.println("- Clock  : NOT synchronized (timestamp omitted)");
    }
    if (!mqttConfigValid()) {
        Serial.println("- MQTT   : Not configured (placeholders in secrets.h)");
    } else {
        Serial.printf("- MQTT   : %s (published: %lu, failed: %lu)\n",
                      mqtt.connected() ? "Connected" : "Disconnected (retrying)",
                      publishCount, publishFailCount);
    }
    Serial.println("========================================");
}
