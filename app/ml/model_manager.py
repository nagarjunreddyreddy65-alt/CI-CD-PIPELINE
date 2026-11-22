"""
Model Registry & Lifecycle Manager.
Handles model artifact persistence, versioning, minimum training sample validation,
and synthetic historical bootstrap data generation for benchmarking.
"""

from typing import Dict, Any, Tuple, Optional
import os
import joblib
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.ml.failure_predictor import FailurePredictor
from app.ml.runtime_predictor import RuntimePredictor


class ModelManager:
    """
    Central manager for training, serializing, loading, and validating ML models.
    Enforces Safety Rule 17: Validates that minimum historical samples (>= 15) are satisfied.
    """

    def __init__(self, registry_dir: Optional[str] = None):
        self.registry_dir = os.path.abspath(registry_dir or settings.MODEL_REGISTRY_PATH)
        os.makedirs(self.registry_dir, exist_ok=True)

        self.failure_predictor = FailurePredictor()
        self.runtime_predictor = RuntimePredictor()

    def generate_synthetic_historical_data(self, n_samples: int = 50) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
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
            fail_prob = 0.05 + (0.35 if is_sensitive else 0.0) + (0.25 if tot_lines > 150 else 0.0) + hist_fail_rate
            failed = 1 if np.random.rand() < fail_prob else 0
            y_fail.append(failed)

            # Runtime logic: base time + time per test + line diff penalty
            dur = max(2.0, 3.0 + (selected_tests * 0.4) + (tot_lines * 0.02) + np.random.normal(0, 1.0))
            y_time.append(round(dur, 2))

        return np.array(X_list, dtype=np.float64), np.array(y_fail, dtype=np.int32), np.array(y_time, dtype=np.float64)

    def train_and_persist(self, n_samples: int = 50) -> Dict[str, Any]:
        """Trains both models on synthetic bootstrap data and persists artifacts to disk."""
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

        logger.info(f"Successfully trained and saved models to {self.registry_dir}")

        return {
            "status": "TRAINED_AND_SAVED",
            "samples": n_samples,
            "failure_metrics": fail_metrics,
            "runtime_metrics": time_metrics,
            "artifact_paths": {
                "failure_model": fail_path,
                "runtime_model": time_path,
            },
        }

    def load_models(self) -> bool:
        """Loads model artifacts from disk if available."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

        if os.path.exists(fail_path) and os.path.exists(time_path):
            try:
                self.failure_predictor = joblib.load(fail_path)
                self.runtime_predictor = joblib.load(time_path)
                return True
            except Exception as e:
                logger.error(f"Failed to load ML artifacts from {self.registry_dir}: {e}")
                return False
        return False

    def get_models_status(self) -> Dict[str, Any]:
        """Returns readiness and artifact presence for predictive models."""
        fail_path = os.path.join(self.registry_dir, "failure_predictor.joblib")
        time_path = os.path.join(self.registry_dir, "runtime_predictor.joblib")

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
        }

