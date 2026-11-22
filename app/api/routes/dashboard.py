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
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database.session import get_db, engine
from app.database.models import (
    PipelineRun,
    ExecutionPlan,
    Prediction,
    Telemetry,
    SecurityScan,
    Repository,
    Commit,
    AuditLog,
)
from app.ml.model_manager import ModelManager
from app.telemetry.event_correlator import EventCorrelator, FailureEvent
from app.core.config import settings

router = APIRouter(tags=["Web Dashboard"])

# Setup Jinja2 Templates Directory
TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates"))
templates = Jinja2Templates(directory=TEMPLATE_DIR)
model_manager = ModelManager()


@router.get("/dashboard", response_class=HTMLResponse)
def root_dashboard(request: Request, db: Session = Depends(get_db)):
    """Landing route serving the Executive Pipeline Overview."""
    return get_overview_page(request, db)


@router.get("/dashboard/overview", response_class=HTMLResponse)
def get_overview_page(request: Request, db: Session = Depends(get_db)):
    """Page A: Executive Pipeline Overview."""
    runs = db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).all()
    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r.status == "SUCCESS")
    failed_runs = sum(1 for r in runs if r.status == "FAILED")
    optimized_runs = sum(1 for r in runs if r.is_optimized)
    fallback_runs = sum(1 for r in runs if r.fallback_triggered)

    avg_duration = round(sum(r.total_duration_sec for r in runs) / max(1, total_runs), 2)
    optimization_rate = round((optimized_runs / max(1, total_runs)) * 100.0, 1)
    fallback_rate = round((fallback_runs / max(1, total_runs)) * 100.0, 1)

    # Estimate time saved
    plans = db.query(ExecutionPlan).all()
    time_saved_total = 0.0
    for p in plans:
        if p.decision == "OPTIMIZED" and p.tests_reduction_pct > 0:
            time_saved_total += round(20.0 * (p.tests_reduction_pct / 100.0), 1)

    # Recent runs table
    recent_runs = []
    for r in runs[:10]:
        repo_name = r.repository.name if r.repository else "AutonomousDevOps/CI-CD-PIPELINE"
        commit_hash = r.commit.commit_hash if r.commit else "local-commit"
        plan = r.execution_plan
        sel_count = plan.selected_tests_count if plan else 0
        tot_count = plan.total_tests_count if plan else 0
        dec_reason = plan.decision_reason if plan else "Standard Execution"

        recent_runs.append({
            "id": r.id,
            "repository_name": repo_name,
            "commit_hash": commit_hash,
            "status": r.status,
            "duration_sec": r.total_duration_sec,
            "is_optimized": r.is_optimized,
            "selected_tests": sel_count,
            "total_tests": tot_count,
            "decision_reason": dec_reason,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-",
        })

    # Chart data
    chart_labels = [f"Run {i+1}" for i in range(min(10, total_runs))]
    chart_durations = [r.total_duration_sec for r in reversed(runs[:10])]

    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "request": request,
            "active_page": "overview",
            "is_demo_data": False,
            "kpis": {
                "total_runs": total_runs,
                "successful_runs": successful_runs,
                "failed_runs": failed_runs,
                "optimized_runs": optimized_runs,
                "fallback_runs": fallback_runs,
                "avg_duration_sec": avg_duration,
                "time_saved_sec": round(time_saved_total, 1),
                "optimization_rate": optimization_rate,
                "fallback_rate": fallback_rate,
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

        history_runs.append({
            "id": r.id,
            "repository_name": repo_name,
            "branch": commit.branch if commit else "main",
            "commit_hash": commit.commit_hash if commit else "sha-unknown",
            "author_name": commit.author_name if commit else "Developer",
            "commit_message": commit.message if commit else "Commit update",
            "status": r.status,
            "duration_sec": r.total_duration_sec,
            "selected_tests": plan.selected_tests_count if plan else 0,
            "total_tests": plan.total_tests_count if plan else 0,
            "reduction_pct": plan.tests_reduction_pct if plan else 0.0,
            "is_optimized": r.is_optimized,
            "decision_reason": plan.decision_reason if plan else "Standard Execution",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "-",
        })

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
    models_status = model_manager.get_models_status()
    predictions = db.query(Prediction).order_by(Prediction.created_at.desc()).limit(20).all()

    pred_history = []
    risk_labels = []
    risk_values = []

    for i, p in enumerate(reversed(predictions)):
        risk_labels.append(f"Pred {i+1}")
        risk_values.append(p.predicted_failure_probability)

    for p in predictions:
        run = p.pipeline_run
        commit_hash = run.commit.commit_hash if (run and run.commit) else "sha-unknown"
        actual_dur = run.total_duration_sec if run else 0.0

        pred_history.append({
            "commit_hash": commit_hash,
            "model_version": p.model_version,
            "failure_prob": p.predicted_failure_probability,
            "failure_class": p.predicted_failure_class,
            "predicted_duration_sec": p.predicted_duration_sec,
            "actual_duration_sec": actual_dur,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "-",
        })

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
                    "risk_threshold": model_manager.failure_predictor.risk_threshold,
                },
                "runtime_predictor": {
                    "is_trained": models_status["runtime_predictor"]["is_trained"],
                    "version": models_status["runtime_predictor"]["version"],
                },
            },
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

        opt_plans.append({
            "commit_hash": commit_hash,
            "decision": p.decision,
            "selected_tests_count": p.selected_tests_count,
            "total_tests_count": p.total_tests_count,
            "reduction_pct": p.tests_reduction_pct,
            "safety_rule_triggered": p.safety_rule_triggered,
            "decision_reason": p.decision_reason,
            "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "-",
        })

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
    blocked_releases = sum(1 for s in scans if s.status == "FAILED" or s.highest_severity in ("HIGH", "CRITICAL"))
    secret_leaks = sum(s.findings_count for s in scans if "gitleaks" in s.tool_name.lower())

    scan_records = []
    for s in scans:
        scan_records.append({
            "tool_name": s.tool_name,
            "status": s.status,
            "highest_severity": s.highest_severity,
            "findings_count": s.findings_count,
            "summary": s.summary,
            "executed_at": s.executed_at.strftime("%Y-%m-%d %H:%M") if s.executed_at else "-",
        })

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
    total_records = len(telemetries)

    avg_cpu = round(sum(t.cpu_percent_avg for t in telemetries) / max(1, total_records), 1)
    avg_mem = round(sum(t.memory_mb_peak for t in telemetries) / max(1, total_records), 1)

    chart_labels = [f"Job {i+1}" for i in range(min(15, total_records))]
    chart_cpu = [t.cpu_percent_avg for t in reversed(telemetries[:15])]
    chart_mem = [t.memory_mb_peak for t in reversed(telemetries[:15])]

    # Correlate failure events from failed pipeline runs
    correlator = EventCorrelator()
    failed_runs = db.query(PipelineRun).filter(PipelineRun.status == "FAILED").all()
    events = []
    for fr in failed_runs:
        events.append(FailureEvent(
            event_id=fr.id,
            repository=fr.repository.name if fr.repository else "AutonomousDevOps/CI-CD-PIPELINE",
            commit_hash=fr.commit.commit_hash if fr.commit else "sha",
            workflow_name=fr.workflow_name,
            error_message=fr.fallback_reason or "PipelineFailed",
            timestamp=fr.created_at,
        ))

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
            "anomalies_count": 0,
            "correlated_groups": [g.to_dict() for g in groups],
            "telemetry_chart_labels": chart_labels,
            "telemetry_chart_cpu": chart_cpu,
            "telemetry_chart_mem": chart_mem,
        },
    )


