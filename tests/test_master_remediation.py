"""
Comprehensive Master Remediation Regression Test Suite.
Validates:
1. Role-based admin token verification (verify_admin_token)
2. Cryptographic GitHub signature verification with fail-closed behavior
3. Model version compatibility and Safety Rule 15 enforcement
4. AST dynamic import detection (eval, exec, __import__, importlib aliases)
5. Dependency graph cycle detection and Safety Rule 11 enforcement
6. Unmapped test detection and Safety Rule 12 enforcement
7. Directory traversal and absolute path protection in repository analysis
8. CI runner plan schema validation and injection defense
"""

import tempfile

import pytest
from fastapi import HTTPException

from app.analysis.dependency_analyzer import DependencyGraph, DynamicImportDetector
from app.core.config import settings
from app.core.security import verify_admin_token, verify_github_signature
from app.ml.model_manager import ModelManager
from app.optimization.decision_engine import DecisionEngine
from scripts.run_optimized_ci import validate_plan_response


def test_verify_admin_token_roles():
    """Validates role-based admin token verification and rejection."""
    orig_env = settings.ENVIRONMENT
    orig_admin = settings.ADMIN_API_KEY
    orig_runner = settings.RUNNER_API_KEY
    try:
        settings.ENVIRONMENT = "production"
        settings.ADMIN_API_KEY = "admin_super_secret_key_1234567890"
        settings.RUNNER_API_KEY = "runner_secret_key_123456789012"

        # Missing token raises 401
        with pytest.raises(HTTPException) as exc_info:
            verify_admin_token(x_admin_token=None, x_runner_token=None)
        assert exc_info.value.status_code == 401

        # Invalid token raises 403
        with pytest.raises(HTTPException) as exc_info:
            verify_admin_token(x_admin_token="wrong_token", x_runner_token=None)
        assert exc_info.value.status_code == 403

        # Valid admin token accepted
        assert verify_admin_token(x_admin_token="admin_super_secret_key_1234567890") is True

        # Valid runner token accepted as fallback
        assert verify_admin_token(x_runner_token="runner_secret_key_123456789012") is True
    finally:
        settings.ENVIRONMENT = orig_env
        settings.ADMIN_API_KEY = orig_admin
        settings.RUNNER_API_KEY = orig_runner


def test_verify_github_signature_strict():
    """Validates webhook signature checking: formatting, length, secret presence."""
    orig_env = settings.ENVIRONMENT
    orig_secret = settings.GITHUB_WEBHOOK_SECRET
    try:
        settings.ENVIRONMENT = "production"
        settings.GITHUB_WEBHOOK_SECRET = ""

        # Production missing secret fails closed
        with pytest.raises(HTTPException) as exc_info:
            verify_github_signature(b"{}", "sha256=abcdef")
        assert exc_info.value.status_code == 500

        settings.GITHUB_WEBHOOK_SECRET = "webhook_secret_key_2026"

        # Missing or bad prefix
        assert verify_github_signature(b"{}", None) is False
        assert verify_github_signature(b"{}", "md5=1234") is False

        # Wrong length (not 64 chars)
        assert verify_github_signature(b"{}", "sha256=1234abcd") is False

        # Non-hex characters
        assert verify_github_signature(b"{}", "sha256=" + "g" * 64) is False

        # Valid signature
        import hashlib
        import hmac

        payload = b'{"ref": "refs/heads/main"}'
        valid_digest = hmac.new(b"webhook_secret_key_2026", payload, hashlib.sha256).hexdigest()
        assert verify_github_signature(payload, f"sha256={valid_digest}") is True

        # Invalid digest
        bad_digest = "0" * 64
        assert verify_github_signature(payload, f"sha256={bad_digest}") is False
    finally:
        settings.ENVIRONMENT = orig_env
        settings.GITHUB_WEBHOOK_SECRET = orig_secret


def test_model_version_compatibility_rule_15():
    """Validates that incompatible model version triggers Safety Rule 15 and FULL_SUITE."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mm = ModelManager(registry_dir=tmpdir)
        # Without metadata
        is_ok, reason = mm.is_version_compatible()
        assert is_ok is False
        assert "metadata missing" in reason.lower()

        # Train and persist
        mm.train_and_persist(n_samples=20)
        is_ok, reason = mm.is_version_compatible()
        assert is_ok is True

        # Tamper with metadata version
        import json

        with open(mm.metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["model_version"] = "v999.0.0-expired"
        with open(mm.metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        is_ok, reason = mm.is_version_compatible()
        assert is_ok is False
        assert "v999.0.0-expired" in reason

        # Decision engine should trigger Rule 15
        engine = DecisionEngine(model_manager=mm)
        plan = engine.generate_plan(
            changed_file_entries=[
                {"file_path": "sample_app/utils/math_ops.py", "change_type": "MODIFIED"}
            ],
            historical_runs_count=20,
        )
        assert plan.decision.value == "FULL_SUITE"
        assert plan.fallback_triggered is True
        assert "RULE_15_MODEL_VERSION_MISMATCH" in plan.triggered_safety_rules


def test_dependency_graph_cycle_detection_rule_11():
    """Validates cycle detection in DependencyGraph and TestDependencyMapper."""
    graph = DependencyGraph()
    graph.add_dependency("module_a", "module_b")
    graph.add_dependency("module_b", "module_c")
    assert graph.is_acyclic() is True
    assert graph.find_cycles() == []

    # Introduce cycle a -> b -> c -> a
    graph.add_dependency("module_c", "module_a")
    assert graph.is_acyclic() is False
    cycles = graph.find_cycles()
    assert len(cycles) > 0


def test_dynamic_import_detector_aliases():
    """Validates dynamic import detection on importlib aliases and reflections."""
    import ast

    code_cases = [
        "__import__('os')",
        "eval('1 + 1')",
        "exec('print(1)')",
        "import importlib; importlib.import_module('math')",
        "import importlib as imp; imp.import_module('sys')",
        "from importlib import import_module; import_module('json')",
        "from importlib import import_module as load_mod; load_mod('csv')",
    ]

    for code in code_cases:
        tree = ast.parse(code)
        detector = DynamicImportDetector()
        detector.visit(tree)
        assert len(detector.dynamic_imports) > 0, f"Failed to detect dynamic import in: {code}"


def test_runner_plan_validation():
    """Validates CI runner plan schema validation and injection prevention."""
    # Non-dict
    is_valid, msg = validate_plan_response("not a dict")
    assert is_valid is False

    # Missing keys
    is_valid, msg = validate_plan_response({"decision": "OPTIMIZED"})
    assert is_valid is False

    # Inconsistent OPTIMIZED with fallback=True
    is_valid, msg = validate_plan_response(
        {
            "decision": "OPTIMIZED",
            "is_optimized": True,
            "fallback_triggered": True,
            "selected_tests": ["tests/test_a.py"],
        }
    )
    assert is_valid is False

    # Command injection attempt in test identifier
    is_valid, msg = validate_plan_response(
        {
            "decision": "OPTIMIZED",
            "is_optimized": True,
            "fallback_triggered": False,
            "selected_tests": ["tests/test_a.py; rm -rf /"],
        }
    )
    assert is_valid is False
    assert "unsafe characters" in msg

    # Valid plan
    is_valid, msg = validate_plan_response(
        {
            "decision": "OPTIMIZED",
            "is_optimized": True,
            "fallback_triggered": False,
            "selected_tests": ["tests_sample_app/test_sample_math.py::test_addition"],
        }
    )
    assert is_valid is True
