"""User service managing profile validation, status, and role assignments."""

import re
from typing import Any

from sample_app.utils.string_ops import sanitize_string


class UserService:
    """Business logic for user management."""

    EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    def __init__(self):
        self._users: dict[str, dict[str, Any]] = {}

    def register_user(
        self, user_id: str, username: str, email: str, role: str = "developer"
    ) -> dict[str, Any]:
        """Registers a new user profile with validation."""
        clean_user = sanitize_string(username)
        clean_email = sanitize_string(email)

        if not clean_user or len(clean_user) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if not self.EMAIL_REGEX.match(clean_email):
            raise ValueError(f"Invalid email address: {clean_email}")
        if user_id in self._users:
            raise ValueError(f"User ID {user_id} is already registered")

        user_record = {
            "id": user_id,
            "username": clean_user,
            "email": clean_email,
            "role": role,
            "is_active": True,
        }
        self._users[user_id] = user_record
        return user_record

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Retrieves user by ID."""
        return self._users.get(user_id)

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivates an active user."""
        if user_id in self._users:
            self._users[user_id]["is_active"] = False
            return True
        return False
