idf_component_register(
  SRCS "main.c"
  INCLUDE_DIRS "."
  REQUIRES esp_event esp_netif esp_wifi mqtt nvs_flash json lwip
)
