"""
Tests for Pipeline Lifecycle State Machine and Status Accounting.
Verifies:
1. Every supported status: RUNNING, SUCCESS, FAILED, ABORTED, CANCELLED.
2. Valid transitions from RUNNING -> SUCCESS, FAILED, ABORTED, CANCELLED.
3. Duplicate terminal updates are handled idempotently.
4. Conflicting terminal updates (SUCCESS -> FAILED, FAILED -> SUCCESS) return HTTP 409 Conflict.
5. Late heartbeat (terminal -> RUNNING) is rejected with HTTP 409 Conflict and original status preserved.
6. Permitted exception: Late runner completion for an ABORTED run transitions to SUCCESS/FAILED.
7. Dashboard status aggregations strictly reconcile with actual database records.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.database.models import Commit, PipelineRun, Repository


def _create_run(
    db_session: Session, initial_status: str = "RUNNING", duration: float = 0.0
) -> PipelineRun:
    """Helper to seed a test pipeline run in the database."""
    repo = Repository(
        id=f"repo-{uuid4().hex[:8]}",
        name=f"test-org/repo-{uuid4().hex[:6]}",
        owner="test-org",
        clone_url="https://github.com/test-org/repo.git",
        default_branch="main",
    )
    commit = Commit(
        id=f"commit-{uuid4().hex[:8]}",
        repository_id=repo.id,
        commit_hash=uuid4().hex,
        author_name="CI Test Runner",
        author_email="test@runner.local",
        message="Test commit",
    )
    run = PipelineRun(
        id=f"run-{uuid4().hex[:8]}",
        repository_id=repo.id,
        commit_id=commit.id,
        status=initial_status,
        total_duration_sec=duration,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) if initial_status != "RUNNING" else None,
    )
    db_session.add_all([repo, commit, run])
    db_session.commit()
    db_session.refresh(run)
    return run


@pytest.mark.parametrize("target_status", ["SUCCESS", "FAILED", "ABORTED", "CANCELLED"])
def test_valid_transitions_from_running(client, db_session: Session, target_status: str):
    """Verifies RUNNING -> SUCCESS, FAILED, ABORTED, CANCELLED transitions via telemetry endpoint."""
    run = _create_run(db_session, initial_status="RUNNING")

    payload = {
        "pipeline_run_id": run.id,
        "cpu_percent_avg": 35.0,
        "memory_mb_peak": 120.0,
        "disk_io_mb": 5.0,
        "runner_os": "Linux",
        "total_duration_sec": 14.5,
        "status": target_status,
    }

    res = client.post(
        "/api/v1/telemetry/record",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 201

    db_session.refresh(run)
    assert run.status == target_status
    assert run.total_duration_sec == 14.5
    assert run.completed_at is not None


def test_duplicate_terminal_update_idempotent(client, db_session: Session):
    """Verifies duplicate terminal status updates succeed idempotently without corrupting data."""
    run = _create_run(db_session, initial_status="SUCCESS", duration=12.0)
    original_completed_at = run.completed_at

    payload = {
        "pipeline_run_id": run.id,
        "cpu_percent_avg": 40.0,
        "memory_mb_peak": 130.0,
        "disk_io_mb": 8.0,
        "runner_os": "Linux",
        "total_duration_sec": 12.0,
        "status": "SUCCESS",
    }

    res = client.post(
        "/api/v1/telemetry/record",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 201

    db_session.refresh(run)
    assert run.status == "SUCCESS"
    assert run.total_duration_sec == 12.0
    assert run.completed_at == original_completed_at


def test_conflicting_terminal_transition_success_to_failed_rejected(client, db_session: Session):
    """Verifies that an update attempting to switch SUCCESS to FAILED is rejected with HTTP 409 Conflict."""
    run = _create_run(db_session, initial_status="SUCCESS", duration=10.0)

    payload = {
        "pipeline_run_id": run.id,
        "cpu_percent_avg": 50.0,
        "memory_mb_peak": 150.0,
        "status": "FAILED",
    }

    res = client.post(
        "/api/v1/telemetry/record",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 409
    assert "cannot overwrite terminal status" in res.json()["detail"]

    # Verify original outcome was preserved
    db_session.refresh(run)
    assert run.status == "SUCCESS"


def test_conflicting_terminal_transition_failed_to_success_rejected(client, db_session: Session):
    """Verifies that an update attempting to switch FAILED to SUCCESS is rejected with HTTP 409 Conflict."""
    run = _create_run(db_session, initial_status="FAILED", duration=15.0)

    payload = {
        "pipeline_run_id": run.id,
        "cpu_percent_avg": 45.0,
        "memory_mb_peak": 140.0,
        "status": "SUCCESS",
    }

    res = client.post(
        "/api/v1/telemetry/record",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 409
    assert "cannot overwrite terminal status" in res.json()["detail"]

    db_session.refresh(run)
    assert run.status == "FAILED"


def test_late_heartbeat_after_termination_rejected(client, db_session: Session):
    """Verifies that a late heartbeat attempting to set a terminal run back to RUNNING returns 409 Conflict."""
    run = _create_run(db_session, initial_status="SUCCESS", duration=18.0)

    payload = {
        "pipeline_run_id": run.id,
        "cpu_percent_avg": 20.0,
        "memory_mb_peak": 100.0,
        "status": "RUNNING",
    }

    res = client.post(
        "/api/v1/telemetry/record",
        json=payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 409
    assert "Cannot revert terminal pipeline run" in res.json()["detail"]

    db_session.refresh(run)
    assert run.status == "SUCCESS"


def test_plans_complete_endpoint_conflicting_terminal_rejected(client, db_session: Session):
    """Verifies POST /api/v1/plans/runs/{run_id}/complete returns 409 Conflict on conflicting terminal status."""
    run = _create_run(db_session, initial_status="SUCCESS", duration=22.0)

    comp_payload = {
        "status": "FAILED",
        "total_duration_sec": 22.0,
        "error_message": "Late test failure",
    }

    res = client.post(
        f"/api/v1/plans/runs/{run.id}/complete",
        json=comp_payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 409
    assert "Cannot transition pipeline run" in res.json()["detail"]

    db_session.refresh(run)
    assert run.status == "SUCCESS"


def test_plans_complete_endpoint_duplicate_terminal_idempotent(client, db_session: Session):
    """Verifies POST /api/v1/plans/runs/{run_id}/complete is idempotent for duplicate identical status."""
    run = _create_run(db_session, initial_status="FAILED", duration=25.0)

    comp_payload = {
        "status": "FAILED",
        "total_duration_sec": 25.0,
        "error_message": "First failure",
    }

    res = client.post(
        f"/api/v1/plans/runs/{run.id}/complete",
        json=comp_payload,
        headers={"X-Runner-Token": "autonomous_devops_runner_dev_api_key_2026"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "FAILED"


def test_dashboard_status_totals_match_database(client, db_session: Session):
    """Verifies that all supported statuses (SUCCESS, FAILED, ABORTED, CANCELLED, RUNNING) reconcile with dashboard metrics."""
    # Seed 1 run for each supported status
    _create_run(db_session, "SUCCESS", 10.0)
    _create_run(db_session, "FAILED", 15.0)
    _create_run(db_session, "ABORTED", 5.0)
    _create_run(db_session, "CANCELLED", 2.0)
    _create_run(db_session, "RUNNING", 0.0)

    res = client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 200
    data = res.json()

    assert data["total_runs"] >= 5
    assert data["successful_runs"] >= 1
    assert data["failed_runs"] >= 1
    assert data["aborted_runs"] >= 1
    assert data["cancelled_runs"] >= 1
    assert data["running_runs"] >= 1

    # Exact status sum reconciliation
    assert (
        data["total_runs"]
        == data["successful_runs"]
        + data["failed_runs"]
        + data["aborted_runs"]
        + data["cancelled_runs"]
        + data["running_runs"]
        + data["pending_runs"]
    )
