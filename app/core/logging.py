"""
Structured Logging with Privacy-Aware Secret Redaction.
Ensures sensitive tokens, passwords, and keys never leak into logs or telemetry.
"""

import logging
import re
import sys
from typing import Any, Dict


# Regex patterns matching sensitive credentials, tokens, and keys
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]?([^'\"\s]+)['\"]?"),
    re.compile(r"(?i)(bearer\s+)([a-zA-Z0-9_\-\.]{16,})"),
    re.compile(r"(?i)(secret|token|api[_-]?key|auth)\s*[=:]\s*['\"]?([^'\"\s]+)['\"]?"),
    re.compile(r"(?i)(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{50,})"),
]


def redact_sensitive_text(text: str) -> str:
    """Masks secrets, passwords, and tokens with [REDACTED]."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips sensitive patterns from log output."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive_text(original)


def setup_logger(name: str = "autonomous_devops") -> logging.Logger:
    """Creates a standardized logger with secret redaction."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = RedactingFormatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = setup_logger()
