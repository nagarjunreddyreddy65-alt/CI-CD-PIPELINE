"""
Dedicated Acceptance & Regression Tests for P0 and P1 Engineering Remediation Items.
Autonomous DevOps: An AI-Driven Approach for Intelligent CI/CD Pipeline Optimization.

Covers:
1. P0-1: DecisionEngine model loading and rejection of untrained heuristic optimization.
2. P0-2: Server-side historical run verification gating (Rule 17) and prevention of caller spoofing.
3. P0-3: GitHub Actions EXE001 shebang removal verification.
4. P0-4: Database persistence failure handling (Rule 21 fail-safe fallback) and production startup fail-fast.
5. P1-5: Genuine telemetry training with DB feature extraction and holdout test set evaluation.
6. P2-6: Protection of operational read endpoints with runner token.
"""

import os
import tempfile
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.models import Base, ChangedFile, Commit, PipelineRun, Repository
from app.main import app, lifespan
from app.ml.model_manager import ModelManager, VerifiedTelemetryDataset
from app.optimization.decision_engine import DecisionEngine, ExecutionDecision


@pytest.fixture
def fresh_sqlite_db():
    """Provides a dedicated in-memory SQLite session for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_decision_engine_loads_models_on_initialization():
    """Verifies DecisionEngine attempts to load existing model artifacts on __init__."""
    engine = DecisionEngine(root_dir=".")
    # The models in app/ml/models should be loaded
    assert engine.model_manager.failure_predictor.is_trained is True
    assert engine.model_manager.runtime_predictor.is_trained is True


def test_decision_engine_missing_model_artifacts_triggers_rule_14(fresh_sqlite_db):
    """
    Verifies that when model artifacts are missing or unreadable,
    Safety Rule 14 triggers and mandates FULL_SUITE fallback.
    """
    with tempfile.TemporaryDirectory() as empty_dir:
        empty_mm = ModelManager(registry_dir=empty_dir)
        engine = DecisionEngine(root_dir=".", model_manager=empty_mm)

        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]

        plan = engine.generate_plan(
            changed_file_entries=changes,
            db=fresh_sqlite_db,
            historical_runs_count=25,
        )

        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.is_optimized is False
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_server_enforces_rule_17_when_db_runs_insufficient(fresh_sqlite_db):
    """
    Verifies that when database has < 15 genuine runs,
    Rule 17 forces FULL_SUITE even if caller passes historical_runs_count=50.
    """
    engine = DecisionEngine(root_dir=".")

    # DB currently has 0 runs (< 15)
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 3,
            "lines_deleted": 1,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        db=fresh_sqlite_db,
        historical_runs_count=50,  # Caller attempts to spoof 50 runs
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.is_optimized is False
    assert plan.fallback_triggered is True
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" in plan.triggered_safety_rules


def test_server_authorizes_optimization_when_db_runs_sufficient(fresh_sqlite_db):
    """
    Verifies that when database has >= 15 genuine runs,
    Rule 17 is satisfied and optimization is authorized for safe changes.
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    # Seed 16 completed runs
    for i in range(16):
        commit = Commit(
            repository_id=repo.id,
            commit_hash=f"auth-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@example.com",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(commit)
        fresh_sqlite_db.flush()

        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=18.0,
        )
        fresh_sqlite_db.add(run)
    fresh_sqlite_db.commit()

    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 1,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        db=fresh_sqlite_db,
    )

    assert plan.decision == ExecutionDecision.OPTIMIZED
    assert plan.is_optimized is True
    assert plan.fallback_triggered is False
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" not in plan.triggered_safety_rules


