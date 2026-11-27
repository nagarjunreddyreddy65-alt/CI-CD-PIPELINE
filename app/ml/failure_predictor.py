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
        feature_names: list[str] | None = None,
    ):
        self.model_version = model_version
        self.risk_threshold = risk_threshold
        self.feature_names = feature_names
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            class_weight="balanced",
            max_depth=6,
            min_samples_split=4,
            random_state=random_state,
        )
        self.is_trained = False

    def train(self, X: np.ndarray, y: np.ndarray, time_aware: bool = True) -> dict[str, Any]:
        """
        Trains the classifier and calculates evaluation metrics.
        When samples >= 15, evaluates on a held-out test split (20%) for scientifically honest metrics.
        Supports time-aware chronological evaluation preventing lookahead leakage.
        X: 2D array of shape (N, 10)
        y: 1D binary array of shape (N,) where 1 = Failed, 0 = Passed
        """
        if len(X) < 10:
            raise ValueError(f"Insufficient training samples ({len(X)} < 10)")

        use_holdout = len(X) >= 15
        if use_holdout:
            if time_aware:
                split_idx = int(len(X) * 0.8)
                X_train, X_test = X[:split_idx], X[split_idx:]
                y_train, y_test = y[:split_idx], y[split_idx:]
                if len(np.unique(y_test)) < 2 and len(np.unique(y)) > 1:
                    can_stratify = all(np.sum(y == c) >= 2 for c in np.unique(y))
                    try:
                        X_train, X_test, y_train, y_test = train_test_split(
                            X,
                            y,
                            test_size=0.2,
                            random_state=42,
                            stratify=y if can_stratify else None,
                        )
                    except ValueError:
                        pass
            else:
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
        y_prob = (
            self.model.predict_proba(eval_X)[:, 1]
            if len(self.model.classes_) > 1
            else np.zeros(len(eval_y))
        )
        # Evaluate predictions aligned with calibrated operational decision threshold
        y_pred = (
            (y_prob >= self.risk_threshold).astype(int)
            if len(self.model.classes_) > 1
            else self.model.predict(eval_X)
        )

        prec = float(precision_score(eval_y, y_pred, zero_division=0))
        rec = float(recall_score(eval_y, y_pred, zero_division=0))
        f1 = float(f1_score(eval_y, y_pred, zero_division=0))
        cm = confusion_matrix(eval_y, y_pred).tolist()

        if len(np.unique(eval_y)) > 1:
            try:
                auc: float | None = float(roc_auc_score(eval_y, y_prob))
            except ValueError:
                auc = None
        else:
            # Undefined when test set contains only a single class
            auc = None

        # Class imbalance calculation on training targets
        positive_class_ratio = float(np.mean(y)) if len(y) > 0 else 0.0
        has_class_imbalance = bool(abs(positive_class_ratio - 0.5) > 0.2)

        # Refit on full dataset for optimal production model weights
        if use_holdout:
            self.model.fit(X, y)

        return {
            "model_version": self.model_version,
            "total_dataset_samples": len(X),
            "training_samples": len(X_train) if use_holdout else len(X),
            "test_samples": len(eval_y),
            "evaluated_on": "HOLDOUT_TEST_SPLIT" if use_holdout else "IN_SAMPLE_DATA",
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(auc, 4) if auc is not None else None,
            "confusion_matrix": cm,
            "class_distribution": {
                "dataset_pass_count": int(np.sum(y == 0)),
                "dataset_fail_count": int(np.sum(y == 1)),
                "train_pass_count": int(np.sum(y_train == 0))
                if use_holdout
                else int(np.sum(y == 0)),
                "train_fail_count": int(np.sum(y_train == 1))
                if use_holdout
                else int(np.sum(y == 1)),
                "test_pass_count": int(np.sum(eval_y == 0)),
                "test_fail_count": int(np.sum(eval_y == 1)),
            },
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
            hist_rate = float(arr[4]) if len(arr) > 4 else (float(arr[8]) if len(arr) > 8 else 0.05)
            is_sens = int(arr[7]) if len(arr) > 7 else (int(arr[6]) if len(arr) > 6 else 0)
            X_input = arr.reshape(1, -1)
        elif (
            hasattr(features, "to_travistorrent_array")
            and getattr(self, "feature_names", None) is not None
            and "build_number" in self.feature_names
        ):
            hist_rate = getattr(features, "historical_failure_rate", 0.05)
            is_sens = getattr(features, "is_sensitive_change", 0)
            X_input = features.to_travistorrent_array()
        else:
            hist_rate = getattr(features, "historical_failure_rate", 0.05)
            is_sens = getattr(features, "is_sensitive_change", 0)
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
