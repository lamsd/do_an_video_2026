from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings
from app.protocol import Envelope

log = logging.getLogger(__name__)
MessageHandler = Callable[[str, Envelope], None]


class MqttBridge:
    """One backend MQTT client; it has coordinator-only broker permissions."""

    def __init__(self, settings: Settings, handler: MessageHandler):
        self.settings = settings
        self.handler = handler
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="meeting-backend-coordinator",
            protocol=mqtt.MQTTv311,
        )
        self.client.username_pw_set("backend", settings.mqtt_backend_password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mqtt-coordinator")

    def start(self) -> None:
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
        self.client.loop_start()

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        self.worker.shutdown(wait=True, cancel_futures=True)

    def publish(self, topic: str, envelope: Envelope, retain: bool = False) -> None:
        result = self.client.publish(topic, envelope.as_json_bytes(), qos=1, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed for {topic}: rc={result.rc}")

    def _on_connect(
        self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any
    ) -> None:
        if reason_code != 0:
            log.error("MQTT backend connection failed: %s", reason_code)
            return
        self.client.subscribe("lab/#", qos=1)
        log.info("MQTT coordinator connected and subscribed")

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _p: Any) -> None:
        log.warning("MQTT coordinator disconnected: %s", reason_code)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            envelope = Envelope.model_validate(json.loads(message.payload.decode("utf-8")))
            # Paho's network loop must stay free for heartbeats while TTS/analysis runs.
            self.worker.submit(self.handler, message.topic, envelope)
        except Exception:
            log.exception("Discarded invalid MQTT message on %s", message.topic)