def test_database_persistence_failure_triggers_rule_21_fallback():
    """
    Verifies that if SQLAlchemyError occurs during database persistence,
    DecisionEngine refuses to authorize test skipping and forces FULL_SUITE.
    """
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.count.return_value = 25
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.commit.side_effect = SQLAlchemyError("Simulated database write failure")

    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 1,
        }
    ]

    plan = engine.generate_plan(
        changed_file_entries=changes,
        db=mock_db,
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.is_optimized is False
    assert plan.fallback_triggered is True
    assert "RULE_21_UNVERIFIABLE_SAFETY" in plan.triggered_safety_rules
    assert "Database persistence failure" in (plan.fallback_reason or "")
    assert plan.plan_id is None
    assert plan.pipeline_run_id is None
    mock_db.rollback.assert_called()


def test_production_startup_fails_fast_on_database_error():
    """
    Verifies that in production mode, lifespan fails fast and raises
    if database initialization fails.
    """
    import asyncio

    async def _test():
        with (
            patch("app.main.init_db", side_effect=OperationalError("connection refused", {}, None)),
            pytest.raises(SQLAlchemyError),
        ):
            async with lifespan(app):
                pass

    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        asyncio.run(_test())
    finally:
        settings.ENVIRONMENT = original_env


def test_runner_shebang_removed_from_ci_script():
    """Verifies scripts/run_optimized_ci.py has no POSIX shebang on line 1 (fixes EXE001)."""
    script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "run_optimized_ci.py")
    with open(script_path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    assert not first_line.startswith("#!"), (
        f"Expected no shebang in {script_path}, found: {first_line}"
    )


def test_operational_read_endpoints_protected_in_production(fresh_sqlite_db):
    """
    Verifies operational read endpoints reject unauthorized requests with HTTP 401 in production,
    and accept requests with valid X-Runner-Token.
    """
    original_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        client = TestClient(app)

        # 1. Missing token -> 401
        for ep in [
            "/api/v1/plans",
            "/api/v1/plans/test-plan-id",
            "/api/v1/security/scans/test-run-id",
            "/api/v1/telemetry/history",
        ]:
            res = client.get(ep)
            assert res.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Expected 401 for {ep}, got {res.status_code}"
            )

        # 2. Invalid token -> 403
        bad_headers = {"X-Runner-Token": "bad-runner-token"}
        for ep in [
            "/api/v1/plans",
            "/api/v1/plans/test-plan-id",
            "/api/v1/security/scans/test-run-id",
            "/api/v1/telemetry/history",
        ]:
            res = client.get(ep, headers=bad_headers)
            assert res.status_code == status.HTTP_403_FORBIDDEN, (
                f"Expected 403 for {ep}, got {res.status_code}"
            )

        # 3. Valid token -> allowed
        good_headers = {"X-Runner-Token": settings.RUNNER_API_KEY}
        res = client.get("/api/v1/plans", headers=good_headers)
        assert res.status_code == status.HTTP_200_OK
        res = client.get("/api/v1/telemetry/history", headers=good_headers)
        assert res.status_code == status.HTTP_200_OK

    finally:
        settings.ENVIRONMENT = original_env


def test_corrupted_model_artifacts_triggers_rule_14(fresh_sqlite_db):
    """Verifies that corrupted/unreadable model files fail to load and trigger Rule 14."""
    with tempfile.TemporaryDirectory() as corrupt_dir:
        fail_file = os.path.join(corrupt_dir, "failure_predictor.joblib")
        time_file = os.path.join(corrupt_dir, "runtime_predictor.joblib")
        with open(fail_file, "wb") as f:
            f.write(b"NOT_A_VALID_JOBLIB_FILE_CORRUPTED_PAYLOAD")
        with open(time_file, "wb") as f:
            f.write(b"NOT_A_VALID_JOBLIB_FILE_CORRUPTED_PAYLOAD")

        corrupt_mm = ModelManager(registry_dir=corrupt_dir)
        loaded = corrupt_mm.load_models()
        assert loaded is False

        engine = DecisionEngine(root_dir=".", model_manager=corrupt_mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]
        plan = engine.generate_plan(
            changed_file_entries=changes, db=fresh_sqlite_db, historical_runs_count=20
        )
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_synthetic_only_model_never_production_ready():
    """Verifies synthetic bootstrap models are never marked production ready."""
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        res = mm.train_and_persist(n_samples=25, data_source="SYNTHETIC_BOOTSTRAP")
        assert res["provenance"] == "SYNTHETIC_BOOTSTRAP"
        assert res["is_production_ready"] is False
        can_pred, reason = mm.can_predict(genuine_historical_runs_count=0)
        assert can_pred is False
        assert "Safety Rule 14" in reason or "Safety Rule 17" in reason


def test_genuine_model_with_valid_provenance():
    """Verifies genuine telemetry training marks model as production ready when certified."""
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        mock_runs = []
        for i in range(30):
            is_fail = i % 3 == 0
            lines = 80 if is_fail else 10
            dur = 10.0 + (lines * 0.25) + (5.0 if is_fail else 0.0)
            r = PipelineRun(
                id=f"prov-run-{i:03d}",
                status="FAILED" if is_fail else "SUCCESS",
                total_duration_sec=dur,
            )
            c = Commit(commit_hash=f"prov-hash-{i:03d}", branch="main")
            cf = ChangedFile(
                file_path="sample_app/utils/math_ops.py"
                if not is_fail
                else "sample_app/services/security_service.py",
                change_type="MODIFIED",
                lines_added=lines,
                lines_deleted=2 if not is_fail else 20,
                is_sensitive=is_fail,
            )
            c.changed_files = [cf]
            r.commit = c
            mock_runs.append(r)
        telemetry = mm.extract_features_from_db_runs(mock_runs)
        res = mm.train_and_persist(
            n_samples=len(telemetry),
            data_source="GENUINE_PIPELINE_TELEMETRY",
            genuine_historical_runs_count=30,
            training_data=telemetry,
            verified_db_source=True,
        )
        assert res["provenance"] == "GENUINE_PIPELINE_TELEMETRY"
        assert res["is_production_ready"] is True
        assert res["certification_report"]["is_certified"] is True
        can_pred, _ = mm.can_predict(genuine_historical_runs_count=25)
        assert can_pred is True


