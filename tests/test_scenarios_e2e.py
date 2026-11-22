"""
Comprehensive End-to-End Scenario Validation & Controlled Defect Injection Tests.
Validates the 15 core deterministic safety scenarios and defect detection behavior.
"""

import os
import subprocess
import sys

from app.analysis.test_mapper import TestDependencyMapper
from app.optimization.decision_engine import DecisionEngine
from app.optimization.safety_policy import (
    SafetyContext,
    SafetyPolicyEvaluator,
    SafetyRuleCode,
)


def test_scenario_01_leaf_code_change_optimized():
    """Scenario 1: Non-sensitive leaf code change triggers OPTIMIZED test selection."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 3,
            "lines_deleted": 1,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "OPTIMIZED"
    assert plan.is_optimized is True
    assert plan.fallback_triggered is False
    assert plan.selected_tests_count > 0
    assert plan.tests_reduction_pct > 0.0


def test_scenario_02_auth_change_fallback():
    """Scenario 2: Auth modification triggers Safety Rule 2 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "sample_app/auth/security_service.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert "RULE_2_AUTH" in plan.triggered_safety_rules


def test_scenario_03_migration_change_fallback():
    """Scenario 3: Database migration triggers Safety Rule 1 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "alembic/versions/001_initial.py",
            "change_type": "MODIFIED",
            "lines_added": 10,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert "RULE_1_MIGRATION" in plan.triggered_safety_rules


def test_scenario_04_billing_change_fallback():
    """Scenario 4: Billing modification triggers Safety Rule 3 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "sample_app/billing/payment_processor.py",
            "change_type": "MODIFIED",
            "lines_added": 5,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert "RULE_3_PAYMENT" in plan.triggered_safety_rules


def test_scenario_05_crypto_change_fallback():
    """Scenario 5: Cryptographic change triggers Safety Rule 4 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "sample_app/crypto/vault.py",
            "change_type": "MODIFIED",
            "lines_added": 4,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert "RULE_4_CRYPTO" in plan.triggered_safety_rules


def test_scenario_06_dependency_manifest_fallback():
    """Scenario 6: Dependency manifest change triggers Safety Rule 5 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "requirements.txt",
            "change_type": "MODIFIED",
            "lines_added": 1,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert SafetyRuleCode.RULE_5_DEPENDENCY_MANIFEST.value in plan.triggered_safety_rules


def test_scenario_07_lock_file_fallback():
    """Scenario 7: Lock file change triggers Safety Rule 6 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {"file_path": "uv.lock", "change_type": "MODIFIED", "lines_added": 10, "lines_deleted": 5}
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert SafetyRuleCode.RULE_6_LOCK_FILE.value in plan.triggered_safety_rules


def test_scenario_08_ci_workflow_fallback():
    """Scenario 8: CI workflow change triggers Safety Rule 7 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": ".github/workflows/ci.yml",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert SafetyRuleCode.RULE_7_CI_WORKFLOW.value in plan.triggered_safety_rules


def test_scenario_09_unsupported_file_fallback():
    """Scenario 9: Unsupported file extension triggers Safety Rule 8 (FULL_SUITE)."""
    engine = DecisionEngine(root_dir=".")
    change = [
        {
            "file_path": "data/archive.bin",
            "change_type": "MODIFIED",
            "lines_added": 0,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(
        changed_file_entries=change, historical_runs_count=25, risk_threshold=0.50
    )

    assert plan.decision.value == "FULL_SUITE"
    assert plan.fallback_triggered is True
    assert SafetyRuleCode.RULE_8_UNSUPPORTED_FILES.value in plan.triggered_safety_rules


def test_scenario_10_ast_syntax_error_fallback():
    """Scenario 10: AST syntax error triggers Safety Rule 9 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(SafetyContext(has_ast_syntax_error=True))
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_9_AST_PARSE_FAILURE.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_11_dynamic_import_fallback():
    """Scenario 11: Dynamic import triggers Safety Rule 10 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(SafetyContext(has_dynamic_import=True))
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_10_DYNAMIC_IMPORT.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_12_empty_test_selection_fallback():
    """Scenario 12: Empty test selection for non-empty change triggers Safety Rule 13 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(
        SafetyContext(is_test_selection_empty=True, non_empty_code_change=True)
    )
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_13_EMPTY_TEST_SELECTION.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_13_missing_model_fallback():
    """Scenario 13: Missing ML model artifact triggers Safety Rule 14 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(SafetyContext(model_artifact_exists=False))
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_14_MODEL_ARTIFACT_MISSING.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_14_low_confidence_ml_fallback():
    """Scenario 14: Prediction confidence < 0.70 triggers Safety Rule 18 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(SafetyContext(prediction_confidence=0.55))
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_18_LOW_PREDICTION_CONFIDENCE.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_15_insufficient_historical_runs_fallback():
    """Scenario 15: Historical runs < 15 triggers Safety Rule 17 (FULL_SUITE)."""
    evaluator = SafetyPolicyEvaluator()
    res = evaluator.evaluate(SafetyContext(historical_runs_count=10))
    assert res.is_safe_to_optimize is False
    assert SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA.value in [
        t.rule_code.value for t in res.triggered_rules
    ]


def test_scenario_16_controlled_defect_injection_detected():
    """Scenario 16: Defect injected into math_ops is detected by selected test suite."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    math_file = os.path.join(root_dir, "sample_app", "utils", "math_ops.py")

    with open(math_file, "r", encoding="utf-8") as f:
        original = f.read()

    mutated = original.replace("return a + b", "return a + b + 9999")
    assert mutated != original, "Target pattern for mutation must exist"

    mapper = TestDependencyMapper(root_dir)
    change = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 3,
            "lines_deleted": 1,
        }
    ]
    map_res = mapper.map_changes_to_tests(change)
    selected_tests = [t for t in map_res.affected_test_identifiers if "tests_sample_app" in t]
    assert len(selected_tests) > 0, "Selected tests must not be empty"

    try:
        with open(math_file, "w", encoding="utf-8") as f:
            f.write(mutated)

        # Run selected tests on defective code
        cmd = [sys.executable, "-m", "pytest"] + selected_tests + ["-p", "no:httpbin", "-q"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        # Must detect defect (fail)
        assert result.returncode != 0, "Defect should cause selected tests to fail!"
    finally:
        # Guarantee restoration
        with open(math_file, "w", encoding="utf-8") as f:
            f.write(original)

    # Verify clean pass after restoration
    verify_cmd = [sys.executable, "-m", "pytest"] + selected_tests + ["-p", "no:httpbin", "-q"]
    verify_result = subprocess.run(verify_cmd, capture_output=True, text=True, check=False)
    assert verify_result.returncode == 0, "Selected tests must pass after restoration"
