#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "secrets.h"

// Identifiants Wi-Fi
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

// Paramètres du Broker MQTT
const char* mqtt_broker = MQTT_BROKER_IP; // Adresse IP broker
const int mqtt_port = MQTT_PORT;          // Port MQTT par défaut
const char* mqtt_topic = "enviromesh/devices/G43/telemetry";
// Identifiants d'authentification EMQX (depuis le .env)
const char* mqtt_username = MQTT_USERNAME;
const char* mqtt_password = MQTT_PASSWORD;

WiFiClient espClient;
PubSubClient client(espClient);

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message reçu sur le topic [");
  Serial.print(topic);
  Serial.print("] : ");
  for (int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
  }
  Serial.println();
}

void reconnect() {
  while (!client.connected()) {
    String client_id = "ESP32Client-";
    client_id += String(WiFi.macAddress());
    Serial.print("Connexion au broker MQTT...");
    
    // Connexion avec identifiants MQTT
    if (client.connect(client_id.c_str(), mqtt_username, mqtt_password)) {
      Serial.println("Connecté !");
      Serial.print("Abonnement au topic: ");
      Serial.println(mqtt_topic);
      client.subscribe(mqtt_topic);
    } else {
      Serial.print("Échec, rc=");
      Serial.println(client.state());
      Serial.println(" Nouvelle tentative dans 5 secondes");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  // Connexion Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnecté au Wi-Fi !");
  
  client.setServer(mqtt_broker, mqtt_port);
  client.setCallback(callback);

  client.setBufferSize(512);

}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Publish telemetry every 5 seconds
  static unsigned long lastMsg = 0;
  unsigned long now = millis();

  if (now - lastMsg > 5000) {
    lastMsg = now;

    StaticJsonDocument<512> doc;

    // Device information
    doc["device_id"] = "G11";
    doc["zone"] = "Sector_A_Warehouse";

    // Metrics
    JsonObject metrics = doc.createNestedObject("metrics");

    metrics["gas_ppm"] = random(10000, 50001) / 100.0;
    metrics["temperature_c"] = random(2000, 3001) / 100.0;
    metrics["humidity"] = random(4000, 7001) / 100.0;
    metrics["pressure_hpa"] = 1013.25;
    metrics["water_leak"] = 0;
    metrics["motion_detected"] = 0;

    // Protocol
    doc["protocol"] = "Wi-Fi";

    // Metadata
    JsonObject metadata = doc.createNestedObject("metadata");
    metadata["group_code"] = "G1";
    metadata["firmware_version"] = "1.0.0";

    // Serialize JSON
    char payload[512];

    size_t payloadLength =
        serializeJson(doc, payload, sizeof(payload));

    if (payloadLength == 0 || payloadLength >= sizeof(payload)) {
      Serial.println("ERROR: JSON serialization failed");
      return;
    }

    if (doc.overflowed()) {
      Serial.println("JSON document overflow!");
    }

    // Publish to MQTT
    bool success = client.publish(
        mqtt_topic,
        payload
    );

    Serial.print("Topic: ");
    Serial.println(mqtt_topic);

    Serial.print("Payload: ");
    Serial.println(payload);

    Serial.print("Payload length: ");
    Serial.println(payloadLength);

    Serial.print("JSON memory used: ");
    Serial.println(doc.memoryUsage());

    Serial.print("Publish status: ");
    Serial.println(success ? "Success" : "Failed");
  }
}

