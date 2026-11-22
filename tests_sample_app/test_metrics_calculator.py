"""Unit tests for sample_app.analytics.metrics_calculator."""

from sample_app.analytics.metrics_calculator import (
    analyze_test_run_stability,
    calculate_percentiles,
    calculate_pipeline_throughput,
)


def test_pipeline_throughput():
    assert calculate_pipeline_throughput(24, 2.0) == 12.0
    assert calculate_pipeline_throughput(10, 0.0) == 0.0


def test_calculate_percentiles():
    durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    pct = calculate_percentiles(durations)
    assert pct["p50"] == 50.0
    assert pct["p90"] == 90.0
    assert pct["p95"] == 100.0


def test_test_run_stability():
    stable_runs = [10.0, 10.2, 9.8, 10.1, 9.9]
    result = analyze_test_run_stability(stable_runs)
    assert result["is_stable"] is True
    assert result["mean_duration"] == 10.0
