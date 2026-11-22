"""
Integration Tests for the Deterministic Decision Engine.
Verifies coordination between AST mapping, ML risk prediction, Safety Rules, and DB persistence.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import AuditLog, Base, ExecutionPlan, PipelineRun, Prediction
from app.ml.model_manager import ModelManager
from app.optimization.decision_engine import DecisionEngine, ExecutionDecision


@pytest.fixture
def sqlite_db_session():
    """In-memory SQLite session for testing DB persistence."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def trained_model_manager(tmp_path):
    """Initializes and trains model manager with genuine telemetry schema."""
    manager = ModelManager(registry_dir=str(tmp_path))
    X, y_fail, y_time = manager.generate_synthetic_historical_data(n_samples=40)
    manager.train_and_persist(
        n_samples=40,
        data_source="GENUINE_PIPELINE_TELEMETRY",
        genuine_historical_runs_count=40,
        training_data=(X, y_fail, y_time),
        is_production_ready=True,
        verified_db_source=True,
    )
    return manager


def test_decision_engine_optimized_workflow(trained_model_manager):
    """
    When an isolated utility function is changed, DecisionEngine authorizes OPTIMIZED execution.
    """
    engine = DecisionEngine(root_dir=".", model_manager=trained_model_manager)

    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 8,
            "lines_deleted": 2,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        historical_failure_rate=0.03,
        previous_execution_duration=20.0,
        historical_runs_count=30,
        risk_threshold=0.60,
    )

    assert plan.decision == ExecutionDecision.OPTIMIZED
    assert plan.is_optimized is True
    assert plan.fallback_triggered is False
    assert plan.fallback_reason is None
    assert plan.selected_tests_count > 0
    assert plan.selected_tests_count < plan.total_tests_count
    assert plan.tests_reduction_pct > 0.0
    assert plan.estimated_time_saved_sec > 0.0
    assert any("test_math_ops.py" in t for t in plan.selected_tests)


def test_decision_engine_auth_fallback(trained_model_manager):
    """
    When authentication code is changed, Safety Rule 2 enforces mandatory FULL_SUITE fallback.
    """
    engine = DecisionEngine(root_dir=".", model_manager=trained_model_manager)

    changes = [
        {
            "file_path": "sample_app/auth/security_service.py",
            "change_type": "MODIFIED",
            "lines_added": 12,
            "lines_deleted": 4,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        historical_failure_rate=0.02,
        previous_execution_duration=25.0,
        historical_runs_count=30,
        risk_threshold=0.60,
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.is_optimized is False
    assert plan.fallback_triggered is True
    assert "Safety Rule 2" in plan.fallback_reason
    assert "RULE_2_AUTH" in plan.triggered_safety_rules
    assert plan.selected_tests_count == plan.total_tests_count
    assert plan.tests_reduction_pct == 0.0


def test_decision_engine_high_risk_threshold_fallback(trained_model_manager):
    """
    When risk threshold is configured very low (e.g. 0.001), high risk triggers precautionary full suite.
    """
    engine = DecisionEngine(root_dir=".", model_manager=trained_model_manager)

    changes = [
        {
            "file_path": "sample_app/utils/string_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 5,
            "lines_deleted": 1,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        historical_failure_rate=0.05,
        previous_execution_duration=15.0,
        historical_runs_count=30,
        risk_threshold=0.0001,  # Forces threshold trigger
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.fallback_triggered is True
    assert "HIGH_RISK_THRESHOLD_EXCEEDED" in plan.triggered_safety_rules


def test_decision_engine_db_persistence(trained_model_manager, sqlite_db_session):
    """
    Verifies that generate_plan correctly persists run, plan, prediction, and audit logs.
    """
    engine = DecisionEngine(root_dir=".", model_manager=trained_model_manager)

    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 4,
            "lines_deleted": 1,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        db=sqlite_db_session,
        repository_name="AutonomousDevOps/CI-CD-PIPELINE",
        commit_hash="persisted-sha-12345",
        branch="main",
        commit_message="Refactor math utils",
    )

    assert plan.plan_id is not None
    assert plan.pipeline_run_id is not None

    # Query DB entities
    saved_plan = (
        sqlite_db_session.query(ExecutionPlan).filter(ExecutionPlan.id == plan.plan_id).first()
    )
    assert saved_plan is not None
    assert saved_plan.decision == plan.decision.value

    saved_run = (
        sqlite_db_session.query(PipelineRun).filter(PipelineRun.id == plan.pipeline_run_id).first()
    )
    assert saved_run is not None
    assert saved_run.commit.commit_hash == "persisted-sha-12345"

    saved_pred = (
        sqlite_db_session.query(Prediction)
        .filter(Prediction.pipeline_run_id == saved_run.id)
        .first()
    )
    assert saved_pred is not None

    audit_entry = (
        sqlite_db_session.query(AuditLog).filter(AuditLog.entity_id == saved_plan.id).first()
    )
    assert audit_entry is not None
    assert audit_entry.event_type == "EXECUTION_PLAN_GENERATED"
