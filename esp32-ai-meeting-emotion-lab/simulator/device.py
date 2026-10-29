from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt
from app.identities import AgentIdentity
from app.protocol import Envelope, topic_context, topic_device
from app.state import DeviceState, can_transition

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimulatorConnection:
    host: str
    port: int
    password: str


class VirtualEsp32:
    """One process-level MQTT client per board, following the ESP32 state machine."""

    def __init__(self, identity: AgentIdentity, connection: SimulatorConnection):
        self.identity = identity
        self.connection = connection
        self.state = DeviceState.BOOTING
        self.active_session_id: str | None = None
        self.active_turn_token: str | None = None
        self.active_turn_id: str | None = None
        self.active_sequence_number: int | None = None
        self.last_heartbeat = 0.0
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-{identity.device_id}",
            protocol=mqtt.MQTTv311,
        )
        self.client.username_pw_set(identity.agent_id, connection.password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.client.will_set(
            topic_device(identity.agent_id, "heartbeat"),
            Envelope(
                agent_id=identity.agent_id,
                device_id=identity.device_id,
                event_type="device.disconnected",
                payload={"state": DeviceState.DISCONNECTED},
            ).as_json_bytes(),
            qos=1,
            retain=True,
        )

    def start(self) -> None:
        self._transition(DeviceState.WIFI_CONNECTING)
        self._transition(DeviceState.MQTT_CONNECTING)
        self.client.connect_async(self.connection.host, self.connection.port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        self.state = DeviceState.DISCONNECTED

    def tick(self) -> None:
        if self.state == DeviceState.DISCONNECTED:
            return
        if time.monotonic() - self.last_heartbeat >= 4:
            self._publish_heartbeat()

    def _on_connect(
        self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any
    ) -> None:
        if reason_code != 0:
            self.state = DeviceState.ERROR
            log.error("%s MQTT connect failed: %s", self.identity.device_id, reason_code)
            return
        if self.state == DeviceState.DISCONNECTED:
            self.state = DeviceState.MQTT_CONNECTING
        self._transition(DeviceState.REGISTERING)
        self.client.subscribe(topic_device(self.identity.agent_id, "turn/grant"), qos=1)
        self.client.subscribe(topic_device(self.identity.agent_id, "generation/response"), qos=1)
        self.client.subscribe(topic_device(self.identity.agent_id, "control"), qos=1)
        self.client.subscribe("lab/session/+/context", qos=1)
        self._publish(
            topic_device(self.identity.agent_id, "register"),
            Envelope(
                agent_id=self.identity.agent_id,
                device_id=self.identity.device_id,
                event_type="device.register",
                payload={
                    "mqtt_client_id": f"sim-{self.identity.device_id}",
                    "firmware_version": "simulator-v1",
                },
            ),
        )
        self._transition(DeviceState.READY)
        self._publish_heartbeat()

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _p: Any) -> None:
        self.state = DeviceState.DISCONNECTED
        log.warning("%s MQTT disconnected: %s", self.identity.device_id, reason_code)

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            event = Envelope.model_validate(json.loads(message.payload.decode("utf-8")))
            if message.topic == topic_device(self.identity.agent_id, "turn/grant"):
                self._on_grant(event)
            elif message.topic == topic_device(self.identity.agent_id, "generation/response"):
                self._on_generation_response(event)
            elif message.topic == topic_device(self.identity.agent_id, "control"):
                self._on_control(event)
            elif message.topic == topic_context(event.session_id or ""):
                self.active_session_id = event.session_id
        except Exception:
            self.state = DeviceState.ERROR
            log.exception("%s rejected malformed broker event", self.identity.device_id)

    def _on_grant(self, event: Envelope) -> None:
        if (
            event.agent_id != self.identity.agent_id
            or not event.session_id
            or not event.turn_token
            or not event.turn_id
            or event.sequence_number is None
        ):
            return
        if self.state not in {DeviceState.READY, DeviceState.LISTENING}:
            return
        self.active_session_id = event.session_id
        self.active_turn_token = event.turn_token
        self.active_turn_id = event.turn_id
        self.active_sequence_number = event.sequence_number
        self._transition(DeviceState.LISTENING)
        self._transition(DeviceState.THINKING)
        self._publish(
            topic_device(self.identity.agent_id, "generation/request"),
            Envelope(
                agent_id=self.identity.agent_id,
                device_id=self.identity.device_id,
                session_id=event.session_id,
                turn_token=event.turn_token,
                turn_id=event.turn_id,
                sequence_number=event.sequence_number,
                event_type="generation.request",
                payload={"requested_by": self.identity.device_id},
            ),
        )
        self._publish_heartbeat()

    def _on_generation_response(self, event: Envelope) -> None:
        if event.turn_token != self.active_turn_token or event.session_id != self.active_session_id:
            return
        text = str(event.payload.get("text", "")).strip()
        if not text:
            self.state = DeviceState.ERROR
            return
        self._transition(DeviceState.SPEAKING)
        self._publish(
            topic_device(self.identity.agent_id, "turn/published"),
            Envelope(
                agent_id=self.identity.agent_id,
                device_id=self.identity.device_id,
                session_id=event.session_id,
                turn_token=event.turn_token,
                turn_id=self.active_turn_id,
                sequence_number=self.active_sequence_number,
                event_type="turn.published",
                payload={"text": text, "relay": "mo-phong-thiet-bi-vat-ly"},
            ),
        )
        self.active_turn_token = None
        self.active_turn_id = None
        self.active_sequence_number = None
        self._transition(DeviceState.READY)
        self._publish_heartbeat()

    def _on_control(self, event: Envelope) -> None:
        if event.agent_id != self.identity.agent_id:
            return
        command = str(event.payload.get("event", ""))
        target = {
            "pause": DeviceState.PAUSED,
            "resume": DeviceState.READY,
            "stop": DeviceState.STOPPED,
        }.get(command)
        if target is None or target == self.state:
            return
        if can_transition(self.state, target):
            self._transition(target)
            self.active_turn_token = None
            self.active_turn_id = None
            self.active_sequence_number = None
            self._publish_heartbeat()

    def _publish_heartbeat(self) -> None:
        self.last_heartbeat = time.monotonic()
        self._publish(
            topic_device(self.identity.agent_id, "heartbeat"),
            Envelope(
                agent_id=self.identity.agent_id,
                device_id=self.identity.device_id,
                session_id=self.active_session_id,
                event_type="device.heartbeat",
                payload={"state": self.state},
            ),
            retain=True,
        )

    def _publish(self, topic: str, event: Envelope, retain: bool = False) -> bool:
        result = self.client.publish(topic, event.as_json_bytes(), qos=1, retain=retain)
        if result.rc == mqtt.MQTT_ERR_NO_CONN:
            # Paho reconnects asynchronously. A heartbeat emitted in the small interval
            # before on_connect must not terminate all four simulated devices.
            self.state = DeviceState.DISCONNECTED
            log.warning("%s skipped publish while MQTT reconnects", self.identity.device_id)
            return False
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed on {topic}: {result.rc}")
        return True

    def _transition(self, next_state: DeviceState) -> None:
        if next_state == self.state:
            return
        if not can_transition(self.state, next_state):
            raise RuntimeError(f"Invalid transition {self.state} -> {next_state}")
        self.state = next_state

