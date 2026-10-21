from __future__ import annotations

from collections.abc import Sequence

from app.config import Settings
from app.identities import AgentIdentity


class AgentTextGenerator:
    """Backend-only GPT adapter; ESP32 boards never receive an API key."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, agent: AgentIdentity, topic: str, history: Sequence[tuple[str, str]]) -> tuple[str, str]:
        if not self.settings.openai_api_key:
            return self._offline(agent, topic, history), "mau-ngoai-tuyen"
        from openai import OpenAI

        context = "\n".join(f"{speaker}: {text}" for speaker, text in history[-12:])
        own_memory = "\n".join(text for speaker, text in history[-12:] if speaker == agent.agent_id)
        instructions = (
            f"{agent.system_instructions}\n\n"
            f"Phong cách giọng dự kiến: {agent.speaking_style}.\n"
            "Chỉ trả lời bằng tiếng Việt, tối đa 120 từ. Hãy phản hồi trực tiếp các ý trước đó, "
            "không đưa lời khuyên lâm sàng và luôn thể hiện mình là tác nhân AI.\n\n"
            f"Ký ức riêng gần đây của bạn:\n{own_memory or '(chưa có)'}"
        )
        client = OpenAI(api_key=self.settings.openai_api_key)
        response = client.responses.create(
            model=self.settings.openai_chat_model,
            instructions=instructions,
            input=f"Chủ đề: {topic}\n\nNgữ cảnh chung đã được phép chia sẻ:\n{context or '(lượt mở đầu)'}",
        )
        text = response.output_text.strip()
        if not text:
            raise RuntimeError("GPT returned an empty agent turn")
        return text, "openai-responses"

    @staticmethod
    def _offline(agent: AgentIdentity, topic: str, history: Sequence[tuple[str, str]]) -> str:
        prior = history[-1][1] if history else "cách đặt vấn đề ban đầu"
        templates = {
            "empathy": (
                f"Với chủ đề “{topic}”, tôi nghĩ cần đặt trải nghiệm của người tham gia ở vị trí trung tâm. "
                f"Từ ý “{prior[:92]}”, chúng ta có thể hỏi họ cần lời giải thích và sự đồng thuận nào để cảm thấy an toàn?"
            ),
            "critical": (
                f"Với “{topic}”, ý trước đó “{prior[:92]}” cần được tách thành giả định và bằng chứng. "
                "Ta nên xác định chỉ số đo, điều kiện đối chứng và ranh giới dữ liệu tuyệt đối không thu thập."
            ),
            "optimistic": (
                f"Một thử nghiệm nhỏ cho “{topic}” có thể kế thừa ý “{prior[:92]}”: thiết kế có thể đảo ngược, "
                "lấy phản hồi minh bạch và chỉ mở rộng khi các biện pháp bảo vệ đã được kiểm chứng."
            ),
            "moderator": (
                f"Tôi xin điều phối phần này của chủ đề “{topic}”. Các ý chính đang liên kết giữa hỗ trợ con người, "
                "bằng chứng và thử nghiệm từng bước. Câu hỏi tiếp theo là: tín hiệu đồng thuận và thành công nào cần được kiểm chứng?"
            ),
        }
        return templates[agent.agent_id]

