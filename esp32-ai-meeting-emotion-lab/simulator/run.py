from __future__ import annotations

import logging
import os
import time

from app.identities import AGENTS

from simulator.device import SimulatorConnection, VirtualEsp32


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    devices = []
    for agent in AGENTS:
        password_key = f"MQTT_{agent.agent_id.upper()}_PASSWORD"
        password = os.getenv(password_key)
        if not password:
            raise RuntimeError(f"{password_key} must be set for simulator device {agent.device_id}")
        device = VirtualEsp32(agent, SimulatorConnection(host, port, password))
        device.start()
        devices.append(device)
    try:
        while True:
            for device in devices:
                device.tick()
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for device in devices:
            device.stop()


if __name__ == "__main__":
    main()

