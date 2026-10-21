from __future__ import annotations

import asyncio
from collections.abc import Sequence

from app.agents.profiles import AgentProfile
from app.config import Settings


class ChatGenerator:
    """OpenAI-backed text generation with an explicitly labeled offline fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def generate(
        self, profile: AgentProfile, topic: str, history: Sequence[tuple[str, str]]
    ) -> tuple[str, str]:
        if not self.settings.openai_api_key:
            return self._offline_reply(profile, topic, history), "offline-template"
        return await asyncio.to_thread(self._openai_reply, profile, topic, history), "openai-responses"

    def _openai_reply(
        self, profile: AgentProfile, topic: str, history: Sequence[tuple[str, str]]
    ) -> str:
        from openai import OpenAI

        conversation = "\n".join(f"{speaker}: {text}" for speaker, text in history[-12:])
        prompt = (
            f"Discussion topic: {topic}\n\nShared discussion context:\n{conversation or '(opening turn)'}\n\n"
            "Give one response of at most 120 words. Clearly engage with the immediately preceding "
            "point when there is one."
        )
        client = OpenAI(api_key=self.settings.openai_api_key)
        response = client.responses.create(
            model=self.settings.openai_chat_model,
            instructions=profile.system_prompt,
            input=prompt,
        )
        text = (response.output_text or "").strip()
        if not text:
            raise RuntimeError("OpenAI returned an empty discussion turn")
        return text

    @staticmethod
    def _offline_reply(
        profile: AgentProfile, topic: str, history: Sequence[tuple[str, str]]) -> str:
        previous = history[-1][1] if history else "the initial framing"
        templates = {
            "empathy": (
                f"A helpful starting point for “{topic}” is to keep the people affected by the decision "
                f"visible. Building on {previous[:110]!r}, we could ask what support and explanation "
                "participants would need to engage safely."
            ),
            "critical": (
                f"The proposal around “{topic}” is promising, but we should separate assumptions from "
                f"evidence. The previous point ({previous[:110]!r}) needs a measurable success criterion, "
                "a comparison condition, and a clear privacy boundary."
            ),
            "optimistic": (
                f"There is a practical path forward for “{topic}”: start with a small, consent-based pilot "
                f"and learn from the prior point ({previous[:110]!r}). A reversible prototype and transparent "
                "feedback loop can make progress without overstating conclusions."
            ),
            "moderator": (
                f"This round connects support, evidence, and an incremental pilot for “{topic}”. We agree "
                "that safeguards and evaluation matter; the key open question is: which outcome and consent "
                "signal must be validated before the next round?"
            ),
        }
        return templates[profile.id]

