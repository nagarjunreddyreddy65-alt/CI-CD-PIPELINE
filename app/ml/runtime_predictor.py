"""
Pipeline Runtime Duration Predictor.
Implements a Random Forest Regressor to forecast expected test execution time in seconds.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error


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

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
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
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def predict(self, features: Any) -> RuntimePredictionResult:
        """Predicts execution duration in seconds with an estimated uncertainty band."""
        now_utc = datetime.now(UTC).isoformat()

        if isinstance(features, np.ndarray):
            arr = features.flatten()
            prev_dur = float(arr[9]) if len(arr) > 9 else 30.0
            X_input = arr.reshape(1, -1)
        else:
            prev_dur = features.previous_execution_duration
            X_input = features.to_array()

        if not self.is_trained:
            # Fallback baseline: scale duration based on selected tests count
            base_dur = max(2.0, prev_dur)
            est = base_dur

            return RuntimePredictionResult(
                predicted_duration_sec=est,
                confidence_interval_low_sec=round(max(1.0, est * 0.8), 2),
                confidence_interval_high_sec=round(est * 1.25, 2),
                model_version=f"{self.model_version}-untrained-fallback",
                prediction_timestamp=now_utc,
            )

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
