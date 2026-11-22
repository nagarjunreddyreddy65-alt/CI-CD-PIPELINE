"""
API tests for Prediction & ML Endpoints.
"""

from fastapi import status


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


def test_get_models_status_endpoint(client):
    """Tests GET /api/v1/predictions/models returns active model metadata."""
    response = client.get("/api/v1/predictions/models")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["success"] is True
    assert "failure_predictor" in data
    assert "runtime_predictor" in data
