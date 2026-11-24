"""
Unit Tests for Test Selector and Reduction Telemetry.
"""

from app.optimization.test_selector import SelectedTestPlan, TestSelector


def test_reduction_percentage_calculation():
    """Verifies reduction calculation across full-suite, optimized, zero-test, and invalid-count scenarios."""
    selector = TestSelector()
    # Optimized scenarios
    assert selector.calculate_reduction(100, 20) == 80.0
    assert selector.calculate_reduction(141, 9) == 93.62
    assert selector.calculate_reduction(10, 0) == 100.0

    # Full-suite scenarios (no reduction)
    assert selector.calculate_reduction(50, 50) == 0.0
    assert selector.calculate_reduction(141, 141) == 0.0

    # Zero-test scenarios safely handled
    assert selector.calculate_reduction(0, 0) == 0.0
    assert selector.calculate_reduction(0, 5) == 0.0

    # Invalid-count scenarios safely handled
    assert selector.calculate_reduction(-10, 5) == 0.0
    assert selector.calculate_reduction(100, -5) == 0.0
    assert selector.calculate_reduction(50, 60) == 0.0


def test_build_test_plan_optimized():
    selector = TestSelector()
    all_tests = [
        "tests_sample_app/test_math_ops.py::test_addition",
        "tests_sample_app/test_math_ops.py::test_subtraction",
        "tests_sample_app/test_string_ops.py::test_slugify",
        "tests_sample_app/test_user_service.py::test_register_user_success",
    ]
    selected = [
        "tests_sample_app/test_math_ops.py::test_addition",
        "tests_sample_app/test_math_ops.py::test_subtraction",
    ]

    plan: SelectedTestPlan = selector.build_test_plan(
        selected_identifiers=selected,
        all_repository_tests=all_tests,
        force_full_suite=False,
    )

    assert plan.total_tests_count == 4
    assert plan.selected_tests_count == 2
    assert plan.skipped_tests_count == 2
    assert plan.reduction_percentage == 50.0
    assert plan.selected_test_files == ["tests_sample_app/test_math_ops.py"]
    assert "pytest" in plan.pytest_command_string
    assert "test_addition" in plan.pytest_command_string


def test_build_test_plan_force_full_suite():
    selector = TestSelector()
    all_tests = [
        "tests_sample_app/test_math_ops.py::test_addition",
        "tests_sample_app/test_string_ops.py::test_slugify",
    ]

    plan: SelectedTestPlan = selector.build_test_plan(
        selected_identifiers=["tests_sample_app/test_math_ops.py::test_addition"],
        all_repository_tests=all_tests,
        force_full_suite=True,
    )

    assert plan.total_tests_count == 2
    assert plan.selected_tests_count == 2
    assert plan.reduction_percentage == 0.0
