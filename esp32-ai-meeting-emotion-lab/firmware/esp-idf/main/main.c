#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_mqtt_client.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"

static const char *TAG = "ai-meeting";
static const int WIFI_READY_BIT = BIT0;
static EventGroupHandle_t wifi_events;
static esp_mqtt_client_handle_t mqtt;
static char state[24] = "booting";
static char active_session[40] = "";
static char active_token[40] = "";
static char active_turn_id[40] = "";
static int active_sequence = 0;

static void topic(char *output, size_t size, const char *suffix) {
    snprintf(output, size, "lab/device/%s/%s", CONFIG_LAB_AGENT_ID, suffix);
}

static void add_timestamp(cJSON *root) {
    time_t now = time(NULL);
    if (now < 1700000000) return;  // Backend assigns receipt time until SNTP has synchronized.
    struct tm utc;
    gmtime_r(&now, &utc);
    char timestamp[28];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utc);
    cJSON_AddStringToObject(root, "timestamp", timestamp);
}

static cJSON *envelope(const char *event_type) {
    cJSON *root = cJSON_CreateObject();
    char message_id[80];
    snprintf(message_id, sizeof(message_id), "%s-%08" PRIx32, CONFIG_LAB_DEVICE_ID, esp_random());
    cJSON_AddStringToObject(root, "schema_version", "mqtt-v1");
    cJSON_AddStringToObject(root, "message_id", message_id);
    add_timestamp(root);
    cJSON_AddStringToObject(root, "agent_id", CONFIG_LAB_AGENT_ID);
    cJSON_AddStringToObject(root, "device_id", CONFIG_LAB_DEVICE_ID);
    cJSON_AddStringToObject(root, "event_type", event_type);
    if (active_session[0]) cJSON_AddStringToObject(root, "session_id", active_session);
    if (active_token[0]) cJSON_AddStringToObject(root, "turn_token", active_token);
    if (active_turn_id[0]) cJSON_AddStringToObject(root, "turn_id", active_turn_id);
    if (active_sequence) cJSON_AddNumberToObject(root, "sequence_number", active_sequence);
    cJSON_AddItemToObject(root, "payload", cJSON_CreateObject());
    return root;
}

static void publish_json(const char *suffix, const char *event_type, cJSON *root, int retain) {
    char mqtt_topic[96];
    topic(mqtt_topic, sizeof(mqtt_topic), suffix);
    char *wire = cJSON_PrintUnformatted(root);
    if (wire) {
        esp_mqtt_client_publish(mqtt, mqtt_topic, wire, 0, 1, retain);
        cJSON_free(wire);
    }
    cJSON_Delete(root);
}

static void publish_heartbeat(void) {
    cJSON *root = envelope("device.heartbeat");
    cJSON_AddStringToObject(cJSON_GetObjectItem(root, "payload"), "state", state);
    publish_json("heartbeat", "device.heartbeat", root, 1);
}

static void publish_register(void) {
    cJSON *root = envelope("device.register");
    cJSON *payload = cJSON_GetObjectItem(root, "payload");
    cJSON_AddStringToObject(payload, "mqtt_client_id", CONFIG_LAB_DEVICE_ID);
    cJSON_AddStringToObject(payload, "firmware_version", CONFIG_LAB_FIRMWARE_VERSION);
    publish_json("register", "device.register", root, 0);
}

static void request_generation(void) {
    strcpy(state, "thinking");
    cJSON *root = envelope("generation.request");
    cJSON_AddStringToObject(cJSON_GetObjectItem(root, "payload"), "requested_by", CONFIG_LAB_DEVICE_ID);
    publish_json("generation/request", "generation.request", root, 0);
    publish_heartbeat();
}

static void publish_turn(const char *text) {
    strcpy(state, "speaking");
    cJSON *root = envelope("turn.published");
    cJSON *payload = cJSON_GetObjectItem(root, "payload");
    cJSON_AddStringToObject(payload, "text", text);
    cJSON_AddStringToObject(payload, "relay", "physical-esp32-idf");
    publish_json("turn/published", "turn.published", root, 0);
    active_token[0] = active_turn_id[0] = '\0';
    active_sequence = 0;
    strcpy(state, "ready");
    publish_heartbeat();
}

static int matches_device_topic(const char *topic_name, const char *suffix) {
    char expected[96];
    topic(expected, sizeof(expected), suffix);
    return strcmp(topic_name, expected) == 0;
}

static void handle_control(cJSON *message) {
    cJSON *payload = cJSON_GetObjectItem(message, "payload");
    cJSON *command = cJSON_GetObjectItem(payload, "event");
    if (!cJSON_IsString(command)) return;
    if (strcmp(command->valuestring, "pause") == 0) strcpy(state, "paused");
    if (strcmp(command->valuestring, "resume") == 0) strcpy(state, "ready");
    if (strcmp(command->valuestring, "stop") == 0) strcpy(state, "stopped");
    active_token[0] = active_turn_id[0] = '\0';
    active_sequence = 0;
    publish_heartbeat();
}

