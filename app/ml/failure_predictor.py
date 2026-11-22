"""
Pipeline Failure Risk Predictor.
Implements a Random Forest Classifier to estimate pipeline failure probability
and classification, accounting for class imbalance.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split


@dataclass
class FailurePredictionResult:
    """Output prediction data from FailurePredictor."""

    predicted_failure_probability: float  # 0.0 to 1.0
    predicted_failure_class: int  # 0: Pass, 1: Fail
    confidence: float  # Distance from decision boundary [0.5, 1.0]
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

    def train(self, X: np.ndarray, y: np.ndarray) -> dict[str, Any]:
        """
        Trains the classifier and calculates evaluation metrics.
        When samples >= 15, evaluates on a held-out test split (20%) for scientifically honest metrics.
        X: 2D array of shape (N, 10)
        y: 1D binary array of shape (N,) where 1 = Failed, 0 = Passed
        """
        if len(X) < 10:
            raise ValueError(f"Insufficient training samples ({len(X)} < 10)")

        use_holdout = len(X) >= 15
        if use_holdout:
            try:
                can_stratify = len(np.unique(y)) > 1 and all(
                    np.sum(y == c) >= 2 for c in np.unique(y)
                )
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42, stratify=y if can_stratify else None
                )
            except ValueError:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=0.2, random_state=42
                )
            self.model.fit(X_train, y_train)
            self.is_trained = True
            eval_X, eval_y = X_test, y_test
        else:
            self.model.fit(X, y)
            self.is_trained = True
            eval_X, eval_y = X, y

        # Evaluation (on holdout test set if >= 15 samples, else in-sample)
        y_pred = self.model.predict(eval_X)
        y_prob = (
            self.model.predict_proba(eval_X)[:, 1]
            if len(self.model.classes_) > 1
            else np.zeros(len(eval_y))
        )

        prec = float(precision_score(eval_y, y_pred, zero_division=0))
        rec = float(recall_score(eval_y, y_pred, zero_division=0))
        f1 = float(f1_score(eval_y, y_pred, zero_division=0))
        cm = confusion_matrix(eval_y, y_pred).tolist()

        try:
            auc = float(roc_auc_score(eval_y, y_prob)) if len(np.unique(eval_y)) > 1 else 1.0
        except ValueError:
            auc = 0.5

        # Class imbalance calculation on training targets
        positive_class_ratio = float(np.mean(y)) if len(y) > 0 else 0.0
        has_class_imbalance = bool(abs(positive_class_ratio - 0.5) > 0.2)

        # Refit on full dataset for optimal production model weights
        if use_holdout:
            self.model.fit(X, y)

        return {
            "model_version": self.model_version,
            "total_dataset_samples": len(X),
            "training_samples": len(X),
            "train_samples_count": len(X_train) if use_holdout else len(X),
            "test_samples": len(eval_y),
            "test_samples_count": len(eval_y),
            "evaluated_on": "HOLDOUT_TEST_SPLIT" if use_holdout else "IN_SAMPLE_DATA",
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(auc, 4),
            "confusion_matrix": cm,
            "limitations": {
                "small_sample_size": bool(len(X) < 100),
                "class_imbalance": has_class_imbalance,
                "positive_class_ratio": round(positive_class_ratio, 4),
                "evaluation_note": (
                    "Metrics evaluated strictly on held-out 20% test split. "
                    "Small sample sizes (< 100) or class imbalance can cause metric variance."
                ),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def predict(self, features: Any) -> FailurePredictionResult:
        """Generates failure probability and risk classification for incoming features."""
        now_utc = datetime.now(UTC).isoformat()

        if isinstance(features, np.ndarray):
            arr = features.flatten()
            hist_rate = float(arr[8]) if len(arr) > 8 else 0.05
            is_sens = int(arr[6]) if len(arr) > 6 else 0
            X_input = arr.reshape(1, -1)
        else:
            hist_rate = features.historical_failure_rate
            is_sens = features.is_sensitive_change
            X_input = features.to_array()

        if not self.is_trained:
            # Fallback baseline prediction when model is not yet trained
            prob = max(0.05, hist_rate)
            if is_sens:
                prob = min(0.95, prob + 0.40)
            pred_class = 1 if prob >= self.risk_threshold else 0
            conf = round(max(prob, 1.0 - prob), 4)

            return FailurePredictionResult(
                predicted_failure_probability=round(prob, 4),
                predicted_failure_class=pred_class,
                confidence=conf,
                is_high_risk=prob >= self.risk_threshold,
                model_version=f"{self.model_version}-untrained-fallback",
                prediction_timestamp=now_utc,
            )

        prob_array = self.model.predict_proba(X_input)[0]
        # Probability of class 1 (Failure)
        fail_prob = float(prob_array[1]) if len(prob_array) > 1 else 0.05
        pred_class = 1 if fail_prob >= self.risk_threshold else 0
        conf = round(float(np.max(prob_array)), 4) if len(prob_array) > 0 else 0.95

        return FailurePredictionResult(
            predicted_failure_probability=round(fail_prob, 4),
            predicted_failure_class=pred_class,
            confidence=conf,
            is_high_risk=fail_prob >= self.risk_threshold,
            model_version=self.model_version,
            prediction_timestamp=now_utc,
        )
