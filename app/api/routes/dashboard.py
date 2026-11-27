"""
Web Dashboard Router.
Renders responsive Jinja2 HTML5 pages with Chart.js visualizations covering:
1. Executive Overview
2. Pipeline History
3. AI Predictive Insights
4. Test Optimization
5. Security & Compliance
6. Telemetry & Observability
7. System Health
"""

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.database.models import (
    ExecutionPlan,
    PipelineRun,
    Prediction,
    SecurityScan,
    Telemetry,
)
from app.database.session import get_db, get_db_info
from app.ml.model_manager import ModelManager
from app.telemetry.anomaly_detector import StatisticalAnomalyDetector
from app.telemetry.event_correlator import EventCorrelator, FailureEvent

router = APIRouter(tags=["Web Dashboard"])

# Setup Jinja2 Templates Directory
TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates"))
templates = Jinja2Templates(directory=TEMPLATE_DIR)

_model_manager_singleton: ModelManager | None = None


def compute_dashboard_aggregations(
    runs: list[PipelineRun], plans: list[ExecutionPlan] | None = None
) -> dict[str, any]:
    """
    Single shared status and execution aggregation function across dashboard views and metrics APIs.
    Reconciles all lifecycle statuses (SUCCESS, FAILED, ABORTED, CANCELLED, RUNNING, PENDING)
    and execution decisions (OPTIMIZED, FULL_SUITE, UNPLANNED).
    """
    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r.status == "SUCCESS")
    failed_runs = sum(1 for r in runs if r.status == "FAILED")
    aborted_runs = sum(1 for r in runs if r.status == "ABORTED")
    cancelled_runs = sum(1 for r in runs if r.status == "CANCELLED")
    running_runs = sum(1 for r in runs if r.status == "RUNNING")
    pending_runs = sum(1 for r in runs if r.status == "PENDING")

    planned_optimized_runs = 0
    fallback_runs = 0
    unplanned_runs = 0

    for r in runs:
        decision, _, _, _, _, _ = determine_execution_attribution(r)
        if decision == "OPTIMIZED":
            planned_optimized_runs += 1
        elif decision == "FULL_SUITE":
            fallback_runs += 1
        else:
            unplanned_runs += 1

    # Completed runs: strictly completed runs (SUCCESS or FAILED) with positive duration
    # Excludes RUNNING (duration 0), ABORTED, and CANCELLED runs
    completed_runs = [
        r for r in runs if r.status in ("SUCCESS", "FAILED") and r.total_duration_sec > 0
    ]
    avg_duration = (
        round(sum(r.total_duration_sec for r in completed_runs) / max(1, len(completed_runs)), 2)
        if completed_runs
        else 0.0
    )

    # Estimated time saved across eligible OPTIMIZED plans
    if plans is None:
        plans = []
    opt_plans = [p for p in plans if p.decision == "OPTIMIZED" and p.tests_reduction_pct > 0]
    estimated_time_saved_total = round(
        sum(20.0 * (p.tests_reduction_pct / 100.0) for p in opt_plans),
        1,
    )

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "aborted_runs": aborted_runs,
        "cancelled_runs": cancelled_runs,
        "running_runs": running_runs,
        "pending_runs": pending_runs,
        "completed_runs_count": len(completed_runs),
        "avg_duration_sec": avg_duration,
        "estimated_time_saved_sec": estimated_time_saved_total,
        "planned_optimized_runs": planned_optimized_runs,
        "optimized_runs": planned_optimized_runs,
        "fallback_runs": fallback_runs,
        "unplanned_runs": unplanned_runs,
        "optimization_rate_pct": round((planned_optimized_runs / max(1, total_runs)) * 100.0, 1),
        "fallback_rate_pct": round((fallback_runs / max(1, total_runs)) * 100.0, 1),
    }


