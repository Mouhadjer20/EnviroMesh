// EnviroMesh G61 - communications tab
// Wi-Fi, NTP, BLE, MQTT, JSON (build / validation / cycle) and connectivity status.
// Globals, constants and prototypes are declared in main.ino.

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
// BLUETOOTH LOW ENERGY (BLE) - companion app link
// ==========================================

// BLE callbacks run in the BLE task: they only set flags or copy bytes (no servo or Serial work here).
class BleServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *server) override {
        bleClientConnected = true;
    }
    void onDisconnect(BLEServer *server) override {
        bleClientConnected = false;
        bleNeedAdvertise = true;   // advertising is restarted from loop()
    }
};

class BleRxCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override {
        auto value = characteristic->getValue();   // std::string or String depending on the core version
        portENTER_CRITICAL(&bleMux);
        for (size_t i = 0; i < value.length(); i++) {
            if (bleRxLen < sizeof(bleRxBuf)) bleRxBuf[bleRxLen++] = (char)value[i];
        }
        portEXIT_CRITICAL(&bleMux);
    }
};

void initializeBluetooth() {
    BLEDevice::init(BT_DEVICE_NAME);

#if BLE_REQUIRE_PAIRING
    // Pairing with a static passkey: the phone asks the user to type BLE_PASSKEY, then bonds.
    // Uses the ESP-IDF security calls directly, because the Arduino BLE wrapper API differs between core versions.
    uint32_t passkey = BLE_PASSKEY;
    uint8_t authReq = ESP_LE_AUTH_REQ_SC_MITM_BOND;   // secure connections + MITM protection + bonding
    uint8_t ioCap = ESP_IO_CAP_OUT;                   // "display only": the passkey is fixed, the phone asks for it
    uint8_t keySize = 16;
    uint8_t initKey = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;
    uint8_t rspKey = ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK;
    esp_ble_gap_set_security_param(ESP_BLE_SM_SET_STATIC_PASSKEY, &passkey, sizeof(uint32_t));
    esp_ble_gap_set_security_param(ESP_BLE_SM_AUTHEN_REQ_MODE, &authReq, sizeof(uint8_t));
    esp_ble_gap_set_security_param(ESP_BLE_SM_IOCAP_MODE, &ioCap, sizeof(uint8_t));
    esp_ble_gap_set_security_param(ESP_BLE_SM_MAX_KEY_SIZE, &keySize, sizeof(uint8_t));
    esp_ble_gap_set_security_param(ESP_BLE_SM_SET_INIT_KEY, &initKey, sizeof(uint8_t));
    esp_ble_gap_set_security_param(ESP_BLE_SM_SET_RSP_KEY, &rspKey, sizeof(uint8_t));
#endif

    bleServer = BLEDevice::createServer();
    bleServer->setCallbacks(new BleServerCallbacks());

    BLEService *service = bleServer->createService(BLE_SERVICE_UUID);

    // TX: ESP32 -> phone (notifications)
    bleTx = service->createCharacteristic(BLE_TX_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    bleTx->addDescriptor(new BLE2902());

    // RX: phone -> ESP32 (commands)
    BLECharacteristic *rx = service->createCharacteristic(
        BLE_RX_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    rx->setCallbacks(new BleRxCallbacks());
#if BLE_REQUIRE_PAIRING
    rx->setAccessPermissions(ESP_GATT_PERM_WRITE_ENC_MITM);   // writes are refused unless the phone is bonded
#endif

    service->start();

    BLEAdvertising *advertising = BLEDevice::getAdvertising();
    advertising->addServiceUUID(BLE_SERVICE_UUID);
    advertising->setScanResponse(true);
    BLEDevice::startAdvertising();

    Serial.printf("[BLE] Advertising as \"%s\". Pair the phone first (passkey required: %s).\n",
                  BT_DEVICE_NAME, BLE_REQUIRE_PAIRING ? "yes" : "no");
}

// One text line in the format read by the BioGuard app (parseData):
//   GAZ=<0-1023> EAU=<0-1023> TEMP=<celsius> MOUVEMENT=DETECTE|AUCUN ROBINET=OUVERT|FERME
// ESP32 ADC values (0-4095) are divided by 4 to match the app's 0-1023 scale.
// ROBINET reflects the last COMMANDED servo angle (the real position is not verified).
// The line is split into small notifications; the app reassembles it up to the newline.
void sendBtReport() {
    if (!bleClientConnected || bleTx == nullptr) return;

    String s;
    s.reserve(120);
    s += "GAZ=" + String(currentMeasurements.mq2Raw / 4);
    s += " EAU=" + String(currentMeasurements.waterRaw / 4);
    if (currentMeasurements.dhtValid) s += " TEMP=" + String(currentMeasurements.temperature, 1);
    s += currentMeasurements.motionDetected ? " MOUVEMENT=DETECTE" : " MOUVEMENT=AUCUN";
    s += (currentMeasurements.lastCommandedAngle >= 90) ? " ROBINET=OUVERT" : " ROBINET=FERME";
    s += "\n";

    const uint8_t *data = (const uint8_t *)s.c_str();
    size_t len = s.length();
    for (size_t offset = 0; offset < len; offset += BLE_CHUNK_BYTES) {
        size_t n = (len - offset < BLE_CHUNK_BYTES) ? (len - offset) : BLE_CHUNK_BYTES;
        bleTx->setValue((uint8_t *)(data + offset), n);
        bleTx->notify();
        delay(10);   // lets the BLE stack send each chunk
    }
}

// Commands sent by the app: OUVRIR (servo 90 deg) and FERMER (servo 0 deg).
// A command has priority over the PIR for BT_OVERRIDE_MS, then PIR control resumes.
void handleBtCommand(const String &cmd) {
    String c = cmd;
    c.trim();
    c.toUpperCase();
    if (c.length() == 0) return;

    if (c == "OUVRIR") {
        controlServo(90);
        btOverrideActive = true;
        btOverrideUntilMs = millis() + BT_OVERRIDE_MS;
        Serial.println("[BLE] Command OUVRIR -> servo 90 deg (PIR control paused)");
    } else if (c == "FERMER") {
        controlServo(0);
        btOverrideActive = true;
        btOverrideUntilMs = millis() + BT_OVERRIDE_MS;
        Serial.println("[BLE] Command FERMER -> servo 0 deg (PIR control paused)");
    } else {
        Serial.printf("[BLE] Unknown command ignored: %s\n", c.c_str());
    }
}

// Called every loop iteration: connection log, advertising restart, app commands,
// manual override end, periodic report.
void bluetoothTask() {
    unsigned long now = millis();

    if (bleClientConnected != bleLastReportedConnected) {
        bleLastReportedConnected = bleClientConnected;
        Serial.println(bleClientConnected ? "[BLE] Phone connected." : "[BLE] Phone disconnected.");
    }

    if (bleNeedAdvertise) {
        bleNeedAdvertise = false;
        delay(100);   // the BLE stack needs a short pause before advertising again
        BLEDevice::startAdvertising();
        Serial.println("[BLE] Advertising restarted.");
    }

    // Take the bytes written by the phone (copied from the BLE task under a lock)
    char local[sizeof(bleRxBuf)];
    size_t n = 0;
    portENTER_CRITICAL(&bleMux);
    n = bleRxLen;
    memcpy(local, bleRxBuf, n);
    bleRxLen = 0;
    portEXIT_CRITICAL(&bleMux);

    for (size_t i = 0; i < n; i++) {
        char ch = local[i];
        if (ch == '\n' || ch == '\r') {
            if (btRxLine.length() > 0) {
                handleBtCommand(btRxLine);
                btRxLine = "";
            }
        } else if (btRxLine.length() < 32) {
            btRxLine += ch;
        }
    }

    if (btOverrideActive && (long)(now - btOverrideUntilMs) >= 0) {
        btOverrideActive = false;
        controlServo(currentMeasurements.motionDetected ? 90 : 0);
        Serial.println("[BLE] Manual override ended, PIR control resumed.");
    }

    if (now - lastBtReportMs >= BT_REPORT_INTERVAL_MS) {
        lastBtReportMs = now;
        sendBtReport();
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
