"""
Application Configuration using Pydantic Settings.
Centralizes environment variables, safety thresholds, and system flags.
Enforces strict secret validation in production while maintaining effortless local development.
"""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET_KEY = "autonomous_devops_insecure_default_secret_key_change_in_production"
INSECURE_DEFAULT_RUNNER_KEY = "autonomous_devops_runner_dev_api_key_2026"
INSECURE_DEFAULT_POSTGRES_PWD = "devops_secure_password_2026"


class Settings(BaseSettings):
    """System-wide configuration settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application metadata
    PROJECT_NAME: str = (
        "Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization"
    )
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(
        default="development", description="development | testing | production"
    )
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    API_V1_PREFIX: str = "/api/v1"

    # Server binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = Field(
        default=INSECURE_DEFAULT_SECRET_KEY,
        description="Key for cryptographic signatures and token hashing",
    )
    RUNNER_API_KEY: str = Field(
        default=INSECURE_DEFAULT_RUNNER_KEY,
        description="Pre-shared key used by isolated GitHub Actions runners",
    )
    ADMIN_API_KEY: str | None = Field(
        default=None,
        description="Pre-shared key for privileged administrative operations (defaults to RUNNER_API_KEY if unset)",
    )
    GITHUB_WEBHOOK_SECRET: str | None = "autonomous_devops_webhook_dev_secret"

    # Database configuration
    DATABASE_URL: str = Field(
        default=f"postgresql+psycopg2://devops_user:{INSECURE_DEFAULT_POSTGRES_PWD}@localhost:5432/autonomous_devops_db",
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
    CORS_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        """
        Enforces strict secret and environment validation in production mode.
        Fails fast if default or weak credentials are detected in production.
        Never prints actual secret values in error messages.
        """
        if self.ENVIRONMENT == "production":
            errors: list[str] = []
            if self.DEBUG:
                errors.append("DEBUG mode must be disabled (DEBUG=False) in production.")
            if self.SECRET_KEY == INSECURE_DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < 32:
                errors.append(
                    "SECRET_KEY must be overridden with a strong secret (min 32 chars) in production. "
                    "Generate one using: openssl rand -hex 32"
                )
            if self.RUNNER_API_KEY == INSECURE_DEFAULT_RUNNER_KEY or len(self.RUNNER_API_KEY) < 16:
                errors.append(
                    "RUNNER_API_KEY must be overridden with a strong pre-shared key (min 16 chars) in production."
                )
            if (
                not self.GITHUB_WEBHOOK_SECRET
                or self.GITHUB_WEBHOOK_SECRET == "autonomous_devops_webhook_dev_secret"
            ):
                errors.append(
                    "GITHUB_WEBHOOK_SECRET must be configured with a strong secret in production."
                )
            if INSECURE_DEFAULT_POSTGRES_PWD in self.DATABASE_URL:
                errors.append(
                    "DATABASE_URL contains the default insecure development password in production. "
                    "Provide a secure DATABASE_URL via environment variables."
                )
            if self.USE_SQLITE_FALLBACK:
                errors.append(
                    "USE_SQLITE_FALLBACK must be False in production mode. "
                    "Production requires a resilient PostgreSQL database."
                )
            if errors:
                error_msg = "CRITICAL PRODUCTION CONFIGURATION ERROR:\n" + "\n".join(
                    f" - {err}" for err in errors
                )
                raise ValueError(error_msg)
        return self


settings = Settings()
