#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>


// Identifiants Wi-Fi
const char* ssid = "POCO X3 Pro";
const char* password = "HG221A22";

// Paramètres du Broker MQTT
const char* mqtt_broker = "192.168.43.99"; // Adresse IP broker
const int mqtt_port = 1883;             // Port MQTT par défaut
//const char* mqtt_topic = "esp32/test";   // Topic de publication/souscription
const char* mqtt_topic = "enviromesh/devices/G11/telemetry";
// Identifiants d'authentification EMQX (depuis le .env)
const char* mqtt_username = "enviromesh_backend";
const char* mqtt_password = "REPLACE_WITH_ANOTHER_LONG_RANDOM_PASSWORD";


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

}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Exemple : Publier un message toutes les 5 secondes
  static unsigned long lastMsg = 0;
  unsigned long now = millis();
  if (now - lastMsg > 5000) {
    lastMsg = now;
    StaticJsonDocument<512> doc;
    char payload[512];
    const char* msg = "Bonjour depuis l'ESP32 !";
    doc["msg"] = String(msg);
    size_t payloadLength = serializeJson(doc, payload, sizeof(payload));
    if (payloadLength == 0 || payloadLength >= sizeof(payload)) {
      Serial.println("ERROR: Telemetry JSON serialization failed");
      return;
    }
    bool success = client.publish(mqtt_topic, payload);
    Serial.println("\n--- MQTT Transmission ---");
    Serial.print("Payload: ");
    Serial.println(payload);
    Serial.print("Publish status: ");
    Serial.println(success ? "Success" : "Failed");
  }
}
