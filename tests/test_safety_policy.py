"""
Comprehensive Unit Tests for the Deterministic Safety Policy.
Verifies that all 21 mandatory fallback scenarios correctly trigger full-suite execution.
"""

import pytest
import math
from app.optimization.safety_policy import (
    SafetyPolicyEvaluator,
    SafetyContext,
    SafetyRuleCode,
    SAFETY_RULE_CATALOG,
)


@pytest.fixture
def evaluator():
    return SafetyPolicyEvaluator()


def test_safety_catalog_completeness():
    """Ensure exactly 21 rules are cataloged and mapped with correct numbers 1-21."""
    assert len(SAFETY_RULE_CATALOG) == 21
    rule_numbers = [defn.rule_number for defn in SAFETY_RULE_CATALOG.values()]
    assert sorted(rule_numbers) == list(range(1, 22))


def test_safe_context_permits_optimization(evaluator):
    """When all conditions are clean, safety evaluator authorizes optimization."""
    ctx = SafetyContext(
        has_migration_changes=False,
        has_auth_changes=False,
        has_payment_changes=False,
        has_crypto_changes=False,
        has_dependency_manifest_changes=False,
        has_lock_file_changes=False,
        has_ci_workflow_changes=False,
        has_unsupported_files=False,
        has_ast_syntax_error=False,
        has_dynamic_import=False,
        has_circular_dependency=False,
        has_unmapped_tests=False,
        is_test_selection_empty=False,
        non_empty_code_change=True,
        model_artifact_exists=True,
        model_version_compatible=True,
        predicted_probability=0.08,
        prediction_confidence=0.92,
        historical_runs_count=25,
        api_reachable=True,
        github_api_success=True,
        unverifiable_safety_detected=False,
    )
    result = evaluator.evaluate(ctx)
    assert result.is_safe_to_optimize is True
    assert result.fallback_required is False
    assert len(result.triggered_rules) == 0
    assert result.primary_fallback_reason is None


@pytest.mark.parametrize("rule_num,field_kwargs,expected_code", [
    (1, {"has_migration_changes": True}, SafetyRuleCode.RULE_1_MIGRATION),
    (2, {"has_auth_changes": True}, SafetyRuleCode.RULE_2_AUTH),
    (3, {"has_payment_changes": True}, SafetyRuleCode.RULE_3_PAYMENT),
    (4, {"has_crypto_changes": True}, SafetyRuleCode.RULE_4_CRYPTO),
    (5, {"has_dependency_manifest_changes": True}, SafetyRuleCode.RULE_5_DEPENDENCY_MANIFEST),
    (6, {"has_lock_file_changes": True}, SafetyRuleCode.RULE_6_LOCK_FILE),
    (7, {"has_ci_workflow_changes": True}, SafetyRuleCode.RULE_7_CI_WORKFLOW),
    (8, {"has_unsupported_files": True}, SafetyRuleCode.RULE_8_UNSUPPORTED_FILES),
    (9, {"has_ast_syntax_error": True}, SafetyRuleCode.RULE_9_AST_PARSE_FAILURE),
    (10, {"has_dynamic_import": True}, SafetyRuleCode.RULE_10_DYNAMIC_IMPORT),
    (11, {"has_circular_dependency": True}, SafetyRuleCode.RULE_11_CIRCULAR_OR_DISCONNECTED),
    (12, {"has_unmapped_tests": True}, SafetyRuleCode.RULE_12_UNMAPPED_TESTS),
    (13, {"is_test_selection_empty": True, "non_empty_code_change": True}, SafetyRuleCode.RULE_13_EMPTY_TEST_SELECTION),
    (14, {"model_artifact_exists": False}, SafetyRuleCode.RULE_14_MODEL_ARTIFACT_MISSING),
    (15, {"model_version_compatible": False}, SafetyRuleCode.RULE_15_MODEL_VERSION_MISMATCH),
    (16, {"predicted_probability": float("nan")}, SafetyRuleCode.RULE_16_INVALID_PREDICTION_OUTPUT),
    (17, {"historical_runs_count": 10}, SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA),
    (18, {"prediction_confidence": 0.55}, SafetyRuleCode.RULE_18_LOW_PREDICTION_CONFIDENCE),
    (19, {"api_reachable": False}, SafetyRuleCode.RULE_19_API_UNREACHABLE),
    (20, {"github_api_success": False}, SafetyRuleCode.RULE_20_GITHUB_API_FAILURE),
    (21, {"unverifiable_safety_detected": True}, SafetyRuleCode.RULE_21_UNVERIFIABLE_SAFETY),
])
def test_all_21_rules_trigger_fallback(evaluator, rule_num, field_kwargs, expected_code):
    """Verifies each of the 21 mandatory safety rules triggers a fallback when activated."""
    # Start with a clean safe baseline
    base_kwargs = {
        "has_migration_changes": False,
        "has_auth_changes": False,
        "has_payment_changes": False,
        "has_crypto_changes": False,
        "has_dependency_manifest_changes": False,
        "has_lock_file_changes": False,
        "has_ci_workflow_changes": False,
        "has_unsupported_files": False,
        "has_ast_syntax_error": False,
        "has_dynamic_import": False,
        "has_circular_dependency": False,
        "has_unmapped_tests": False,
        "is_test_selection_empty": False,
        "non_empty_code_change": True,
        "model_artifact_exists": True,
        "model_version_compatible": True,
        "predicted_probability": 0.05,
        "prediction_confidence": 0.95,
        "historical_runs_count": 25,
        "api_reachable": True,
        "github_api_success": True,
        "unverifiable_safety_detected": False,
    }
    base_kwargs.update(field_kwargs)
    ctx = SafetyContext(**base_kwargs)

    result = evaluator.evaluate(ctx)
    assert result.is_safe_to_optimize is False
    assert result.fallback_required is True
    assert len(result.triggered_rules) >= 1
    assert any(t.rule_code == expected_code for t in result.triggered_rules)
    assert f"Safety Rule {rule_num}:" in result.primary_fallback_reason


def test_invalid_prediction_out_of_bounds(evaluator):
    """Rule 16: probability outside [0.0, 1.0] must trigger fallback."""
    ctx = SafetyContext(predicted_probability=1.5)
    res = evaluator.evaluate(ctx)
    assert res.fallback_required is True
    assert any(t.rule_code == SafetyRuleCode.RULE_16_INVALID_PREDICTION_OUTPUT for t in res.triggered_rules)


def test_multiple_simultaneous_safety_triggers(evaluator):
    """When multiple safety violations occur, all must be collected and audited."""
    ctx = SafetyContext(
        has_auth_changes=True,
        has_migration_changes=True,
        has_payment_changes=True,
        historical_runs_count=5,
    )
    res = evaluator.evaluate(ctx)
    assert res.fallback_required is True
    assert len(res.triggered_rules) >= 4
    rule_codes = [t.rule_code for t in res.triggered_rules]
    assert SafetyRuleCode.RULE_1_MIGRATION in rule_codes
    assert SafetyRuleCode.RULE_2_AUTH in rule_codes
    assert SafetyRuleCode.RULE_3_PAYMENT in rule_codes
    assert SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA in rule_codes