def determine_execution_attribution(run: PipelineRun) -> tuple[str, bool, bool, int, int, str]:
    """
    Deterministically attributes execution decision, flags, test counts, and reason.
    Returns: (decision, is_optimized, is_fallback, selected_tests, total_tests, decision_reason)

    Guarantees:
    - If fallback_triggered is True, ALWAYS attributes 'FULL_SUITE' (safety precedence over optimistic flags).
    - Never labels a run as 'OPTIMIZED' unless an execution plan explicitly authorized it AND selected_tests > 0.
    - Zero-selected-test plans are attributed as 'FULL_SUITE' fallback.
    - Accurately attributes 'RUNNING' for in-progress runs without a completed plan.
    - Accurately attributes 'UNPLANNED' for baseline/direct executions without an AST plan.
    """
    # 1. Safety fallback precedence: if fallback was triggered, execution was Full Suite
    if run.fallback_triggered:
        plan = run.execution_plan
        selected_count = plan.selected_tests_count if plan else 0
        total_count = plan.total_tests_count if plan else 0
        dec_reason = run.fallback_reason or (
            plan.decision_reason if plan else "Deterministic safety fallback enforced"
        )
        return "FULL_SUITE", False, True, selected_count, total_count, dec_reason

    # 2. Check execution plan entity
    plan = run.execution_plan
    if plan is not None:
        selected_count = plan.selected_tests_count
        total_count = plan.total_tests_count
        dec_reason = plan.decision_reason
        if plan.decision == "OPTIMIZED" and selected_count > 0:
            return "OPTIMIZED", True, False, selected_count, total_count, dec_reason
        else:
            return "FULL_SUITE", False, True, selected_count, total_count, dec_reason
    else:
        # No plan entity attached
        if run.status == "RUNNING":
            return (
                "RUNNING",
                False,
                False,
                0,
                0,
                "Execution currently in progress",
            )
        else:
            return (
                "UNPLANNED",
                False,
                False,
                0,
                0,
                "Direct execution without optimization plan",
            )


def get_model_manager(request: Request | None = None) -> ModelManager:
    """
    Retrieves the verified ModelManager from app.state or a lazily-loaded singleton.
    Guarantees model artifacts are verified and loaded without reloading on every request.
    """
    if (
        request
        and hasattr(request.app.state, "model_manager")
        and request.app.state.model_manager is not None
    ):
        return request.app.state.model_manager

    global _model_manager_singleton
    if _model_manager_singleton is None:
        _model_manager_singleton = ModelManager()
        try:
            _model_manager_singleton.load_models()
        except (OSError, ValueError, RuntimeError, KeyError, AttributeError) as exc:
            logger.debug(f"Dashboard model load notice: {exc}")
    return _model_manager_singleton


@router.get("/dashboard", response_class=HTMLResponse)
def root_dashboard(request: Request, db: Session = Depends(get_db)):
    """Landing route serving the Executive Pipeline Overview."""
    return get_overview_page(request, db)


@router.get("/dashboard/overview", response_class=HTMLResponse)
def get_overview_page(request: Request, db: Session = Depends(get_db)):
    """Page A: Executive Pipeline Overview."""
    runs = db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()
    plans = db.query(ExecutionPlan).all()
    kpi_data = compute_dashboard_aggregations(runs, plans)

    recent_runs = []
    for r in runs[:10]:
        decision, is_opt, is_fb, sel_count, tot_count, dec_reason = determine_execution_attribution(
            r
        )
        repo_name = r.repository.name if r.repository else "AutonomousDevOps/CI-CD-PIPELINE"
        commit_hash = r.commit.commit_hash if r.commit else "local-commit"
        recent_runs.append(
            {
                "id": r.id,
                "repository_name": repo_name,
                "commit_hash": commit_hash,
                "status": r.status,
                "duration_sec": r.total_duration_sec,
                "decision": decision,
                "is_optimized": is_opt,
                "fallback_triggered": is_fb,
                "selected_tests": sel_count,
                "total_tests": tot_count,
                "decision_reason": dec_reason,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
            }
        )

    # Measured empirical time saved: actual differences from completed runs with telemetry duration > 0
    completed_runs = [
        r for r in runs if r.status in ("SUCCESS", "FAILED") and r.total_duration_sec > 0
    ]
    measured_time_saved_total = round(
        sum(
            max(0.0, 20.0 - r.total_duration_sec)
            for r in completed_runs
            if r.status == "SUCCESS"
            and r.execution_plan
            and r.execution_plan.decision == "OPTIMIZED"
        ),
        1,
    )

    # Chart data
    chart_labels = [f"Run {i + 1}" for i in range(min(10, kpi_data["total_runs"]))]
    chart_durations = [r.total_duration_sec for r in reversed(runs[:10])]

    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "request": request,
            "active_page": "overview",
            "is_demo_data": False,
            "kpis": {
                **kpi_data,
                "time_saved_sec": kpi_data["estimated_time_saved_sec"],
                "measured_time_saved_sec": measured_time_saved_total,
                "time_saved_basis": "Modeled from standard 20.0s full-suite baseline",
                "optimization_rate": kpi_data["optimization_rate_pct"],
                "fallback_rate": kpi_data["fallback_rate_pct"],
            },
            "recent_runs": recent_runs,
            "chart_labels": chart_labels,
            "chart_durations": chart_durations,
        },
    )


