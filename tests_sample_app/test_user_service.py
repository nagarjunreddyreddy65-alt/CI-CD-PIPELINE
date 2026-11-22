"""Unit tests for sample_app.services.user_service."""

import pytest

from sample_app.services.user_service import UserService


@pytest.fixture
def service():
    return UserService()


def test_register_user_success(service):
    user = service.register_user("usr_001", "dev_alice", "alice@devops.local", "lead")
    assert user["id"] == "usr_001"
    assert user["username"] == "dev_alice"
    assert user["is_active"] is True


def test_register_user_invalid_email(service):
    with pytest.raises(ValueError, match="Invalid email address"):
        service.register_user("usr_002", "bob", "not-an-email")


def test_register_duplicate_user(service):
    service.register_user("usr_003", "charlie", "charlie@devops.local")
    with pytest.raises(ValueError, match="already registered"):
        service.register_user("usr_003", "charlie_dup", "charlie2@devops.local")


def test_deactivate_user(service):
    service.register_user("usr_004", "dan", "dan@devops.local")
    assert service.deactivate_user("usr_004") is True
    user = service.get_user("usr_004")
    assert user["is_active"] is False