@router.get("/dashboard/health", response_class=HTMLResponse)
def get_health_page(request: Request):
    """Page G: System Health & Diagnostics."""
    models_status = model_manager.get_models_status()

    return templates.TemplateResponse(
        request=request,
        name="health.html",
        context={
            "request": request,
            "active_page": "health",
            "is_demo_data": False,
            "health_status": {
                "api_status": "ONLINE",
                "version": settings.VERSION,
                "db_engine": "PostgreSQL / SQLite",
                "failure_model_version": models_status["failure_predictor"]["version"],
                "runtime_model_version": models_status["runtime_predictor"]["version"],
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            },
        },
    )


@router.get("/api/v1/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """API endpoint returning aggregated JSON metrics for graphs or third-party consumers."""
    runs = db.query(PipelineRun).all()
    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r.status == "SUCCESS")
    failed_runs = sum(1 for r in runs if r.status == "FAILED")
    optimized_runs = sum(1 for r in runs if r.is_optimized)
    fallback_runs = sum(1 for r in runs if r.fallback_triggered)

    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "optimized_runs": optimized_runs,
        "fallback_runs": fallback_runs,
        "optimization_rate_pct": round((optimized_runs / max(1, total_runs)) * 100.0, 1),
        "fallback_rate_pct": round((fallback_runs / max(1, total_runs)) * 100.0, 1),
    }
