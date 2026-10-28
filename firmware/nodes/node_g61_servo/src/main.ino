/**
 * @file main.ino
 * @brief EnviroMesh G61 environmental and servo node.
 *
 * Reads MQ-2, DHT11, water and PIR sensors and drives an SG90 servo on an
 * ESP32. Telemetry is built as JSON, timestamped in UTC via NTP, and published
 * over Wi-Fi to an MQTT broker on enviromesh/devices/G61/telemetry..
 * Copy secrets.h.example to secrets.h and fill it in before compiling.
 * 
 *   layout :
 *   main.ino    : includes, constants, data structure, globals, prototypes, setup(), loop()
 *   sensors.ino : sensors, calibration, PIR, servo, serial report
 *   comms.ino   : Wi-Fi, NTP, BLE, MQTT, JSON
 * Board setting: Tools > Partition Scheme > "Huge APP (3MB No OTA/1MB SPIFFS)"
 */

#include <WiFi.h>
#include <time.h>
#include <DHT.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>   // PubSubClient (Nick O'Leary)   
#include <BLEDevice.h>      // Bluetooth Low Energy (built into the ESP32 Arduino core)
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h> 

#if !defined(CONFIG_BT_ENABLED)
  #error Bluetooth is not enabled for this board. Select "ESP32 Dev Module".
#endif

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
// --- BLE (companion app) settings ---
// The link uses the Nordic UART Service (NUS): a standard BLE "serial port" made of two characteristics.
//   RX: the phone WRITES commands here   TX: the ESP32 NOTIFIES text reports here
#define BLE_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_RX_UUID      "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_TX_UUID      "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

// 1 = commands (OUVRIR / FERMER) are accepted only from a phone paired with the passkey. Recommended.
// 0 = no pairing required (debug only).
#define BLE_REQUIRE_PAIRING 1
#ifndef BLE_PASSKEY
  #define BLE_PASSKEY 123456   // 6 digits; override it in secrets.h and do not commit the real one
#endif

const char*         BT_DEVICE_NAME        = "EnviroMesh-G61";  // name shown when pairing the phone
const unsigned long BT_REPORT_INTERVAL_MS = 2000;              // one text report every 2 s
const unsigned long BT_OVERRIDE_MS        = 30000;             // an app command pauses PIR control of the servo for 30 s
const size_t        BLE_CHUNK_BYTES       = 20;                // safe notification size with the default BLE MTU

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
BLEServer *bleServer = nullptr;
BLECharacteristic *bleTx = nullptr;

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
unsigned long lastBtReportMs = 0;
unsigned long btOverrideUntilMs = 0;
bool btOverrideActive = false;   // true while an app command has priority over the PIR
String btRxLine;
volatile bool bleClientConnected = false;
volatile bool bleNeedAdvertise = false;
bool bleLastReportedConnected = false;
portMUX_TYPE bleMux = portMUX_INITIALIZER_UNLOCKED;
char bleRxBuf[64];            // bytes written by the phone, filled by the BLE task, consumed by loop()
volatile size_t bleRxLen = 0;

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
void initializeBluetooth();
void bluetoothTask();
void handleBtCommand(const String &cmd);
void sendBtReport();
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
    initializeBluetooth();

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

    // MQTT client setup (no connection yet), then Wi-Fi (bounded wait; the loop keeps retrying)
    initializeMQTT();
    connectWiFi();
    waitForNetworkAtStartup();

    // First sensor snapshot
    collectMeasurements();

    Serial.println("[System] Initialization complete. Entering main loop.\n");
}

void loop() {
    unsigned long now = millis();

    // Keep Wi-Fi and MQTT alive without blocking
    maintainWiFi();
    reconnectMQTT();
    mqtt.loop();
    maintainMQ2Calibration();
    pollMotion();   // fast PIR polling + immediate servo reaction + event-triggered publication
    bluetoothTask();   // app commands + text report over Bluetooth

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
