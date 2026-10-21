FROM eclipse-mosquitto:2.0
COPY docker/mosquitto/mosquitto.conf /mosquitto/config/mosquitto.conf
COPY docker/mosquitto/aclfile /mosquitto/config/aclfile
COPY docker/mosquitto/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

