"""
Deterministic Safety Policy Engine.
Implements the 21 mandatory fallback scenarios defined in docs/SAFETY_POLICY.md.

Guiding Axiom:
"The AI predicts probability; deterministic safety rules decide execution."
Under NO circumstance is an AI model permitted to bypass safety rules or
independently authorize skipping tests.
"""

import math
from dataclasses import dataclass, field
from enum import Enum


class SafetyRuleCode(str, Enum):
    # Category: Code Change & File Types
    RULE_1_MIGRATION = "RULE_1_MIGRATION"
    RULE_2_AUTH = "RULE_2_AUTH"
    RULE_3_PAYMENT = "RULE_3_PAYMENT"
    RULE_4_CRYPTO = "RULE_4_CRYPTO"
    RULE_5_DEPENDENCY_MANIFEST = "RULE_5_DEPENDENCY_MANIFEST"
    RULE_6_LOCK_FILE = "RULE_6_LOCK_FILE"
    RULE_7_CI_WORKFLOW = "RULE_7_CI_WORKFLOW"
    RULE_8_UNSUPPORTED_FILES = "RULE_8_UNSUPPORTED_FILES"

    # Category: AST & Dependency Graph
    RULE_9_AST_PARSE_FAILURE = "RULE_9_AST_PARSE_FAILURE"
    RULE_10_DYNAMIC_IMPORT = "RULE_10_DYNAMIC_IMPORT"
    RULE_11_CIRCULAR_OR_DISCONNECTED = "RULE_11_CIRCULAR_OR_DISCONNECTED"
    RULE_12_UNMAPPED_TESTS = "RULE_12_UNMAPPED_TESTS"
    RULE_13_EMPTY_TEST_SELECTION = "RULE_13_EMPTY_TEST_SELECTION"

    # Category: Machine Learning
    RULE_14_MODEL_ARTIFACT_MISSING = "RULE_14_MODEL_ARTIFACT_MISSING"
    RULE_15_MODEL_VERSION_MISMATCH = "RULE_15_MODEL_VERSION_MISMATCH"
    RULE_16_INVALID_PREDICTION_OUTPUT = "RULE_16_INVALID_PREDICTION_OUTPUT"
    RULE_17_INSUFFICIENT_TRAINING_DATA = "RULE_17_INSUFFICIENT_TRAINING_DATA"
    RULE_18_LOW_PREDICTION_CONFIDENCE = "RULE_18_LOW_PREDICTION_CONFIDENCE"

    # Category: Infrastructure & Environment
    RULE_19_API_UNREACHABLE = "RULE_19_API_UNREACHABLE"
    RULE_20_GITHUB_API_FAILURE = "RULE_20_GITHUB_API_FAILURE"
    RULE_21_UNVERIFIABLE_SAFETY = "RULE_21_UNVERIFIABLE_SAFETY"


@dataclass
class SafetyRuleDefinition:
    rule_number: int
    code: SafetyRuleCode
    description: str
    category: str


