"""
Security and Authentication Helpers.
Validates runner authentication tokens and HMAC webhook signatures.
"""

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_runner_token(x_runner_token: str | None = Header(None)) -> bool:
    """
    Validates that incoming requests from isolated GitHub Actions runners
    provide a valid pre-shared runner authentication key.

    Uses constant-time string comparison (hmac.compare_digest) to prevent
    timing side-channel attacks. Note: this verifies a pre-shared token equality,
    not an HMAC signature calculation.
    """
    if settings.ENVIRONMENT == "testing" and not x_runner_token:
        return True
    if not x_runner_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing runner authentication token (X-Runner-Token header required)",
        )
    if not hmac.compare_digest(x_runner_token, settings.RUNNER_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid runner authentication token",
        )
    return True


def verify_github_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """Validates GitHub webhook SHA-256 HMAC signature against secret."""
    if not settings.GITHUB_WEBHOOK_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_hash = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    received_hash = signature_header.split("sha256=")[-1]
    return hmac.compare_digest(expected_hash, received_hash)
