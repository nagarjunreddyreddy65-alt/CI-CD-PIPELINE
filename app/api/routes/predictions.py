"""
Prediction API Routes.
Exposes endpoints for pipeline failure risk assessment, runtime prediction,
and model training/registration.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.core.security import verify_admin_token, verify_runner_token
from app.database.session import get_db
from app.ml.feature_extractor import FeatureExtractor
from app.ml.model_manager import ModelManager

router = APIRouter(prefix="/predictions", tags=["Machine Learning Predictions"])

# Global model manager instance with artifact verification and preloading
model_manager = ModelManager()
try:
    model_manager.load_models()
except (OSError, ValueError, RuntimeError, KeyError, AttributeError) as exc:
    logger.debug(f"Predictions initial model load notice: {exc}")


def ensure_models_loaded() -> ModelManager:
    """Ensures models are loaded if valid certified artifacts exist."""
    if not model_manager.failure_predictor.is_trained:
        try:
            model_manager.load_models()
        except (OSError, ValueError, RuntimeError, KeyError, AttributeError) as exc:
            logger.debug(f"Predictions lazy model load notice: {exc}")
    return model_manager


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
    data_source: str = Field(
        default="SYNTHETIC_BOOTSTRAP",
        description="Data provenance: 'SYNTHETIC_BOOTSTRAP' or 'GENUINE_PIPELINE_TELEMETRY'",
    )


@router.post(
    "/predict",
    summary="Predict Failure Risk & Runtime Duration",
    description="Infers pipeline failure probability and expected test execution time from pre-execution features.",
)
def predict_pipeline(
    payload: PredictRequest,
    _authorized: bool = Depends(verify_runner_token),
):
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

    mm = ensure_models_loaded()
    fail_res = mm.failure_predictor.predict(features)
    time_res = mm.runtime_predictor.predict(features)

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
def train_models(
    payload: TrainRequest,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_token),
):
    """Trains and serializes both predictive models with role separation and strict provenance."""
    if payload.data_source not in ("GENUINE_PIPELINE_TELEMETRY", "SYNTHETIC_BOOTSTRAP"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid data_source '{payload.data_source}'. "
                "Must be 'GENUINE_PIPELINE_TELEMETRY' or 'SYNTHETIC_BOOTSTRAP'."
            ),
        )

    try:
        if payload.data_source == "GENUINE_PIPELINE_TELEMETRY":
            result = model_manager.train_from_database(
                db=db,
                min_runs=settings.MIN_TRAINING_RUNS,
            )
        else:
            result = model_manager.train_and_persist(
                n_samples=payload.n_samples,
                data_source="SYNTHETIC_BOOTSTRAP",
                genuine_historical_runs_count=0,
            )
        return {
            "success": True,
            "data": result,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except (OSError, RuntimeError) as e:
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
    mm = ensure_models_loaded()
    return {
        "success": True,
        "failure_predictor": {
            "is_trained": mm.failure_predictor.is_trained,
            "version": mm.failure_predictor.model_version,
            "risk_threshold": mm.failure_predictor.risk_threshold,
        },
        "runtime_predictor": {
            "is_trained": mm.runtime_predictor.is_trained,
            "version": mm.runtime_predictor.model_version,
        },
    }
