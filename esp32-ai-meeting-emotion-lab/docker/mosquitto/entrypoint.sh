#!/bin/sh
set -eu

password_file=/mosquitto/config/passwordfile
rm -f "$password_file"
mosquitto_passwd -b -c "$password_file" backend "$MQTT_BACKEND_PASSWORD"
mosquitto_passwd -b "$password_file" empathy "$MQTT_EMPATHY_PASSWORD"
mosquitto_passwd -b "$password_file" critical "$MQTT_CRITICAL_PASSWORD"
mosquitto_passwd -b "$password_file" optimistic "$MQTT_OPTIMISTIC_PASSWORD"
mosquitto_passwd -b "$password_file" moderator "$MQTT_MODERATOR_PASSWORD"

exec mosquitto -c /mosquitto/config/mosquitto.conf

