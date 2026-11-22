"""
API Tests for Plan Generation & Retrieval Endpoints.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.database.session import get_db
from app.main import app

# Setup shared in-memory test database with StaticPool for API testing
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_api_generate_plan_optimized():
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


def test_api_generate_plan_auth_fallback():
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


def test_api_list_plans():
    response = client.get("/api/v1/plans?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "plans" in data
    assert "count" in data
    assert data["count"] >= 2


def test_api_plan_not_found():
    response = client.get("/api/v1/plans/non-existent-uuid-99999")
    assert response.status_code == 404
