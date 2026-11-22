"""
Pipeline Failure Risk Predictor.
Implements a Random Forest Classifier to estimate pipeline failure probability
and classification, accounting for class imbalance.
"""

from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix, roc_auc_score

from app.ml.feature_extractor import PipelineFeatures


@dataclass
class FailurePredictionResult:
    """Output prediction data from FailurePredictor."""
    predicted_failure_probability: float  # 0.0 to 1.0
    predicted_failure_class: int          # 0: Pass, 1: Fail
    confidence: float                     # Distance from decision boundary [0.5, 1.0]
    is_high_risk: bool
    model_version: str
    prediction_timestamp: str


class FailurePredictor:
    """
    Random Forest Classifier estimating pipeline failure likelihood.
    Employs balanced class weighting to handle real-world CI/CD imbalance.
    """

    def __init__(
        self,
        model_version: str = "v1.0.0",
        n_estimators: int = 100,
        random_state: int = 42,
        risk_threshold: float = 0.35,
    ):
        self.model_version = model_version
        self.risk_threshold = risk_threshold
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            class_weight="balanced",
            max_depth=6,
            min_samples_split=4,
            random_state=random_state,
        )
        self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """
        Trains the classifier and calculates evaluation metrics.
        X: 2D array of shape (N, 10)
        y: 1D binary array of shape (N,) where 1 = Failed, 0 = Passed
        """
        if len(X) < 10:
            raise ValueError(f"Insufficient training samples ({len(X)} < 10)")

        self.model.fit(X, y)
        self.is_trained = True

        # In-sample evaluation
        y_pred = self.model.predict(X)
        y_prob = self.model.predict_proba(X)[:, 1] if len(self.model.classes_) > 1 else np.zeros(len(y))

        prec = float(precision_score(y, y_pred, zero_division=0))
        rec = float(recall_score(y, y_pred, zero_division=0))
        f1 = float(f1_score(y, y_pred, zero_division=0))
        cm = confusion_matrix(y, y_pred).tolist()

        try:
            auc = float(roc_auc_score(y, y_prob)) if len(np.unique(y)) > 1 else 1.0
        except Exception:
            auc = 0.5

        return {
            "model_version": self.model_version,
            "training_samples": len(X),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": cm,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def predict(self, features: PipelineFeatures) -> FailurePredictionResult:
        """Generates failure probability and risk classification for incoming features."""
        now_utc = datetime.now(timezone.utc).isoformat()

        if not self.is_trained:
            # Fallback baseline prediction when model is not yet trained
            prob = max(0.05, features.historical_failure_rate)
            if features.is_sensitive_change:
                prob = min(0.95, prob + 0.40)
            pred_class = 1 if prob >= self.risk_threshold else 0
            conf = round(abs(prob - 0.5) * 2.0, 3)

            return FailurePredictionResult(
                predicted_failure_probability=round(prob, 4),
                predicted_failure_class=pred_class,
                confidence=conf,
                is_high_risk=prob >= self.risk_threshold,
                model_version=f"{self.model_version}-untrained-fallback",
                prediction_timestamp=now_utc,
            )

        X_input = features.to_array()
        prob_array = self.model.predict_proba(X_input)[0]
        # Probability of class 1 (Failure)
        fail_prob = float(prob_array[1]) if len(prob_array) > 1 else 0.05
        pred_class = 1 if fail_prob >= self.risk_threshold else 0
        conf = round(abs(fail_prob - 0.5) * 2.0, 3)

        return FailurePredictionResult(
            predicted_failure_probability=round(fail_prob, 4),
            predicted_failure_class=pred_class,
            confidence=conf,
            is_high_risk=fail_prob >= self.risk_threshold,
            model_version=self.model_version,
            prediction_timestamp=now_utc,
        )
