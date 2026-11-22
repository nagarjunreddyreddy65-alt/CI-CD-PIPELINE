"""
Unit tests for ModelManager.
Verifies model persistence, artifact loading, provenance tracking, and Safety Rule 17.
"""

import json
import os
import shutil
import tempfile

import pytest

from app.ml.model_manager import ModelManager


@pytest.fixture
def temp_manager():
    temp_dir = tempfile.mkdtemp()
    manager = ModelManager(registry_dir=temp_dir)
    yield manager
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_synthetic_data_generation(temp_manager):
    X, y_fail, y_time = temp_manager.generate_synthetic_historical_data(n_samples=40)

    assert X.shape == (40, 10)
    assert len(y_fail) == 40
    assert len(y_time) == 40
    assert set(y_fail).issubset({0, 1})
    assert all(t > 0 for t in y_time)


def test_minimum_training_samples_enforced(temp_manager):
    """Safety Rule 17: Training with fewer than 15 samples must raise ValueError."""
    with pytest.raises(ValueError, match="less than the required minimum of 15"):
        temp_manager.train_and_persist(n_samples=10)


def test_train_and_persist_and_load(temp_manager):
    result = temp_manager.train_and_persist(n_samples=30)

    assert result["status"] == "TRAINED_AND_SAVED"
    assert result["samples"] == 30
    assert result["provenance"] == "SYNTHETIC_BOOTSTRAP"
    assert os.path.exists(result["artifact_paths"]["failure_model"])
    assert os.path.exists(result["artifact_paths"]["runtime_model"])
    assert os.path.exists(result["artifact_paths"]["metadata"])

    # Verify provenance metadata file
    with open(result["artifact_paths"]["metadata"]) as f:
        meta = json.load(f)
    assert meta["provenance"] == "SYNTHETIC_BOOTSTRAP"
    assert meta["is_production_ready"] is False

    # Test loading into a new manager
    new_manager = ModelManager(registry_dir=temp_manager.registry_dir)
    loaded = new_manager.load_models()

    assert loaded is True
    assert new_manager.failure_predictor.is_trained is True
    assert new_manager.runtime_predictor.is_trained is True


def test_provenance_and_can_predict_rule_17(temp_manager):
    """Verifies that synthetic bootstrap samples do not satisfy genuine historical run requirements."""
    temp_manager.train_and_persist(n_samples=30, data_source="SYNTHETIC_BOOTSTRAP")

    # With 0 genuine historical runs: cannot predict
    can_pred, reason = temp_manager.can_predict(genuine_historical_runs_count=0)
    assert can_pred is False
    assert "Safety Rule 14" in reason or "Safety Rule 17" in reason

    # With 10 genuine historical runs (< 15): cannot predict
    can_pred, reason = temp_manager.can_predict(genuine_historical_runs_count=10)
    assert can_pred is False

    # With 15 genuine historical runs: synthetic model STILL cannot predict (Safety Rule 14 provenance rejection)
    can_pred, reason = temp_manager.can_predict(genuine_historical_runs_count=15)
    assert can_pred is False
    assert "Safety Rule 14" in reason
    assert "SYNTHETIC_BOOTSTRAP" in reason

    # When retrained with genuine pipeline telemetry and certified production ready:
    X, y_fail, y_time = temp_manager.generate_synthetic_historical_data(30)
    temp_manager.train_and_persist(
        n_samples=30,
        data_source="GENUINE_PIPELINE_TELEMETRY",
        genuine_historical_runs_count=15,
        training_data=(X, y_fail, y_time),
        is_production_ready=True,
    )
    can_pred, reason = temp_manager.can_predict(genuine_historical_runs_count=15)
    assert can_pred is True
    assert "ready" in reason.lower()
