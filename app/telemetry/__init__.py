"""
Telemetry & Observability Module.
Provides hardware metrics collection (CPU, Memory, Disk), statistical anomaly detection,
and deterministic failure event correlation.
"""

from app.telemetry.anomaly_detector import (
    AnomalyFinding,
    AnomalyReport,
    AnomalyType,
    StatisticalAnomalyDetector,
)
from app.telemetry.collector import (
    TelemetryCollector,
    TelemetrySnapshot,
)
from app.telemetry.event_correlator import (
    CorrelatedEventGroup,
    EventCorrelator,
)

__all__ = [
    "AnomalyFinding",
    "AnomalyReport",
    "AnomalyType",
    "CorrelatedEventGroup",
    "EventCorrelator",
    "StatisticalAnomalyDetector",
    "TelemetryCollector",
    "TelemetrySnapshot",
]
