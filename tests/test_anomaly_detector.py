"""
Unit Tests for Statistical Anomaly Detector.
Verifies Z-score calculations, duration spikes, memory surges, and baseline tolerances.
"""

import pytest

from app.telemetry.anomaly_detector import (
    AnomalyReport,
    AnomalyType,
    StatisticalAnomalyDetector,
)


@pytest.fixture
def baseline_history():
    """Historical runs with stable performance ~10s duration, ~100MB RAM, ~25% CPU."""
    return [
        {
            "duration_sec": 10.0,
            "memory_mb_peak": 100.0,
            "cpu_percent_avg": 25.0,
            "failure_rate": 0.05,
        },
        {
            "duration_sec": 10.5,
            "memory_mb_peak": 102.0,
            "cpu_percent_avg": 26.0,
            "failure_rate": 0.05,
        },
        {
            "duration_sec": 9.8,
            "memory_mb_peak": 99.0,
            "cpu_percent_avg": 24.0,
            "failure_rate": 0.04,
        },
        {
            "duration_sec": 10.2,
            "memory_mb_peak": 101.0,
            "cpu_percent_avg": 25.5,
            "failure_rate": 0.06,
        },
        {
            "duration_sec": 10.1,
            "memory_mb_peak": 100.5,
            "cpu_percent_avg": 25.0,
            "failure_rate": 0.05,
        },
        {
            "duration_sec": 9.9,
            "memory_mb_peak": 100.0,
            "cpu_percent_avg": 24.5,
            "failure_rate": 0.05,
        },
    ]


def test_normal_run_no_anomalies(baseline_history):
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=5)
    current = {
        "duration_sec": 10.3,
        "memory_mb_peak": 101.5,
        "cpu_percent_avg": 25.2,
        "failure_rate": 0.05,
    }

    report: AnomalyReport = detector.detect_anomalies(current, baseline_history)
    assert report.is_anomalous is False
    assert len(report.anomalies) == 0


def test_execution_duration_spike(baseline_history):
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=5)
    # Severe duration spike: 35s (historical is ~10s with tiny std)
    current = {
        "duration_sec": 35.0,
        "memory_mb_peak": 102.0,
        "cpu_percent_avg": 25.0,
        "failure_rate": 0.05,
    }

    report: AnomalyReport = detector.detect_anomalies(current, baseline_history)
    assert report.is_anomalous is True
    assert any(a.anomaly_type == AnomalyType.EXECUTION_TIME_SPIKE for a in report.anomalies)


def test_memory_surge(baseline_history):
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=5)
    # Peak memory spike: 500MB (baseline is ~100MB)
    current = {
        "duration_sec": 10.2,
        "memory_mb_peak": 500.0,
        "cpu_percent_avg": 25.0,
        "failure_rate": 0.05,
    }

    report: AnomalyReport = detector.detect_anomalies(current, baseline_history)
    assert report.is_anomalous is True
    assert any(a.anomaly_type == AnomalyType.MEMORY_SURGE for a in report.anomalies)


def test_insufficient_samples():
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=5)
    # Only 2 samples in history
    short_history = [
        {"duration_sec": 10.0},
        {"duration_sec": 11.0},
    ]
    report = detector.detect_anomalies({"duration_sec": 50.0}, short_history)
    assert report.is_anomalous is False
    assert "Insufficient" in report.summary
