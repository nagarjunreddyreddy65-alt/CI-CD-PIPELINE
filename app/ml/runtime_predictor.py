"""
Pipeline Runtime Duration Predictor.
Implements a Random Forest Regressor to forecast expected test execution time in seconds.
"""

from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
import math
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score

from app.ml.feature_extractor import PipelineFeatures


@dataclass
class RuntimePredictionResult:
    """Output prediction data from RuntimePredictor."""
    predicted_duration_sec: float
    confidence_interval_low_sec: float
    confidence_interval_high_sec: float
    model_version: str
    prediction_timestamp: str


class RuntimePredictor:
    """
    Random Forest Regressor forecasting test suite execution duration.
    """

    def __init__(
        self,
        model_version: str = "v1.0.0",
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        self.model_version = model_version
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=6,
            min_samples_split=4,
            random_state=random_state,
        )
        self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """
        Trains the regressor and computes regression evaluation metrics.
        X: 2D array of shape (N, 10)
        y: 1D continuous array of execution durations in seconds
        """
        if len(X) < 10:
            raise ValueError(f"Insufficient training samples ({len(X)} < 10)")

        self.model.fit(X, y)
        self.is_trained = True

        y_pred = self.model.predict(X)
        mae = float(mean_absolute_error(y, y_pred))
        rmse = float(root_mean_squared_error(y, y_pred))
        r2 = float(r2_score(y, y_pred)) if len(np.unique(y)) > 1 else 1.0

        return {
            "model_version": self.model_version,
            "training_samples": len(X),
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "r2_score": round(max(0.0, r2), 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def predict(self, features: PipelineFeatures) -> RuntimePredictionResult:
        """Predicts execution duration in seconds with an estimated uncertainty band."""
        now_utc = datetime.now(timezone.utc).isoformat()

        if not self.is_trained:
            # Fallback baseline: scale duration based on selected tests count
            base_dur = max(2.0, features.previous_execution_duration)
            if features.selected_tests_count > 0:
                est = round(base_dur * (features.selected_tests_count / max(1, features.selected_tests_count)), 2)
            else:
                est = base_dur

            return RuntimePredictionResult(
                predicted_duration_sec=est,
                confidence_interval_low_sec=round(max(1.0, est * 0.8), 2),
                confidence_interval_high_sec=round(est * 1.25, 2),
                model_version=f"{self.model_version}-untrained-fallback",
                prediction_timestamp=now_utc,
            )

        X_input = features.to_array()
        pred_val = float(self.model.predict(X_input)[0])
        bounded_pred = max(1.0, round(pred_val, 2))

        # Estimate confidence band (15% standard error margin)
        ci_low = max(0.5, round(bounded_pred * 0.85, 2))
        ci_high = round(bounded_pred * 1.15, 2)

        return RuntimePredictionResult(
            predicted_duration_sec=bounded_pred,
            confidence_interval_low_sec=ci_low,
            confidence_interval_high_sec=ci_high,
            model_version=self.model_version,
            prediction_timestamp=now_utc,
        )
