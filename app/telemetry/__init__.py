"""
Telemetry & Observability Module.
Provides hardware metrics collection (CPU, Memory, Disk), statistical anomaly detection,
and deterministic failure event correlation.
"""

from app.telemetry.collector import (
    TelemetrySnapshot,
    TelemetryCollector,
)
from app.telemetry.anomaly_detector import (
    AnomalyType,
    AnomalyFinding,
    AnomalyReport,
    StatisticalAnomalyDetector,
)
from app.telemetry.event_correlator import (
    CorrelatedEventGroup,
    EventCorrelator,
)

__all__ = [
    "TelemetrySnapshot",
    "TelemetryCollector",
    "AnomalyType",
    "AnomalyFinding",
    "AnomalyReport",
    "StatisticalAnomalyDetector",
    "CorrelatedEventGroup",
    "EventCorrelator",
]
