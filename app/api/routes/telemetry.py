"""
API Router for Telemetry, Anomaly Detection & Failure Correlation.
Provides endpoints to ingest runtime telemetry, detect performance anomalies,
and correlate systemic failure events.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.models import PipelineRun, Telemetry
from app.database.session import get_db
from app.telemetry.anomaly_detector import AnomalyReport, StatisticalAnomalyDetector
from app.telemetry.event_correlator import CorrelatedEventGroup, EventCorrelator, FailureEvent

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Observability"])


class TelemetryRecordRequest(BaseModel):
    pipeline_run_id: str = Field(..., json_schema_extra={"example": "run-uuid-12345"})
    cpu_percent_avg: float = Field(..., ge=0.0, le=100.0, json_schema_extra={"example": 42.5})
    memory_mb_peak: float = Field(..., ge=0.0, json_schema_extra={"example": 185.2})
    disk_io_mb: float = Field(0.0, ge=0.0, json_schema_extra={"example": 12.4})
    runner_os: str = Field("Ubuntu-Latest", json_schema_extra={"example": "Ubuntu-Latest"})
    total_duration_sec: float | None = Field(None, ge=0.0, json_schema_extra={"example": 18.5})
    status: str | None = Field("SUCCESS", json_schema_extra={"example": "SUCCESS"})


class AnomalyDetectionRequest(BaseModel):
    current_run: dict[str, float] = Field(
        ...,
        json_schema_extra={
            "example": {"duration_sec": 45.0, "memory_mb_peak": 250.0, "cpu_percent_avg": 85.0}
        },
    )
    historical_runs: list[dict[str, float]] | None = Field(
        None,
        json_schema_extra={
            "example": [
                {"duration_sec": 12.0, "memory_mb_peak": 120.0, "cpu_percent_avg": 35.0},
                {"duration_sec": 14.5, "memory_mb_peak": 125.0, "cpu_percent_avg": 38.0},
                {"duration_sec": 13.0, "memory_mb_peak": 118.0, "cpu_percent_avg": 34.0},
                {"duration_sec": 15.0, "memory_mb_peak": 130.0, "cpu_percent_avg": 40.0},
                {"duration_sec": 13.5, "memory_mb_peak": 122.0, "cpu_percent_avg": 36.0},
            ]
        },
    )


class FailureEventItem(BaseModel):
    event_id: str
    repository: str
    commit_hash: str
    workflow_name: str
    error_message: str
    test_identifier: str | None = None


class CorrelationRequest(BaseModel):
    events: list[FailureEventItem]
    time_window_seconds: int = Field(3600, ge=60, le=86400)


@router.post("/record", status_code=status.HTTP_201_CREATED)
def record_telemetry(
    req: TelemetryRecordRequest,
    db: Session = Depends(get_db),
):
    """
    Records hardware and duration telemetry for a completed or running pipeline.
    """
    # 1. Update pipeline run if duration/status supplied
    run = db.query(PipelineRun).filter(PipelineRun.id == req.pipeline_run_id).first()
    if run:
        if req.total_duration_sec is not None:
            run.total_duration_sec = req.total_duration_sec
        if req.status:
            run.status = req.status
            if req.status in ("SUCCESS", "FAILED"):
                run.completed_at = datetime.now(UTC)

    # 2. Upsert telemetry record
    existing = db.query(Telemetry).filter(Telemetry.pipeline_run_id == req.pipeline_run_id).first()
    if existing:
        existing.cpu_percent_avg = req.cpu_percent_avg
        existing.memory_mb_peak = req.memory_mb_peak
        existing.disk_io_mb = req.disk_io_mb
        existing.runner_os = req.runner_os
        telemetry_obj = existing
    else:
        telemetry_obj = Telemetry(
            pipeline_run_id=req.pipeline_run_id,
            cpu_percent_avg=req.cpu_percent_avg,
            memory_mb_peak=req.memory_mb_peak,
            disk_io_mb=req.disk_io_mb,
            runner_os=req.runner_os,
        )
        db.add(telemetry_obj)

    db.commit()
    db.refresh(telemetry_obj)

    return {
        "success": True,
        "telemetry_id": telemetry_obj.id,
        "pipeline_run_id": telemetry_obj.pipeline_run_id,
        "cpu_percent_avg": telemetry_obj.cpu_percent_avg,
        "memory_mb_peak": telemetry_obj.memory_mb_peak,
        "disk_io_mb": telemetry_obj.disk_io_mb,
        "runner_os": telemetry_obj.runner_os,
        "collected_at": telemetry_obj.collected_at.isoformat(),
    }


@router.post("/detect-anomalies", status_code=status.HTTP_200_OK)
def detect_anomalies(
    req: AnomalyDetectionRequest,
    db: Session = Depends(get_db),
):
    """
    Evaluates observed execution against statistical historical baselines (Z-Scores).
    Detects runtime spikes, memory surges, and CPU anomalies.
    """
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=5)

    hist_data = req.historical_runs
    if not hist_data:
        # Query recent telemetry from DB
        recent_telemetry = (
            db.query(Telemetry)
            .join(PipelineRun)
            .order_by(Telemetry.collected_at.desc())
            .limit(20)
            .all()
        )
        hist_data = [
            {
                "duration_sec": t.pipeline_run.total_duration_sec if t.pipeline_run else 15.0,
                "memory_mb_peak": t.memory_mb_peak,
                "cpu_percent_avg": t.cpu_percent_avg,
            }
            for t in recent_telemetry
        ]

    report: AnomalyReport = detector.detect_anomalies(req.current_run, hist_data)

    return {
        "is_anomalous": report.is_anomalous,
        "anomalies_count": len(report.anomalies),
        "anomalies": [
            {
                "type": a.anomaly_type.value,
                "severity": a.severity.value,
                "metric": a.metric_name,
                "observed": a.observed_value,
                "baseline_mean": a.baseline_mean,
                "baseline_std": a.baseline_std,
                "z_score": a.z_score,
                "message": a.message,
            }
            for a in report.anomalies
        ],
        "samples_evaluated": report.samples_count,
        "summary": report.summary,
        "recommendation": report.recommendation,
    }


@router.post("/correlate-failures", status_code=status.HTTP_200_OK)
def correlate_failures(req: CorrelationRequest):
    """
    Groups and correlates failure events by normalized error signature, repository, and workflow.
    """
    correlator = EventCorrelator(time_window_seconds=req.time_window_seconds)

    events = [
        FailureEvent(
            event_id=item.event_id,
            repository=item.repository,
            commit_hash=item.commit_hash,
            workflow_name=item.workflow_name,
            error_message=item.error_message,
            timestamp=datetime.now(UTC),
            test_identifier=item.test_identifier,
        )
        for item in req.events
    ]

    groups: list[CorrelatedEventGroup] = correlator.correlate_events(events)

    return {
        "correlated_groups_count": len(groups),
        "groups": [g.to_dict() for g in groups],
    }
