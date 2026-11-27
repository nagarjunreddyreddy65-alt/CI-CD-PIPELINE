"""
Tests for Final Audit Remediation Verification
Repository: CI-CD-PIPELINE

Validates:
1. Live feature schema incompatibility:
   - PipelineFeatures.to_travistorrent_array() raises NotImplementedError.
2. Unsupported live inference rejection:
   - Benchmark TravisTorrent models reject live PipelineFeatures with descriptive ValueError.
   - Benchmark models accept valid (N, 10) numpy arrays for historical evaluation.
   - DecisionEngine catches unsupported inference and deterministically falls back to FULL_SUITE (Rule 15).
3. Elimination of illustrative fallbacks in evaluation graphs:
   - generate_ml_evaluation_graphs.py functions fail fast with RuntimeError when empirical data is missing.
4. 3-Way chronological split integrity:
   - Model metadata confirms 70/15/15 chronological partition with strictly monotonic indices.
5. Kubernetes PostgreSQL credentials security:
   - k8s/postgres.yaml contains no hardcoded passwords and uses secretKeyRef.
   - k8s/secrets.example.yaml exists.
6. Deterministic Safety Fallbacks:
   - Rules 1, 7, 14, 15 enforce FULL_SUITE without exception.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.ml.failure_predictor import FailurePredictor
from app.ml.feature_extractor import PipelineFeatures
from app.ml.runtime_predictor import RuntimePredictor
from app.optimization.decision_engine import DecisionEngine, ExecutionDecision

REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================================
# 1. Feature Schema Incompatibility & Live Rejection
# ============================================================================


def test_pipeline_features_to_travistorrent_array_raises_not_implemented():
    """Verify that mapping live Git diff features to TravisTorrent schema raises NotImplementedError."""
    features = PipelineFeatures(
        changed_files_count=5,
        lines_added=120,
        lines_deleted=45,
        total_lines_changed=165,
        affected_modules_count=3,
        selected_tests_count=12,
        is_sensitive_change=0,
        has_test_file_changes=1,
        historical_failure_rate=0.08,
        previous_execution_duration=42.5,
    )
    with pytest.raises(NotImplementedError) as exc_info:
        features.to_travistorrent_array()

    assert "semantically invalid" in str(exc_info.value).lower()
    assert "travistorrent" in str(exc_info.value).lower()


def test_failure_predictor_rejects_live_features_for_travistorrent_benchmark_model():
    """Verify FailurePredictor raises ValueError when a TravisTorrent model is given PipelineFeatures."""
    clf = FailurePredictor(
        model_version="v1.0.0",
        feature_names=[
            "build_number",
            "prior_build_count",
            "previous_failure",
            "previous_duration_sec",
            "historical_failure_rate",
            "rolling_fail_rate_5",
            "rolling_duration_avg_5",
            "is_pull_request",
            "is_master_branch",
            "prior_test_count",
        ],
    )
    clf.is_trained = True
    clf.model = MagicMock()

    live_features = PipelineFeatures(
        changed_files_count=2,
        lines_added=10,
        lines_deleted=5,
        total_lines_changed=15,
        affected_modules_count=1,
        selected_tests_count=8,
        is_sensitive_change=0,
        has_test_file_changes=1,
        historical_failure_rate=0.05,
        previous_execution_duration=30.0,
    )

    with pytest.raises(ValueError) as exc_info:
        clf.predict(live_features)

    assert "Unsupported inference" in str(exc_info.value)
    assert "historical Travis CI benchmark schema" in str(exc_info.value)


def test_runtime_predictor_rejects_live_features_for_travistorrent_benchmark_model():
    """Verify RuntimePredictor raises ValueError when a TravisTorrent model is given PipelineFeatures."""
    reg = RuntimePredictor(
        model_version="v1.0.0",
        feature_names=[
            "build_number",
            "prior_build_count",
            "previous_failure",
            "previous_duration_sec",
            "historical_failure_rate",
            "rolling_fail_rate_5",
            "rolling_duration_avg_5",
            "is_pull_request",
            "is_master_branch",
            "prior_test_count",
        ],
    )
    reg.is_trained = True
    reg.model = MagicMock()

    live_features = PipelineFeatures(
        changed_files_count=2,
        lines_added=10,
        lines_deleted=5,
        total_lines_changed=15,
        affected_modules_count=1,
        selected_tests_count=8,
        is_sensitive_change=0,
        has_test_file_changes=1,
        historical_failure_rate=0.05,
        previous_execution_duration=30.0,
    )

    with pytest.raises(ValueError) as exc_info:
        reg.predict(live_features)

    assert "Unsupported inference" in str(exc_info.value)
    assert "historical Travis CI benchmark schema" in str(exc_info.value)


def test_benchmark_models_accept_raw_numpy_arrays_for_evaluation():
    """Verify benchmark models accept raw (1, 10) or (N, 10) arrays for offline benchmarking."""
    clf = FailurePredictor(
        model_version="v1.0.0",
        feature_names=[
            "build_number",
            "prior_build_count",
            "previous_failure",
            "previous_duration_sec",
            "historical_failure_rate",
            "rolling_fail_rate_5",
            "rolling_duration_avg_5",
            "is_pull_request",
            "is_master_branch",
            "prior_test_count",
        ],
    )
    clf.is_trained = True
    clf.model = MagicMock()
    clf.model.predict_proba.return_value = np.array([[0.8, 0.2]])

    raw_features = np.zeros((1, 10), dtype=float)
    res = clf.predict(raw_features)
    assert res.predicted_failure_probability == pytest.approx(0.2)
    assert res.predicted_failure_class == 0


def test_decision_engine_catches_unsupported_inference_and_falls_back_to_full_suite():
    """Verify DecisionEngine enforces Safety Rule 15 when unsupported inference error occurs."""
    engine = DecisionEngine(root_dir=str(REPO_ROOT))
    benchmark_clf = FailurePredictor(
        model_version="v1.0.0",
        feature_names=["build_number", "prior_build_count"],
    )
    benchmark_clf.is_trained = True
    benchmark_clf.model = MagicMock()
    engine.model_manager.failure_predictor = benchmark_clf

    plan = engine.generate_plan(
        changed_file_entries=[
            {
                "path": "sample_app/utils/math_ops.py",
                "status": "modified",
                "lines_added": 5,
                "lines_deleted": 2,
            }
        ],
        historical_runs_count=20,
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.fallback_triggered is True
    assert "RULE_15_MODEL_VERSION_MISMATCH" in plan.triggered_safety_rules


# ============================================================================
# 2. Illustrative Fallback Elimination in Evaluation Graphs
# ============================================================================


def test_graph_generator_raises_runtime_error_on_missing_roc():
    """Verify plot_roc_curve raises RuntimeError if empirical ROC data is missing."""
    from scripts.generate_ml_evaluation_graphs import plot_roc_curve

    metadata_no_roc = {
        "failure_metrics": {"recall": 0.9, "precision": 0.1, "roc_auc": 0.6},
        "empirical_eval_data": {},
    }
    with pytest.raises(RuntimeError) as exc_info:
        plot_roc_curve(metadata_no_roc)

    assert "Empirical ROC holdout curve data missing" in str(exc_info.value)


def test_graph_generator_raises_runtime_error_on_missing_actual_vs_predicted():
    """Verify plot_actual_vs_predicted raises RuntimeError if empirical regression data is missing."""
    from scripts.generate_ml_evaluation_graphs import plot_actual_vs_predicted

    metadata_no_reg = {
        "runtime_metrics": {"mae": 196.0, "rmse": 417.0, "r2_score": -0.028},
        "empirical_eval_data": {},
    }
    with pytest.raises(RuntimeError) as exc_info:
        plot_actual_vs_predicted(metadata_no_reg)

    assert "Empirical runtime actual-vs-predicted regression data missing" in str(exc_info.value)


def test_graph_generator_raises_runtime_error_on_missing_panel_data():
    """Verify plot_master_evaluation_panel raises RuntimeError if empirical data is missing."""
    from scripts.generate_ml_evaluation_graphs import plot_master_evaluation_panel

    metadata_no_panel = {
        "failure_metrics": {
            "confusion_matrix": [[10, 0], [0, 10]],
            "recall": 0.9,
            "precision": 0.1,
            "roc_auc": 0.6,
            "test_samples": 20,
        },
        "runtime_metrics": {"mae": 196.0, "rmse": 417.0, "r2_score": -0.028},
        "empirical_eval_data": {},
    }
    with pytest.raises(RuntimeError) as exc_info:
        plot_master_evaluation_panel(
            metadata=metadata_no_panel,
            feature_names=["f1"],
            fp_importances=[0.5],
            rp_importances=[0.5],
        )

    assert "Empirical ROC holdout curve data missing" in str(exc_info.value)


# ============================================================================
# 3. 3-Way Chronological Split & Provenance Verification
# ============================================================================


def test_model_metadata_3way_chronological_split_and_honest_metrics():
    """Verify model_metadata.json records the 3-way split and untouched test metrics."""
    metadata_path = REPO_ROOT / "app" / "ml" / "models" / "model_metadata.json"
    assert metadata_path.exists(), "model_metadata.json must exist in repository"

    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Provenance
    assert meta["provenance"] == "TRAVISTORRENT_GENUINE_DATASET"
    assert meta["sample_count"] == 3808
    assert meta["genuine_historical_runs_count"] == 3808

    # Split notes
    notes = meta["evaluation_notes"]
    assert notes["split_strategy"] == "3_WAY_CHRONOLOGICAL_70_15_15"
    assert notes["train_ratio"] == 0.70
    assert notes["val_ratio"] == 0.15
    assert notes["test_ratio"] == 0.15

    # Failure metrics on untouched test split
    fail_m = meta["failure_metrics"]
    assert fail_m["evaluated_on"] == "HOLDOUT_TEST_SPLIT"
    assert fail_m["training_samples"] == 2665
    assert fail_m["validation_samples"] == 571
    assert fail_m["test_samples"] == 572
    assert fail_m["recall"] >= 0.90, f"Expected high recall >= 0.90, got {fail_m['recall']}"
    assert fail_m["precision"] < 0.25, "Precision must honestly reflect CI failure imbalance"

    # Runtime metrics on untouched test split
    time_m = meta["runtime_metrics"]
    assert time_m["evaluated_on"] == "HOLDOUT_TEST_SPLIT"
    assert time_m["training_samples"] == 2665
    assert time_m["validation_samples"] == 571
    assert time_m["test_samples"] == 572
    assert time_m["r2_score"] < 0.05, (
        "R2 score must honestly reflect CI build duration variance without inflation"
    )

    # Validation metrics present
    assert "validation_metrics" in meta
    assert "failure" in meta["validation_metrics"]
    assert "runtime" in meta["validation_metrics"]


# ============================================================================
# 4. Kubernetes PostgreSQL Credentials Security
# ============================================================================


def test_k8s_postgres_manifest_has_no_hardcoded_passwords():
    """Verify k8s/postgres.yaml uses secretKeyRef and contains no plaintext passwords."""
    manifest_path = REPO_ROOT / "k8s" / "postgres.yaml"
    assert manifest_path.exists(), "k8s/postgres.yaml must exist"

    content = manifest_path.read_text(encoding="utf-8")

    # Hardcoded credential must not exist
    assert "devops_secure_password_2026" not in content
    assert "postgres_secret_key" not in content

    # Must use secretKeyRef
    assert "secretKeyRef:" in content
    assert "autonomous-devops-secrets" in content
    assert "postgres-user" in content
    assert "postgres-password" in content
    assert "postgres-db" in content


def test_k8s_secrets_example_template_exists():
    """Verify k8s/secrets.example.yaml template is provided."""
    template_path = REPO_ROOT / "k8s" / "secrets.example.yaml"
    assert template_path.exists(), "k8s/secrets.example.yaml must exist"

    content = template_path.read_text(encoding="utf-8")
    assert "POSTGRES_PASSWORD" in content or "postgres-password" in content
    assert "autonomous-devops-secrets" in content


# ============================================================================
# 5. Deterministic Safety Fallbacks (Rules 1, 7, 14, 15)
# ============================================================================


def test_safety_rule_1_migration_change_enforces_full_suite():
    """Verify database migration changes trigger RULE_1_MIGRATION and enforce FULL_SUITE."""
    engine = DecisionEngine(root_dir=str(REPO_ROOT))
    plan = engine.generate_plan(
        changed_file_entries=[
            {
                "path": "alembic/versions/001_create_tables.py",
                "status": "added",
                "lines_added": 25,
                "lines_deleted": 0,
            }
        ],
        historical_runs_count=20,
    )
    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert "RULE_1_MIGRATION" in plan.triggered_safety_rules


def test_safety_rule_7_ci_workflow_change_enforces_full_suite():
    """Verify CI workflow changes trigger RULE_7_CI_WORKFLOW and enforce FULL_SUITE."""
    engine = DecisionEngine(root_dir=str(REPO_ROOT))
    plan = engine.generate_plan(
        changed_file_entries=[
            {
                "path": ".github/workflows/ci.yml",
                "status": "modified",
                "lines_added": 2,
                "lines_deleted": 1,
            }
        ],
        historical_runs_count=20,
    )
    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert "RULE_7_CI_WORKFLOW" in plan.triggered_safety_rules


def test_safety_rule_14_missing_model_enforces_full_suite():
    """Verify untrained or missing models trigger RULE_14_MODEL_ARTIFACT_MISSING and enforce FULL_SUITE."""
    engine = DecisionEngine(root_dir=str(REPO_ROOT))
    engine.model_manager.can_predict = MagicMock(
        return_value=(False, "Safety Rule 14: Predictive ML models are not trained.")
    )

    plan = engine.generate_plan(
        changed_file_entries=[
            {
                "path": "app/service.py",
                "status": "modified",
                "lines_added": 2,
                "lines_deleted": 1,
            }
        ],
        historical_runs_count=0,
    )
    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules
