"""
Tests for Core Configuration and Privacy-Aware Logging.
"""

from app.core.config import settings
from app.core.logging import redact_sensitive_text


def test_settings_defaults():
    """Verifies that critical safety settings default to secure values."""
    assert "Autonomous DevOps" in settings.PROJECT_NAME
    assert settings.STRICT_FALLBACK_MODE is True
    assert settings.MIN_TRAINING_RUNS == 15
    assert settings.RISK_THRESHOLD == 0.35
    assert settings.USE_SQLITE_FALLBACK is True


def test_secret_redaction():
    """Verifies that passwords, tokens, and authorization keys are automatically redacted."""
    raw_log = "Error connecting to db with password=SuperSecretPassword123 and token='ghp_123456789012345678901234567890123456'"
    redacted = redact_sensitive_text(raw_log)

    assert "SuperSecretPassword123" not in redacted
    assert "ghp_123456789012345678901234567890123456" not in redacted
    assert "[REDACTED]" in redacted