SAFETY_RULE_CATALOG: dict[SafetyRuleCode, SafetyRuleDefinition] = {
    SafetyRuleCode.RULE_1_MIGRATION: SafetyRuleDefinition(
        1,
        SafetyRuleCode.RULE_1_MIGRATION,
        "Database migration or schema modification detected",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_2_AUTH: SafetyRuleDefinition(
        2,
        SafetyRuleCode.RULE_2_AUTH,
        "Authentication or authorization changes detected",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_3_PAYMENT: SafetyRuleDefinition(
        3, SafetyRuleCode.RULE_3_PAYMENT, "Payment or billing code changes detected", "CODE_CHANGE"
    ),
    SafetyRuleCode.RULE_4_CRYPTO: SafetyRuleDefinition(
        4,
        SafetyRuleCode.RULE_4_CRYPTO,
        "Cryptographic or sensitive code modifications detected",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_5_DEPENDENCY_MANIFEST: SafetyRuleDefinition(
        5,
        SafetyRuleCode.RULE_5_DEPENDENCY_MANIFEST,
        "Dependency manifest changes detected",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_6_LOCK_FILE: SafetyRuleDefinition(
        6, SafetyRuleCode.RULE_6_LOCK_FILE, "Lock-file changes detected", "CODE_CHANGE"
    ),
    SafetyRuleCode.RULE_7_CI_WORKFLOW: SafetyRuleDefinition(
        7,
        SafetyRuleCode.RULE_7_CI_WORKFLOW,
        "CI/CD workflow configuration modifications detected",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_8_UNSUPPORTED_FILES: SafetyRuleDefinition(
        8,
        SafetyRuleCode.RULE_8_UNSUPPORTED_FILES,
        "Unknown or unsupported file types changed",
        "CODE_CHANGE",
    ),
    SafetyRuleCode.RULE_9_AST_PARSE_FAILURE: SafetyRuleDefinition(
        9,
        SafetyRuleCode.RULE_9_AST_PARSE_FAILURE,
        "AST parsing failure or syntax error encountered",
        "AST_DEPENDENCY",
    ),
    SafetyRuleCode.RULE_10_DYNAMIC_IMPORT: SafetyRuleDefinition(
        10,
        SafetyRuleCode.RULE_10_DYNAMIC_IMPORT,
        "Unresolved dynamic import or reflection detected",
        "AST_DEPENDENCY",
    ),
    SafetyRuleCode.RULE_11_CIRCULAR_OR_DISCONNECTED: SafetyRuleDefinition(
        11,
        SafetyRuleCode.RULE_11_CIRCULAR_OR_DISCONNECTED,
        "Circular dependency or disconnected dependency graph",
        "AST_DEPENDENCY",
    ),
    SafetyRuleCode.RULE_12_UNMAPPED_TESTS: SafetyRuleDefinition(
        12,
        SafetyRuleCode.RULE_12_UNMAPPED_TESTS,
        "Changed code has no identified or mapped test cases",
        "AST_DEPENDENCY",
    ),
    SafetyRuleCode.RULE_13_EMPTY_TEST_SELECTION: SafetyRuleDefinition(
        13,
        SafetyRuleCode.RULE_13_EMPTY_TEST_SELECTION,
        "Empty selected-test list for non-empty code change",
        "AST_DEPENDENCY",
    ),
    SafetyRuleCode.RULE_14_MODEL_ARTIFACT_MISSING: SafetyRuleDefinition(
        14,
        SafetyRuleCode.RULE_14_MODEL_ARTIFACT_MISSING,
        "ML prediction model artifact missing or unreadable",
        "MACHINE_LEARNING",
    ),
    SafetyRuleCode.RULE_15_MODEL_VERSION_MISMATCH: SafetyRuleDefinition(
        15,
        SafetyRuleCode.RULE_15_MODEL_VERSION_MISMATCH,
        "ML prediction model version mismatch or expired model",
        "MACHINE_LEARNING",
    ),
    SafetyRuleCode.RULE_16_INVALID_PREDICTION_OUTPUT: SafetyRuleDefinition(
        16,
        SafetyRuleCode.RULE_16_INVALID_PREDICTION_OUTPUT,
        "ML prediction output is NaN, infinite, or out-of-bounds",
        "MACHINE_LEARNING",
    ),
    SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA: SafetyRuleDefinition(
        17,
        SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA,
        "Insufficient historical training data (< 15 historical runs)",
        "MACHINE_LEARNING",
    ),
    SafetyRuleCode.RULE_18_LOW_PREDICTION_CONFIDENCE: SafetyRuleDefinition(
        18,
        SafetyRuleCode.RULE_18_LOW_PREDICTION_CONFIDENCE,
        "Prediction confidence score below threshold (< 0.70)",
        "MACHINE_LEARNING",
    ),
    SafetyRuleCode.RULE_19_API_UNREACHABLE: SafetyRuleDefinition(
        19,
        SafetyRuleCode.RULE_19_API_UNREACHABLE,
        "Optimization API unreachable or returned 5xx error",
        "INFRASTRUCTURE",
    ),
    SafetyRuleCode.RULE_20_GITHUB_API_FAILURE: SafetyRuleDefinition(
        20,
        SafetyRuleCode.RULE_20_GITHUB_API_FAILURE,
        "GitHub API failure after retry limit exceeded",
        "INFRASTRUCTURE",
    ),
    SafetyRuleCode.RULE_21_UNVERIFIABLE_SAFETY: SafetyRuleDefinition(
        21,
        SafetyRuleCode.RULE_21_UNVERIFIABLE_SAFETY,
        "Unverifiable safety condition or unhandled exception",
        "INFRASTRUCTURE",
    ),
}


@dataclass
class SafetyContext:
    """Input environment and analysis metadata supplied to the Safety Policy Evaluator."""

    # Code change flags
    has_migration_changes: bool = False
    has_auth_changes: bool = False
    has_payment_changes: bool = False
    has_crypto_changes: bool = False
    has_dependency_manifest_changes: bool = False
    has_lock_file_changes: bool = False
    has_ci_workflow_changes: bool = False
    has_unsupported_files: bool = False

    # AST & Mapping flags
    has_ast_syntax_error: bool = False
    has_dynamic_import: bool = False
    has_circular_dependency: bool = False
    has_unmapped_tests: bool = False
    is_test_selection_empty: bool = False
    non_empty_code_change: bool = True

    # Machine Learning flags
    model_artifact_exists: bool = True
    model_version_compatible: bool = True
    predicted_probability: float | None = 0.05
    prediction_confidence: float = 0.95
    historical_runs_count: int = 20

    # Infrastructure & Fallback flags
    api_reachable: bool = True
    github_api_success: bool = True
    unverifiable_safety_detected: bool = False
    custom_fallback_reason: str | None = None


@dataclass
class SafetyRuleTrigger:
    rule_number: int
    rule_code: SafetyRuleCode
    description: str
    category: str
    details: str | None = None


@dataclass
class SafetyEvaluationResult:
    """Outcome of evaluating all 21 deterministic safety rules."""

    is_safe_to_optimize: bool
    triggered_rules: list[SafetyRuleTrigger] = field(default_factory=list)
    primary_fallback_reason: str | None = None
    all_rules_audited: int = 21

    @property
    def fallback_required(self) -> bool:
        return not self.is_safe_to_optimize


class SafetyPolicyEvaluator:
    """
    Deterministic rule engine that evaluates whether a pipeline execution
    is permitted to run an optimized subset of tests or must execute the FULL SUITE.
    """

    CONFIDENCE_THRESHOLD: float = 0.70
    MIN_HISTORICAL_RUNS: int = 15

    def evaluate(self, context: SafetyContext) -> SafetyEvaluationResult:
        triggers: list[SafetyRuleTrigger] = []

        # Rule 1: Migration changes
        if context.has_migration_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_1_MIGRATION))

        # Rule 2: Auth changes
        if context.has_auth_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_2_AUTH))

        # Rule 3: Payment changes
        if context.has_payment_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_3_PAYMENT))

        # Rule 4: Crypto changes
        if context.has_crypto_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_4_CRYPTO))

        # Rule 5: Dependency manifest changes
        if context.has_dependency_manifest_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_5_DEPENDENCY_MANIFEST))

        # Rule 6: Lock file changes
        if context.has_lock_file_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_6_LOCK_FILE))

        # Rule 7: CI workflow changes
        if context.has_ci_workflow_changes:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_7_CI_WORKFLOW))

        # Rule 8: Unsupported files
        if context.has_unsupported_files:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_8_UNSUPPORTED_FILES))

        # Rule 9: AST syntax error
        if context.has_ast_syntax_error:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_9_AST_PARSE_FAILURE))

        # Rule 10: Dynamic import detected
        if context.has_dynamic_import:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_10_DYNAMIC_IMPORT))

        # Rule 11: Circular or disconnected graph
        if context.has_circular_dependency:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_11_CIRCULAR_OR_DISCONNECTED))

        # Rule 12: Unmapped tests
        if context.has_unmapped_tests:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_12_UNMAPPED_TESTS))

        # Rule 13: Empty test list for non-empty code change
        if context.non_empty_code_change and context.is_test_selection_empty:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_13_EMPTY_TEST_SELECTION))

        # Rule 14: Model artifact missing
        if not context.model_artifact_exists:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_14_MODEL_ARTIFACT_MISSING))

        # Rule 15: Model version mismatch or stale
        if not context.model_version_compatible:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_15_MODEL_VERSION_MISMATCH))

        # Rule 16: Invalid prediction output (None, NaN, Inf, or outside [0.0, 1.0])
        prob = context.predicted_probability
        if prob is None or math.isnan(prob) or math.isinf(prob) or not (0.0 <= prob <= 1.0):
            triggers.append(
                self._create_trigger(
                    SafetyRuleCode.RULE_16_INVALID_PREDICTION_OUTPUT,
                    details=f"Invalid probability value: {prob}",
                )
            )

        # Rule 17: Insufficient historical training data
        if context.historical_runs_count < self.MIN_HISTORICAL_RUNS:
            triggers.append(
                self._create_trigger(
                    SafetyRuleCode.RULE_17_INSUFFICIENT_TRAINING_DATA,
                    details=f"Historical runs ({context.historical_runs_count}) < minimum required ({self.MIN_HISTORICAL_RUNS})",
                )
            )

        # Rule 18: Low prediction confidence
        if context.prediction_confidence < self.CONFIDENCE_THRESHOLD:
            triggers.append(
                self._create_trigger(
                    SafetyRuleCode.RULE_18_LOW_PREDICTION_CONFIDENCE,
                    details=f"Confidence ({context.prediction_confidence:.2f}) < threshold ({self.CONFIDENCE_THRESHOLD:.2f})",
                )
            )

        # Rule 19: API unreachable
        if not context.api_reachable:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_19_API_UNREACHABLE))

        # Rule 20: GitHub API failure
        if not context.github_api_success:
            triggers.append(self._create_trigger(SafetyRuleCode.RULE_20_GITHUB_API_FAILURE))

        # Rule 21: Unverifiable safety or unhandled exception
        if context.unverifiable_safety_detected or context.custom_fallback_reason:
            triggers.append(
                self._create_trigger(
                    SafetyRuleCode.RULE_21_UNVERIFIABLE_SAFETY,
                    details=context.custom_fallback_reason
                    or "Unverifiable safety condition detected",
                )
            )

        is_safe = len(triggers) == 0
        primary_reason = None
        if not is_safe:
            primary_trigger = triggers[0]
            primary_reason = (
                f"Safety Rule {primary_trigger.rule_number}: {primary_trigger.description}"
            )
            if primary_trigger.details:
                primary_reason += f" ({primary_trigger.details})"

        return SafetyEvaluationResult(
            is_safe_to_optimize=is_safe,
            triggered_rules=triggers,
            primary_fallback_reason=primary_reason,
            all_rules_audited=len(SAFETY_RULE_CATALOG),
        )

    def _create_trigger(
        self, code: SafetyRuleCode, details: str | None = None
    ) -> SafetyRuleTrigger:
        defn = SAFETY_RULE_CATALOG[code]
        return SafetyRuleTrigger(
            rule_number=defn.rule_number,
            rule_code=code,
            description=defn.description,
            category=defn.category,
            details=details,
        )
