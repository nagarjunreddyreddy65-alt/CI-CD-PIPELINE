"""
Deterministic Decision Engine.
Coordinates AST dependency mapping, Machine Learning predictions, and Deterministic Safety Policy
to produce safe, auditable execution plans for CI/CD runners.

Core Axiom:
"AI predicts failure risk & duration. Deterministic safety rules decide execution."
"""

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.analysis.change_analyzer import ChangeAnalysisResult, ChangeAnalyzer
from app.analysis.test_mapper import TestDependencyMapper, TestMappingResult
from app.core.logging import logger
from app.database.models import (
    AuditLog,
    ChangedFile,
    Commit,
    ExecutionPlan,
    PipelineRun,
    Prediction,
    Repository,
)
from app.ml.feature_extractor import FeatureExtractor
from app.ml.model_manager import ModelManager
from app.optimization.safety_policy import (
    SafetyContext,
    SafetyEvaluationResult,
    SafetyPolicyEvaluator,
)
from app.optimization.test_selector import SelectedTestPlan, TestSelector


class ExecutionDecision(str, Enum):
    OPTIMIZED = "OPTIMIZED"
    FULL_SUITE = "FULL_SUITE"


@dataclass
class ExecutionPlanResult:
    __test__ = False  # Prevent Pytest collection
    decision: ExecutionDecision
    decision_reason: str
    is_optimized: bool
    fallback_triggered: bool
    fallback_reason: str | None
    selected_tests: list[str]
    selected_test_files: list[str]
    pytest_command: str
    total_tests_count: int
    selected_tests_count: int
    tests_reduction_pct: float
    predicted_failure_probability: float
    predicted_failure_class: int
    predicted_duration_sec: float
    estimated_time_saved_sec: float
    triggered_safety_rules: list[str]
    features: dict[str, Any]
    model_version: str
    pipeline_run_id: str | None = None
    plan_id: str | None = None


