"""
Leakage-Safe Feature Extraction Engine.
Extracts numerical and categorical features strictly available BEFORE pipeline execution.
Never incorporates post-execution metrics (current duration, current pass/fail) into feature vectors.
"""

from dataclasses import asdict, dataclass
from typing import Any, ClassVar

import numpy as np


@dataclass
class PipelineFeatures:
    """Pre-execution feature vector for ML model inference."""

    changed_files_count: int
    lines_added: int
    lines_deleted: int
    total_lines_changed: int
    affected_modules_count: int
    selected_tests_count: int
    is_sensitive_change: int  # 0 or 1
    has_test_file_changes: int  # 0 or 1
    historical_failure_rate: float  # Historical failure rate of repository (0.0 to 1.0)
    previous_execution_duration: float  # Duration of most recent completed run in seconds

    def to_array(self) -> np.ndarray:
        """Converts feature object to 2D numpy array suitable for scikit-learn models."""
        return np.array(
            [
                self.changed_files_count,
                self.lines_added,
                self.lines_deleted,
                self.total_lines_changed,
                self.affected_modules_count,
                self.selected_tests_count,
                self.is_sensitive_change,
                self.has_test_file_changes,
                self.historical_failure_rate,
                self.previous_execution_duration,
            ],
            dtype=np.float64,
        ).reshape(1, -1)

    def to_travistorrent_array(
        self, branch: str = "main", build_number: int | None = None
    ) -> np.ndarray:
        """
        Maps pre-execution git commit and telemetry features into the standardized 10-feature
        vector expected by the trained Travis CI models:
        [build_number, prior_build_count, previous_failure, previous_duration_sec,
         historical_failure_rate, rolling_fail_rate_5, rolling_duration_avg_5,
         is_pull_request, is_master_branch, prior_test_count]
        """
        b_num = float(build_number or max(10, self.changed_files_count * 5 + 50))
        prior_b = max(1.0, b_num - 1.0)
        prev_fail = 1.0 if self.historical_failure_rate >= 0.50 else 0.0
        prev_dur = max(1.0, float(self.previous_execution_duration))
        hist_fail = float(self.historical_failure_rate)
        roll_fail = hist_fail
        roll_dur = prev_dur
        is_pr = 0.0 if branch.lower() in ("main", "master") else 1.0
        is_master = 1.0 if branch.lower() in ("main", "master") else 0.0
        prior_tests = float(self.selected_tests_count)

        return np.array(
            [
                b_num,
                prior_b,
                prev_fail,
                prev_dur,
                hist_fail,
                roll_fail,
                roll_dur,
                is_pr,
                is_master,
                prior_tests,
            ],
            dtype=np.float64,
        ).reshape(1, -1)

    def to_dict(self) -> dict[str, Any]:
        """Converts features to JSON-serializable dictionary."""
        return asdict(self)


class FeatureExtractor:
    """
    Extracts reproducible, standardized features from commit metadata,
    dependency mapping results, and repository historical records.
    """

    FEATURE_NAMES: ClassVar[list[str]] = [
        "changed_files_count",
        "lines_added",
        "lines_deleted",
        "total_lines_changed",
        "affected_modules_count",
        "selected_tests_count",
        "is_sensitive_change",
        "has_test_file_changes",
        "historical_failure_rate",
        "previous_execution_duration",
    ]

    @classmethod
    def extract_features(
        cls,
        changed_files_count: int,
        lines_added: int,
        lines_deleted: int,
        affected_modules_count: int,
        selected_tests_count: int,
        is_sensitive_change: bool = False,
        has_test_file_changes: bool = False,
        historical_failure_rate: float = 0.05,
        previous_execution_duration: float = 30.0,
    ) -> PipelineFeatures:
        """
        Creates a validated PipelineFeatures instance ensuring proper numeric bounds.
        """
        total_lines = max(0, lines_added + lines_deleted)
        bounded_failure_rate = max(0.0, min(1.0, float(historical_failure_rate)))
        bounded_duration = max(1.0, float(previous_execution_duration))

        return PipelineFeatures(
            changed_files_count=max(0, int(changed_files_count)),
            lines_added=max(0, int(lines_added)),
            lines_deleted=max(0, int(lines_deleted)),
            total_lines_changed=total_lines,
            affected_modules_count=max(0, int(affected_modules_count)),
            selected_tests_count=max(0, int(selected_tests_count)),
            is_sensitive_change=1 if is_sensitive_change else 0,
            has_test_file_changes=1 if has_test_file_changes else 0,
            historical_failure_rate=round(bounded_failure_rate, 4),
            previous_execution_duration=round(bounded_duration, 2),
        )

    @classmethod
    def extract(cls, *args, **kwargs) -> PipelineFeatures:
        """Convenience alias for extract_features."""
        return cls.extract_features(*args, **kwargs)
