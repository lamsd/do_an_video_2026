#!/bin/sh
set -eu

password_file=/mosquitto/data/passwordfile
umask 077
rm -f "$password_file"
mosquitto_passwd -b -c "$password_file" backend "$MQTT_BACKEND_PASSWORD"
mosquitto_passwd -b "$password_file" empathy "$MQTT_EMPATHY_PASSWORD"
mosquitto_passwd -b "$password_file" critical "$MQTT_CRITICAL_PASSWORD"
mosquitto_passwd -b "$password_file" optimistic "$MQTT_OPTIMISTIC_PASSWORD"
mosquitto_passwd -b "$password_file" moderator "$MQTT_MODERATOR_PASSWORD"

# Official Mosquitto images may invoke this entrypoint as root while the broker
# itself runs as the unprivileged mosquitto user. This is harmless when already
# unprivileged and fixes a root-owned 0600 password file otherwise.
chown mosquitto:mosquitto "$password_file" 2>/dev/null || true
chmod 0600 "$password_file"

exec mosquitto -c /mosquitto/config/mosquitto.conf

