from app.state import DeviceState, can_transition


def test_device_state_machine_rejects_turn_before_registration() -> None:
    assert can_transition(DeviceState.BOOTING, DeviceState.WIFI_CONNECTING)
    assert can_transition(DeviceState.READY, DeviceState.LISTENING)
    assert can_transition(DeviceState.LISTENING, DeviceState.THINKING)
    assert not can_transition(DeviceState.BOOTING, DeviceState.THINKING)
    assert not can_transition(DeviceState.SPEAKING, DeviceState.THINKING)

