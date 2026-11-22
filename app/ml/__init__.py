"""
Machine Learning Subpackage for Autonomous DevOps.
Provides leakage-safe feature extraction, failure risk classification,
runtime duration regression, and model lifecycle management.
"""

from app.ml.feature_extractor import FeatureExtractor, PipelineFeatures
from app.ml.failure_predictor import FailurePredictor, FailurePredictionResult
from app.ml.runtime_predictor import RuntimePredictor, RuntimePredictionResult
from app.ml.model_manager import ModelManager

__all__ = [
    "FeatureExtractor",
    "PipelineFeatures",
    "FailurePredictor",
    "FailurePredictionResult",
    "RuntimePredictor",
    "RuntimePredictionResult",
    "ModelManager",
]
