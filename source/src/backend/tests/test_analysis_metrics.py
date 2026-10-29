from app.repositories.analysis import run_metrics


def test_run_metrics_keeps_operational_coverage_and_batch_duration_distinct():
    metrics = run_metrics(
        total_units=10,
        accepted_units=8,
        predicted_units=6,
        inference_total_ms=37,
    )

    assert metrics == {
        "unit_count": 10,
        "accepted_unit_count": 8,
        "predicted_unit_count": 6,
        "acceptance_rate": 0.8,
        "prediction_coverage": 0.75,
        "effective_coverage": 0.6,
        "coverage": 0.75,
        "inference_total_ms": 37,
    }


def test_run_metrics_handles_an_empty_transcript_without_a_division_error():
    metrics = run_metrics(
        total_units=0,
        accepted_units=0,
        predicted_units=0,
        inference_total_ms=0,
    )

    assert metrics["acceptance_rate"] == 0
    assert metrics["prediction_coverage"] == 0
    assert metrics["effective_coverage"] == 0
