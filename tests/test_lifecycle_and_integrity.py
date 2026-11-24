"""
Integration and Unit Tests for Pipeline Lifecycle, Data Integrity, and AI/ML Lifecycles.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.
"""

import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import BASE_DIR, settings
from app.database.models import (
    AuditLog,
    Commit,
    PipelineRun,
    Repository,
    Telemetry,
    TestCase,
    TestResult,
)
from app.database.session import SessionLocal
from app.main import app
from app.ml.model_manager import ModelManager
from app.optimization.decision_engine import DecisionEngine
from app.optimization.reconciliation import reconcile_stale_runs
from app.telemetry.anomaly_detector import AnomalyType, StatisticalAnomalyDetector


@pytest.fixture
def client():
    """Provides FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def sample_pipeline_run(db_session):
    """Creates a sample repository, commit, and RUNNING pipeline run."""
    unique_suffix = uuid.uuid4().hex[:8]
    repo = Repository(
        name=f"test-repo-{unique_suffix}",
        owner="TestOrg",
        clone_url="https://github.com/TestOrg/test-repo.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    commit = Commit(
        repository_id=repo.id,
        commit_hash=f"c-{unique_suffix}",
        branch="main",
        author_name="CI Test Runner",
        author_email="runner@ci.org",
        message="Test commit for lifecycle verification",
    )
    db_session.add(commit)
    db_session.flush()

    run = PipelineRun(
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="Autonomous DevOps CI",
        status="RUNNING",
        trigger_event="push",
        is_optimized=True,
        fallback_triggered=False,
        total_duration_sec=0.0,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_stable_database_and_model_path_resolution():
    """
    Verifies that SQLITE_FALLBACK_URL and MODEL_REGISTRY_PATH are resolved
    against BASE_DIR to eliminate CWD dependency.
    """
    assert os.path.isabs(BASE_DIR)
    assert os.path.exists(BASE_DIR)

    # SQLite fallback URL must be absolute and point to BASE_DIR / autonomous_devops_local.db
    assert settings.SQLITE_FALLBACK_URL.startswith("sqlite:///")
    db_path = settings.SQLITE_FALLBACK_URL.replace("sqlite:///", "")
    assert os.path.isabs(db_path)
    assert "autonomous_devops_local.db" in db_path

    # Model registry path must be absolute and point to BASE_DIR / app / ml / models
    assert os.path.isabs(settings.MODEL_REGISTRY_PATH)
    assert os.path.exists(settings.MODEL_REGISTRY_PATH)


def test_pipeline_run_completion_success(db_session, sample_pipeline_run):
    """
    Verifies that DecisionEngine.complete_pipeline_run transitions a RUNNING
    execution to SUCCESS with explicit duration and audit record.
    """
    run_id = sample_pipeline_run.id
    completed_run = DecisionEngine.complete_pipeline_run(
        db=db_session,
        pipeline_run_id=run_id,
        status="SUCCESS",
        total_duration_sec=14.25,
    )

    assert completed_run is not None
    assert completed_run.status == "SUCCESS"
    assert completed_run.total_duration_sec == 14.25
    assert completed_run.completed_at is not None

    # Verify audit log entry
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity_id == run_id, AuditLog.event_type == "PIPELINE_RUN_COMPLETED")
        .first()
    )
    assert audit is not None
    assert "SUCCESS" in audit.details
    assert "14.25s" in audit.details


def test_pipeline_run_completion_duration_calculation_from_timestamps(
    db_session, sample_pipeline_run
):
    """
    Verifies that if total_duration_sec is not provided, duration is calculated
    from (completed_at - created_at) timestamps.
    """
    run_id = sample_pipeline_run.id
    # Set created_at to 20 seconds in the past
    past_created = datetime.now(UTC) - timedelta(seconds=20)
    sample_pipeline_run.created_at = past_created
    db_session.commit()

    completed_run = DecisionEngine.complete_pipeline_run(
        db=db_session,
        pipeline_run_id=run_id,
        status="FAILED",
        error_message="Unit test assertions failed",
    )

    assert completed_run is not None
    assert completed_run.status == "FAILED"
    assert completed_run.total_duration_sec >= 19.0
    assert completed_run.fallback_reason == "Unit test assertions failed"
    assert completed_run.completed_at is not None


def test_complete_run_endpoint_authorized(client, sample_pipeline_run):
    """
    Verifies that POST /api/v1/plans/runs/{run_id}/complete transitions run status
    via the REST API when authenticated with the runner token.
    """
    headers = {"X-Runner-Token": settings.RUNNER_API_KEY}
    payload = {
        "status": "SUCCESS",
        "total_duration_sec": 11.8,
    }

    resp = client.post(
        f"/api/v1/plans/runs/{sample_pipeline_run.id}/complete",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == "SUCCESS"
    assert data["total_duration_sec"] == 11.8
    assert data["pipeline_run_id"] == sample_pipeline_run.id


def test_complete_run_endpoint_unauthorized(client, sample_pipeline_run):
    """Verifies that unauthenticated or invalid token callers are rejected with 403."""
    resp = client.post(
        f"/api/v1/plans/runs/{sample_pipeline_run.id}/complete",
        json={"status": "SUCCESS"},
        headers={"X-Runner-Token": "invalid_wrong_token"},
    )
    assert resp.status_code == 403


def test_complete_run_endpoint_not_found(client):
    """Verifies that non-existent run ID returns 404."""
    resp = client.post(
        "/api/v1/plans/runs/non-existent-uuid/complete",
        json={"status": "SUCCESS"},
        headers={"X-Runner-Token": settings.RUNNER_API_KEY},
    )
    assert resp.status_code == 404


def test_stale_run_reconciliation(db_session):
    """
    Verifies that reconcile_stale_runs safely transitions orphaned RUNNING records
    older than threshold to ABORTED with audit trail, leaving active runs intact.
    """
    repo = Repository(
        name=f"rec-repo-{uuid.uuid4().hex[:6]}",
        owner="TestOrg",
        clone_url="https://github.com/TestOrg/rec.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    # 1. Create active run (5 minutes old)
    active_run = PipelineRun(
        id=f"active-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        workflow_name="Active CI",
        status="RUNNING",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        total_duration_sec=0.0,
    )
    # 2. Create stale run (4 hours old)
    stale_run = PipelineRun(
        id=f"stale-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        workflow_name="Abandoned CI",
        status="RUNNING",
        created_at=datetime.now(UTC) - timedelta(hours=4),
        total_duration_sec=0.0,
    )
    db_session.add(active_run)
    db_session.add(stale_run)
    db_session.commit()

    # Run reconciliation with 2-hour threshold
    res = reconcile_stale_runs(db_session, stale_threshold_hours=2.0)
    assert res["reconciled_count"] >= 1

    db_session.refresh(active_run)
    db_session.refresh(stale_run)

    # Active run must remain RUNNING
    assert active_run.status == "RUNNING"

    # Stale run must be transitioned to ABORTED
    assert stale_run.status == "ABORTED"
    assert stale_run.completed_at is not None
    assert "Orphaned uncompleted execution" in stale_run.fallback_reason

    # Clean up test rows
    db_session.delete(active_run)
    db_session.delete(stale_run)
    db_session.commit()


def test_reconciliation_preserves_runs_with_recent_telemetry_heartbeat(db_session):
    """
    Verifies that a run created >2h ago is NOT aborted if it received a recent
    telemetry heartbeat within the stale threshold window.
    """
    repo = Repository(
        name=f"heartbeat-repo-{uuid.uuid4().hex[:6]}",
        owner="TestOrg",
        clone_url="https://github.com/TestOrg/hb.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    # Created 3 hours ago, but telemetry heartbeat collected 10 minutes ago
    run_with_heartbeat = PipelineRun(
        id=f"hb-run-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        workflow_name="Long Running Test Job",
        status="RUNNING",
        created_at=datetime.now(UTC) - timedelta(hours=3),
        total_duration_sec=0.0,
    )
    db_session.add(run_with_heartbeat)
    db_session.flush()

    telem = Telemetry(
        pipeline_run_id=run_with_heartbeat.id,
        cpu_percent_avg=55.0,
        memory_mb_peak=320.0,
        runner_os="Ubuntu-Latest",
        collected_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(telem)
    db_session.commit()

    res = reconcile_stale_runs(db_session, stale_threshold_hours=2.0)
    db_session.refresh(run_with_heartbeat)

    # Must NOT be aborted: preserved because telemetry heartbeat is fresh
    assert run_with_heartbeat.status == "RUNNING"
    skipped_ids = [item["run_id"] for item in res["active_skipped"]]
    assert run_with_heartbeat.id in skipped_ids

    # Clean up
    db_session.delete(telem)
    db_session.delete(run_with_heartbeat)
    db_session.commit()


def test_reconciliation_preserves_runs_with_recent_test_execution_activity(db_session):
    """
    Verifies that a run created >2h ago is NOT aborted if it executed test cases
    within the stale threshold window.
    """
    repo = Repository(
        name=f"testact-repo-{uuid.uuid4().hex[:6]}",
        owner="TestOrg",
        clone_url="https://github.com/TestOrg/ta.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    # Created 3.5 hours ago, but a test result executed 15 minutes ago
    run_with_tests = PipelineRun(
        id=f"testact-run-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        workflow_name="Active Heavy Test Suite",
        status="RUNNING",
        created_at=datetime.now(UTC) - timedelta(hours=3, minutes=30),
        total_duration_sec=0.0,
    )
    db_session.add(run_with_tests)
    db_session.flush()

    test_case = TestCase(
        repository_id=repo.id,
        test_identifier="tests/test_suite.py::test_integration_large",
        file_path="tests/test_suite.py",
        function_name="test_integration_large",
    )
    db_session.add(test_case)
    db_session.flush()

    test_res = TestResult(
        pipeline_run_id=run_with_tests.id,
        test_case_id=test_case.id,
        status="PASSED",
        duration_ms=45000.0,
        executed_at=datetime.now(UTC) - timedelta(minutes=15),
    )
    db_session.add(test_res)
    db_session.commit()

    res = reconcile_stale_runs(db_session, stale_threshold_hours=2.0)
    db_session.refresh(run_with_tests)

    # Must NOT be aborted: preserved because test execution is fresh
    assert run_with_tests.status == "RUNNING"
    skipped_ids = [item["run_id"] for item in res["active_skipped"]]
    assert run_with_tests.id in skipped_ids

    # Clean up
    db_session.delete(test_res)
    db_session.delete(test_case)
    db_session.delete(run_with_tests)
    db_session.commit()


def test_late_runner_completion_transitions_aborted_to_terminal(db_session):
    """
    Verifies that if a runner was reconciled to ABORTED but eventually completes,
    complete_pipeline_run accepts the late terminal status and logs LATE_RUNNER_COMPLETION_RECORDED.
    """
    repo = Repository(
        name=f"late-repo-{uuid.uuid4().hex[:6]}",
        owner="TestOrg",
        clone_url="https://github.com/TestOrg/late.git",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    run = PipelineRun(
        id=f"late-run-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        workflow_name="Autonomous DevOps CI",
        status="ABORTED",
        created_at=datetime.now(UTC) - timedelta(hours=3),
        total_duration_sec=10800.0,
        fallback_reason="Orphaned uncompleted execution recovered during reconciliation",
    )
    db_session.add(run)
    db_session.commit()

    completed = DecisionEngine.complete_pipeline_run(
        db=db_session,
        pipeline_run_id=run.id,
        status="SUCCESS",
        total_duration_sec=142.5,
    )

    assert completed is not None
    assert completed.status == "SUCCESS"
    assert completed.total_duration_sec == 142.5

    # Verify audit log entry
    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.entity_id == run.id,
            AuditLog.event_type == "LATE_RUNNER_COMPLETION_RECORDED",
        )
        .first()
    )
    assert audit is not None
    assert "ABORTED to SUCCESS" in audit.details
    assert "Late completion: True" in audit.details

    # Clean up
    db_session.delete(run)
    db_session.commit()


def test_model_manager_loads_genuine_certified_models():
    """
    Verifies that ModelManager loads genuine models and properly certifies readiness.
    """
    mm = ModelManager()
    loaded = mm.load_models()

    assert loaded is True
    assert mm.failure_predictor.is_trained is True
    assert mm.runtime_predictor.is_trained is True
    assert mm.failure_predictor.model_version == "v1.0.0"

    # Can predict should pass with genuine historical runs
    can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
    assert can_pred is True
    assert "ready" in reason.lower()


def test_tampered_model_hash_rejection():
    """
    Verifies that if an artifact hash does not match metadata, load_models rejects it.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        manager = ModelManager(registry_dir=temp_dir)
        # Train genuine models in temp directory
        manager.train_and_persist(n_samples=20, data_source="SYNTHETIC_BOOTSTRAP")

        # Tamper failure_predictor model by modifying bytes
        fail_path = os.path.join(temp_dir, "failure_predictor.joblib")
        with open(fail_path, "ab") as f:
            f.write(b"\x00TAMPERED_BYTES\x00")

        # Attempt to load in a fresh manager instance
        fresh_manager = ModelManager(registry_dir=temp_dir)
        load_result = fresh_manager.load_models()

        # Must reject loading due to hash mismatch
        assert load_result is False
        assert fresh_manager.failure_predictor.is_trained is False
        assert fresh_manager.runtime_predictor.is_trained is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_anomaly_detector_insufficient_samples():
    """Verifies that StatisticalAnomalyDetector requires minimum historical samples."""
    detector = StatisticalAnomalyDetector(min_historical_samples=3)

    # 0 historical samples
    rep0 = detector.detect_anomalies(
        current_run={"duration_sec": 15.0},
        historical_runs=[],
    )
    assert rep0.is_anomalous is False
    assert "Insufficient" in rep0.summary

    # 2 historical samples (< 3)
    rep2 = detector.detect_anomalies(
        current_run={"duration_sec": 15.0},
        historical_runs=[{"duration_sec": 12.0}, {"duration_sec": 13.0}],
    )
    assert rep2.is_anomalous is False
    assert "Insufficient" in rep2.summary