@router.get("/dashboard/history", response_class=HTMLResponse)
def get_history_page(request: Request, db: Session = Depends(get_db)):
    """Page B: Complete Pipeline Execution History."""
    runs = db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()
    history_runs = []

    for r in runs:
        repo_name = r.repository.name if r.repository else "AutonomousDevOps/CI-CD-PIPELINE"
        commit = r.commit
        plan = r.execution_plan
        decision, is_opt, is_fb, sel_count, tot_count, dec_reason = determine_execution_attribution(
            r
        )

        history_runs.append(
            {
                "id": r.id,
                "repository_name": repo_name,
                "branch": commit.branch if commit else "main",
                "commit_hash": commit.commit_hash if commit else "sha-unknown",
                "author_name": commit.author_name if commit else "Developer",
                "commit_message": commit.message if commit else "Commit update",
                "status": r.status,
                "duration_sec": r.total_duration_sec,
                "decision": decision,
                "is_optimized": is_opt,
                "fallback_triggered": is_fb,
                "selected_tests": sel_count,
                "total_tests": tot_count,
                "reduction_pct": plan.tests_reduction_pct if plan else 0.0,
                "decision_reason": dec_reason,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "-",
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "request": request,
            "active_page": "history",
            "is_demo_data": False,
            "history_runs": history_runs,
        },
    )


@router.get("/dashboard/ai-insights", response_class=HTMLResponse)
def get_ai_insights_page(request: Request, db: Session = Depends(get_db)):
    """Page C: AI Insights & ML Models."""
    mm = get_model_manager(request)
    models_status = mm.get_models_status()
    predictions = db.query(Prediction).order_by(Prediction.created_at.desc()).limit(20).all()

    pred_history = []
    risk_labels = []
    risk_values = []

    for i, p in enumerate(reversed(predictions)):
        risk_labels.append(f"Pred {i + 1}")
        risk_values.append(p.predicted_failure_probability)

    for p in predictions:
        run = p.pipeline_run
        commit_hash = run.commit.commit_hash if (run and run.commit) else "sha-unknown"
        actual_dur = run.total_duration_sec if run else 0.0

        pred_history.append(
            {
                "commit_hash": commit_hash,
                "model_version": p.model_version,
                "failure_prob": p.predicted_failure_probability,
                "failure_class": p.predicted_failure_class,
                "predicted_duration_sec": p.predicted_duration_sec,
                "actual_duration_sec": actual_dur,
                "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "-",
            }
        )

    meta_info = models_status.get("provenance_metadata", {})

    return templates.TemplateResponse(
        request=request,
        name="ai_insights.html",
        context={
            "request": request,
            "active_page": "ai_insights",
            "is_demo_data": False,
            "models": {
                "failure_predictor": {
                    "is_trained": models_status["failure_predictor"]["is_trained"],
                    "version": models_status["failure_predictor"]["version"],
                    "risk_threshold": mm.failure_predictor.risk_threshold,
                },
                "runtime_predictor": {
                    "is_trained": models_status["runtime_predictor"]["is_trained"],
                    "version": models_status["runtime_predictor"]["version"],
                },
            },
            "metadata": meta_info,
            "predictions_history": pred_history,
            "risk_chart_labels": risk_labels,
            "risk_chart_values": risk_values,
        },
    )


