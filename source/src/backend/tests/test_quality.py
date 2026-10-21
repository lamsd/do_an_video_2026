from app.analysis.quality import evaluate_segment, normalize_text


def test_normalize_text_preserves_vietnamese_diacritics():
    assert normalize_text("  Bạn   đến  từ  đâu? ") == "Bạn đến từ đâu?"


def test_known_youtube_hallucination_is_rejected():
    decision = evaluate_segment(
        text="Hãy subscribe cho kênh La La School Để không bỏ lỡ những video hấp dẫn",
        upstream_language="vi",
        is_final=True,
        retracted=False,
        duration=3,
    )
    assert decision.status == "rejected"
    assert "known_hallucination" in decision.reasons


def test_partial_youtube_hallucination_is_rejected():
    decision = evaluate_segment(
        text="Kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn",
        upstream_language="vi",
        is_final=True,
        retracted=False,
        duration=3,
    )
    assert decision.status == "rejected"
    assert "known_hallucination" in decision.reasons


def test_vietnamese_text_overrides_bad_upstream_language():
    decision = evaluate_segment(
        text="Bạn đến từ đâu vậy?",
        upstream_language="en",
        is_final=True,
        retracted=False,
        duration=2,
    )
    assert decision.status == "accepted"
    assert decision.language == "vi"