static void handle_mqtt_data(const char *topic_name, const char *data, int length) {
    cJSON *message = cJSON_ParseWithLength(data, length);
    if (!message) return;
    cJSON *agent = cJSON_GetObjectItem(message, "agent_id");
    cJSON *session = cJSON_GetObjectItem(message, "session_id");
    cJSON *token = cJSON_GetObjectItem(message, "turn_token");
    cJSON *turn_id = cJSON_GetObjectItem(message, "turn_id");
    cJSON *sequence = cJSON_GetObjectItem(message, "sequence_number");

    if (matches_device_topic(topic_name, "control")) {
        handle_control(message);
    } else if (matches_device_topic(topic_name, "turn/grant") &&
               strcmp(state, "ready") == 0 && cJSON_IsString(agent) &&
               strcmp(agent->valuestring, CONFIG_LAB_AGENT_ID) == 0 && cJSON_IsString(session) &&
               cJSON_IsString(token) && cJSON_IsString(turn_id) && cJSON_IsNumber(sequence)) {
        snprintf(active_session, sizeof(active_session), "%s", session->valuestring);
        snprintf(active_token, sizeof(active_token), "%s", token->valuestring);
        snprintf(active_turn_id, sizeof(active_turn_id), "%s", turn_id->valuestring);
        active_sequence = sequence->valueint;
        strcpy(state, "listening");
        request_generation();
    } else if (matches_device_topic(topic_name, "generation/response") && cJSON_IsString(session) &&
               cJSON_IsString(token) && cJSON_IsString(turn_id) &&
               strcmp(session->valuestring, active_session) == 0 &&
               strcmp(token->valuestring, active_token) == 0 &&
               strcmp(turn_id->valuestring, active_turn_id) == 0) {
        cJSON *payload = cJSON_GetObjectItem(message, "payload");
        cJSON *text = cJSON_GetObjectItem(payload, "text");
        if (cJSON_IsString(text) && text->valuestring[0]) publish_turn(text->valuestring);
    }
    cJSON_Delete(message);
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t event_id, void *event_data) {
    (void)arg;
    (void)base;
    esp_mqtt_event_handle_t event = event_data;
    if (event_id == MQTT_EVENT_CONNECTED) {
        char grant[96], response[96], control[96];
        topic(grant, sizeof(grant), "turn/grant");
        topic(response, sizeof(response), "generation/response");
        topic(control, sizeof(control), "control");
        esp_mqtt_client_subscribe(mqtt, grant, 1);
        esp_mqtt_client_subscribe(mqtt, response, 1);
        esp_mqtt_client_subscribe(mqtt, control, 1);
        esp_mqtt_client_subscribe(mqtt, "lab/session/+/context", 1);
        strcpy(state, "registering");
        publish_register();
        strcpy(state, "ready");
        publish_heartbeat();
    } else if (event_id == MQTT_EVENT_DATA) {
        char mqtt_topic[128];
        int copy = event->topic_len < (int)sizeof(mqtt_topic) - 1 ? event->topic_len : (int)sizeof(mqtt_topic) - 1;
        memcpy(mqtt_topic, event->topic, copy);
        mqtt_topic[copy] = '\0';
        handle_mqtt_data(mqtt_topic, event->data, event->data_len);
    } else if (event_id == MQTT_EVENT_DISCONNECTED) {
        strcpy(state, "disconnected");
    }
}

static void start_mqtt(void) {
    strcpy(state, "mqtt_connecting");
    static char lwt_topic[96];
    static char lwt_message[384];
    topic(lwt_topic, sizeof(lwt_topic), "heartbeat");
    snprintf(
        lwt_message,
        sizeof(lwt_message),
        "{\"schema_version\":\"mqtt-v1\",\"message_id\":\"%s-lwt\",\"agent_id\":\"%s\","
        "\"device_id\":\"%s\",\"event_type\":\"device.disconnected\","
        "\"payload\":{\"state\":\"disconnected\"}}",
        CONFIG_LAB_DEVICE_ID,
        CONFIG_LAB_AGENT_ID,
        CONFIG_LAB_DEVICE_ID
    );
    esp_mqtt_client_config_t config = {
        .broker.address.uri = CONFIG_LAB_MQTT_URI,
        .credentials.username = CONFIG_LAB_MQTT_USERNAME,
        .credentials.authentication.password = CONFIG_LAB_MQTT_PASSWORD,
        .session.last_will = {
            .topic = lwt_topic,
            .msg = lwt_message,
            .qos = 1,
            .retain = true,
        },
    };
    mqtt = esp_mqtt_client_init(&config);
    esp_mqtt_client_register_event(mqtt, ESP_EVENT_ANY_ID, mqtt_event, NULL);
    esp_mqtt_client_start(mqtt);
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg;
    (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        strcpy(state, "wifi_connecting");
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(wifi_events, WIFI_READY_BIT);
}

static void start_wifi(void) {
    strcpy(state, "wifi_connecting");
    wifi_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL, NULL));
    wifi_config_t config = {0};
    snprintf((char *)config.sta.ssid, sizeof(config.sta.ssid), "%s", CONFIG_LAB_WIFI_SSID);
    snprintf((char *)config.sta.password, sizeof(config.sta.password), "%s", CONFIG_LAB_WIFI_PASSWORD);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
}

void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    start_wifi();
    xEventGroupWaitBits(wifi_events, WIFI_READY_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
    esp_sntp_setoperatingmode(ESP_SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
    start_mqtt();
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(4000));
        if (mqtt && strcmp(state, "disconnected") != 0) publish_heartbeat();
    }
}
