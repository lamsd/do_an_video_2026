from __future__ import annotations

from enum import StrEnum


class DeviceState(StrEnum):
    BOOTING = "booting"
    WIFI_CONNECTING = "wifi_connecting"
    MQTT_CONNECTING = "mqtt_connecting"
    REGISTERING = "registering"
    READY = "ready"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    PAUSED = "paused"
    STOPPED = "stopped"
    DISCONNECTED = "disconnected"
    ERROR = "error"


ALLOWED_TRANSITIONS: dict[DeviceState, set[DeviceState]] = {
    DeviceState.BOOTING: {DeviceState.WIFI_CONNECTING, DeviceState.ERROR},
    DeviceState.WIFI_CONNECTING: {DeviceState.MQTT_CONNECTING, DeviceState.DISCONNECTED, DeviceState.ERROR},
    DeviceState.MQTT_CONNECTING: {DeviceState.REGISTERING, DeviceState.DISCONNECTED, DeviceState.ERROR},
    DeviceState.REGISTERING: {DeviceState.READY, DeviceState.DISCONNECTED, DeviceState.ERROR},
    DeviceState.READY: {DeviceState.LISTENING, DeviceState.PAUSED, DeviceState.STOPPED, DeviceState.DISCONNECTED, DeviceState.ERROR},
    DeviceState.LISTENING: {
        DeviceState.THINKING,
        DeviceState.READY,
        DeviceState.PAUSED,
        DeviceState.STOPPED,
        DeviceState.DISCONNECTED,
        DeviceState.ERROR,
    },
    DeviceState.THINKING: {
        DeviceState.SPEAKING,
        DeviceState.PAUSED,
        DeviceState.STOPPED,
        DeviceState.DISCONNECTED,
        DeviceState.ERROR,
    },
    DeviceState.SPEAKING: {
        DeviceState.READY,
        DeviceState.PAUSED,
        DeviceState.STOPPED,
        DeviceState.DISCONNECTED,
        DeviceState.ERROR,
    },
    DeviceState.PAUSED: {DeviceState.READY, DeviceState.STOPPED, DeviceState.DISCONNECTED},
    DeviceState.STOPPED: {DeviceState.READY, DeviceState.DISCONNECTED},
    DeviceState.DISCONNECTED: {DeviceState.WIFI_CONNECTING, DeviceState.ERROR},
    DeviceState.ERROR: {DeviceState.WIFI_CONNECTING, DeviceState.DISCONNECTED},
}


def can_transition(current: DeviceState, next_state: DeviceState) -> bool:
    return next_state in ALLOWED_TRANSITIONS[current]

