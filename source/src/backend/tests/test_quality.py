from app.analysis.quality import evaluate_segment, normalize_text, route_language


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


def test_subscribe_variant_is_rejected_before_analytics():
    decision = evaluate_segment(
        text="Đừng quên nhấn đăng ký kênh và bật chuông thông báo nhé",
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
    assert decision.language_source == "content_override_upstream"


def test_router_marks_code_switched_text_as_mixed_instead_of_vietnamese():
    language, source = route_language("Cảm ơn team, please review the report", "vi")

    assert language == "mixed"
    assert source == "content_mixed"


def test_router_uses_english_content_when_provider_language_is_wrong():
    language, source = route_language("Please review the meeting notes", "vi")

    assert language == "en"
    assert source == "content_override_upstream"


def test_router_keeps_ambiguous_text_unknown_without_provider_metadata():
    language, source = route_language("OK 123", None)

    assert language == "unknown"
    assert source == "insufficient_evidence"


def test_foreign_script_is_kept_for_audit_but_rejected_from_analytics():
    decision = evaluate_segment(
        text="นี่คือเสียงรบกวน",
        # This mirrors the failure mode of a forced/default language metadata
        # value: the source text itself must still protect analytics.
        upstream_language="vi",
        is_final=True,
        retracted=False,
        duration=2,
    )

    assert decision.status == "rejected"
    assert "unsupported_script" in decision.reasons
