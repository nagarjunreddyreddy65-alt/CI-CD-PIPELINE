"""
Tests for Core Configuration and Privacy-Aware Logging.
Verifies safety defaults, production configuration validation, and secret redaction.
"""

import pytest

from app.core.config import Settings, settings
from app.core.logging import redact_sensitive_text


def test_settings_defaults():
    """Verifies that critical safety settings default to secure values."""
    assert "Autonomous DevOps" in settings.PROJECT_NAME
    assert settings.STRICT_FALLBACK_MODE is True
    assert settings.MIN_TRAINING_RUNS == 15
    assert settings.RISK_THRESHOLD == 0.35
    assert settings.USE_SQLITE_FALLBACK is True


def test_production_configuration_rejects_insecure_defaults():
    """Verifies that running in production with default secrets raises a descriptive ValueError."""
    with pytest.raises(ValueError, match="CRITICAL PRODUCTION CONFIGURATION ERROR"):
        Settings(
            ENVIRONMENT="production",
            # Defaults for SECRET_KEY and RUNNER_API_KEY will trigger failure
        )


def test_production_configuration_accepts_valid_strong_secrets():
    """Verifies that running in production with valid strong secrets passes validation."""
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a" * 32,
        RUNNER_API_KEY="b" * 20,
        DATABASE_URL="postgresql+psycopg2://custom_user:strong_prod_password_999@db:5432/prod_db",
        USE_SQLITE_FALLBACK=False,
    )
    assert prod_settings.ENVIRONMENT == "production"
    assert prod_settings.USE_SQLITE_FALLBACK is False


def test_secret_redaction():
    """Verifies that passwords, tokens, and authorization keys are automatically redacted."""
    raw_log = "Error connecting to db with password=SuperSecretPassword123 and token='ghp_123456789012345678901234567890123456'"
    redacted = redact_sensitive_text(raw_log)

    assert "SuperSecretPassword123" not in redacted
    assert "ghp_123456789012345678901234567890123456" not in redacted
    assert "[REDACTED]" in redacted
