#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#include "secrets.h"

#ifndef AGENT_ID
#error "Build a named PlatformIO environment such as -e esp32-01."
#endif
#ifndef DEVICE_ID
#error "A fixed DEVICE_ID is required for every physical board."
#endif

namespace {
constexpr unsigned long HEARTBEAT_INTERVAL_MS = 4000;
constexpr size_t JSON_CAPACITY = 1536;

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
String activeSessionId;
String activeTurnToken;
String activeTurnId;
unsigned long activeSequenceNumber = 0;
String sharedDiscussionTopic;
String deviceState = "booting";
unsigned long lastHeartbeatAt = 0;

String deviceRoot() { return String("lab/device/") + AGENT_ID + "/"; }
String heartbeatTopic() { return deviceRoot() + "heartbeat"; }
String grantTopic() { return deviceRoot() + "turn/grant"; }
String generationResponseTopic() { return deviceRoot() + "generation/response"; }
String controlTopic() { return deviceRoot() + "control"; }

const char* mqttPassword() {
  if (String(AGENT_ID) == "empathy") return MQTT_EMPATHY_PASSWORD;
  if (String(AGENT_ID) == "critical") return MQTT_CRITICAL_PASSWORD;
  if (String(AGENT_ID) == "optimistic") return MQTT_OPTIMISTIC_PASSWORD;
  return MQTT_MODERATOR_PASSWORD;
}

String utcTimestamp() {
  const time_t now = time(nullptr);
  if (now < 1700000000) return "";
  struct tm utc;
  gmtime_r(&now, &utc);
  char buffer[28];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return String(buffer);
}

void addEnvelope(JsonDocument& doc, const char* eventType, const String& sessionId = "", const String& token = "") {
  doc["schema_version"] = "mqtt-v1";
  doc["message_id"] = String(DEVICE_ID) + "-" + String((uint32_t)esp_random(), HEX);
  const String timestamp = utcTimestamp();
  if (timestamp.length()) doc["timestamp"] = timestamp;
  doc["agent_id"] = AGENT_ID;
  doc["device_id"] = DEVICE_ID;
  doc["event_type"] = eventType;
  if (sessionId.length()) doc["session_id"] = sessionId;
  if (token.length()) doc["turn_token"] = token;
  if (activeTurnId.length()) doc["turn_id"] = activeTurnId;
  if (activeSequenceNumber) doc["sequence_number"] = activeSequenceNumber;
}

bool publishJson(const String& topic, JsonDocument& doc, bool retain = false) {
  char buffer[JSON_CAPACITY];
  const size_t length = serializeJson(doc, buffer, sizeof(buffer));
  return mqtt.publish(topic.c_str(), reinterpret_cast<const uint8_t*>(buffer), length, retain);
}

void publishHeartbeat() {
  JsonDocument doc;
  addEnvelope(doc, "device.heartbeat", activeSessionId, activeTurnToken);
  doc["payload"]["state"] = deviceState;
  publishJson(heartbeatTopic(), doc, true);
  lastHeartbeatAt = millis();
}

void requestGeneration(const String& sessionId, const String& token) {
  JsonDocument doc;
  addEnvelope(doc, "generation.request", sessionId, token);
  doc["payload"]["requested_by"] = DEVICE_ID;
  deviceState = "thinking";
  publishJson(deviceRoot() + "generation/request", doc);
  publishHeartbeat();
}

void publishTurn(const String& text) {
  JsonDocument doc;
  addEnvelope(doc, "turn.published", activeSessionId, activeTurnToken);
  doc["payload"]["text"] = text;
  doc["payload"]["relay"] = "physical-esp32";
  deviceState = "speaking";
  publishJson(deviceRoot() + "turn/published", doc);
  activeTurnToken = "";
  activeTurnId = "";
  activeSequenceNumber = 0;
  deviceState = "ready";
  publishHeartbeat();
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return;
  const String incomingTopic(topic);
  const String agentId = doc["agent_id"] | "";
  const String sessionId = doc["session_id"] | "";
  const String token = doc["turn_token"] | "";
  const String turnId = doc["turn_id"] | "";
  const unsigned long sequenceNumber = doc["sequence_number"] | 0;

  if (incomingTopic == grantTopic()) {
    if (agentId != AGENT_ID || !sessionId.length() || !token.length() || !turnId.length() || !sequenceNumber || deviceState != "ready") return;
    activeSessionId = sessionId;
    activeTurnToken = token;
    activeTurnId = turnId;
    activeSequenceNumber = sequenceNumber;
    deviceState = "listening";
    requestGeneration(activeSessionId, activeTurnToken);
    return;
  }
  if (incomingTopic == generationResponseTopic()) {
    if (sessionId != activeSessionId || token != activeTurnToken || turnId != activeTurnId) return;
    const String text = doc["payload"]["text"] | "";
    if (text.length()) publishTurn(text);
    return;
  }
  if (incomingTopic.startsWith("lab/session/") && incomingTopic.endsWith("/context")) {
    if (sessionId.length()) activeSessionId = sessionId;
    sharedDiscussionTopic = doc["payload"]["topic"] | "";
  }
  if (incomingTopic == controlTopic()) {
    const String command = doc["payload"]["event"] | "";
    if (command == "pause") {
      activeTurnToken = "";
      activeTurnId = "";
      activeSequenceNumber = 0;
      deviceState = "paused";
    } else if (command == "resume") {
      activeTurnToken = "";
      activeTurnId = "";
      activeSequenceNumber = 0;
      deviceState = "ready";
    } else if (command == "stop") {
      activeTurnToken = "";
      activeTurnId = "";
      activeSequenceNumber = 0;
      deviceState = "stopped";
    }
    publishHeartbeat();
  }
}

void connectWifi() {
  deviceState = "wifi_connecting";
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
  }
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void connectMqtt() {
  deviceState = "mqtt_connecting";
  while (!mqtt.connected()) {
    String clientId = DEVICE_ID;
    JsonDocument lastWill;
    addEnvelope(lastWill, "device.disconnected");
    lastWill["payload"]["state"] = "disconnected";
    char lwt[256];
    serializeJson(lastWill, lwt, sizeof(lwt));
    if (mqtt.connect(clientId.c_str(), AGENT_ID, mqttPassword(), heartbeatTopic().c_str(), 1, true, lwt)) {
      mqtt.subscribe(grantTopic().c_str(), 1);
      mqtt.subscribe(generationResponseTopic().c_str(), 1);
      mqtt.subscribe(controlTopic().c_str(), 1);
      mqtt.subscribe("lab/session/+/context", 1);
      JsonDocument registerDoc;
      addEnvelope(registerDoc, "device.register");
      registerDoc["payload"]["mqtt_client_id"] = clientId;
      registerDoc["payload"]["firmware_version"] = FIRMWARE_VERSION;
      deviceState = "registering";
      publishJson(deviceRoot() + "register", registerDoc);
      deviceState = "ready";
      publishHeartbeat();
    } else {
      delay(1500);
    }
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  connectWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(2048);
  mqtt.setCallback(onMqttMessage);
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
  if (millis() - lastHeartbeatAt >= HEARTBEAT_INTERVAL_MS) publishHeartbeat();
}

