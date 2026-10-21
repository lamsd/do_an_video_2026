# Research and data guardrails

- Every generated participant is labeled as an AI bot. Do not imply a human authored a bot turn.
- Generated audio is stored under `data/media/<session_id>/`; do not commit it, and delete it under the study's retention policy.
- Collect, store, or process human audio only after explicit, recorded, revocable consent. Add access control, encryption, and an auditable delete operation before any human study.
- Keep human-labelled training/evaluation corpora (for example RAVDESS or CREMA-D) separate from synthetic outputs. Confirm each dataset's licence before use.
- `intended_speaking_style`, any text interpretation, acoustic-model output, and depression risk are different constructs. This application does not calculate depression risk or provide clinical decision support.
- An acoustic emotion result remains `unavailable` until an operator configures a separately evaluated model checkpoint and version. Never report fabricated accuracy, confidence, or benchmark results.

