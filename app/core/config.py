"""
Application Configuration using Pydantic Settings.
Centralizes environment variables, safety thresholds, and system flags.
"""

from typing import List, Optional
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """System-wide configuration settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application metadata
    PROJECT_NAME: str = "Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="development | testing | production")
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    API_V1_PREFIX: str = "/api/v1"

    # Server binding
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = Field(
        default="autonomous_devops_insecure_default_secret_key_change_in_production",
        description="Key for cryptographic signatures and token hashing",
    )
    RUNNER_API_KEY: str = Field(
        default="autonomous_devops_runner_dev_api_key_2026",
        description="Pre-shared key used by isolated GitHub Actions runners",
    )
    GITHUB_WEBHOOK_SECRET: Optional[str] = "autonomous_devops_webhook_dev_secret"

    # Database configuration
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://devops_user:devops_secure_password_2026@localhost:5432/autonomous_devops_db",
        description="Primary PostgreSQL connection string",
    )
    SQLITE_FALLBACK_URL: str = Field(
        default="sqlite:///./autonomous_devops_local.db",
        description="Local SQLite fallback connection string",
    )
    USE_SQLITE_FALLBACK: bool = Field(
        default=True,
        description="Whether to fall back to SQLite if PostgreSQL is unreachable",
    )

    # Machine Learning & Model Management
    MODEL_REGISTRY_PATH: str = "./app/ml/models"
    MIN_TRAINING_RUNS: int = 15
    RISK_THRESHOLD: float = 0.35
    PREDICTION_CONFIDENCE_THRESHOLD: float = 0.70

    # Deterministic Safety Policy
    STRICT_FALLBACK_MODE: bool = True
    MAX_UNRESOLVED_DYNAMIC_IMPORTS: int = 0

    # Security Scanning Thresholds
    ENABLE_BANDIT_SCAN: bool = True
    ENABLE_PIP_AUDIT: bool = True
    ENABLE_GITLEAKS: bool = True
    BLOCK_ON_SECURITY_SEVERITY: str = "HIGH"

    # CORS Allowed Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
