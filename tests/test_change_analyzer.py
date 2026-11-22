"""
Unit tests for ChangeAnalyzer.
Verifies file classification, diff parsing, and deterministic sensitivity detection.
"""

import pytest

from app.analysis.change_analyzer import ChangeAnalyzer


@pytest.fixture
def analyzer():
    return ChangeAnalyzer()


def test_classify_standard_python_file(analyzer):
    info = analyzer.classify_file("sample_app/utils/math_ops.py")
    assert info["is_python"] is True
    assert info["is_test"] is False
    assert info["is_sensitive"] is False
    assert info["is_unsupported"] is False


def test_classify_test_file(analyzer):
    info = analyzer.classify_file("tests_sample_app/test_math_ops.py")
    assert info["is_python"] is True
    assert info["is_test"] is True
    assert info["is_sensitive"] is False


def test_classify_database_migration(analyzer):
    info = analyzer.classify_file("app/database/migrations/versions/initial.py")
    assert info["is_sensitive"] is True
    assert "DATABASE_MIGRATION" in info["sensitive_categories"]

    sql_info = analyzer.classify_file("scripts/schema_update.sql")
    assert sql_info["is_sensitive"] is True
    assert "DATABASE_MIGRATION" in sql_info["sensitive_categories"]


def test_classify_auth_and_security(analyzer):
    info = analyzer.classify_file("sample_app/auth/security_service.py")
    assert info["is_sensitive"] is True
    assert "AUTH_SECURITY" in info["sensitive_categories"]


def test_classify_payment_and_billing(analyzer):
    info = analyzer.classify_file("sample_app/billing/payment_processor.py")
    assert info["is_sensitive"] is True
    assert "PAYMENT_BILLING" in info["sensitive_categories"]


def test_classify_lock_files_and_manifests(analyzer):
    lock_info = analyzer.classify_file("uv.lock")
    assert lock_info["is_sensitive"] is True
    assert "LOCK_FILE" in lock_info["sensitive_categories"]

    manifest_info = analyzer.classify_file("requirements.txt")
    assert manifest_info["is_sensitive"] is True
    assert "DEPENDENCY_MANIFEST" in manifest_info["sensitive_categories"]


def test_classify_ci_workflows(analyzer):
    info = analyzer.classify_file(".github/workflows/ci.yml")
    assert info["is_sensitive"] is True
    assert "CI_WORKFLOW" in info["sensitive_categories"]

    docker_info = analyzer.classify_file("Dockerfile")
    assert docker_info["is_sensitive"] is True
    assert "CI_WORKFLOW" in docker_info["sensitive_categories"]


def test_classify_unsupported_binary_file(analyzer):
    info = analyzer.classify_file("data/archive.bin")
    assert info["is_unsupported"] is True


def test_analyze_changes_batch(analyzer):
    changes = [
        {
            "path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 10,
            "lines_deleted": 2,
        },
        {
            "path": "sample_app/auth/security_service.py",
            "change_type": "MODIFIED",
            "lines_added": 5,
            "lines_deleted": 1,
        },
        {"path": "README.md", "change_type": "MODIFIED", "lines_added": 20, "lines_deleted": 0},
    ]
    result = analyzer.analyze_changes(changes)

    assert result.total_files_changed == 3
    assert result.total_lines_added == 35
    assert result.total_lines_deleted == 3
    assert len(result.python_files) == 2
    assert len(result.non_python_files) == 1
    assert result.has_auth_changes is True
    assert "AUTH_SECURITY" in result.sensitive_triggers
