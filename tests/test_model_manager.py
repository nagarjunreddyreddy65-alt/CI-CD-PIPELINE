"""
Unit tests for ModelManager.
Verifies model persistence, artifact loading, and Safety Rule 17 (minimum training samples).
"""

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
    """Safety Rule 17: Training with fewer than 15 historical runs must raise ValueError."""
    with pytest.raises(ValueError, match="less than the required minimum of 15"):
        temp_manager.train_and_persist(n_samples=10)


def test_train_and_persist_and_load(temp_manager):
    result = temp_manager.train_and_persist(n_samples=30)

    assert result["status"] == "TRAINED_AND_SAVED"
    assert result["samples"] == 30
    assert os.path.exists(result["artifact_paths"]["failure_model"])
    assert os.path.exists(result["artifact_paths"]["runtime_model"])

    # Test loading into a new manager
    new_manager = ModelManager(registry_dir=temp_manager.registry_dir)
    loaded = new_manager.load_models()

    assert loaded is True
    assert new_manager.failure_predictor.is_trained is True
    assert new_manager.runtime_predictor.is_trained is True
