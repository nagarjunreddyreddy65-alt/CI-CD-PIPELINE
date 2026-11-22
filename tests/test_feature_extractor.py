"""
Unit tests for FeatureExtractor.
Verifies pre-execution feature vector generation, data types, and information leakage prevention.
"""

import numpy as np

from app.ml.feature_extractor import FeatureExtractor


def test_feature_extraction_bounds():
    features = FeatureExtractor.extract_features(
        changed_files_count=3,
        lines_added=50,
        lines_deleted=10,
        affected_modules_count=2,
        selected_tests_count=12,
        is_sensitive_change=True,
        has_test_file_changes=False,
        historical_failure_rate=0.15,
        previous_execution_duration=25.5,
    )

    assert features.changed_files_count == 3
    assert features.lines_added == 50
    assert features.lines_deleted == 10
    assert features.total_lines_changed == 60
    assert features.is_sensitive_change == 1
    assert features.has_test_file_changes == 0
    assert features.historical_failure_rate == 0.15
    assert features.previous_execution_duration == 25.5


def test_feature_negative_clamping():
    """Negative values should be clamped to valid lower bounds."""
    features = FeatureExtractor.extract_features(
        changed_files_count=-5,
        lines_added=-10,
        lines_deleted=-2,
        affected_modules_count=-1,
        selected_tests_count=-10,
        historical_failure_rate=1.8,  # Exceeds 1.0
        previous_execution_duration=-100.0,
    )

    assert features.changed_files_count == 0
    assert features.lines_added == 0
    assert features.lines_deleted == 0
    assert features.total_lines_changed == 0
    assert features.historical_failure_rate == 1.0
    assert features.previous_execution_duration == 1.0


def test_feature_array_conversion():
    features = FeatureExtractor.extract_features(
        changed_files_count=2,
        lines_added=20,
        lines_deleted=5,
        affected_modules_count=1,
        selected_tests_count=6,
    )
    arr = features.to_array()

    assert isinstance(arr, np.ndarray)
    assert arr.shape == (1, 10)
    assert arr.dtype == np.float64


def test_no_future_leakage():
    """Confirms no post-pipeline attributes (actual pass/fail, actual duration) exist in feature vector."""
    features = FeatureExtractor.extract_features(1, 10, 5, 1, 5)
    f_dict = features.to_dict()

    assert "actual_duration" not in f_dict
    assert "current_failure" not in f_dict
    assert "actual_failed_tests" not in f_dict
    assert len(FeatureExtractor.FEATURE_NAMES) == 10