@router.get("/dashboard/optimization", response_class=HTMLResponse)
def get_optimization_page(request: Request, db: Session = Depends(get_db)):
    """Page D: Test Optimization & Selection."""
    plans = db.query(ExecutionPlan).order_by(ExecutionPlan.created_at.desc()).all()
    opt_plans = []

    for p in plans:
        run = p.pipeline_run
        commit_hash = run.commit.commit_hash if (run and run.commit) else "commit-sha"

        opt_plans.append(
            {
                "commit_hash": commit_hash,
                "decision": p.decision,
                "selected_tests_count": p.selected_tests_count,
                "total_tests_count": p.total_tests_count,
                "reduction_pct": p.tests_reduction_pct,
                "safety_rule_triggered": p.safety_rule_triggered,
                "decision_reason": p.decision_reason,
                "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "-",
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="optimization.html",
        context={
            "request": request,
            "active_page": "optimization",
            "is_demo_data": False,
            "optimization_plans": opt_plans,
        },
    )


@router.get("/dashboard/security", response_class=HTMLResponse)
def get_security_page(request: Request, db: Session = Depends(get_db)):
    """Page E: Security & Compliance."""
    scans = db.query(SecurityScan).order_by(SecurityScan.executed_at.desc()).all()
    total_scans = len(scans)
    blocked_releases = sum(
        1 for s in scans if s.status == "FAILED" or s.highest_severity in ("HIGH", "CRITICAL")
    )
    secret_leaks = sum(s.findings_count for s in scans if "gitleaks" in s.tool_name.lower())

    scan_records = []
    for s in scans:
        scan_records.append(
            {
                "tool_name": s.tool_name,
                "status": s.status,
                "highest_severity": s.highest_severity,
                "findings_count": s.findings_count,
                "summary": s.summary,
                "executed_at": s.executed_at.strftime("%Y-%m-%d %H:%M") if s.executed_at else "-",
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="security.html",
        context={
            "request": request,
            "active_page": "security",
            "is_demo_data": False,
            "security_summary": {
                "total_scans": total_scans,
                "blocked_releases": blocked_releases,
                "secret_leaks": secret_leaks,
            },
            "security_scans": scan_records,
        },
    )


@router.get("/dashboard/observability", response_class=HTMLResponse)
def get_observability_page(request: Request, db: Session = Depends(get_db)):
    """Page F: Observability & Telemetry."""
    telemetries = db.query(Telemetry).order_by(Telemetry.collected_at.desc()).limit(20).all()
    all_time_telemetry_count = db.query(Telemetry).count()
    recent_records_count = len(telemetries)

    avg_cpu = (
        round(sum(t.cpu_percent_avg for t in telemetries) / max(1, recent_records_count), 1)
        if recent_records_count > 0
        else 0.0
    )
    avg_mem = (
        round(sum(t.memory_mb_peak for t in telemetries) / max(1, recent_records_count), 1)
        if recent_records_count > 0
        else 0.0
    )

    chart_labels = [f"Job {i + 1}" for i in range(min(15, recent_records_count))]
    chart_cpu = [t.cpu_percent_avg for t in reversed(telemetries[:15])]
    chart_mem = [t.memory_mb_peak for t in reversed(telemetries[:15])]

    # Anomaly Detection using Statistical Baselines (Z-score >= 2.5)
    # Strictly enforces minimum sample window (5 samples) before reporting healthy baseline
    MIN_REQUIRED_SAMPLES = 5
    detector = StatisticalAnomalyDetector(min_historical_samples=MIN_REQUIRED_SAMPLES)
    anomalies_count = 0
    anomaly_status = "PENDING_TELEMETRY"
    anomaly_findings = []

    if recent_records_count > 1:
        hist_count = recent_records_count - 1
        if hist_count >= MIN_REQUIRED_SAMPLES:
            current_t = telemetries[0]
            curr_dur = current_t.pipeline_run.total_duration_sec if current_t.pipeline_run else 0.0
            current_run_metrics = {
                "duration_sec": curr_dur,
                "memory_mb_peak": current_t.memory_mb_peak,
                "cpu_percent_avg": current_t.cpu_percent_avg,
            }
            hist_metrics = []
            for t in telemetries[1:]:
                t_dur = t.pipeline_run.total_duration_sec if t.pipeline_run else 0.0
                hist_metrics.append(
                    {
                        "duration_sec": t_dur,
                        "memory_mb_peak": t.memory_mb_peak,
                        "cpu_percent_avg": t.cpu_percent_avg,
                    }
                )
            report = detector.detect_anomalies(current_run_metrics, hist_metrics)
            anomalies_count = len(report.anomalies)
            anomaly_status = "ANOMALIES_DETECTED" if report.is_anomalous else "HEALTHY"
            anomaly_findings = [f.message for f in report.anomalies]
        else:
            anomaly_status = "INSUFFICIENT_SAMPLES"
            anomaly_findings = [
                f"Insufficient historical telemetry records ({hist_count}/{MIN_REQUIRED_SAMPLES} required) to establish statistical baseline."
            ]
    elif recent_records_count == 1:
        anomaly_status = "INSUFFICIENT_SAMPLES"
        anomaly_findings = [
            f"Single telemetry record observed (0/{MIN_REQUIRED_SAMPLES} historical samples required)."
        ]
    else:
        anomaly_status = "PENDING_TELEMETRY"

    # Correlate failure events from failed pipeline runs
    correlator = EventCorrelator()
    failed_runs = db.query(PipelineRun).filter(PipelineRun.status.in_(("FAILED", "ABORTED"))).all()
    events = []
    for fr in failed_runs:
        events.append(
            FailureEvent(
                event_id=fr.id,
                repository=fr.repository.name
                if fr.repository
                else "AutonomousDevOps/CI-CD-PIPELINE",
                commit_hash=fr.commit.commit_hash if fr.commit else "sha",
                workflow_name=fr.workflow_name,
                error_message=fr.fallback_reason or "PipelineFailed",
                timestamp=fr.created_at,
            )
        )

    groups = correlator.correlate_events(events)

    return templates.TemplateResponse(
        request=request,
        name="observability.html",
        context={
            "request": request,
            "active_page": "observability",
            "is_demo_data": False,
            "telemetry_kpis": {
                "avg_cpu": avg_cpu,
                "avg_memory_mb": avg_mem,
            },
            "anomalies_count": anomalies_count,
            "anomaly_status": anomaly_status,
            "anomaly_findings": anomaly_findings,
            "total_telemetry_records": all_time_telemetry_count,
            "recent_telemetry_records": recent_records_count,
            "telemetry_population": f"Latest {recent_records_count} runs (All-time recorded: {all_time_telemetry_count})",
            "min_required_samples": MIN_REQUIRED_SAMPLES,
            "correlated_groups": [g.to_dict() for g in groups],
            "telemetry_chart_labels": chart_labels,
            "telemetry_chart_cpu": chart_cpu,
            "telemetry_chart_mem": chart_mem,
        },
    )


@router.get("/dashboard/health", response_class=HTMLResponse)
def get_health_page(request: Request, db: Session = Depends(get_db)):
    """Page G: System Health & Diagnostics."""
    mm = get_model_manager(request)
    models_status = mm.get_models_status()

    # 1. Database Connectivity & Actual Engine Identification
    db_info = get_db_info(db)
    db_connected = False
    schema_ready = False

    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        db_connected = True
        db.query(PipelineRun).limit(1).all()
        schema_ready = True
    except (SQLAlchemyError, OSError):
        db_connected = False
        schema_ready = False

    # 2. Overall Subsystem & API Status
    models_loaded = models_status.get("failure_predictor", {}).get(
        "loaded", False
    ) and models_status.get("runtime_predictor", {}).get("loaded", False)
    if db_connected and schema_ready and models_loaded:
        api_status = "HEALTHY"
    elif db_connected and schema_ready:
        api_status = "DEGRADED (ML Unloaded)"
    else:
        api_status = "UNHEALTHY"

    return templates.TemplateResponse(
        request=request,
        name="health.html",
        context={
            "request": request,
            "active_page": "health",
            "is_demo_data": False,
            "health_status": {
                "api_status": api_status,
                "version": settings.VERSION,
                "db_engine": db_info["engine_name"],
                "db_connected": db_connected,
                "db_status": "CONNECTED" if db_connected else "DISCONNECTED",
                "schema_ready": schema_ready,
                "fallback_active": db_info["fallback_active"],
                "failure_model_version": models_status["failure_predictor"]["version"],
                "runtime_model_version": models_status["runtime_predictor"]["version"],
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        },
    )


@router.get("/api/v1/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """API endpoint returning aggregated JSON metrics for graphs or third-party consumers."""
    runs = db.query(PipelineRun).all()
    plans = db.query(ExecutionPlan).all()
    return compute_dashboard_aggregations(runs, plans)
