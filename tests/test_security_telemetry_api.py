"""
API Tests for Security Scanning and Telemetry Endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.models import Base, Commit, PipelineRun, Repository
from app.database.session import get_db
from app.main import app

# Setup shared in-memory test database for API testing
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db_override():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


client = TestClient(app)
client.headers.update({"X-Runner-Token": settings.RUNNER_API_KEY})


@pytest.fixture(scope="module", autouse=True)
def seed_pipeline_run():
    """Seeds a test repository and pipeline run into the in-memory database."""
    db = TestingSessionLocal()
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    db.add(repo)
    db.flush()

    commit = Commit(
        repository_id=repo.id,
        commit_hash="sec-test-commit-sha-999",
        branch="main",
        author_name="Security Analyst",
        author_email="sec@example.com",
        message="Add security scanning tests",
    )
    db.add(commit)
    db.flush()

    run = PipelineRun(
        id="test-run-sec-001",
        repository_id=repo.id,
        commit_id=commit.id,
        workflow_name="Security CI",
        status="RUNNING",
    )
    db.add(run)
    db.commit()
    db.close()


def test_api_submit_bandit_security_scan():
    payload = {
        "pipeline_run_id": "test-run-sec-001",
        "tool_name": "Bandit",
        "raw_output": {
            "results": [
                {
                    "test_id": "B303",
                    "test_name": "md5",
                    "issue_severity": "MEDIUM",
                    "issue_text": "Use of insecure MD5 hash function",
                    "filename": "sample_app/crypto.py",
                    "line_number": 12,
                }
            ]
        },
    }

    res = client.post("/api/v1/security/scan", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["tool_name"] == "Bandit"
    assert data["status"] == "WARNING"
    assert data["highest_severity"] == "MEDIUM"
    assert data["findings_count"] == 1
    assert data["should_block_release"] is False


def test_api_submit_gitleaks_blocks_release():
    payload = {
        "pipeline_run_id": "test-run-sec-001",
        "tool_name": "Gitleaks",
        "raw_output": [
            {
                "RuleID": "aws-secret-key",
                "Description": "AWS Secret Access Key",
                "File": ".env",
                "StartLine": 2,
                "Secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            }
        ],
    }

    res = client.post("/api/v1/security/scan", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["tool_name"] == "Gitleaks"
    assert data["status"] == "FAILED"
    assert data["highest_severity"] == "CRITICAL"
    assert data["should_block_release"] is True
    assert data["findings"][0]["redacted_snippet"] == "[REDACTED_SECRET]"


def test_api_get_security_scans():
    res = client.get("/api/v1/security/scans/test-run-sec-001")
    assert res.status_code == 200
    data = res.json()
    assert data["total_scans"] >= 2
    assert data["is_release_blocked"] is True


def test_api_record_telemetry():
    payload = {
        "pipeline_run_id": "test-run-sec-001",
        "cpu_percent_avg": 45.2,
        "memory_mb_peak": 192.5,
        "disk_io_mb": 8.0,
        "runner_os": "Ubuntu-22.04",
        "total_duration_sec": 16.4,
        "status": "SUCCESS",
    }

    res = client.post("/api/v1/telemetry/record", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["cpu_percent_avg"] == 45.2
    assert data["memory_mb_peak"] == 192.5


def test_api_record_telemetry_invalid_status_rejected_422():
    """Verifies that unapproved status values are rejected with HTTP 422 Unprocessable Entity."""
    payload = {
        "pipeline_run_id": "test-run-sec-001",
        "cpu_percent_avg": 40.0,
        "memory_mb_peak": 150.0,
        "status": "INVALID_UNKNOWN_STATUS",
    }
    res = client.post("/api/v1/telemetry/record", json=payload)
    assert res.status_code == 422


def test_api_record_telemetry_terminal_lock_prevents_rollback_to_running():
    """
    Verifies that a completed terminal execution (SUCCESS/FAILED/ABORTED) cannot be reverted
    back to RUNNING by late or misordered telemetry payloads.
    """
    db = TestingSessionLocal()
    unique_run_id = f"term-lock-{uuid.uuid4().hex[:8]}"
    isolated_run = PipelineRun(
        id=unique_run_id,
        repository_id="isolated-repo-id",
        workflow_name="Terminal Lock CI",
        status="RUNNING",
    )
    db.add(isolated_run)
    db.commit()
    db.close()

    # 1. Transition to terminal FAILED status
    fail_payload = {
        "pipeline_run_id": unique_run_id,
        "cpu_percent_avg": 35.0,
        "memory_mb_peak": 140.0,
        "status": "FAILED",
    }
    res1 = client.post("/api/v1/telemetry/record", json=fail_payload)
    assert res1.status_code == 201

    # 2. Attempt rollback to RUNNING
    run_payload = {
        "pipeline_run_id": unique_run_id,
        "cpu_percent_avg": 36.0,
        "memory_mb_peak": 142.0,
        "status": "RUNNING",
    }
    res2 = client.post("/api/v1/telemetry/record", json=run_payload)
    assert res2.status_code == 201

    # 3. Query DB to confirm status remained FAILED
    db = TestingSessionLocal()
    run = db.query(PipelineRun).filter(PipelineRun.id == unique_run_id).first()
    assert run is not None
    assert run.status == "FAILED"
    db.close()


def test_api_record_telemetry_supported_lifecycle_statuses():
    """Verifies that all supported PipelineLifecycleStatus enum values are accepted."""
    for st in ["RUNNING", "SUCCESS", "FAILED", "ABORTED", "CANCELLED"]:
        payload = {
            "pipeline_run_id": "test-run-sec-001",
            "cpu_percent_avg": 25.0,
            "memory_mb_peak": 110.0,
            "status": st,
        }
        res = client.post("/api/v1/telemetry/record", json=payload)
        assert res.status_code == 201


def test_api_detect_anomalies():
    payload = {
        "current_run": {"duration_sec": 48.0, "memory_mb_peak": 150.0, "cpu_percent_avg": 50.0},
        "historical_runs": [
            {"duration_sec": 12.0, "memory_mb_peak": 140.0, "cpu_percent_avg": 48.0},
            {"duration_sec": 11.5, "memory_mb_peak": 142.0, "cpu_percent_avg": 47.0},
            {"duration_sec": 12.5, "memory_mb_peak": 139.0, "cpu_percent_avg": 49.0},
            {"duration_sec": 12.0, "memory_mb_peak": 141.0, "cpu_percent_avg": 48.5},
            {"duration_sec": 11.8, "memory_mb_peak": 140.5, "cpu_percent_avg": 48.0},
        ],
    }

    res = client.post("/api/v1/telemetry/detect-anomalies", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["is_anomalous"] is True
    assert data["anomalies_count"] >= 1
    assert data["anomalies"][0]["type"] == "EXECUTION_TIME_SPIKE"


def test_api_correlate_failures():
    payload = {
        "time_window_seconds": 3600,
        "events": [
            {
                "event_id": "f1",
                "repository": "AutonomousDevOps/CI-CD-PIPELINE",
                "commit_hash": "sha-1",
                "workflow_name": "CI",
                "error_message": "TimeoutError: Database connection timed out after 5000ms",
            },
            {
                "event_id": "f2",
                "repository": "AutonomousDevOps/CI-CD-PIPELINE",
                "commit_hash": "sha-2",
                "workflow_name": "CI",
                "error_message": "TimeoutError: Database connection timed out after 5000ms",
            },
        ],
    }

    res = client.post("/api/v1/telemetry/correlate-failures", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["correlated_groups_count"] == 1
    assert data["groups"][0]["is_systemic"] is True
