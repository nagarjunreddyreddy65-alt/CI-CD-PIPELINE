"""
Prediction API Routes.
Exposes endpoints for pipeline failure risk assessment, runtime prediction,
and model training/registration.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.ml.feature_extractor import FeatureExtractor
from app.ml.model_manager import ModelManager

router = APIRouter(prefix="/predictions", tags=["Machine Learning Predictions"])

# Global model manager instance
model_manager = ModelManager()


class PredictRequest(BaseModel):
    changed_files_count: int = Field(default=1, ge=0)
    lines_added: int = Field(default=10, ge=0)
    lines_deleted: int = Field(default=2, ge=0)
    affected_modules_count: int = Field(default=1, ge=0)
    selected_tests_count: int = Field(default=5, ge=0)
    is_sensitive_change: bool = Field(default=False)
    has_test_file_changes: bool = Field(default=False)
    historical_failure_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    previous_execution_duration: float = Field(default=30.0, ge=1.0)


class TrainRequest(BaseModel):
    n_samples: int = Field(
        default=50, ge=15, description="Number of bootstrap training samples (min 15)"
    )


@router.post(
    "/predict",
    summary="Predict Failure Risk & Runtime Duration",
    description="Infers pipeline failure probability and expected test execution time from pre-execution features.",
)
def predict_pipeline(payload: PredictRequest):
    """Generates failure risk probability and runtime duration estimates."""
    features = FeatureExtractor.extract_features(
        changed_files_count=payload.changed_files_count,
        lines_added=payload.lines_added,
        lines_deleted=payload.lines_deleted,
        affected_modules_count=payload.affected_modules_count,
        selected_tests_count=payload.selected_tests_count,
        is_sensitive_change=payload.is_sensitive_change,
        has_test_file_changes=payload.has_test_file_changes,
        historical_failure_rate=payload.historical_failure_rate,
        previous_execution_duration=payload.previous_execution_duration,
    )

    fail_res = model_manager.failure_predictor.predict(features)
    time_res = model_manager.runtime_predictor.predict(features)

    return {
        "success": True,
        "failure_prediction": {
            "predicted_failure_probability": fail_res.predicted_failure_probability,
            "predicted_failure_class": fail_res.predicted_failure_class,
            "confidence": fail_res.confidence,
            "is_high_risk": fail_res.is_high_risk,
            "model_version": fail_res.model_version,
        },
        "runtime_prediction": {
            "predicted_duration_sec": time_res.predicted_duration_sec,
            "confidence_interval_low_sec": time_res.confidence_interval_low_sec,
            "confidence_interval_high_sec": time_res.confidence_interval_high_sec,
            "model_version": time_res.model_version,
        },
        "features_evaluated": features.to_dict(),
        "timestamp": fail_res.prediction_timestamp,
    }


@router.post(
    "/train",
    summary="Train & Register ML Models",
    description="Trains Random Forest Classifier and Regressor using historical/bootstrap pipeline telemetry.",
)
def train_models(payload: TrainRequest):
    """Trains and serializes both predictive models."""
    try:
        result = model_manager.train_and_persist(n_samples=payload.n_samples)
        return {
            "success": True,
            "data": result,
        }
    except (ValueError, OSError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model training failed: {e!s}",
        )


@router.get(
    "/models",
    summary="Get Model Status & Metrics",
    description="Returns metadata, readiness, and versions of active ML models.",
)
def get_model_status():
    """Inspects active model readiness and versions."""
    return {
        "success": True,
        "failure_predictor": {
            "is_trained": model_manager.failure_predictor.is_trained,
            "version": model_manager.failure_predictor.model_version,
            "risk_threshold": model_manager.failure_predictor.risk_threshold,
        },
        "runtime_predictor": {
            "is_trained": model_manager.runtime_predictor.is_trained,
            "version": model_manager.runtime_predictor.model_version,
        },
    }
