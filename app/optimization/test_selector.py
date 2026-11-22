"""
Test Selector & Command Generator.
Translates selected test identifiers into structured execution commands and computes
test reduction telemetry.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import shlex


@dataclass
class SelectedTestPlan:
    __test__ = False  # Prevent Pytest collection
    selected_test_identifiers: List[str]
    selected_test_files: List[str]
    pytest_command_args: List[str]
    pytest_command_string: str
    total_tests_count: int
    selected_tests_count: int
    skipped_tests_count: int
    reduction_percentage: float


class TestSelector:
    __test__ = False  # Prevent Pytest collection
    """
    Selects, deduplicates, and formats tests for execution in CI/CD runner.
    Computes exact reduction percentage against the complete repository test suite.
    """

    def __init__(self, default_pytest_flags: Optional[List[str]] = None):
        self.default_flags = default_pytest_flags or ["-v", "--tb=short"]

    def calculate_reduction(self, total_tests: int, selected_tests: int) -> float:
        """Computes test suite reduction percentage safely avoiding division by zero."""
        if total_tests <= 0:
            return 0.0
        reduction = ((total_tests - selected_tests) / total_tests) * 100.0
        return max(0.0, min(100.0, round(reduction, 2)))

    def build_test_plan(
        self,
        selected_identifiers: List[str],
        all_repository_tests: List[str],
        force_full_suite: bool = False,
    ) -> SelectedTestPlan:
        """
        Builds a SelectedTestPlan based on test identifiers and safety mode.
        If force_full_suite is True, selects all repository tests.
        """
        total_count = len(all_repository_tests)

        if force_full_suite or not selected_identifiers:
            chosen = list(all_repository_tests)
        else:
            # Preserve order while removing duplicates
            seen = set()
            chosen = []
            for t in selected_identifiers:
                if t not in seen:
                    seen.add(t)
                    chosen.append(t)

        selected_count = len(chosen)
        skipped_count = max(0, total_count - selected_count)
        reduction_pct = self.calculate_reduction(total_count, selected_count)

        # Extract unique test files
        files_set = set()
        for item in chosen:
            file_part = item.split("::")[0]
            files_set.add(file_part)
        selected_files = sorted(list(files_set))

        # Build pytest command arguments
        pytest_args = ["-m", "pytest"] + self.default_flags
        if force_full_suite and not selected_identifiers:
            # Run test directory defaults
            pytest_args.extend(["tests/", "tests_sample_app/"])
        else:
            pytest_args.extend(chosen)

        # Build command string
        quoted_args = [shlex.quote(arg) for arg in pytest_args]
        pytest_command_str = "python " + " ".join(quoted_args)

        return SelectedTestPlan(
            selected_test_identifiers=chosen,
            selected_test_files=selected_files,
            pytest_command_args=pytest_args,
            pytest_command_string=pytest_command_str,
            total_tests_count=total_count,
            selected_tests_count=selected_count,
            skipped_tests_count=skipped_count,
            reduction_percentage=reduction_pct,
        )