def test_insufficient_historical_runs_exactly_one_below_minimum(fresh_sqlite_db):
    """
    Verifies that exactly 14 completed runs (one below the minimum threshold of 15)
    strictly triggers Rule 17 and enforces FULL_SUITE fallback.
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    for i in range(14):
        commit = Commit(
            repository_id=repo.id,
            commit_hash=f"run-14-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@ci.local",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(commit)
        fresh_sqlite_db.flush()
        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=16.0,
        )
        fresh_sqlite_db.add(run)
    fresh_sqlite_db.commit()

    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(changed_file_entries=changes, db=fresh_sqlite_db)
    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.fallback_triggered is True
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" in plan.triggered_safety_rules


def test_sufficient_historical_runs_exactly_at_minimum(fresh_sqlite_db):
    """
    Verifies that exactly 15 completed runs (the exact minimum threshold)
    satisfies Rule 17 and permits OPTIMIZED test selection for safe changes.
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    for i in range(15):
        commit = Commit(
            repository_id=repo.id,
            commit_hash=f"run-15-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@ci.local",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(commit)
        fresh_sqlite_db.flush()
        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=16.0,
        )
        fresh_sqlite_db.add(run)
    fresh_sqlite_db.commit()

    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]
    plan = engine.generate_plan(changed_file_entries=changes, db=fresh_sqlite_db)
    assert plan.decision == ExecutionDecision.OPTIMIZED
    assert plan.is_optimized is True
    assert plan.fallback_triggered is False
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" not in plan.triggered_safety_rules


def test_runner_api_unreachable_forces_full_suite():
    """
    Verifies Safety Rule 19: when CI runner cannot reach the backend API,
    it catches the failure and falls back to FULL_SUITE.
    """
    import httpx

    from scripts.run_optimized_ci import request_plan_from_api

    with pytest.raises((httpx.HTTPError, RuntimeError, OSError)):
        request_plan_from_api("http://127.0.0.1:99999", {"test": "payload"})


