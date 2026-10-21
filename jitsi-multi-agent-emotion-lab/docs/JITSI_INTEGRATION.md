# Jitsi integration boundary

This prototype sends generated WAV files to a virtual microphone on an Ubuntu desktop. It does **not** implement four independent Jitsi meeting bots, receive participant audio, or claim that the Jitsi IFrame API exposes raw audio tracks.

## Generated-audio MVP

1. In the logged-in desktop session, run `./scripts/setup_virtual_audio.sh`.
2. Run `./scripts/check_virtual_audio.sh`; it must list `JitsiLabSink` and `JitsiLabMic`.
3. Open a Jitsi meeting in a browser and select **JitsiLabMic** in the microphone/device settings.
4. Route an exported/generated sample with `./scripts/play_audio_to_jitsi.sh data/media/<session>/<turn>.wav`.
5. Run `./scripts/cleanup_virtual_audio.sh` after the experiment.

The playback script holds a lock until `paplay` exits, so an operator-driven playback queue remains sequential. Browser Jitsi captures only the virtual microphone source selected in its device settings; no physical microphone is needed.

## PipeWire and PulseAudio

Most current Ubuntu desktop installations expose PipeWire through the PulseAudio-compatible `pactl`/`paplay` tools. The scripts use that compatibility layer and must be run by the same logged-in user whose browser joins Jitsi. A headless Docker container normally cannot access that user audio server safely.

## Future participant-audio adapter

For participant audio research, add an adapter behind an interface such as:

```python
class ParticipantAudioAdapter(Protocol):
    async def subscribe(self, meeting_id: str, consent_record_id: str) -> AsyncIterator[AudioFrame]: ...
```

The adapter should be implemented only with a Jitsi/media integration that explicitly provides raw tracks and after consent, retention, access control, encryption, and a withdrawal/deletion workflow are approved. The IFrame API is appropriate for embedding and controlling a meeting UI but is not a raw-media ingestion interface.

