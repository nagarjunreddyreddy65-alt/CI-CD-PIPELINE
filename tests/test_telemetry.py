"""
Unit Tests for Hardware Telemetry Collection.
"""

import pytest
from app.telemetry.collector import TelemetryCollector, TelemetrySnapshot


def test_telemetry_snapshot_creation():
    collector = TelemetryCollector()
    snapshot = collector.create_snapshot(
        cpu_percent_avg=38.5,
        memory_mb_peak=145.2,
        disk_io_mb=5.1,
        total_duration_sec=22.4,
        test_duration_sec=19.1,
        test_count=50,
        tests_passed=48,
        tests_failed=2,
        tests_skipped=0,
    )

    assert snapshot.cpu_percent_avg == 38.5
    assert snapshot.memory_mb_peak == 145.2
    assert snapshot.test_count == 50
    assert snapshot.tests_passed == 48
    assert snapshot.tests_failed == 2
    assert snapshot.tests_skipped == 0
    assert snapshot.runner_os != ""
    assert snapshot.collected_at != ""


def test_telemetry_negative_clamping():
    collector = TelemetryCollector()
    snapshot = collector.create_snapshot(
        cpu_percent_avg=-10.0,
        memory_mb_peak=-50.0,
        disk_io_mb=-1.0,
        total_duration_sec=-5.0,
        test_duration_sec=-2.0,
        test_count=-10,
        tests_passed=-5,
        tests_failed=-1,
    )

    assert snapshot.cpu_percent_avg == 0.0
    assert snapshot.memory_mb_peak == 0.0
    assert snapshot.disk_io_mb == 0.0
    assert snapshot.total_duration_sec == 0.0
    assert snapshot.test_count == 0


def test_instant_metrics_capture():
    collector = TelemetryCollector()
    instant = collector.capture_instant_metrics()
    assert "cpu_percent" in instant
    assert "memory_mb" in instant
    assert instant["memory_mb"] > 0.0
