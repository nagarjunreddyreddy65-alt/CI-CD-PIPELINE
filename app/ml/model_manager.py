"""
Model Registry & Lifecycle Manager.
Handles model artifact persistence, versioning, minimum training sample validation,
provenance metadata tracking, and synthetic historical bootstrap data generation.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

import joblib
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.ml.failure_predictor import FailurePredictor
from app.ml.runtime_predictor import RuntimePredictor


class ModelManager:
    """
    Central manager for training, serializing, loading, and validating ML models.
    Enforces Safety Rule 17: Validates that minimum genuine historical samples (>= 15) are satisfied.
    Maintains rigorous provenance separation between synthetic bootstrap samples and genuine telemetry.
    """

    def __init__(self, registry_dir: str | None = None):
        self.registry_dir = os.path.abspath(registry_dir or settings.MODEL_REGISTRY_PATH)
        os.makedirs(self.registry_dir, exist_ok=True)

        self.failure_predictor = FailurePredictor()
        self.runtime_predictor = RuntimePredictor()
        self.metadata_path = os.path.join(self.registry_dir, "model_metadata.json")

    def extract_features_from_db_runs(
        self, runs: list[Any]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Extracts genuine pre-execution feature vectors and execution targets from historical database records.
        Eliminates training-data leakage:
        1. NEVER incorporates post-execution fields like 'fallback_triggered' or 'error_message' into input features.
        2. NEVER uses the current run's 'total_duration_sec' as its own previous duration feature.
        3. Preceding duration and failure rate are calculated strictly from chronologically antecedent runs.
        4. When 'Prediction.features_json' was captured pre-execution, uses those validated features.
        5. Incomplete, non-terminal, or zero-duration runs are excluded.
        Returns:
            X: features array (N, 10)
            y_fail: binary failure outcome array (N,) (1 = FAILED, 0 = SUCCESS)
            y_time: duration in seconds (N,)
        """
        # Filter for valid completed runs
        valid_runs = []
        for r in runs:
            status_val = getattr(r, "status", None)
            dur = float(getattr(r, "total_duration_sec", 0.0) or 0.0)
            if status_val in ["SUCCESS", "FAILED"] and dur > 0.0:
                valid_runs.append(r)

        # Sort chronologically by created_at if available
        def _get_sort_key(item: Any) -> float:
            created = getattr(item, "created_at", None)
            if created and hasattr(created, "timestamp"):
                return float(created.timestamp())
            return 0.0

        valid_runs.sort(key=_get_sort_key)

        X_list = []
        y_fail = []
        y_time = []

        for i, r in enumerate(valid_runs):
            feat_vec = None

            # 1. First preference: Check if pre-execution features were logged at plan-generation time
            preds = getattr(r, "predictions", None)
            pred = preds[0] if preds and len(preds) > 0 else getattr(r, "prediction", None)
            if pred and getattr(pred, "features_json", None):
                try:
                    f = json.loads(pred.features_json)
                    if isinstance(f, dict):
                        # Ensure strictly pre-execution keys
                        feat_vec = [
                            float(f.get("changed_files_count", 1)),
                            float(f.get("lines_added", 10)),
                            float(f.get("lines_deleted", 2)),
                            float(f.get("total_lines_changed", 12)),
                            float(f.get("affected_modules_count", 1)),
                            float(f.get("selected_tests_count", 5)),
                            float(1.0 if f.get("is_sensitive_change") else 0.0),
                            float(1.0 if f.get("has_test_file_changes") else 0.0),
                            float(f.get("historical_failure_rate", 0.05)),
                            float(f.get("previous_execution_duration", 25.0)),
                        ]
                except (json.JSONDecodeError, TypeError):
                    feat_vec = None

            # 2. Second preference: Reconstruct strictly from pre-execution commit/file entities
            if feat_vec is None:
                commit = getattr(r, "commit", None)
                changed_files = getattr(commit, "changed_files", []) if commit else []
                n_files = max(1, len(changed_files))
                lines_add = sum(getattr(cf, "lines_added", 0) for cf in changed_files)
                lines_del = sum(getattr(cf, "lines_deleted", 0) for cf in changed_files)
                tot_lines = lines_add + lines_del

                # Genuine pre-execution sensitivity: inspect file paths only; NEVER fallback_triggered!
                sensitive_keywords = [
                    "alembic",
                    "migration",
                    "auth",
                    "security",
                    "token",
                    "jwt",
                    "payment",
                    "billing",
                    "crypto",
                    "requirements",
                    "lock",
                    "workflow",
                ]
                is_sens = (
                    1
                    if any(
                        getattr(cf, "is_sensitive", False)
                        or any(
                            kw in getattr(cf, "file_path", "").lower() for kw in sensitive_keywords
                        )
                        for cf in changed_files
                    )
                    else 0
                )
                has_tests = (
                    1
                    if any("test" in getattr(cf, "file_path", "").lower() for cf in changed_files)
                    else 0
                )
                plan = getattr(r, "execution_plan", None)
                sel_tests = getattr(plan, "selected_tests_count", 5) if plan else 5

                # Preceding execution history: strictly from runs PRIOR to run i
                if i > 0:
                    prior_runs = valid_runs[:i]
                    prior_fails = sum(1 for p in prior_runs if getattr(p, "status", "") == "FAILED")
                    hist_fail_rate = round(prior_fails / len(prior_runs), 4)
                    prev_dur = float(getattr(valid_runs[i - 1], "total_duration_sec", 25.0) or 25.0)
                else:
                    # Documented baseline for the very first execution in repository history
                    hist_fail_rate = 0.05
                    prev_dur = 25.0

                feat_vec = [
                    float(n_files),
                    float(lines_add),
                    float(lines_del),
                    float(tot_lines),
                    float(max(1, n_files)),
                    float(sel_tests),
                    float(is_sens),
                    float(has_tests),
                    float(hist_fail_rate),
                    float(prev_dur),
                ]

            X_list.append(feat_vec)

            # Target extraction: genuine completed outcome
            status_val = getattr(r, "status", "SUCCESS")
            failed = 1 if status_val == "FAILED" else 0
            y_fail.append(failed)

            dur = float(getattr(r, "total_duration_sec", 20.0) or 20.0)
            y_time.append(max(1.0, round(dur, 2)))

        return (
            np.array(X_list, dtype=np.float64),
            np.array(y_fail, dtype=np.int32),
            np.array(y_time, dtype=np.float64),
        )

    def generate_synthetic_historical_data(
        self, n_samples: int = 50
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generates realistic synthetic pipeline history for model bootstrap & testing.
        Returns:
            X: features array (N, 10)
            y_fail: binary failure outcomes (N,)
            y_time: continuous runtime durations in seconds (N,)
        """
        np.random.seed(42)
        X_list = []
        y_fail = []
        y_time = []

        for _ in range(n_samples):
            changed_files = int(np.random.poisson(3) + 1)
            lines_add = int(np.random.exponential(40) + 5)
            lines_del = int(np.random.exponential(15) + 2)
            tot_lines = lines_add + lines_del
            affected_mods = int(np.random.poisson(2) + 1)
            selected_tests = int(np.random.randint(5, 35))
            is_sensitive = 1 if np.random.rand() < 0.15 else 0
            has_tests = 1 if np.random.rand() < 0.50 else 0
            hist_fail_rate = float(np.random.uniform(0.02, 0.20))
            prev_dur = float(np.random.uniform(5.0, 60.0))

            feature_vec = [
                changed_files,
                lines_add,
                lines_del,
                tot_lines,
                affected_mods,
                selected_tests,
                is_sensitive,
                has_tests,
                hist_fail_rate,
                prev_dur,
            ]
            X_list.append(feature_vec)

            # Failure logic: sensitive changes + large edits have higher failure probability
            fail_prob = (
                0.05
                + (0.35 if is_sensitive else 0.0)
                + (0.25 if tot_lines > 150 else 0.0)
                + hist_fail_rate
            )
            failed = 1 if np.random.rand() < fail_prob else 0
            y_fail.append(failed)

            # Runtime logic: base time + time per test + line diff penalty
            dur = max(
                2.0,
                3.0 + (selected_tests * 0.4) + (tot_lines * 0.02) + np.random.normal(0, 1.0),
            )
            y_time.append(round(dur, 2))

        return (
            np.array(X_list, dtype=np.float64),
            np.array(y_fail, dtype=np.int32),
            np.array(y_time, dtype=np.float64),
        )

    def train_and_persist(
        self,
        n_samples: int = 50,
        data_source: str = "SYNTHETIC_BOOTSTRAP",
        genuine_historical_runs_count: int = 0,
        training_data: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
        is_production_ready: bool | None = None,
    ) -> dict[str, Any]:
        """
        Trains both models on provided or generated samples and persists artifacts with provenance metadata.
        Explicitly tracks whether training used synthetic bootstrap data or genuine telemetry.
        """
        if data_source == "SYNTHETIC_BOOTSTRAP":
            # Synthetic bootstrap samples MUST NEVER count toward genuine historical runs
            genuine_historical_runs_count = 0
            is_prod_ready = False
        else:
            is_prod_ready = genuine_historical_runs_count >= settings.MIN_TRAINING_RUNS and (
                is_production_ready if is_production_ready is not None else True
            )

        if training_data is not None:
            X, y_fail, y_time = training_data
        else:
            if n_samples < settings.MIN_TRAINING_RUNS:
                raise ValueError(
                    f"Cannot train models: {n_samples} samples is less than the required minimum of {settings.MIN_TRAINING_RUNS}"
                )
            X, y_fail, y_time = self.generate_synthetic_historical_data(n_samples)

        fail_metrics = self.failure_predictor.train(X, y_fail)
        time_metrics = self.runtime_predictor.train(X, y_time)

        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        joblib.dump(self.failure_predictor, fail_path)
        joblib.dump(self.runtime_predictor, time_path)

        metadata = {
            "provenance": data_source,
            "sample_count": len(X),
            "genuine_historical_runs_count": genuine_historical_runs_count,
            "is_production_ready": is_prod_ready,
            "trained_at": datetime.now(UTC).isoformat(),
            "failure_metrics": fail_metrics,
            "runtime_metrics": time_metrics,
            "model_version": self.failure_predictor.model_version,
            "evaluation_notes": {
                "sample_size_limitation": "Small datasets (< 100 samples) exhibit higher variance.",
                "holdout_split_ratio": 0.20 if len(X) >= 15 else 0.0,
            },
        }

        try:
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except OSError as e:
            logger.warning(f"Could not persist model metadata to {self.metadata_path}: {e}")

        logger.info(
            f"Successfully trained models ({data_source}) and saved artifacts to {self.registry_dir}"
        )

        return {
            "status": "TRAINED_AND_SAVED",
            "provenance": data_source,
            "samples": len(X),
            "is_production_ready": is_prod_ready,
            "failure_metrics": fail_metrics,
            "runtime_metrics": time_metrics,
            "artifact_paths": {
                "failure_model": fail_path,
                "runtime_model": time_path,
                "metadata": self.metadata_path,
            },
        }

    def can_predict(self, genuine_historical_runs_count: int) -> tuple[bool, str]:
        """
        Validates whether models are authorized to produce optimization predictions.
        Enforces strict model provenance, certification, and Safety Rules 14 & 17:
        1. Both failure and runtime predictors must be loaded in memory and trained.
        2. Model metadata file (model_metadata.json) must exist and be valid JSON.
        3. Metadata 'provenance' must be exactly 'GENUINE_PIPELINE_TELEMETRY'.
        4. Metadata 'is_production_ready' must be True.
        5. Metadata 'sample_count' and 'genuine_historical_runs_count' must be >= settings.MIN_TRAINING_RUNS.
        6. Server-verified genuine historical runs must be >= settings.MIN_TRAINING_RUNS.
        Synthetic bootstrap models or models with missing/malformed metadata must NEVER authorize test skipping.
        """
        min_runs = settings.MIN_TRAINING_RUNS

        # 1. Require in-memory models to be loaded and trained
        if not self.failure_predictor.is_trained or not self.runtime_predictor.is_trained:
            return (
                False,
                "Safety Rule 14: Predictive ML models are not trained or artifacts are missing.",
            )

        # 2. Check metadata file exists
        if not os.path.exists(self.metadata_path):
            return (
                False,
                "Safety Rule 14: Model metadata file is missing. Untrained or unverified models cannot authorize optimization.",
            )

        # 3. Read and parse metadata
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            return (
                False,
                f"Safety Rule 14: Model metadata is corrupt or unreadable ({e}). Full suite fallback enforced.",
            )

        if not isinstance(metadata, dict):
            return (
                False,
                "Safety Rule 14: Model metadata is malformed. Full suite fallback enforced.",
            )

        provenance = metadata.get("provenance")
        is_prod_ready = metadata.get("is_production_ready")
        meta_sample_count = metadata.get("sample_count", 0)
        meta_genuine_runs = metadata.get("genuine_historical_runs_count", 0)

        # 4. Require provenance == GENUINE_PIPELINE_TELEMETRY
        if provenance != "GENUINE_PIPELINE_TELEMETRY":
            return (
                False,
                f"Safety Rule 14: Model provenance is '{provenance}', not 'GENUINE_PIPELINE_TELEMETRY'. Synthetic bootstrap models cannot authorize test skipping.",
            )

        # 5. Require is_production_ready == True
        if is_prod_ready is not True:
            return (
                False,
                "Safety Rule 14: Model is not certified production ready (is_production_ready is false). Full suite fallback enforced.",
            )

        # 6. Require metadata sample count and genuine runs >= min_runs
        if not isinstance(meta_sample_count, (int, float)) or meta_sample_count < min_runs:
            return (
                False,
                f"Safety Rule 17: Model metadata sample count ({meta_sample_count}) < minimum required ({min_runs}). Full suite fallback enforced.",
            )

        if not isinstance(meta_genuine_runs, (int, float)) or meta_genuine_runs < min_runs:
            return (
                False,
                f"Safety Rule 17: Model metadata genuine historical runs ({meta_genuine_runs}) < minimum required ({min_runs}). Full suite fallback enforced.",
            )

        # 7. Require server-verified genuine historical runs in DB >= min_runs
        if genuine_historical_runs_count < min_runs:
            return (
                False,
                (
                    f"Safety Rule 17: Genuine historical pipeline runs ({genuine_historical_runs_count}) "
                    f"is less than required minimum ({min_runs}). Full suite fallback enforced."
                ),
            )

        return True, "Models validated and ready for inference."

    def load_models(self) -> bool:
        """Loads model artifacts from disk if available."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        if os.path.exists(fail_path) and os.path.exists(time_path):
            try:
                self.failure_predictor = joblib.load(fail_path)
                self.runtime_predictor = joblib.load(time_path)
                return True
            except (OSError, EOFError, ValueError, KeyError, AttributeError) as e:
                logger.error(f"Failed to load ML artifacts from {self.registry_dir}: {e}")
                return False
        return False

    def get_models_status(self) -> dict[str, Any]:
        """Returns readiness, provenance, and artifact presence for predictive models."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        provenance_info: dict[str, Any] = {
            "provenance": "SYNTHETIC_BOOTSTRAP",
            "genuine_historical_runs_count": 0,
            "is_production_ready": False,
        }
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path) as f:
                    provenance_info = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

        return {
            "failure_predictor": {
                "is_trained": self.failure_predictor.is_trained,
                "version": self.failure_predictor.model_version,
                "model_file_exists": os.path.exists(fail_path),
                "artifact_path": fail_path,
            },
            "runtime_predictor": {
                "is_trained": self.runtime_predictor.is_trained,
                "version": self.runtime_predictor.model_version,
                "model_file_exists": os.path.exists(time_path),
                "artifact_path": time_path,
            },
            "provenance_metadata": provenance_info,
        }