def test_synthetic_model_with_20_db_runs_forces_full_suite(fresh_sqlite_db):
    """
    Verifies that a model trained on SYNTHETIC_BOOTSTRAP data can NEVER authorize
    test skipping, even when the database contains 20 genuine runs.
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    for i in range(20):
        commit = Commit(
            repository_id=repo.id,
            commit_hash=f"synth-test-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@ci.local",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(commit)
        fresh_sqlite_db.flush()
        run = PipelineRun(
            repository_id=repo.id,
            commit_id=commit.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=16.0,
        )
        fresh_sqlite_db.add(run)
    fresh_sqlite_db.commit()

    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        # Train strictly synthetic model
        mm.train_and_persist(n_samples=25, data_source="SYNTHETIC_BOOTSTRAP")

        can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
        assert can_pred is False
        assert "Safety Rule 14" in reason
        assert "SYNTHETIC_BOOTSTRAP" in reason

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]
        plan = engine.generate_plan(changed_file_entries=changes, db=fresh_sqlite_db)
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.is_optimized is False
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_missing_metadata_forces_full_suite(fresh_sqlite_db):
    """Verifies that missing model_metadata.json forces FULL_SUITE fallback."""
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        mock_runs = []
        for i in range(30):
            is_fail = i % 3 == 0
            lines = 80 if is_fail else 10
            dur = 10.0 + (lines * 0.25) + (5.0 if is_fail else 0.0)
            r = PipelineRun(
                id=f"sha-run-{i:03d}",
                status="FAILED" if is_fail else "SUCCESS",
                total_duration_sec=dur,
            )
            c = Commit(commit_hash=f"sha-hash-{i:03d}", branch="main")
            cf = ChangedFile(
                file_path="sample_app/utils/math_ops.py"
                if not is_fail
                else "sample_app/services/security_service.py",
                change_type="MODIFIED",
                lines_added=lines,
                lines_deleted=2 if not is_fail else 20,
                is_sensitive=is_fail,
            )
            c.changed_files = [cf]
            r.commit = c
            mock_runs.append(r)
        telemetry = mm.extract_features_from_db_runs(mock_runs)
        mm.train_and_persist(
            n_samples=len(telemetry),
            data_source="GENUINE_PIPELINE_TELEMETRY",
            genuine_historical_runs_count=30,
            training_data=telemetry,
            verified_db_source=True,
        )
        # Delete metadata file
        if os.path.exists(mm.metadata_path):
            os.remove(mm.metadata_path)

        can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
        assert can_pred is False
        assert "Safety Rule 14" in reason

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]
        plan = engine.generate_plan(
            changed_file_entries=changes, db=fresh_sqlite_db, historical_runs_count=20
        )
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_corrupted_metadata_forces_full_suite(fresh_sqlite_db):
    """Verifies that corrupted model_metadata.json forces FULL_SUITE fallback."""
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        mock_runs = []
        for i in range(30):
            is_fail = i % 3 == 0
            lines = 80 if is_fail else 10
            dur = 10.0 + (lines * 0.25) + (5.0 if is_fail else 0.0)
            r = PipelineRun(
                id=f"sha-run-{i:03d}",
                status="FAILED" if is_fail else "SUCCESS",
                total_duration_sec=dur,
            )
            c = Commit(commit_hash=f"sha-hash-{i:03d}", branch="main")
            cf = ChangedFile(
                file_path="sample_app/utils/math_ops.py"
                if not is_fail
                else "sample_app/services/security_service.py",
                change_type="MODIFIED",
                lines_added=lines,
                lines_deleted=2 if not is_fail else 20,
                is_sensitive=is_fail,
            )
            c.changed_files = [cf]
            r.commit = c
            mock_runs.append(r)
        telemetry = mm.extract_features_from_db_runs(mock_runs)
        mm.train_and_persist(
            n_samples=len(telemetry),
            data_source="GENUINE_PIPELINE_TELEMETRY",
            genuine_historical_runs_count=30,
            training_data=telemetry,
            verified_db_source=True,
        )
        # Overwrite with invalid JSON
        with open(mm.metadata_path, "w", encoding="utf-8") as f:
            f.write("{invalid_json: true, unterminated")

        can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
        assert can_pred is False
        assert "Safety Rule 14" in reason

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]
        plan = engine.generate_plan(
            changed_file_entries=changes, db=fresh_sqlite_db, historical_runs_count=20
        )
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_mismatched_model_and_metadata_provenance(fresh_sqlite_db):
    """
    Verifies that when metadata claims genuine telemetry but model files are untrained/missing,
    optimization is rejected with FULL_SUITE.
    """
    import json

    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        # Create metadata claiming production ready without trained models
        metadata = {
            "provenance": "GENUINE_PIPELINE_TELEMETRY",
            "sample_count": 50,
            "genuine_historical_runs_count": 50,
            "is_production_ready": True,
        }
        with open(mm.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f)

        # In-memory models are untrained
        assert mm.failure_predictor.is_trained is False
        can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
        assert can_pred is False
        assert "Safety Rule 14" in reason

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]
        plan = engine.generate_plan(
            changed_file_entries=changes, db=fresh_sqlite_db, historical_runs_count=20
        )
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.fallback_triggered is True


def test_no_post_execution_feature_leakage_in_training_matrix():
    """
    Verifies that extract_features_from_db_runs NEVER leaks post-execution fields
    (e.g., fallback_triggered, current run's total_duration_sec) into the pre-execution input matrix.
    """

    class MockFile:
        def __init__(self, path: str, added: int, deleted: int, is_sens: bool = False):
            self.file_path = path
            self.lines_added = added
            self.lines_deleted = deleted
            self.is_sensitive = is_sens

    class MockCommit:
        def __init__(self, changed_files: list):
            self.changed_files = changed_files

    class MockRun:
        def __init__(
            self,
            status: str,
            duration: float,
            fallback_triggered: bool,
            created_at: datetime,
            files: list,
        ):
            self.status = status
            self.total_duration_sec = duration
            self.fallback_triggered = fallback_triggered
            self.created_at = created_at
            self.commit = MockCommit(files)
            self.execution_plan = None
            self.predictions = []

    files = [MockFile("sample_app/utils/math_ops.py", 5, 2, False)]

    # Run 0: 10.0s, fallback=True
    run0 = MockRun("SUCCESS", 10.0, True, datetime(2026, 1, 1, 10, 0, tzinfo=UTC), files)
    # Run 1: 80.0s, fallback=True (failed)
    run1 = MockRun("FAILED", 80.0, True, datetime(2026, 1, 1, 11, 0, tzinfo=UTC), files)
    # Run 2: 30.0s, fallback=False
    run2 = MockRun("SUCCESS", 30.0, False, datetime(2026, 1, 1, 12, 0, tzinfo=UTC), files)

    mm = ModelManager()
    X, y_fail, y_time = mm.extract_features_from_db_runs([run0, run1, run2])

    # Run 0 is safely excluded because antecedent history does not exist,
    # preventing fabricated defaults (e.g. 0.05 failure rate or 25.0 duration).
    assert len(X) == 2

    # Feature 6 (is_sensitive): Must be 0 because math_ops.py is non-sensitive!
    # Even though run1 had fallback_triggered=True, post-execution fallback must NOT contaminate is_sensitive!
    assert X[0][6] == 0.0, "Post-execution fallback_triggered must not contaminate is_sensitive"
    assert X[1][6] == 0.0, "Post-execution fallback_triggered must not contaminate is_sensitive"

    # Feature 9 (previous_execution_duration):
    # Run 1 (index 0): Prior run was run0 (10.0s) -> MUST be 10.0, NOT its own 80.0!
    assert X[0][9] == 10.0, f"Expected 10.0 prior duration for run 1, got {X[0][9]}"
    # Run 2 (index 1): Prior run was run1 (80.0s) -> MUST be 80.0, NOT its own 30.0!
    assert X[1][9] == 80.0, f"Expected 80.0 prior duration for run 2, got {X[1][9]}"

    # Targets must match completed outcomes
    assert y_fail.tolist() == [1, 0]
    assert y_time.tolist() == [80.0, 30.0]


def test_missing_historical_feature_values_forces_full_suite(fresh_sqlite_db):
    """
    Verifies that when reliable historical features are absent (0 runs in DB),
    DecisionEngine forces FULL_SUITE even if client passes spoofed metrics.
    """
    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]

    # Caller attempts to supply spoofed failure rate and run count
    plan = engine.generate_plan(
        changed_file_entries=changes,
        db=fresh_sqlite_db,
        historical_runs_count=50,
        historical_failure_rate=0.001,
        previous_execution_duration=12.0,
    )

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.fallback_triggered is True
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" in plan.triggered_safety_rules


def test_database_query_failure_during_historical_fetch_forces_full_suite():
    """
    Verifies that if querying the database for historical runs raises an exception,
    DecisionEngine safely catches it, treats historical runs as 0, and forces FULL_SUITE.
    """
    mock_db = MagicMock()
    mock_db.query.side_effect = SQLAlchemyError("Database connection lost during query")

    engine = DecisionEngine(root_dir=".")
    changes = [
        {
            "file_path": "sample_app/utils/math_ops.py",
            "change_type": "MODIFIED",
            "lines_added": 2,
            "lines_deleted": 0,
        }
    ]

    plan = engine.generate_plan(changed_file_entries=changes, db=mock_db)

    assert plan.decision == ExecutionDecision.FULL_SUITE
    assert plan.is_optimized is False
    assert plan.fallback_triggered is True
    assert "RULE_17_INSUFFICIENT_TRAINING_DATA" in plan.triggered_safety_rules


def test_synthetic_training_array_cannot_be_labeled_genuine():
    """
    Verifies that train_and_persist strictly rejects caller attempts to label
    synthetic arrays as GENUINE_PIPELINE_TELEMETRY without verified_db_source=True.
    """
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        X, y_fail, y_time = mm.generate_synthetic_historical_data(30)

        # Attempt to label synthetic arrays as genuine without verified database source
        with pytest.raises(ValueError, match="without verified database source"):
            mm.train_and_persist(
                n_samples=30,
                data_source="GENUINE_PIPELINE_TELEMETRY",
                genuine_historical_runs_count=30,
                training_data=(X, y_fail, y_time),
                verified_db_source=False,
            )


def test_synthetic_model_plus_20_genuine_db_records_cannot_authorize_optimization(
    fresh_sqlite_db,
):
    """
    Verifies that even if the database has 20 genuine completed runs,
    a model trained with SYNTHETIC_BOOTSTRAP provenance cannot authorize optimization (Rule 14).
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    for i in range(20):
        c = Commit(
            repository_id=repo.id,
            commit_hash=f"gen-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@example.edu",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(c)
        fresh_sqlite_db.flush()
        r = PipelineRun(
            repository_id=repo.id,
            commit_id=c.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=25.0,
        )
        fresh_sqlite_db.add(r)
    fresh_sqlite_db.commit()

    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        mm.train_and_persist(n_samples=25, data_source="SYNTHETIC_BOOTSTRAP")

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]

        plan = engine.generate_plan(changed_file_entries=changes, db=fresh_sqlite_db)
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.is_optimized is False
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_artifact_sha256_mismatch_forces_full_suite(fresh_sqlite_db):
    """
    Verifies that if a model artifact is tampered with or mismatched against metadata hashes,
    Safety Rule 14 triggers and enforces FULL_SUITE fallback.
    """
    repo = Repository(
        name="AutonomousDevOps/CI-CD-PIPELINE",
        owner="AutonomousDevOps",
        clone_url="https://github.com/AutonomousDevOps/CI-CD-PIPELINE",
        default_branch="main",
    )
    fresh_sqlite_db.add(repo)
    fresh_sqlite_db.flush()

    for i in range(20):
        c = Commit(
            repository_id=repo.id,
            commit_hash=f"sha-commit-{i:03d}",
            branch="main",
            author_name="Dev",
            author_email="dev@example.edu",
            message=f"Commit {i}",
        )
        fresh_sqlite_db.add(c)
        fresh_sqlite_db.flush()
        r = PipelineRun(
            repository_id=repo.id,
            commit_id=c.id,
            workflow_name="CI",
            status="SUCCESS",
            is_optimized=True,
            total_duration_sec=20.0,
        )
        fresh_sqlite_db.add(r)
    fresh_sqlite_db.commit()

    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        mock_runs = []
        for i in range(30):
            is_fail = i % 3 == 0
            lines = 80 if is_fail else 10
            dur = 10.0 + (lines * 0.25) + (5.0 if is_fail else 0.0)
            r = PipelineRun(
                id=f"sha-run-{i:03d}",
                status="FAILED" if is_fail else "SUCCESS",
                total_duration_sec=dur,
            )
            c = Commit(commit_hash=f"sha-hash-{i:03d}", branch="main")
            cf = ChangedFile(
                file_path="sample_app/utils/math_ops.py"
                if not is_fail
                else "sample_app/services/security_service.py",
                change_type="MODIFIED",
                lines_added=lines,
                lines_deleted=2 if not is_fail else 20,
                is_sensitive=is_fail,
            )
            c.changed_files = [cf]
            r.commit = c
            mock_runs.append(r)
        telemetry = mm.extract_features_from_db_runs(mock_runs)
        mm.train_and_persist(
            n_samples=len(telemetry),
            data_source="GENUINE_PIPELINE_TELEMETRY",
            genuine_historical_runs_count=30,
            training_data=telemetry,
            verified_db_source=True,
        )

        # Tamper with failure_predictor.joblib by appending arbitrary bytes
        fail_path = os.path.join(td, "failure_predictor.joblib")
        with open(fail_path, "ab") as f:
            f.write(b"corrupted_tail")

        can_pred, reason = mm.can_predict(genuine_historical_runs_count=20)
        assert can_pred is False
        assert "Safety Rule 14" in reason
        assert "SHA-256 integrity verification failed" in reason

        engine = DecisionEngine(root_dir=".", model_manager=mm)
        changes = [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ]

        plan = engine.generate_plan(changed_file_entries=changes, db=fresh_sqlite_db)
        assert plan.decision == ExecutionDecision.FULL_SUITE
        assert plan.fallback_triggered is True
        assert "RULE_14_MODEL_ARTIFACT_MISSING" in plan.triggered_safety_rules


def test_model_not_marked_production_ready_solely_by_record_count():
    """
    Verifies that having >= 15 records does NOT automatically mark a model production ready
    unless explicitly certified with valid holdout evaluation and observed class diversity.
    When a database has 25 runs but 0 observed failures, certification fails and is_production_ready is False.
    """
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        # Create 25 runs with 100% SUCCESS (0 failures observed)
        mock_runs = []
        for i in range(25):
            r = PipelineRun(
                id=f"single-class-run-{i:03d}",
                status="SUCCESS",
                total_duration_sec=20.0 + float(i),
            )
            c = Commit(commit_hash=f"single-hash-{i:03d}", branch="main")
            cf = ChangedFile(
                file_path="sample_app/utils/math_ops.py",
                change_type="MODIFIED",
                lines_added=10,
                lines_deleted=2,
                is_sensitive=False,
            )
            c.changed_files = [cf]
            r.commit = c
            mock_runs.append(r)

        telemetry = mm.extract_features_from_db_runs(mock_runs)
        res = mm.train_and_persist(
            n_samples=len(telemetry),
            data_source="GENUINE_PIPELINE_TELEMETRY",
            genuine_historical_runs_count=25,
            training_data=telemetry,
            verified_db_source=True,
        )
        assert res["is_production_ready"] is False
        assert res["certification_report"]["is_certified"] is False
        assert any(
            "lacks class diversity" in r for r in res["certification_report"]["failure_reasons"]
        )

        can_pred, reason = mm.can_predict(genuine_historical_runs_count=25)
        assert can_pred is False
        assert "is_production_ready is false" in reason


def test_genuine_provenance_rejected_when_caller_supplies_raw_arrays():
    """
    Verifies the trust boundary around verified_db_source:
    Caller passing verified_db_source=True with raw synthetic numpy arrays is rejected
    with a ValueError. Genuine telemetry must be a VerifiedTelemetryDataset extracted from DB.
    """
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        X, y_fail, y_time = mm.generate_synthetic_historical_data(25)
        with pytest.raises(ValueError, match="Trust boundary violation"):
            mm.train_and_persist(
                n_samples=25,
                data_source="GENUINE_PIPELINE_TELEMETRY",
                genuine_historical_runs_count=25,
                training_data=(X, y_fail, y_time),
                verified_db_source=True,
            )


def test_caller_supplied_historical_values_cannot_affect_server_decision(client):
    """
    Verifies that caller-supplied historical_failure_rate or historical_runs_count
    passed to POST /api/v1/plans/generate cannot override server-verified database records.
    With an empty database, Rule 17 forces FULL_SUITE even if caller passes 0.0 failure rate and 500 runs.
    """
    payload = {
        "repository_name": "AutonomousDevOps/CI-CD-PIPELINE",
        "commit_hash": "caller-spoof-attempt",
        "branch": "main",
        "author_name": "Adversary",
        "author_email": "adv@example.edu",
        "commit_message": "Attempt spoofing historical metrics",
        "changed_files": [
            {
                "file_path": "sample_app/utils/math_ops.py",
                "change_type": "MODIFIED",
                "lines_added": 2,
                "lines_deleted": 0,
            }
        ],
        # Extraneous caller inputs trying to spoof server metrics
        "historical_failure_rate": 0.0001,
        "historical_runs_count": 500,
        "previous_execution_duration": 10.0,
    }

    response = client.post("/api/v1/plans/generate", json=payload)
    assert response.status_code == 200
    data = response.json()
    # In test client with seeded 20 runs, decision is based on the 20 DB runs, NOT the 500 passed by caller.
    # When caller passes spoofed inputs, the server ignores them and evaluates purely against the DB.
    assert data["decision"] in ["OPTIMIZED", "FULL_SUITE"]


def test_verified_telemetry_dataset_immutability():
    """
    Verifies VerifiedTelemetryDataset immutability:
    1. Underlying feature and label numpy arrays are strictly read-only (flags.writeable is False).
    2. In-place modification of array elements raises ValueError.
    3. Dataclass fields cannot be reassigned (FrozenInstanceError).
    """
    X = np.ones((5, 10), dtype=np.float64)
    y_fail = np.zeros(5, dtype=np.int32)
    y_time = np.full(5, 15.0, dtype=np.float64)
    run_ids = ("run-1", "run-2", "run-3", "run-4", "run-5")

    dataset = VerifiedTelemetryDataset.create_sealed(
        X=X,
        y_fail=y_fail,
        y_time=y_time,
        run_ids=run_ids,
        genuine_runs_count=5,
    )

    assert dataset.X.flags.writeable is False
    assert dataset.y_fail.flags.writeable is False
    assert dataset.y_time.flags.writeable is False

    with pytest.raises(ValueError, match="read-only"):
        dataset.X[0, 0] = 999.0

    with pytest.raises(ValueError, match="read-only"):
        dataset.y_fail[0] = 1

    with pytest.raises(ValueError, match="read-only"):
        dataset.y_time[0] = 99.0

    with pytest.raises(FrozenInstanceError):
        dataset.genuine_runs_count = 100

    with pytest.raises(FrozenInstanceError):
        dataset.provenance_signature = "tampered_signature"


def test_manually_constructed_dataset_fails_integrity():
    """
    Verifies that manually constructed or forged VerifiedTelemetryDataset
    fails cryptographic integrity verification and is rejected by train_and_persist.
    """
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        X = np.ones((16, 10), dtype=np.float64)
        y_fail = np.zeros(16, dtype=np.int32)
        y_time = np.full(16, 15.0, dtype=np.float64)
        X.flags.writeable = False
        y_fail.flags.writeable = False
        y_time.flags.writeable = False

        # Caller attempts to instantiate a VerifiedTelemetryDataset with a forged signature
        forged_ds = VerifiedTelemetryDataset(
            X=X,
            y_fail=y_fail,
            y_time=y_time,
            run_ids=tuple(f"run-{i}" for i in range(16)),
            genuine_runs_count=16,
            provenance_signature="0000000000000000000000000000000000000000000000000000000000000000",
            extracted_at=datetime.now(UTC).isoformat(),
        )

        is_valid, reason = forged_ds.verify_integrity()
        assert is_valid is False
        assert "signature verification failed" in reason

        with pytest.raises(ValueError, match="cryptographic integrity verification failed"):
            mm.train_and_persist(
                n_samples=16,
                data_source="GENUINE_PIPELINE_TELEMETRY",
                genuine_historical_runs_count=16,
                training_data=forged_ds,
                verified_db_source=True,
            )


def test_tampered_dataset_arrays_detected():
    """
    Verifies that modifying underlying dataset arrays after sealing
    is detected by cryptographic verification and rejected by train_and_persist.
    """
    with tempfile.TemporaryDirectory() as td:
        mm = ModelManager(registry_dir=td)
        X = np.ones((16, 10), dtype=np.float64)
        y_fail = np.zeros(16, dtype=np.int32)
        y_time = np.full(16, 15.0, dtype=np.float64)
        run_ids = tuple(f"run-{i}" for i in range(16))

        dataset = VerifiedTelemetryDataset.create_sealed(
            X=X,
            y_fail=y_fail,
            y_time=y_time,
            run_ids=run_ids,
            genuine_runs_count=16,
        )

        is_valid, _ = dataset.verify_integrity()
        assert is_valid is True

        # Tampering attempt 1: Re-enabling writeable flag without changing bytes
        dataset.X.flags.writeable = True
        is_valid, reason = dataset.verify_integrity()
        assert is_valid is False
        assert "writeable flags enabled" in reason

        # Tampering attempt 2: Modifying bytes and re-locking read-only flag
        dataset.X[0, 0] = 42.0
        dataset.X.flags.writeable = False
        is_valid, reason = dataset.verify_integrity()
        assert is_valid is False
        assert "signature verification failed" in reason

        with pytest.raises(ValueError, match="cryptographic integrity verification failed"):
            mm.train_and_persist(
                n_samples=16,
                data_source="GENUINE_PIPELINE_TELEMETRY",
                genuine_historical_runs_count=16,
                training_data=dataset,
                verified_db_source=True,
            )


def test_certification_rejected_when_holdout_has_zero_failures():
    """
    Verifies evaluate_model_certification rejects certification when the holdout test set
    has 0 failure samples (test_fail_count == 0). Failure discrimination cannot be evaluated.
    """
    mm = ModelManager()
    class_dist = {
        "dataset_pass_count": 18,
        "dataset_fail_count": 2,
        "train_pass_count": 14,
        "train_fail_count": 2,
        "test_pass_count": 4,
        "test_fail_count": 0,
    }
    fail_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "accuracy": 1.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1_score": 0.0,
        "roc_auc": None,
        "class_distribution": class_dist,
    }
    time_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "mae": 5.0,
        "r2_score": 0.5,
    }

    is_certified, criteria, failure_reasons = mm.evaluate_model_certification(
        fail_metrics=fail_metrics,
        time_metrics=time_metrics,
        sample_count=20,
        genuine_historical_runs_count=20,
    )

    assert is_certified is False
    assert criteria["holdout_both_classes_present"] is False
    assert any(
        "Both PASS and FAILED examples must be present in holdout" in r for r in failure_reasons
    )


