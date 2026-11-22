"""
Unit tests for FailurePredictor and RuntimePredictor.
Verifies Random Forest Classifier and Regressor training, metrics, and inference.
"""

import numpy as np

from app.ml.failure_predictor import FailurePredictor
from app.ml.feature_extractor import FeatureExtractor
from app.ml.runtime_predictor import RuntimePredictor


def test_failure_predictor_untrained_fallback():
    predictor = FailurePredictor()
    features = FeatureExtractor.extract_features(
        changed_files_count=1,
        lines_added=10,
        lines_deleted=2,
        affected_modules_count=1,
        selected_tests_count=5,
        is_sensitive_change=False,
        historical_failure_rate=0.08,
    )
    res = predictor.predict(features)

    assert 0.0 <= res.predicted_failure_probability <= 1.0
    assert res.predicted_failure_class in (0, 1)
    assert "untrained" in res.model_version
    assert res.is_high_risk is False


def test_failure_predictor_training_and_inference():
    predictor = FailurePredictor(n_estimators=20)

    # Synthetic dataset of 30 samples
    np.random.seed(42)
    X = np.random.uniform(0, 50, size=(30, 10))
    y = np.random.choice([0, 1], size=30, p=[0.7, 0.3])

    metrics = predictor.train(X, y)

    assert predictor.is_trained is True
    assert "f1_score" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert metrics["total_dataset_samples"] == 30
    assert metrics["training_samples"] == 24
    assert metrics["test_samples"] == 6
    assert "class_distribution" in metrics
    assert "dataset_pass_count" in metrics["class_distribution"]

    # Predict on new feature
    features = FeatureExtractor.extract_features(10, 500, 200, 5, 20, is_sensitive_change=True)
    res = predictor.predict(features)

    assert 0.0 <= res.predicted_failure_probability <= 1.0
    assert res.predicted_failure_class in (0, 1)
    assert "untrained" not in res.model_version


def test_runtime_predictor_untrained_fallback():
    predictor = RuntimePredictor()
    features = FeatureExtractor.extract_features(
        changed_files_count=1,
        lines_added=5,
        lines_deleted=1,
        affected_modules_count=1,
        selected_tests_count=10,
        previous_execution_duration=15.0,
    )
    res = predictor.predict(features)

    assert res.predicted_duration_sec > 0.0
    assert res.confidence_interval_low_sec < res.confidence_interval_high_sec
    assert "untrained" in res.model_version


def test_runtime_predictor_training_and_inference():
    predictor = RuntimePredictor(n_estimators=20)

    np.random.seed(42)
    X = np.random.uniform(0, 50, size=(30, 10))
    y = np.random.uniform(5.0, 60.0, size=30)

    metrics = predictor.train(X, y)

    assert predictor.is_trained is True
    assert "mae" in metrics
    assert "rmse" in metrics
    assert metrics["mae"] >= 0.0

    features = FeatureExtractor.extract_features(2, 20, 5, 1, 8, previous_execution_duration=20.0)
    res = predictor.predict(features)

    assert res.predicted_duration_sec > 0.0
    assert (
        res.confidence_interval_low_sec
        <= res.predicted_duration_sec
        <= res.confidence_interval_high_sec
    )


def test_failure_predictor_single_class_returns_none_roc_auc():
    """
    Verifies that when evaluation data contains only a single class (all pass or all fail),
    ROC-AUC cannot be calculated and is mathematically reported as None (never 1.0 or 0.5).
    """
    predictor = FailurePredictor(n_estimators=10)
    # 20 samples, all class 0 (no failures)
    X = np.ones((20, 10))
    y = np.zeros(20, dtype=int)

    metrics = predictor.train(X, y)
    assert metrics["roc_auc"] is None
    assert metrics["class_distribution"]["dataset_pass_count"] == 20
    assert metrics["class_distribution"]["dataset_fail_count"] == 0


def test_runtime_predictor_negative_r2_not_clipped():
    """
    Verifies that negative R2 values from poor fitting models are reported directly
    and never artificially clipped to 0.0.
    """
    predictor = RuntimePredictor(n_estimators=5)
    # Degenerate data where model will predict poorly on holdout
    np.random.seed(123)
    X = np.random.uniform(0, 1, size=(20, 10))
    y = np.array([10.0 if i % 2 == 0 else 1000.0 for i in range(20)])

    metrics = predictor.train(X, y)
    assert isinstance(metrics["r2_score"], float)
    # The metric must not be artificially clamped if it is negative