def test_anomaly_detector_detects_execution_time_spike():
    """Verifies that StatisticalAnomalyDetector flags Z-Score >= 2.5 spikes."""
    detector = StatisticalAnomalyDetector(z_threshold=2.5, min_historical_samples=4)

    historical = [
        {"duration_sec": 10.0, "memory_mb_peak": 100.0, "cpu_percent_avg": 20.0},
        {"duration_sec": 10.5, "memory_mb_peak": 102.0, "cpu_percent_avg": 21.0},
        {"duration_sec": 9.8, "memory_mb_peak": 99.0, "cpu_percent_avg": 19.5},
        {"duration_sec": 10.2, "memory_mb_peak": 101.0, "cpu_percent_avg": 20.5},
    ]

    # Extreme spike: duration 90s vs baseline ~10s
    outlier_run = {"duration_sec": 90.0, "memory_mb_peak": 100.0, "cpu_percent_avg": 20.0}
    rep = detector.detect_anomalies(outlier_run, historical)

    assert rep.is_anomalous is True
    assert len(rep.anomalies) >= 1
    assert any(a.anomaly_type == AnomalyType.EXECUTION_TIME_SPIKE for a in rep.anomalies)


def test_all_seven_dashboard_routes_render_cleanly(client):
    """
    Verifies that all 7 dashboard views render with HTTP 200, valid HTML,
    and without missing context or template errors.
    """
    routes = [
        ("/dashboard/overview", "Overview"),
        ("/dashboard/history", "History"),
        ("/dashboard/ai-insights", "AI Insights"),
        ("/dashboard/optimization", "Optimization"),
        ("/dashboard/security", "Security"),
        ("/dashboard/observability", "Observability"),
        ("/dashboard/health", "Health"),
    ]

    for path, name in routes:
        resp = client.get(path)
        assert resp.status_code == 200, f"Dashboard route {path} failed with {resp.status_code}"
        html = resp.text
        assert "<!DOCTYPE html>" in html, f"Route {path} did not return valid HTML5"

        if path == "/dashboard/overview":
            assert "Estimated (20.0s standard suite baseline)" in html
        elif path == "/dashboard/ai-insights":
            assert "Verified Model Loaded" in html
        elif path == "/dashboard/observability":
            assert "Anomalies Flagged" in html
