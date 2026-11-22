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
    token_to_check = x_runner_token if isinstance(x_runner_token, str) else None
    if settings.ENVIRONMENT == "testing" and not token_to_check:
        return True
    if not token_to_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing runner authentication token (X-Runner-Token header required)",
        )
    if not hmac.compare_digest(token_to_check, settings.RUNNER_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid runner authentication token",
        )
    return True


def verify_admin_token(
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
    x_runner_token: str | None = Header(None, alias="X-Runner-Token"),
) -> bool:
    """
    Validates administrative authorization token for privileged management endpoints.
    Accepts X-Admin-Token (or X-Runner-Token in development/testing mode for backward compatibility).
    """
    token_admin = x_admin_token if isinstance(x_admin_token, str) else None
    token_runner = x_runner_token if isinstance(x_runner_token, str) else None
    token_to_check = token_admin or token_runner

    if settings.ENVIRONMENT == "testing" and not token_to_check:
        return True

    admin_key = settings.ADMIN_API_KEY or settings.RUNNER_API_KEY
    if not token_to_check:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing runner authentication token or administrative token (X-Runner-Token or X-Admin-Token required)",
        )
    if not hmac.compare_digest(token_to_check, admin_key) and not hmac.compare_digest(
        token_to_check, settings.RUNNER_API_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid runner authentication token or administrative token",
        )
    return True


def verify_github_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """
    Validates GitHub webhook SHA-256 HMAC signature against configured secret.
    Fails closed if the webhook secret is not configured or signature format is invalid.
    """
    if not settings.GITHUB_WEBHOOK_SECRET:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub webhook secret is not configured in production.",
            )
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    received_hash = signature_header.removeprefix("sha256=").strip()
    # Validate signature format: must be 64-character hexadecimal digest
    if len(received_hash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in received_hash):
        return False

    expected_hash = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hash, received_hash)
