// EnviroMesh G61 - sensors tab
// Sensors, calibration, PIR, servo and serial report.
// Globals, constants and prototypes are declared in main.ino.

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
        if (!btOverrideActive) controlServo(state ? 90 : 0);   // 90 deg upon motion, 0 deg otherwise (command only, position not verified)

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
