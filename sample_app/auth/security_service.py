"""
Authentication & Cryptographic Security Service.
NOTE: This is a sensitive security module.
Any change in this module triggers Safety Rule 2 (Authentication Fallback).
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any


class SecurityService:
    """Handles password hashing and lightweight HMAC token verification."""

    SECRET_SALT = b"autonomous_devops_auth_salt_2026"

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Generates salted SHA-256 password hash."""
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            cls.SECRET_SALT,
            iterations=100_000,
        ).hex()

    @classmethod
    def verify_password(cls, password: str, expected_hash: str) -> bool:
        """Verifies password using constant-time comparison."""
        computed_hash = cls.hash_password(password)
        return hmac.compare_digest(computed_hash, expected_hash)

    @classmethod
    def generate_token(
        cls, user_id: str, role: str, secret_key: str, expires_in_sec: int = 3600
    ) -> str:
        """Generates a signed stateless session token."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode()
        payload = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "sub": user_id,
                    "role": role,
                    "exp": int(time.time()) + expires_in_sec,
                }
            ).encode()
        ).decode()
        message = f"{header}.{payload}".encode()
        signature = base64.urlsafe_b64encode(
            hmac.new(secret_key.encode(), message, hashlib.sha256).digest()
        ).decode()
        return f"{header}.{payload}.{signature}"

    @classmethod
    def verify_token(cls, token: str, secret_key: str) -> dict[str, Any] | None:
        """Verifies and decodes a signed session token."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b64, payload_b64, signature_b64 = parts
            message = f"{header_b64}.{payload_b64}".encode()
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(secret_key.encode(), message, hashlib.sha256).digest()
            ).decode()

            if not hmac.compare_digest(signature_b64, expected_sig):
                return None

            payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
            if payload.get("exp", 0) < int(time.time()):
                return None  # Expired
            return payload
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
            return None
