"""
API Tests for Plan Generation & Retrieval Endpoints.
"""

import pytest

from app.database.models import Commit, PipelineRun, Repository


@pytest.fixture(autouse=True)
def seed_plans_db(db_session):
    """Seeds historical pipeline runs so the test database meets the MIN_TRAINING_RUNS threshold."""
    repo = (
        db_session.query(Repository)
        .filter(Repository.name == "AutonomousDevOps/CI-CD-PIPELINE")
        .first()
    )
    if not repo:
        repo = Repository(
            name="AutonomousDevOps/CI-CD-PIPELINE",
            owner="AutonomousDevOps",
            clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
            default_branch="main",
        )
        db_session.add(repo)
        db_session.flush()

    for i in range(20):
        c_hash = f"seed-plan-commit-{i:03d}"
        commit = Commit(
            repository_id=repo.id,
            commit_hash=c_hash,
            branch="main",
            author_name="CI Runner",
            author_email="runner@ci.local",
            message=f"Seed pipeline run {i}",
        )
        db_session.add(commit)
        db_session.flush()
        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=20.0,
        )
        db_session.add(run)
    db_session.commit()


def test_api_generate_plan_optimized(client):
    payload = {
        "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
        "commit_hash": "a1b2c3d4e5f6",
        "branch": "main",
        "author_name": "Student",
        "author_email": "student@example.edu",
        "commit_message": "Update math utils",
        "changed_files": [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 6,
                "lines_deleted": 2,
            }
        ],
        "historical_failure_rate": 0.05,
        "previous_execution_duration": 22.0,
        "historical_runs_count": 25,
        "risk_threshold": 0.60,
    }

    response = client.post("/api/v1/plans/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "OPTIMIZED"
    assert data["is_optimized"] is True
    assert data["fallback_triggered"] is False
    assert data["selected_tests_count"] > 0
    assert data["tests_reduction_pct"] > 0.0
    assert "pytest" in data["pytest_command"]
    assert data["plan_id"] is not None

    # Retrieve via GET /plans/{plan_id}
    plan_id = data["plan_id"]
    get_res = client.get(f"/api/v1/plans/{plan_id}")
    assert get_res.status_code == 200
    plan_data = get_res.json()
    assert plan_data["id"] == plan_id
    assert plan_data["decision"] == "OPTIMIZED"


def test_api_generate_plan_auth_fallback(client):
    payload = {
        "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
        "commit_hash": "f6e5d4c3b2a1",
        "branch": "feature/auth",
        "author_name": "Security Engineer",
        "author_email": "sec@example.edu",
        "commit_message": "Enhance token security",
        "changed_files": [
            {
                "file_path": "sample_app/auth/security_service.py",
                "change_type": "MODIFIED",
                "lines_added": 15,
                "lines_deleted": 5,
            }
        ],
        "historical_failure_rate": 0.02,
        "previous_execution_duration": 25.0,
        "historical_runs_count": 25,
        "risk_threshold": 0.50,
    }

    response = client.post("/api/v1/plans/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "FULL_SUITE"
    assert data["fallback_triggered"] is True
    assert "Safety Rule 2" in data["fallback_reason"]
    assert "RULE_2_AUTH" in data["triggered_safety_rules"]
    assert data["tests_reduction_pct"] == 0.0


def test_api_list_plans(client):
    # Generate at least two plans
    for i in range(2):
        client.post(
            "/api/v1/plans/generate",
            json={
                "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
                "commit_hash": f"list-plan-sha-{i}",
                "branch": "main",
                "author_name": "Dev",
                "author_email": "dev@ci.local",
                "commit_message": f"List plan test {i}",
                "changed_files": [
                    {
                        "file_path": "sample_app/utils/math_ops.py",
                        "change_type": "MODIFIED",
                        "lines_added": 2,
                        "lines_deleted": 0,
                    }
                ],
            },
        )
    response = client.get("/api/v1/plans?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert "count" in data
    assert data["count"] >= 2


def test_api_plan_not_found(client):
    response = client.get("/api/v1/plans/non-existent-uuid-99999")
    assert response.status_code == 404


def test_api_generate_plan_path_traversal_rejected(client):
    """Tests POST /api/v1/plans/generate rejects path traversal attempts."""
    payload = {
        "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
        "commit_hash": "c81a293f0b4d",
        "branch": "main",
        "author_name": "Developer",
        "author_email": "dev@example.com",
        "commit_message": "Exploit attempt",
        "changed_files": [
            {
                "file_path": "../../etc/shadow",
                "change_type": "MODIFIED",
                "lines_added": 1,
                "lines_deleted": 0,
            }
        ],
    }
    response = client.post("/api/v1/plans/generate", json=payload)
    assert response.status_code == 400
    assert "path traversal is forbidden" in response.json()["detail"]


def test_api_generate_plan_spoofed_runs_rejected(client, db_session):
    """
    Verifies that when database has insufficient genuine runs (< 15),
    a caller supplying a high historical_runs_count is ignored, and Rule 17 triggers FULL_SUITE.
    """
    db_session.query(PipelineRun).delete()
    db_session.commit()

    payload = {
        "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
        "commit_hash": "spoof-test-hash",
        "branch": "main",
        "author_name": "Adversary",
        "author_email": "attacker@example.com",
        "commit_message": "Attempt to bypass Rule 17",
        "changed_files": [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 1,
            }
        ],
        "historical_runs_count": 999,  # Spoofed high count
    }

    res = client.post("/api/v1/plans/generate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["decision"] == "FULL_SUITE"
    assert data["fallback_triggered"] is True
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" in data["triggered_safety_rules"]
