import re
import unicodedata

from .contracts import QualityDecision

HALLUCINATION_PATTERNS = (
    re.compile(r"\bsubscribe\s+cho\s+k[eê]nh\b", re.IGNORECASE),
    re.compile(r"\bc[aả]m\s+[oơ]n\s+c[aá]c\s+b[aạ]n\s+[dđ][aã]\s+theo\s+d[oõ]i\b", re.IGNORECASE),
    re.compile(r"\bgracias\s+por\s+ver\s+el\s+video\b", re.IGNORECASE),
)
VIETNAMESE_MARKERS = re.compile(r"[ăâđêôơưĂÂĐÊÔƠƯ]|\b(bạn|của|không|cho|và|là|mình)\b", re.IGNORECASE)
WORD = re.compile(r"\w+", re.UNICODE)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def route_language(text: str, upstream_language: str | None) -> str:
    if VIETNAMESE_MARKERS.search(text):
        return "vi"
    upstream = (upstream_language or "").lower()
    return upstream if upstream in {"en", "vi"} else "other"


def evaluate_segment(
    *, text: str, upstream_language: str | None, is_final: bool, retracted: bool, duration: float
) -> QualityDecision:
    normalized = normalize_text(text)
    language = route_language(normalized, upstream_language)
    reasons: list[str] = []
    if not is_final:
        reasons.append("not_final")
    if retracted:
        reasons.append("retracted")
    if duration < 0:
        reasons.append("invalid_duration")
    if len(WORD.findall(normalized)) < 3:
        reasons.append("too_short")
    if any(pattern.search(normalized) for pattern in HALLUCINATION_PATTERNS):
        reasons.append("known_hallucination")
    if not normalized:
        reasons.append("empty_text")
    return QualityDecision(
        status="accepted" if not reasons else "rejected",
        reasons=reasons,
        normalized_text=normalized,
        language=language,
    )