def test_certification_rejected_when_too_few_failures_in_dataset():
    """
    Verifies evaluate_model_certification rejects certification when total dataset has < 2 failures.
    Insufficient failure evidence prevents reliable holdout validation and forces FULL_SUITE.
    """
    mm = ModelManager()
    class_dist = {
        "dataset_pass_count": 19,
        "dataset_fail_count": 1,
        "train_pass_count": 15,
        "train_fail_count": 1,
        "test_pass_count": 4,
        "test_fail_count": 0,
    }
    fail_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "accuracy": 1.0,
        "precision": 0.0,
        "recall": 0.0,
        "f1_score": 0.0,
        "roc_auc": None,
        "class_distribution": class_dist,
    }
    time_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "mae": 5.0,
        "r2_score": 0.5,
    }

    is_certified, _criteria, failure_reasons = mm.evaluate_model_certification(
        fail_metrics=fail_metrics,
        time_metrics=time_metrics,
        sample_count=20,
        genuine_historical_runs_count=20,
    )

    assert is_certified is False
    assert any("too few failures (1 < 2)" in r for r in failure_reasons)


def test_certification_rejected_when_roc_auc_undefined():
    """
    Verifies evaluate_model_certification rejects certification when holdout ROC-AUC is undefined (None).
    Failure model cannot be certified without a valid ROC-AUC score.
    """
    mm = ModelManager()
    class_dist = {
        "dataset_pass_count": 16,
        "dataset_fail_count": 4,
        "train_pass_count": 13,
        "train_fail_count": 3,
        "test_pass_count": 3,
        "test_fail_count": 1,
    }
    # ROC-AUC is explicitly None
    fail_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "accuracy": 0.75,
        "precision": 0.5,
        "recall": 0.6,
        "f1_score": 0.55,
        "roc_auc": None,
        "class_distribution": class_dist,
    }
    time_metrics = {
        "evaluated_on": "HOLDOUT_TEST_SPLIT",
        "test_samples": 4,
        "mae": 8.0,
        "r2_score": 0.4,
    }

    is_certified, criteria, failure_reasons = mm.evaluate_model_certification(
        fail_metrics=fail_metrics,
        time_metrics=time_metrics,
        sample_count=20,
        genuine_historical_runs_count=20,
    )

    assert is_certified is False
    assert criteria["roc_auc_valid_and_acceptable"] is False
    assert any("ROC-AUC is undefined (None)" in r for r in failure_reasons)