class DecisionEngine:
    __test__ = False  # Prevent Pytest collection
    """
    Main orchestrator for generating deterministic, ML-informed CI/CD execution plans.
    """

    def __init__(
        self,
        root_dir: str | None = None,
        model_manager: ModelManager | None = None,
        safety_evaluator: SafetyPolicyEvaluator | None = None,
        test_selector: TestSelector | None = None,
    ):
        self.root_dir = os.path.abspath(root_dir or ".")
        self.change_analyzer = ChangeAnalyzer(self.root_dir)
        self.test_mapper = TestDependencyMapper(self.root_dir)
        self.model_manager = model_manager or ModelManager()
        if (
            not self.model_manager.failure_predictor.is_trained
            or not self.model_manager.runtime_predictor.is_trained
        ):
            self.model_manager.load_models()
        self.safety_evaluator = safety_evaluator or SafetyPolicyEvaluator()
        self.test_selector = test_selector or TestSelector()
        self.feature_extractor = FeatureExtractor()

    def generate_plan(
        self,
        changed_file_entries: list[dict[str, Any]],
        historical_failure_rate: float = 0.05,
        previous_execution_duration: float = 25.0,
        historical_runs_count: int = 20,
        risk_threshold: float = 0.50,
        db: Session | None = None,
        repository_name: str | None = None,
        commit_hash: str | None = None,
        branch: str = "main",
        author_name: str = "Developer",
        author_email: str = "dev@example.com",
        commit_message: str = "Code update",
    ) -> ExecutionPlanResult:
        """
        Executes end-to-end plan generation workflow:
        1. Classifies changed files.
        2. Discovers tests and maps dependencies via AST.
        3. Extracts pre-execution ML features.
        4. Runs ML failure risk & runtime prediction.
        5. Evaluates 21 Deterministic Safety Policy rules.
        6. Selects tests & computes reduction metrics.
        7. Persists execution record to DB if session provided.
        """
        all_tests = self.test_mapper.discover_all_test_functions()

        # Step 1: Change Analysis
        change_res: ChangeAnalysisResult = self.change_analyzer.analyze_changes(
            changed_file_entries
        )

        # Step 2: AST Dependency & Test Mapping
        mapping_res: TestMappingResult = self.test_mapper.map_changes_to_tests(changed_file_entries)

        selected_candidate_tests = mapping_res.affected_test_identifiers
        affected_modules = mapping_res.affected_modules

        # Step 3: Historical Telemetry Resolution (Server-side DB verification takes precedence)
        historical_features_available = True
        if db is not None:
            try:
                completed_db_runs = (
                    db.query(PipelineRun)
                    .filter(PipelineRun.status.in_(["SUCCESS", "FAILED"]))
                    .order_by(PipelineRun.created_at.desc())
                    .limit(50)
                    .all()
                )
                effective_historical_runs = len(completed_db_runs)
                if effective_historical_runs >= 15:
                    failed_runs = sum(1 for r in completed_db_runs if r.status == "FAILED")
                    effective_failure_rate = round(failed_runs / effective_historical_runs, 4)
                    valid_dur_runs = [
                        r
                        for r in completed_db_runs
                        if float(getattr(r, "total_duration_sec", 0.0) or 0.0) > 0.0
                    ]
                    if valid_dur_runs:
                        effective_prev_duration = float(valid_dur_runs[0].total_duration_sec)
                    else:
                        effective_prev_duration = None
                        historical_features_available = False
                else:
                    effective_failure_rate = None
                    effective_prev_duration = None
                    historical_features_available = False
            except SQLAlchemyError as e:
                logger.warning(f"Failed to query historical runs from DB: {e}")
                effective_historical_runs = 0
                effective_failure_rate = None
                effective_prev_duration = None
                historical_features_available = False
        else:
            effective_historical_runs = (
                historical_runs_count if historical_runs_count is not None else 0
            )
            effective_failure_rate = historical_failure_rate
            effective_prev_duration = previous_execution_duration
            if (
                effective_historical_runs < 15
                or effective_failure_rate is None
                or effective_prev_duration is None
            ):
                historical_features_available = False

        # Ensure models are loaded and verified
        is_trained = (
            self.model_manager.failure_predictor.is_trained
            and self.model_manager.runtime_predictor.is_trained
        )
        if not is_trained:
            self.model_manager.load_models()
            is_trained = (
                self.model_manager.failure_predictor.is_trained
                and self.model_manager.runtime_predictor.is_trained
            )

        models_status = self.model_manager.get_models_status()
        base_artifacts_exist = (
            models_status["failure_predictor"]["model_file_exists"]
            and models_status["runtime_predictor"]["model_file_exists"]
            and is_trained
        )

        can_pred, can_pred_reason = self.model_manager.can_predict(
            genuine_historical_runs_count=effective_historical_runs
        )

        model_missing_or_invalid = not base_artifacts_exist or (
            "Safety Rule 14" in (can_pred_reason if not can_pred else "")
        )

        # If server-side historical features are unavailable or DB query failed, force FULL_SUITE without invented features
        if not historical_features_available and can_pred:
            can_pred = False
            can_pred_reason = (
                f"Safety Rule 17: Reliable server-side historical metrics unavailable or database query failed "
                f"(genuine runs: {effective_historical_runs}). Full suite fallback enforced."
            )

        # If model artifacts are missing, corrupt, synthetic, or uncertified, flag Rule 14
        model_artifacts_exist = base_artifacts_exist and not model_missing_or_invalid
        model_ver_ok = True
        model_ver_reason = ""

        # Step 4 & 5: Feature Extraction & ML Predictions (guaranteed pre-execution only)
        if can_pred and effective_failure_rate is not None and effective_prev_duration is not None:
            features = self.feature_extractor.extract(
                changed_files_count=change_res.total_changed_files,
                lines_added=change_res.total_lines_added,
                lines_deleted=change_res.total_lines_deleted,
                affected_modules_count=len(affected_modules),
                selected_tests_count=len(selected_candidate_tests),
                is_sensitive_change=change_res.is_sensitive,
                has_test_file_changes=change_res.has_test_changes,
                historical_failure_rate=effective_failure_rate,
                previous_execution_duration=effective_prev_duration,
            )
            try:
                fail_res = self.model_manager.failure_predictor.predict(features)
                fail_prob = fail_res.predicted_failure_probability
                fail_class = fail_res.predicted_failure_class
                confidence = fail_res.confidence

                runtime_res = self.model_manager.runtime_predictor.predict(features)
                pred_duration = runtime_res.predicted_duration_sec
                features_dict = features.to_dict()
            except (ValueError, NotImplementedError) as e:
                logger.warning(
                    f"ML inference unsupported or rejected: {e}. Enforcing Safety Rule 15 fallback."
                )
                fail_prob = 1.0
                fail_class = 1
                confidence = 0.50
                pred_duration = 0.0
                features_dict = features.to_dict()
                model_missing_or_invalid = True
                model_artifacts_exist = False
                model_ver_ok = False
                model_ver_reason = f"Safety Rule 15: {e}"
                can_pred = False
                can_pred_reason = f"Safety Rule 15: {e}"
        else:
            # Fallback path: do not invoke ML on invented inputs
            fail_prob = 0.0
            fail_class = 0
            confidence = 0.0
            pred_duration = 0.0
            features_dict = {
                "changed_files_count": change_res.total_changed_files,
                "lines_added": change_res.total_lines_added,
                "lines_deleted": change_res.total_lines_deleted,
                "total_lines_changed": change_res.total_lines_added
                + change_res.total_lines_deleted,
                "affected_modules_count": len(affected_modules),
                "selected_tests_count": len(selected_candidate_tests),
                "is_sensitive_change": change_res.is_sensitive,
                "has_test_file_changes": change_res.has_test_changes,
                "historical_runs_count": effective_historical_runs,
            }

        # Step 6: Construct Safety Context & Evaluate Deterministic Rules
        # Check AST parse and dynamic import status from mapping
        has_ast_error = "Safety Rule 9" in (mapping_res.fallback_reason or "")
        has_dynamic_imp = "Safety Rule 10" in (mapping_res.fallback_reason or "")
        has_circular = "Safety Rule 11" in (mapping_res.fallback_reason or "")
        has_unmapped = "Safety Rule 12" in (mapping_res.fallback_reason or "")
        is_empty_selection = (
            len(selected_candidate_tests) == 0 and change_res.total_changed_files > 0
        )

        base_ver_ok, base_ver_reason = self.model_manager.is_version_compatible()
        if "Safety Rule 15" in (can_pred_reason if not can_pred else ""):
            model_ver_ok = False
            model_ver_reason = can_pred_reason
        else:
            model_ver_ok = base_ver_ok and model_ver_ok
            if not base_ver_ok:
                model_ver_reason = base_ver_reason

        fallback_custom_reason = (
            mapping_res.fallback_reason
            if mapping_res.fallback_required
            else (None if can_pred else can_pred_reason)
        )
        if not model_ver_ok and not fallback_custom_reason:
            fallback_custom_reason = f"Safety Rule 15: {model_ver_reason}"

        safety_ctx = SafetyContext(
            has_migration_changes=change_res.has_migration_changes,
            has_auth_changes=change_res.has_auth_changes,
            has_payment_changes=change_res.has_payment_changes,
            has_crypto_changes=change_res.has_crypto_changes,
            has_dependency_manifest_changes=change_res.has_dependency_manifest_changes,
            has_lock_file_changes=change_res.has_lock_file_changes,
            has_ci_workflow_changes=change_res.has_ci_workflow_changes,
            has_unsupported_files=change_res.has_unsupported_files,
            has_ast_syntax_error=has_ast_error,
            has_dynamic_import=has_dynamic_imp,
            has_circular_dependency=has_circular,
            has_unmapped_tests=has_unmapped,
            is_test_selection_empty=is_empty_selection,
            non_empty_code_change=(change_res.total_changed_files > 0),
            model_artifact_exists=model_artifacts_exist,
            model_version_compatible=model_ver_ok,
            predicted_probability=fail_prob,
            predicted_duration=pred_duration,
            prediction_confidence=confidence,
            historical_runs_count=effective_historical_runs,
            api_reachable=True,
            github_api_success=True,
            unverifiable_safety_detected=False,
            custom_fallback_reason=fallback_custom_reason,
        )

        safety_res: SafetyEvaluationResult = self.safety_evaluator.evaluate(safety_ctx)

        # High risk threshold policy check (Risk threshold evaluation)
        high_risk_triggered = False
        if fail_prob >= risk_threshold:
            high_risk_triggered = True

        # Final Decision Formulation
        triggered_rules_names = [t.rule_code.value for t in safety_res.triggered_rules]

        if not can_pred or not safety_res.is_safe_to_optimize:
            decision = ExecutionDecision.FULL_SUITE
            fallback_triggered = True
            fallback_reason = (
                safety_res.primary_fallback_reason
                if not safety_res.is_safe_to_optimize
                else can_pred_reason
            )
            decision_reason = (
                f"Full test suite required by deterministic safety policy: {fallback_reason}."
            )
            force_full = True
        elif high_risk_triggered:
            decision = ExecutionDecision.FULL_SUITE
            fallback_triggered = True
            fallback_reason = f"High Failure Risk Policy: Predicted failure probability {fail_prob:.1%} >= threshold {risk_threshold:.1%}"
            decision_reason = (
                f"Full test suite triggered as safety precaution due to high predicted pipeline failure risk "
                f"({fail_prob:.1%})."
            )
            force_full = True
            triggered_rules_names.append("HIGH_RISK_THRESHOLD_EXCEEDED")
        else:
            decision = ExecutionDecision.OPTIMIZED
            fallback_triggered = False
            fallback_reason = None
            decision_reason = (
                f"Optimized test execution authorized. Code changes are non-sensitive and mapped to "
                f"{len(selected_candidate_tests)} affected tests (Predicted failure risk: {fail_prob:.1%})."
            )
            force_full = False

        # Step 6: Test Selection & Command Formatting
        selected_plan: SelectedTestPlan = self.test_selector.build_test_plan(
            selected_identifiers=selected_candidate_tests if not force_full else all_tests,
            all_repository_tests=all_tests,
            force_full_suite=force_full,
        )

        # Calculate estimated time saved
        # If optimized: saved time = (baseline_duration) * (reduction_pct / 100)
        baseline_time = (
            effective_prev_duration
            if (effective_prev_duration and effective_prev_duration > 0)
            else 30.0
        )
        if decision == ExecutionDecision.OPTIMIZED:
            estimated_time_saved = round(
                baseline_time * (selected_plan.reduction_percentage / 100.0), 2
            )
        else:
            estimated_time_saved = 0.0

        plan_result = ExecutionPlanResult(
            decision=decision,
            decision_reason=decision_reason,
            is_optimized=(decision == ExecutionDecision.OPTIMIZED),
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
            selected_tests=selected_plan.selected_test_identifiers,
            selected_test_files=selected_plan.selected_test_files,
            pytest_command=selected_plan.pytest_command_string,
            total_tests_count=selected_plan.total_tests_count,
            selected_tests_count=selected_plan.selected_tests_count,
            tests_reduction_pct=selected_plan.reduction_percentage,
            predicted_failure_probability=fail_prob,
            predicted_failure_class=fail_class,
            predicted_duration_sec=pred_duration,
            estimated_time_saved_sec=estimated_time_saved,
            triggered_safety_rules=triggered_rules_names,
            features=features_dict,
            model_version=models_status["failure_predictor"]["version"],
        )

        # Step 7: Database Persistence (if session provided)
        if db is not None:
            self._persist_to_db(
                db=db,
                plan_result=plan_result,
                all_tests=all_tests,
                changed_file_entries=changed_file_entries,
                repository_name=repository_name or "AutonomousDevOps/CI-CD-PIPELINE",
                commit_hash=commit_hash or f"commit-{int(time.time())}",
                branch=branch,
                author_name=author_name,
                author_email=author_email,
                commit_message=commit_message,
            )

        return plan_result

    def _persist_to_db(
        self,
        db: Session,
        plan_result: ExecutionPlanResult,
        all_tests: list[str],
        changed_file_entries: list[dict[str, Any]],
        repository_name: str,
        commit_hash: str,
        branch: str,
        author_name: str,
        author_email: str,
        commit_message: str,
    ) -> None:
        """Persists repository, commit, pipeline run, execution plan, and audit logs to PostgreSQL/SQLite."""
        try:
            # 1. Get or create repository
            repo = db.query(Repository).filter(Repository.name == repository_name).first()
            if not repo:
                owner = (
                    repository_name.split("/")[0] if "/" in repository_name else "AutonomousDevOps"
                )
                repo = Repository(
                    name=repository_name,
                    owner=owner,
                    clone_url=f"https://github.com/{repository_name}",
                    default_branch=branch,
                )
                db.add(repo)
                db.flush()

            # 2. Get or create commit
            commit = (
                db.query(Commit)
                .filter(Commit.repository_id == repo.id, Commit.commit_hash == commit_hash)
                .first()
            )
            if not commit:
                commit = Commit(
                    repository_id=repo.id,
                    commit_hash=commit_hash,
                    branch=branch,
                    author_name=author_name,
                    author_email=author_email,
                    message=commit_message,
                )
                db.add(commit)
                db.flush()

                # Record changed files
                for item in changed_file_entries:
                    cf = ChangedFile(
                        commit_id=commit.id,
                        file_path=item.get("file_path", ""),
                        change_type=item.get("change_type", "MODIFIED"),
                        lines_added=item.get("lines_added", 0),
                        lines_deleted=item.get("lines_deleted", 0),
                        is_sensitive=plan_result.fallback_triggered,
                    )
                    db.add(cf)

            # 3. Create PipelineRun
            pipeline_run = PipelineRun(
                repository_id=repo.id,
                commit_id=commit.id,
                workflow_name="Autonomous DevOps CI",
                status="RUNNING",
                trigger_event="push",
                is_optimized=plan_result.is_optimized,
                fallback_triggered=plan_result.fallback_triggered,
                fallback_reason=plan_result.fallback_reason,
                total_duration_sec=0.0,
            )
            db.add(pipeline_run)
            db.flush()

            # 4. Create ExecutionPlan
            plan = ExecutionPlan(
                pipeline_run_id=pipeline_run.id,
                decision=plan_result.decision.value,
                decision_reason=plan_result.decision_reason,
                selected_tests_count=plan_result.selected_tests_count,
                total_tests_count=plan_result.total_tests_count,
                tests_reduction_pct=plan_result.tests_reduction_pct,
                selected_tests_json=json.dumps(plan_result.selected_tests),
                safety_rule_triggered=",".join(plan_result.triggered_safety_rules)
                if plan_result.triggered_safety_rules
                else None,
            )
            db.add(plan)
            db.flush()

            # 5. Create Prediction
            pred = Prediction(
                pipeline_run_id=pipeline_run.id,
                model_version=plan_result.model_version,
                predicted_failure_probability=plan_result.predicted_failure_probability,
                predicted_failure_class=plan_result.predicted_failure_class,
                predicted_duration_sec=plan_result.predicted_duration_sec,
                features_json=json.dumps(plan_result.features),
            )
            db.add(pred)

            # 6. Create AuditLog
            audit = AuditLog(
                event_type="EXECUTION_PLAN_GENERATED",
                entity_type="ExecutionPlan",
                entity_id=plan.id,
                details=f"Decision: {plan_result.decision.value}. Reason: {plan_result.decision_reason}",
            )
            db.add(audit)

            db.commit()

            plan_result.pipeline_run_id = pipeline_run.id
            plan_result.plan_id = plan.id
            logger.info(
                f"Persisted execution plan {plan.id} for run {pipeline_run.id} (Decision: {plan_result.decision.value})"
            )

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Error persisting execution plan to DB: {e}")
            plan_result.decision = ExecutionDecision.FULL_SUITE
            plan_result.is_optimized = False
            plan_result.fallback_triggered = True
            plan_result.fallback_reason = f"Safety Rule 21: Database persistence failure: audit record could not be stored ({e})"
            plan_result.decision_reason = f"Full test suite required by deterministic safety policy: {plan_result.fallback_reason}."
            if "RULE_21_UNVERIFIABLE_SAFETY" not in plan_result.triggered_safety_rules:
                plan_result.triggered_safety_rules.append("RULE_21_UNVERIFIABLE_SAFETY")

            full_plan = self.test_selector.build_test_plan(
                selected_identifiers=all_tests,
                all_repository_tests=all_tests,
                force_full_suite=True,
            )
            plan_result.selected_tests = full_plan.selected_test_identifiers
            plan_result.selected_test_files = full_plan.selected_test_files
            plan_result.pytest_command = full_plan.pytest_command_string
            plan_result.selected_tests_count = full_plan.selected_tests_count
            plan_result.tests_reduction_pct = 0.0
            plan_result.estimated_time_saved_sec = 0.0
            plan_result.plan_id = None
            plan_result.pipeline_run_id = None

    @staticmethod
    def complete_pipeline_run(
        db: Session,
        pipeline_run_id: str,
        status: str,
        total_duration_sec: float | None = None,
        error_message: str | None = None,
    ) -> PipelineRun | None:
        """
        Transitions a pipeline run to terminal status (SUCCESS, FAILED, ABORTED, CANCELLED),
        computing duration and recording an audit trail. Handles late runner completions
        safely if previously reconciled as ABORTED.
        """
        run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
        if not run:
            return None

        is_late_completion = run.status == "ABORTED" and status in ("SUCCESS", "FAILED")
        terminal_states = {"SUCCESS", "FAILED", "CANCELLED"}
        if run.status in terminal_states and not is_late_completion:
            if run.status == status:
                # Duplicate terminal request with identical status: idempotent no-op
                return run
            # Conflicting terminal update
            raise ValueError(
                f"Cannot transition pipeline run '{pipeline_run_id}' from terminal status '{run.status}' to '{status}'."
            )

        completed_ts = datetime.now(UTC)
        run.completed_at = completed_ts
        original_status = run.status
        run.status = status

        if total_duration_sec is not None:
            run.total_duration_sec = total_duration_sec
        elif run.created_at:
            created_tz = (
                run.created_at if run.created_at.tzinfo else run.created_at.replace(tzinfo=UTC)
            )
            run.total_duration_sec = max(0.0, round((completed_ts - created_tz).total_seconds(), 2))

        if error_message and not run.fallback_reason:
            run.fallback_reason = error_message

        event_name = (
            "LATE_RUNNER_COMPLETION_RECORDED" if is_late_completion else "PIPELINE_RUN_COMPLETED"
        )
        audit = AuditLog(
            event_type=event_name,
            entity_type="PipelineRun",
            entity_id=run.id,
            details=(
                f"Run transitioned from {original_status} to {status}. "
                f"Duration: {run.total_duration_sec}s. Late completion: {is_late_completion}."
            ),
        )
        db.add(audit)
        db.commit()
        db.refresh(run)
        return run
