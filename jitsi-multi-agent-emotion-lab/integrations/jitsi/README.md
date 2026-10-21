# Jitsi adapter boundary

`backend/app/integrations/jitsi.py` contains the narrow contract between persisted WAV artifacts and a trusted Ubuntu host-side playback runner. The actual PulseAudio/PipeWire device commands remain in [`scripts/`](../../scripts/) because a Dockerized web backend normally does not own the logged-in browser's audio server.

This folder intentionally does not claim an implementation of four Jitsi bots or raw participant-audio ingestion. See [JITSI_INTEGRATION.md](../../docs/JITSI_INTEGRATION.md) for the consent-gated future-adapter direction.

