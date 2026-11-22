"""Unit tests for sample_app.auth.security_service (Sensitive Auth Module)."""

import pytest
import time
from sample_app.auth.security_service import SecurityService


def test_password_hashing_and_verification():
    raw_pass = "SecurePass123!"
    pw_hash = SecurityService.hash_password(raw_pass)
    assert pw_hash != raw_pass
    assert SecurityService.verify_password(raw_pass, pw_hash) is True
    assert SecurityService.verify_password("WrongPassword!", pw_hash) is False


def test_short_password_rejected():
    with pytest.raises(ValueError, match="at least 8 characters"):
        SecurityService.hash_password("short")


def test_stateless_token_generation_and_verification():
    secret = "test_signing_key_secret_2026"
    token = SecurityService.generate_token("usr_100", "admin", secret, expires_in_sec=10)
    payload = SecurityService.verify_token(token, secret)

    assert payload is not None
    assert payload["sub"] == "usr_100"
    assert payload["role"] == "admin"


def test_tampered_token_rejected():
    secret = "test_signing_key_secret_2026"
    token = SecurityService.generate_token("usr_100", "admin", secret)
    tampered = token[:-4] + "abcd"
    assert SecurityService.verify_token(tampered, secret) is None


def test_expired_token_rejected():
    secret = "test_signing_key_secret_2026"
    # Create token expired 5 seconds ago
    token = SecurityService.generate_token("usr_100", "admin", secret, expires_in_sec=-5)
    assert SecurityService.verify_token(token, secret) is None
