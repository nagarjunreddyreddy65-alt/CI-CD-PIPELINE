"""
Unit tests for TestDependencyMapper.
Verifies test mapping, test reduction calculation, and deterministic safety fallback enforcement.
"""

import os

import pytest

from app.analysis.test_mapper import TestDependencyMapper


@pytest.fixture
def mapper():
    return TestDependencyMapper(root_dir=os.getcwd())


def test_isolated_util_change_optimizes_tests(mapper):
    """
    Modifying math_ops.py only affects math_ops and downstream metrics_calculator.
    Unrelated tests (auth, billing, user service) should NOT be selected!
    """
    changes = [
        {
            "path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 4,
            "lines_deleted": 1,
        }
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is False
    assert result.fallback_reason is None
    assert len(result.affected_test_identifiers) > 0
    assert result.selected_tests_count < result.total_repository_tests
    assert result.estimated_test_reduction_pct > 0.0

    # Verify math tests are selected
    selected_tests = " ".join(result.affected_test_identifiers)
    assert "test_math_ops.py" in selected_tests

    # Verify unrelated auth & billing tests are skipped safely
    assert "test_security_service.py" not in selected_tests
    assert "test_payment_processor.py" not in selected_tests


def test_auth_change_triggers_safety_fallback(mapper):
    """Modifying security_service.py must trigger Safety Rule 2 full-suite fallback."""
    changes = [
        {
            "path": "sample_app/auth/security_service.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is True
    assert "Safety Rule 2" in result.fallback_reason
    assert result.selected_tests_count == result.total_repository_tests
    assert result.estimated_test_reduction_pct == 0.0


def test_payment_change_triggers_safety_fallback(mapper):
    """Modifying payment_processor.py must trigger Safety Rule 3 full-suite fallback."""
    changes = [
        {
            "path": "sample_app/billing/payment_processor.py",
            "change_type": "MODIFIED",
            "lines_added": 5,
            "lines_deleted": 0,
        }
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is True
    assert "Safety Rule 3" in result.fallback_reason
    assert result.selected_tests_count == result.total_repository_tests


def test_database_migration_triggers_safety_fallback(mapper):
    """Modifying a migration file must trigger Safety Rule 1 full-suite fallback."""
    changes = [
        {
            "path": "app/database/models.py",
            "change_type": "MODIFIED",
            "lines_added": 1,
            "lines_deleted": 0,
        }
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is True
    assert "Safety Rule 1" in result.fallback_reason


def test_ci_workflow_change_triggers_safety_fallback(mapper):
    """Modifying CI config must trigger Safety Rule 7 full-suite fallback."""
    changes = [
        {
            "path": ".github/workflows/ci.yml",
            "change_type": "MODIFIED",
            "lines_added": 3,
            "lines_deleted": 1,
        }
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is True
    assert "Safety Rule 7" in result.fallback_reason


def test_lock_file_change_triggers_safety_fallback(mapper):
    """Modifying lock file must trigger Safety Rule 6 full-suite fallback."""
    changes = [
        {"path": "uv.lock", "change_type": "MODIFIED", "lines_added": 100, "lines_deleted": 50}
    ]
    result = mapper.map_changes_to_tests(changes)

    assert result.fallback_required is True
    assert "Safety Rule 6" in result.fallback_reason
