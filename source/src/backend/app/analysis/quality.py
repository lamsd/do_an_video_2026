import re
import unicodedata

from .contracts import QualityDecision

HALLUCINATION_PATTERNS = (
    re.compile(r"\bsubscribe\s+cho\s+k[eê]nh\b", re.IGNORECASE),
    re.compile(
        r"\bk[eê]nh\s+.+?\s+(?:đ[eêếể]\s+)?kh[oô]ng\s+b[oỏ]\s+l[ơỡ]\s+nh[ưữ]ng\s+video\s+h[aấ]p\s+d[aẫ]n\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:h[aã]y\s+|đ[ừu]ng\s+qu[eê]n\s+)?(?:nh[aấ]n|b[aấ]m)?\s*"
        r"(?:n[uú]t\s+)?(?:đ[aă]ng\s*k[ýy]|subscribe)\s+(?:cho\s+|v[aà]o\s+)?"
        r"(?:k[eê]nh|channel)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:like|th[ií]ch)\b.{0,40}\b(?:đ[aă]ng\s*k[ýy]|subscribe)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bc[aả]m\s+[oơ]n\s+c[aá]c\s+b[aạ]n\s+[dđ][aã]\s+theo\s+d[oõ]i\b", re.IGNORECASE),
    re.compile(
        r"\b(?:c[aả]m\s+[oơ]n|thank(?:s|\s+you))\b.{0,80}"
        r"\b(?:đ[aã]\s+theo\s+d[oõ]i|for\s+watching)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bh[eẹ]n\s+g[aặ]p\s+l[aạ]i\b.{0,80}\b(?:video|k[eê]nh|channel)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bgracias\s+por\s+ver\s+el\s+video\b", re.IGNORECASE),
)
VIETNAMESE_MARKERS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯ]|\b(bạn|của|không|cho|và|là|mình|được|với|trong|nhưng)\b",
    re.IGNORECASE,
)
ENGLISH_MARKERS = re.compile(
    r"\b(the|and|is|are|this|that|we|you|please|thank|meeting|will|can|for|with|to)\b",
    re.IGNORECASE,
)
WORD = re.compile(r"\w+", re.UNICODE)
# Vietnamese never needs Thai, Han/CJK, Japanese or Korean code points.  An
# auto-language Whisper guess can label a tiny noise burst as one of these;
# surface the raw source for audit, but never let that burst become analytics
# input simply because an upstream language field happened to say ``vi``.
UNSUPPORTED_SCRIPT = re.compile(r"[\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def _canonical_upstream_language(value: str | None) -> str | None:
    """Normalize provider language tags without treating them as ground truth."""
    normalized = (value or "").strip().lower().replace("_", "-")
    if normalized == "vi" or normalized.startswith("vi-"):
        return "vi"
    if normalized == "en" or normalized.startswith("en-"):
        return "en"
    if normalized in {"mixed", "multilingual", "code-switch", "code-switched"}:
        return "mixed"
    return None


def route_language(text: str, upstream_language: str | None) -> tuple[str, str]:
    """Return a conservative language route and the evidence used to choose it.

    This is intentionally a routing heuristic, not a language-identification
    model.  Ambiguous text stays ``unknown`` and code-switched text stays
    ``mixed`` so a Vietnamese-only classifier cannot silently consume it.
    """
    upstream = _canonical_upstream_language(upstream_language)
    has_vietnamese_signal = bool(VIETNAMESE_MARKERS.search(text))
    has_english_signal = bool(ENGLISH_MARKERS.search(text))

    if has_vietnamese_signal and has_english_signal:
        return "mixed", "content_mixed"
    if has_vietnamese_signal:
        return "vi", "content_override_upstream" if upstream not in {None, "vi"} else "content"
    if has_english_signal:
        return "en", "content_override_upstream" if upstream not in {None, "en"} else "content"
    if upstream is not None:
        return upstream, "upstream"
    return "unknown", "insufficient_evidence"


def evaluate_segment(
    *, text: str, upstream_language: str | None, is_final: bool, retracted: bool, duration: float
) -> QualityDecision:
    normalized = normalize_text(text)
    language, language_source = route_language(normalized, upstream_language)
    reasons: list[str] = []
    if not is_final:
        reasons.append("not_final")
    if retracted:
        reasons.append("retracted")
    if duration < 0:
        reasons.append("invalid_duration")
    if len(WORD.findall(normalized)) < 3:
        reasons.append("too_short")
    if UNSUPPORTED_SCRIPT.search(normalized):
        reasons.append("unsupported_script")
    if any(pattern.search(normalized) for pattern in HALLUCINATION_PATTERNS):
        reasons.append("known_hallucination")
    if not normalized:
        reasons.append("empty_text")
    return QualityDecision(
        status="accepted" if not reasons else "rejected",
        reasons=reasons,
        normalized_text=normalized,
        language=language,
        language_source=language_source,
    )
