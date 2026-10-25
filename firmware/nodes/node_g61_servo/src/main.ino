// EnviroMesh - Wi-Fi step: sensors + JSON (phase 2) + Wi-Fi connection + NTP (UTC) time.
// Copy secrets.h.example to secrets.h and fill it in before compiling.

#include <WiFi.h>
#include <time.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>    // ArduinoJson v7

#include "secrets.h"        // WIFI_SSID, WIFI_PASSWORD 

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
const unsigned long JSON_INTERVAL_MS     = 10000;   // JSON build + status report
const unsigned long WIFI_RETRY_MS        = 10000;   // delay between Wi-Fi reconnection attempts
const unsigned long STARTUP_NET_WAIT_MS  = 15000;   // max wait for Wi-Fi (+ NTP) at boot

// --- NTP configuration (UTC, no offset, no daylight saving) ---
const char* NTP_SERVER_1 = "pool.ntp.org";
const char* NTP_SERVER_2 = "time.google.com";

// Any time before 2026-01-01 00:00:00 UTC is considered unsynchronized
const time_t MIN_VALID_EPOCH = 1767225600;

const size_t JSON_BUF_SIZE = 512;   // serialized telemetry (about 330 bytes in practice)

// --- DHT11 Configuration ---
#define DHTTYPE DHT11
DHT dht(PIN_DHT, DHTTYPE);

// --- Servo Instance ---
Servo myservo;

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

// Reused JSON document (avoids repeated allocation of the document object)
JsonDocument telemetryDoc;

// --- Function Prototypes: sensors (unchanged from previous phases) ---
void initializeSensors();
bool calibrateMQ2(int samples = 50);
bool calibrateWaterSensor();
int readMQ2();
bool detectSmoke(int currentVal, int baseline);
bool readDHT11(float &temp, float &hum);
int readWaterSensor();
bool detectWaterLeak(int currentVal, int baseline);
bool readPIR();
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

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("\n[EnviroMesh] System Initialization...");

    // Initialize pins and sensor modules
    initializeSensors();

    // Startup calibration sequence (unchanged)
    Serial.println("[Calibration] Starting MQ-2 calibration (ambient air)...");
    currentMeasurements.mq2CalibrationValid = calibrateMQ2();

    Serial.println("[Calibration] Starting Water Sensor calibration (dry state)...");
    currentMeasurements.waterCalibrationValid = calibrateWaterSensor();

    // Wi-Fi (bounded wait; the loop keeps retrying afterwards)
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

    // Servo configuration
    myservo.setPeriodHertz(50); // Standard 50Hz servo signal
    myservo.attach(PIN_SERVO, 500, 2400);
    controlServo(0); // Initial position set to 0 degrees
}

bool calibrateMQ2(int samples) {
    long sum = 0;
    int minVal = 4095;
    int maxVal = 0;

    // Collect samples to establish baseline readings
    for (int i = 0; i < samples; i++) {
        int val = analogRead(PIN_MQ2);
        sum += val;
        if (val < minVal) minVal = val;
        if (val > maxVal) maxVal = val;
        delay(50);
    }

    int average = sum / samples;
    int spread = maxVal - minVal;

    currentMeasurements.mq2Baseline = average;

    // Stability check: max spread must not exceed tolerance (40 units on 12-bit ADC)
    if (spread < 40) {
        currentMeasurements.mq2Stable = true;
        Serial.printf("-> MQ-2 Calibrated successfully. Baseline (ADC): %d (Stability OK)\n", average);
        return true;
    } else {
        currentMeasurements.mq2Stable = false;
        Serial.println("-> MQ-2 Warning: Unstable environment detected during calibration.");
        return false;
    }
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
    // Relative detection threshold: triggers when value exceeds baseline by > 150 ADC units
    const int smokeDeltaThreshold = 150;
    if (!currentMeasurements.mq2CalibrationValid) return false;

    return (currentVal - baseline) > smokeDeltaThreshold;
}

bool readDHT11(float &temp, float &hum) {
    float h = dht.readHumidity();
    float t = dht.readTemperature(); // Celsius

    if (isnan(h) || isnan(t)) {
        return false; // Failed to read from sensor
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
    currentMeasurements.dhtValid = readDHT11(t, h);
    if (currentMeasurements.dhtValid) {
        currentMeasurements.temperature = t;
        currentMeasurements.humidity = h;
    }

    // 2. MQ-2 Readout
    int mq2Val = readMQ2();
    currentMeasurements.smokeDetected = detectSmoke(mq2Val, currentMeasurements.mq2Baseline);

    // 3. Water Sensor Readout
    int waterVal = readWaterSensor();
    currentMeasurements.waterLeakDetected = detectWaterLeak(waterVal, currentMeasurements.waterDryBaseline);

    // 4. PIR Readout
    currentMeasurements.motionDetected = readPIR();

    // 5. Servo Interaction (Example: turn to 90° upon motion, 0° otherwise)
    if (currentMeasurements.motionDetected) {
        controlServo(90);
    } else {
        controlServo(0);
    }
}

void displayMeasurements() {
    Serial.println("----------------------------------------");
    Serial.println("[EnviroMesh Sensor Report]");

    // Temperature & Humidity
    if (currentMeasurements.dhtValid) {
        Serial.printf("- Temperature : %.1f °C\n", currentMeasurements.temperature);
        Serial.printf("- Humidity    : %.1f %%\n", currentMeasurements.humidity);
    } else {
        Serial.println("- DHT11       : Read error or invalid sensor data");
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
        Serial.println("- MQ-2 (Gas)  : Calibration Unavailable");
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
    m["motion_detected"] = currentMeasurements.motionDetected;

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

// One JSON cycle: build -> self-check -> display (no transmission yet)
void jsonCycle() {
    static char jsonBuf[JSON_BUF_SIZE];

    size_t len = buildTelemetryJSON(jsonBuf, sizeof(jsonBuf));
    if (len == 0) {
        Serial.println("[JSON] Build failed (overflow or buffer too small).");
        return;
    }

    bool localOk = validateJsonMessage(jsonBuf);

    Serial.println("[JSON] Generated message (not transmitted: MQTT not enabled yet):");
    Serial.println(jsonBuf);
    Serial.printf("[JSON] Local self-check: %s\n", localOk ? "OK" : "FAILED");
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
    Serial.println("========================================");
}
