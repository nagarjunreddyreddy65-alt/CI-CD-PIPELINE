"""
Telemetry Collector.
Measures real-time execution duration, psutil hardware telemetry (CPU, peak RAM, Disk I/O),
and test execution counters with privacy-aware secret redaction.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import time
import os
import platform
import psutil

from app.core.logging import logger, redact_secrets


@dataclass
class TelemetrySnapshot:
    cpu_percent_avg: float
    memory_mb_peak: float
    disk_io_mb: float
    total_duration_sec: float
    test_duration_sec: float
    test_count: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    runner_os: str
    collected_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TelemetryCollector:
    """Collects system performance telemetry during pipeline execution."""

    def __init__(self):
        self.os_name = f"{platform.system()} {platform.release()}"

    def capture_instant_metrics(self) -> Dict[str, float]:
        """Captures an instantaneous snapshot of current system resources."""
        proc = psutil.Process(os.getpid())
        mem_info = proc.memory_info()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_mb": round(mem_info.rss / (1024 * 1024), 2),
        }

    def create_snapshot(
        self,
        cpu_percent_avg: float,
        memory_mb_peak: float,
        disk_io_mb: float,
        total_duration_sec: float,
        test_duration_sec: float,
        test_count: int,
        tests_passed: int,
        tests_failed: int,
        tests_skipped: int = 0,
        runner_os: Optional[str] = None,
    ) -> TelemetrySnapshot:
        """Constructs a validated TelemetrySnapshot instance."""
        return TelemetrySnapshot(
            cpu_percent_avg=max(0.0, round(float(cpu_percent_avg), 2)),
            memory_mb_peak=max(0.0, round(float(memory_mb_peak), 2)),
            disk_io_mb=max(0.0, round(float(disk_io_mb), 2)),
            total_duration_sec=max(0.0, round(float(total_duration_sec), 2)),
            test_duration_sec=max(0.0, round(float(test_duration_sec), 2)),
            test_count=max(0, int(test_count)),
            tests_passed=max(0, int(tests_passed)),
            tests_failed=max(0, int(tests_failed)),
            tests_skipped=max(0, int(tests_skipped)),
            runner_os=runner_os or self.os_name,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )
