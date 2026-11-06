/*
  ====================================================================================
  Projet       : SensorHub - Firmware ESP32 (Hub Capteurs & Actionneurs)
  Description  : Surveillance environnementale multi-capteurs en temps réel & contrôle servomoteur
  Protocoles   : Double protocole HYBRIDE HTTP REST + MQTT
  Matériel     : ESP32 DevKit v1, DHT11/DHT22 (T°/Hum), MQ-2/MQ-135 (Gaz), Capteur d'eau, Servomoteur, LED
  Auteur       : SensorHub Team
  Date         : 2026
  ====================================================================================

  BIBLIOTHÈQUES NÉCESSAIRES (à installer via le Gestionnaire de bibliothèques Arduino) :
  1. ArduinoJson (par Benoît Blanchon) - Version 6 ou 7
  2. DHT sensor library (par Adafruit)
  3. Adafruit Unified Sensor (dépendance requise par DHT)
  4. ESP32Servo (par Kevin Harrington) - Pour piloter le servomoteur sans timer bloquant
  5. PubSubClient (par Nick O'Leary) - Pour le protocole MQTT ultra-rapide
  6. WiFi et HTTPClient (incluses par défaut dans le package ESP32 de l'Arduino IDE)

  CÂBLAGE RECOMMANDÉ :
  - DHT11 / DHT22 : VCC -> 3.3V, GND -> GND, DATA -> GPIO 4 (avec résistance pull-up 10k si module sans PCB)
  - Capteur Gaz   : VCC -> 5V (VIN), GND -> GND, AOUT -> GPIO 34 (ADC1)
  - Capteur Eau   : VCC -> 3.3V, GND -> GND, SIG -> GPIO 35 (ADC1)
  - Servomoteur   : Rouge -> 5V (VIN ou alim 5V externe), Marron/Noir -> GND, Jaune/Orange -> GPIO 18
  - LED Alerte    : Anode (+) -> Résistance 220-330Ω -> GPIO 5, Cathode (-) -> GND

  NOTE SUR LA CAMÉRA :
  ⚠️ La caméra OV2640 NE DOIT PAS être branchée sur cette carte ESP32 standard (manque de broches et pas de PSRAM).
  Utilisez une carte dédiée "AI-Thinker ESP32-CAM" programmée avec le fichier "esp32_cam.ino".
  Les deux ESP32 se synchronisent automatiquement via le WiFi et votre tableau de bord web !
  ====================================================================================
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "DHT.h"
#include <ESP32Servo.h>

// ====================================================================================
// 1. CONFIGURATION RÉSEAU, HTTP ET BROKER MQTT
// ====================================================================================

// ⚠️ Hotspot iPhone : vérifie le nom dans Réglages → Général → Informations → Nom
// Exemple : "iPhone de Adem", "iPhone Adem", "Adem’s iPhone"...
const char* WIFI_SSID     = "Iphone";      // ← MODIFIE avec le vrai nom du hotspot iPhone
const char* WIFI_PASSWORD = "12345669";    // Mot de passe hotspot iPhone

// Serveur cloud hébergé sur Render (accessible depuis n'importe quelle connexion Internet)
const char* SERVER_URL    = "https://sensorhub-projet.onrender.com";

// ⚠️ MQTT désactivé : le serveur cloud Render ne supporte pas les connexions MQTT externes
// Toutes les données sont envoyées via HTTP POST uniquement (port 443 HTTPS)
const char* SERVER_IP     = "sensorhub-projet.onrender.com"; // non utilisé (MQTT off)
const int   HTTP_PORT     = 443;
const int   MQTT_PORT     = 1883;

// Clé API de sécurité (doit correspondre à DEFAULT_API_KEY ou à la clé de l'appareil dans SensorHub)
const char* API_KEY       = "esp32-secret-key-123456";

// Identifiant unique de cet appareil (doit correspondre à l'enregistrement dans la table devices)
const char* DEVICE_NAME   = "esp32-01";

// MQTT désactivé pour le cloud (activer seulement en réseau local avec broker MQTT)
bool ENABLE_MQTT          = false;  // Désactivé : serveur cloud sans broker MQTT accessible
bool ENABLE_HTTP          = true;   // Actif : envoi HTTP POST vers Render en HTTPS

// Sujets (Topics) MQTT pour cet appareil
const char* MQTT_TOPIC_DATA     = "sensorhub/esp32-01/data";      // Envoi des mesures
const char* MQTT_TOPIC_COMMANDS = "sensorhub/esp32-01/commands";  // Réception instantanée des ordres
const char* MQTT_TOPIC_STATUS   = "sensorhub/esp32-01/status";    // En ligne / Hors ligne (LWT)

// ====================================================================================
// 2. AFFECTATION DES BROCHES (GPIO) ET SEUILS PHYSIQUES
// ====================================================================================
#define DHTPIN        4       // Broche de données du capteur DHT
#define DHTTYPE       DHT11   // Type de capteur : DHT11 (remplacez par DHT22 si vous utilisez un DHT22 blanc)
#define GAS_PIN       34      // Entrée analogique du capteur de gaz MQ (ADC1)
#define WATER_PIN     35      // Entrée analogique du capteur d'eau / pluie (ADC1)
#define SERVO_PIN     18      // Broche de commande PWM du servomoteur
#define LED_PIN       5       // Broche de commande de la LED d'alerte

// Seuils de déclenchement d'alerte matérielle
const int THRESHOLD_GAS   = 2000; // Alerte si valeur brute ADC > 2000 (sur 4095)
const int THRESHOLD_WATER = 1000; // Alerte si valeur brute ADC > 1000 (détection d'eau)

// ====================================================================================
// 3. VARIABLES GLOBALES, CLIENTS RÉSEAU ET ACTIONNEURS
// ====================================================================================
DHT dht(DHTPIN, DHTTYPE);
Servo valveServo;

WiFiClient espClient;
PubSubClient mqttClient(espClient);

int currentServoAngle        = 0;     // Angle courant du servo (0° = Vanne fermée, 90° = Mi-ouvert, 180° = Ouvert)
bool autoCloseValveOnAlert   = true;  // Sécurité automatique : ferme la vanne en cas d'alerte fuite d'eau ou gaz

unsigned long lastSendTime   = 0;
const unsigned long SEND_INTERVAL = 5000; // Intervalle d'émission : 5 secondes

unsigned long lastMqttRetry  = 0;
const unsigned long MQTT_RETRY_INTERVAL = 5000; // Reconnexion MQTT toutes les 5s max en cas de déconnexion

// Gestion du clignotement de la LED sans délai bloquant
unsigned long lastBlinkTime  = 0;
const unsigned long BLINK_INTERVAL = 400; // Clignote toutes les 400 ms en alerte
bool ledState                = false;
bool isAlertActive           = false;
bool manualLedOverride       = false; // Si l'utilisateur a forcé la LED via le dashboard

// ====================================================================================
// 4. FONCTION UNIFIÉE D'EXÉCUTION DES COMMANDES (APPELÉE PAR HTTP ET MQTT)
// ====================================================================================
void executeCommand(String action, JsonVariant params) {
  Serial.print("[ACTION EXÉCUTÉE] Ordre reçu : ");
  Serial.println(action);

  if (action == "test_led" || action == "toggle_led") {
    manualLedOverride = !manualLedOverride;
    digitalWrite(LED_PIN, manualLedOverride ? HIGH : LOW);
    Serial.print("[ACTION] LED forcée à : ");
    Serial.println(manualLedOverride ? "ALLUMÉE" : "ÉTEINTE");
  } else if (action == "alarm_test") {
    Serial.println("[ACTION] Test alarme déclenché (clignotement rapide 3s)");
    for (int i = 0; i < 6; i++) {
      digitalWrite(LED_PIN, HIGH);
      delay(250);
      digitalWrite(LED_PIN, LOW);
      delay(250);
    }
  } else if (action == "servo_set" || action == "set_servo") {
    int targetAngle = 0;
    if (params.is<JsonObject>() && params.containsKey("angle")) {
      targetAngle = params["angle"].as<int>();
    } else if (params.is<int>()) {
      targetAngle = params.as<int>();
    }
    currentServoAngle = constrain(targetAngle, 0, 180);
    valveServo.write(currentServoAngle);
    Serial.printf("[ACTION] Servomoteur positionné à : %d°\n", currentServoAngle);
  } else if (action == "servo_open" || action == "open_valve") {
    currentServoAngle = 180;
    valveServo.write(currentServoAngle);
    Serial.println("[ACTION] Servomoteur / Vanne : OUVERT (180°)");
  } else if (action == "servo_close" || action == "close_valve") {
    currentServoAngle = 0;
    valveServo.write(currentServoAngle);
    Serial.println("[ACTION] Servomoteur / Vanne : FERMÉ (0°)");
  } else if (action == "reboot") {
    Serial.println("[ACTION] Redémarrage de l'ESP32 demandé...");
    delay(500);
    ESP.restart();
  }
}

// ====================================================================================
// 5. CALLBACK MQTT : RÉCEPTION INSTANTANÉE DES ORDRES (< 20ms)
// ====================================================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("\n⚡ [MQTT REÇU] Topic: ");
  Serial.print(topic);
  Serial.print(" | Payload: ");
  Serial.println(message);

  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (!error && doc.containsKey("command")) {
    String action = doc["command"].as<String>();
    JsonVariant params = doc["params"];
    executeCommand(action, params);
  }
}

// ====================================================================================
// 6. CONNEXION ET RECONNEXION AU BROKER MQTT (AVEC LWT - LAST WILL & TESTAMENT)
// ====================================================================================
void reconnectMQTT() {
  if (mqttClient.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttRetry < MQTT_RETRY_INTERVAL) return;
  lastMqttRetry = now;

  Serial.print("[MQTT] Connexion au broker ");
  Serial.print(SERVER_IP);
  Serial.print(":");
  Serial.print(MQTT_PORT);
  Serial.print("... ");

  // Configuration du LWT (Last Will & Testament) : Si l'ESP32 est déconnecté brusquement,
  // le broker publie automatiquement "offline" sur sensorhub/esp32-01/status
  if (mqttClient.connect(DEVICE_NAME, DEVICE_NAME, API_KEY, MQTT_TOPIC_STATUS, 1, true, "offline")) {
    Serial.println("Connecté avec succès !");

    // Publier le statut en ligne
    mqttClient.publish(MQTT_TOPIC_STATUS, "online", true);

    // S'abonner aux commandes en temps réel
    mqttClient.subscribe(MQTT_TOPIC_COMMANDS, 1);
    Serial.print("[MQTT] Abonné au topic de commandes : ");
    Serial.println(MQTT_TOPIC_COMMANDS);
  } else {
    Serial.print("Échec, rc=");
    Serial.print(mqttClient.state());
    Serial.println(" (Nouvelle tentative dans 5s)");
  }
}

// ====================================================================================
// 7. FONCTION DE CONNEXION AU WIFI AVEC RECONNEXION AUTOMATIQUE
// ====================================================================================
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println();
  Serial.print("[WiFi] Connexion au réseau : ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connecté avec succès !");
    Serial.print("[WiFi] Adresse IP locale de l'ESP32 : ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Échec de la connexion. Nouvelle tentative au prochain cycle.");
  }
}

// ====================================================================================
// 8. ENVOI DES MESURES (HYBRIDE MQTT + HTTP)
// ====================================================================================
void sendSensorData(float temp, float hum, int gas, int water, bool alert, int servoAngle) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[RÉSEAU] WiFi non connecté, abandon de l'envoi.");
    return;
  }

  // Construction du JSON avec ArduinoJson
  StaticJsonDocument<300> doc;
  doc["device"]      = DEVICE_NAME;
  doc["temperature"] = serialized(String(temp, 1));
  doc["humidity"]    = round(hum);
  doc["gas"]         = gas;
  doc["water"]       = water;
  doc["servo_angle"] = servoAngle;
  doc["alert"]       = alert;

  String requestBody;
  serializeJson(doc, requestBody);

  // 1. ENVOI VIA MQTT (Ultra-rapide et très léger)
  if (ENABLE_MQTT && mqttClient.connected()) {
    bool pubOk = mqttClient.publish(MQTT_TOPIC_DATA, requestBody.c_str());
    if (pubOk) {
      Serial.print("[MQTT] ✅ Publication réussie sur ");
      Serial.println(MQTT_TOPIC_DATA);
    } else {
      Serial.println("[MQTT] ❌ Échec de publication.");
    }
  }

  // 2. ENVOI VIA HTTP POST HTTPS vers le serveur cloud
  if (ENABLE_HTTP) {
    HTTPClient http;
    String url = String(SERVER_URL) + "/api/data";

    http.begin(url);
    http.setInsecure(); // ← Accepte le certificat HTTPS sans validation (OK pour IoT)
    http.addHeader("Content-Type", "application/json");
    http.addHeader("x-api-key", API_KEY);
    http.setTimeout(10000); // 10 secondes timeout (réseau mobile peut être lent)

    Serial.print("[HTTP] Envoi POST -> ");
    Serial.println(requestBody);

    int httpResponseCode = http.POST(requestBody);

    if (httpResponseCode > 0) {
      Serial.print("[HTTP] Réponse serveur : Code ");
      Serial.println(httpResponseCode);
    } else {
      Serial.print("[HTTP] Erreur requête : ");
      Serial.println(http.errorToString(httpResponseCode).c_str());
    }

    http.end();
  }
}

// ====================================================================================
// 9. RÉCUPÉRATION DES COMMANDES EN HTTP (POLLING SECOURS)
// ====================================================================================
void checkPendingCommandsHTTP() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(SERVER_URL) + "/api/commands/pending?device=" + String(DEVICE_NAME);

  http.begin(url);
  http.addHeader("x-api-key", API_KEY);

  int httpCode = http.GET();
  if (httpCode == 200) {
    String response = http.getString();

    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, response);

    if (!error && doc.containsKey("commands")) {
      JsonArray commands = doc["commands"].as<JsonArray>();
      for (JsonObject cmd : commands) {
        String action = cmd["command"].as<String>();
        JsonVariant params = cmd["params"];
        executeCommand(action, params);
      }
    }
  }

  http.end();
}

// ====================================================================================
// 10. INITIALISATION DU MICROCONTRÔLEUR (SETUP)
// ====================================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================================");
  Serial.println("   Démarrage SensorHub ESP32 Multi-Capteurs IoT        ");
  Serial.println("   Modes supportés : HTTP REST + MQTT Hybride          ");
  Serial.println("========================================================");

  // Configuration des broches
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // LED éteinte au départ

  pinMode(GAS_PIN, INPUT);
  pinMode(WATER_PIN, INPUT);

  // Configuration de l'ADC de l'ESP32 (résolution 12 bits : 0 à 4095)
  analogReadResolution(12);

  // Initialisation du capteur DHT11
  dht.begin();
  Serial.println("[CAPTEUR] DHT11 initialisé sur GPIO 4.");

  // Initialisation du Servomoteur sur GPIO 18
  valveServo.setPeriodHertz(50);              // Fréquence standard 50 Hz pour servo analogique / numérique
  valveServo.attach(SERVO_PIN, 500, 2400);    // Impulsions min: 500µs, max: 2400µs (couvre 0-180°)
  valveServo.write(currentServoAngle);        // Position de départ (0° - Fermé)
  Serial.printf("[ACTIONNEUR] Servomoteur attaché sur GPIO %d (Position initiale: %d°).\n", SERVO_PIN, currentServoAngle);

  // Connexion WiFi
  connectWiFi();

  // Configuration du client MQTT
  if (ENABLE_MQTT) {
    mqttClient.setServer(SERVER_IP, MQTT_PORT);
    mqttClient.setCallback(mqttCallback);
    mqttClient.setBufferSize(512); // Pour supporter les JSON de commandes
    reconnectMQTT();
  }

  Serial.println("[READY] Initialisation terminée. Boucle active.\n");
}

// ====================================================================================
// 11. BOUCLE PRINCIPALE NON-BLOQUANTE (LOOP)
// ====================================================================================
void loop() {
  // 1. Reconnexion automatique au WiFi si coupure réseau
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  // 2. Gestion et écoute permanente MQTT (commandes instantanées reçues en < 20ms)
  if (ENABLE_MQTT && WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) {
      reconnectMQTT();
    }
    mqttClient.loop();
  }

  unsigned long currentMillis = millis();

  // 3. GESTION DU CLIGNOTEMENT DE LA LED EN CAS D'ALERTE (SANS DELAY BLOQUANT)
  if (isAlertActive && !manualLedOverride) {
    if (currentMillis - lastBlinkTime >= BLINK_INTERVAL) {
      lastBlinkTime = currentMillis;
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState ? HIGH : LOW);
    }
  } else if (!manualLedOverride) {
    digitalWrite(LED_PIN, LOW);
  }

  // 4. ENVOI PÉRIODIQUE DES MESURES TOUTES LES 5 SECONDES
  if (currentMillis - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = currentMillis;

    // Lecture du DHT11
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    // Gestion d'erreur si la lecture DHT échoue ponctuellement
    if (isnan(humidity) || isnan(temperature)) {
      Serial.println("[AVERTISSEMENT] Échec lecture DHT11 !");
      temperature = 22.0; // Valeur de repli sécurisée
      humidity = 50.0;
    }

    // Lecture analogique du capteur de gaz MQ et du capteur d'eau
    int gasValue   = analogRead(GAS_PIN);
    int waterValue = analogRead(WATER_PIN);

    // Détermination de l'état d'alerte selon les seuils matériels
    isAlertActive = (gasValue > THRESHOLD_GAS) || (waterValue > THRESHOLD_WATER);

    // Sécurité automatique hydraulique / gaz : fermeture d'urgence de la vanne
    if (isAlertActive && autoCloseValveOnAlert && currentServoAngle != 0) {
      Serial.println("🚨 [SÉCURITÉ] Alerte fuite/gaz détectée ! Fermeture d'urgence de la vanne (Servo -> 0°)...");
      currentServoAngle = 0;
      valveServo.write(currentServoAngle);
    }

    // Affichage dans le moniteur série
    Serial.println("--------------------------------------------------------");
    Serial.print("Température : "); Serial.print(temperature, 1); Serial.print(" °C | ");
    Serial.print("Humidité : "); Serial.print(humidity, 0); Serial.println(" %");
    Serial.print("Gaz MQ      : "); Serial.print(gasValue); Serial.print(" / 4095 | ");
    Serial.print("Eau         : "); Serial.print(waterValue); Serial.println(" / 4095");
    Serial.print("Servo Vanne : "); Serial.print(currentServoAngle); Serial.println("°");
    Serial.print("Alerte      : "); Serial.println(isAlertActive ? "OUI (LED clignotante)" : "NON");
    Serial.println("--------------------------------------------------------");

    // Envoi des données (publie en MQTT et/ou POST HTTP)
    sendSensorData(temperature, humidity, gasValue, waterValue, isAlertActive, currentServoAngle);

    // Si MQTT est désactivé ou déconnecté, vérification de secours en HTTP
    if (!ENABLE_MQTT || !mqttClient.connected()) {
      checkPendingCommandsHTTP();
    }
  }
}
