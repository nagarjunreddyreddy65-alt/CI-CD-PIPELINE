"""
SQLAlchemy Relational Entities for Autonomous DevOps.
Implements the complete schema specified in Part 6 of the project architecture:
- users
- repositories
- commits
- pipeline_runs
- changed_files
- test_cases
- test_results
- predictions
- execution_plans
- telemetry
- model_versions
- security_scans
- deployments
- audit_logs
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database.session import Base


def utc_now() -> datetime:
    """Returns the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def generate_uuid() -> str:
    """Generates a standard 36-character UUID string."""
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="developer", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(200), nullable=False, index=True)
    owner = Column(String(100), nullable=False, index=True)
    clone_url = Column(String(500), nullable=False)
    default_branch = Column(String(100), default="main", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    commits = relationship("Commit", back_populates="repository", cascade="all, delete-orphan")
    pipeline_runs = relationship(
        "PipelineRun", back_populates="repository", cascade="all, delete-orphan"
    )


class Commit(Base):
    __tablename__ = "commits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commit_hash = Column(String(40), nullable=False, index=True)
    branch = Column(String(100), default="main", nullable=False)
    author_name = Column(String(150), nullable=False)
    author_email = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    repository = relationship("Repository", back_populates="commits")
    changed_files = relationship(
        "ChangedFile", back_populates="commit", cascade="all, delete-orphan"
    )
    pipeline_runs = relationship("PipelineRun", back_populates="commit")

    __table_args__ = (Index("idx_repo_commit", "repository_id", "commit_hash", unique=True),)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commit_id = Column(
        String(36), ForeignKey("commits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_name = Column(String(150), default="CI Pipeline", nullable=False)
    status = Column(
        String(50), default="PENDING", nullable=False, index=True
    )  # PENDING, RUNNING, SUCCESS, FAILED, CANCELLED
    trigger_event = Column(String(50), default="push", nullable=False)  # push, pull_request, manual
    is_optimized = Column(Boolean, default=False, nullable=False)
    fallback_triggered = Column(Boolean, default=False, nullable=False)
    fallback_reason = Column(String(255), nullable=True)
    total_duration_sec = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    repository = relationship("Repository", back_populates="pipeline_runs")
    commit = relationship("Commit", back_populates="pipeline_runs")
    execution_plan = relationship(
        "ExecutionPlan", back_populates="pipeline_run", uselist=False, cascade="all, delete-orphan"
    )
    test_results = relationship(
        "TestResult", back_populates="pipeline_run", cascade="all, delete-orphan"
    )
    predictions = relationship(
        "Prediction", back_populates="pipeline_run", cascade="all, delete-orphan"
    )
    telemetry = relationship(
        "Telemetry", back_populates="pipeline_run", uselist=False, cascade="all, delete-orphan"
    )
    security_scans = relationship(
        "SecurityScan", back_populates="pipeline_run", cascade="all, delete-orphan"
    )


class ChangedFile(Base):
    __tablename__ = "changed_files"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    commit_id = Column(
        String(36), ForeignKey("commits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path = Column(String(500), nullable=False, index=True)
    change_type = Column(String(20), nullable=False)  # ADDED, MODIFIED, DELETED, RENAMED
    lines_added = Column(Integer, default=0, nullable=False)
    lines_deleted = Column(Integer, default=0, nullable=False)
    is_sensitive = Column(Boolean, default=False, nullable=False)

    commit = relationship("Commit", back_populates="changed_files")


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # Prevent Pytest from treating this ORM model as a test suite

    id = Column(String(36), primary_key=True, default=generate_uuid)
    repository_id = Column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_identifier = Column(
        String(500), nullable=False, index=True
    )  # e.g., tests/test_auth.py::test_login
    file_path = Column(String(500), nullable=False, index=True)
    function_name = Column(String(200), nullable=False)
    is_flaky = Column(Boolean, default=False, nullable=False)
    average_duration_ms = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    test_results = relationship("TestResult", back_populates="test_case")


class TestResult(Base):
    __tablename__ = "test_results"
    __test__ = False  # Prevent Pytest from treating this ORM model as a test suite

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_case_id = Column(
        String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(String(20), nullable=False)  # PASSED, FAILED, SKIPPED, ERROR
    duration_ms = Column(Float, default=0.0, nullable=False)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    pipeline_run = relationship("PipelineRun", back_populates="test_results")
    test_case = relationship("TestCase", back_populates="test_results")


class ExecutionPlan(Base):
    __tablename__ = "execution_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    decision = Column(String(50), nullable=False)  # OPTIMIZED, FULL_SUITE
    decision_reason = Column(Text, nullable=False)
    selected_tests_count = Column(Integer, default=0, nullable=False)
    total_tests_count = Column(Integer, default=0, nullable=False)
    tests_reduction_pct = Column(Float, default=0.0, nullable=False)
    selected_tests_json = Column(Text, nullable=False)  # JSON serialized list of test identifiers
    safety_rule_triggered = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    pipeline_run = relationship("PipelineRun", back_populates="execution_plan")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version = Column(String(50), nullable=False)
    predicted_failure_probability = Column(Float, nullable=False)
    predicted_failure_class = Column(Integer, nullable=False)  # 0: Pass, 1: Fail
    predicted_duration_sec = Column(Float, nullable=False)
    features_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    pipeline_run = relationship("PipelineRun", back_populates="predictions")


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    cpu_percent_avg = Column(Float, default=0.0, nullable=False)
    memory_mb_peak = Column(Float, default=0.0, nullable=False)
    disk_io_mb = Column(Float, default=0.0, nullable=False)
    runner_os = Column(String(100), default="Ubuntu-Latest", nullable=False)
    collected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    pipeline_run = relationship("PipelineRun", back_populates="telemetry")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    model_name = Column(String(100), nullable=False)  # failure_classifier, runtime_regressor
    version = Column(String(50), nullable=False, index=True)
    algorithm = Column(String(100), nullable=False)  # RandomForestClassifier, RandomForestRegressor
    accuracy = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    mae = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    artifact_path = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class SecurityScan(Base):
    __tablename__ = "security_scans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name = Column(String(50), nullable=False)  # Bandit, pip-audit, Gitleaks
    status = Column(String(20), nullable=False)  # PASSED, FAILED, WARNING
    highest_severity = Column(
        String(20), default="NONE", nullable=False
    )  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    findings_count = Column(Integer, default=0, nullable=False)
    summary = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    pipeline_run = relationship("PipelineRun", back_populates="security_scans")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_run_id = Column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment = Column(String(50), default="staging", nullable=False)
    status = Column(String(50), default="PENDING", nullable=False)
    deployed_by = Column(String(100), default="system", nullable=False)
    approved_by = Column(String(100), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    event_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    details = Column(Text, nullable=False)
    performed_by = Column(String(100), default="system", nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
