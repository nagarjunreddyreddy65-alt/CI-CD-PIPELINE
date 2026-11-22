"""
API tests for Prediction & ML Endpoints.
"""

import tempfile

import pytest
from fastapi import status

import app.api.routes.predictions as predictions_route
from app.ml.model_manager import ModelManager


@pytest.fixture(autouse=True)
def isolate_predictions_model_manager():
    """Isolates model_manager to a temporary directory so training tests do not overwrite repository models."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_mm = ModelManager(registry_dir=temp_dir)
        temp_mm.train_and_persist(n_samples=40)
        old_mm = predictions_route.model_manager
        predictions_route.model_manager = temp_mm
        try:
            yield temp_mm
        finally:
            predictions_route.model_manager = old_mm


def test_predict_endpoint(client):
    """Tests POST /api/v1/predictions/predict returns failure probability and runtime forecast."""
    payload = {
        "changed_files_count": 2,
        "lines_added": 35,
        "lines_deleted": 8,
        "affected_modules_count": 1,
        "selected_tests_count": 6,
        "is_sensitive_change": False,
        "has_test_file_changes": False,
        "historical_failure_rate": 0.05,
        "previous_execution_duration": 18.0,
    }
    response = client.post("/api/v1/predictions/predict", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert "failure_prediction" in data
    assert 0.0 <= data["failure_prediction"]["predicted_failure_probability"] <= 1.0
    assert data["runtime_prediction"]["predicted_duration_sec"] > 0.0


def test_train_endpoint(client):
    """Tests POST /api/v1/predictions/train triggers model retraining."""
    payload = {"n_samples": 25, "data_source": "SYNTHETIC_BOOTSTRAP"}
    response = client.post("/api/v1/predictions/train", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert data["data"]["status"] == "TRAINED_AND_SAVED"
    assert data["data"]["provenance"] == "SYNTHETIC_BOOTSTRAP"
    assert data["data"]["is_production_ready"] is False
    assert data["data"]["samples"] == 25


def test_train_endpoint_genuine_telemetry_insufficient_samples(client):
    """Tests POST /api/v1/predictions/train rejects genuine training when < 15 runs exist."""
    payload = {"n_samples": 25, "data_source": "GENUINE_PIPELINE_TELEMETRY"}
    response = client.post("/api/v1/predictions/train", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "minimum required is 15" in response.json()["detail"]


def test_train_endpoint_genuine_telemetry_success(client, db_session):
    """Tests POST /api/v1/predictions/train succeeds with real DB features when >= 15 runs exist."""
    from app.database.models import Commit, PipelineRun, Repository

    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    for i in range(16):
        commit = Commit(
            repository_id=repo.id,
            commit_hash=f"train-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@ci.local",
            message=f"Commit {i}",
        )
        db_session.add(commit)
        db_session.flush()
        status_val = "FAILED" if i % 4 == 0 else "SUCCESS"
        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status=status_val,
            is_optimized=True,
            total_duration_sec=15.0 + float(i),
        )
        db_session.add(run)
    db_session.commit()

    payload = {"n_samples": 16, "data_source": "GENUINE_PIPELINE_TELEMETRY"}
    response = client.post("/api/v1/predictions/train", json=payload)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["data"]["provenance"] == "GENUINE_PIPELINE_TELEMETRY"
    assert data["data"]["is_production_ready"] is True
    assert data["data"]["failure_metrics"]["evaluated_on"] == "HOLDOUT_TEST_SPLIT"
    assert data["data"]["runtime_metrics"]["evaluated_on"] == "HOLDOUT_TEST_SPLIT"


def test_get_models_status_endpoint(client):
    """Tests GET /api/v1/predictions/models returns active model metadata."""
    response = client.get("/api/v1/predictions/models")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert "failure_predictor" in data
    assert "runtime_predictor" in data
