"""Unit tests for sample_app.utils.math_ops."""

import pytest
from sample_app.utils.math_ops import (
    add,
    subtract,
    multiply,
    divide,
    compute_average,
    compute_standard_deviation,
)


def test_addition():
    assert add(10, 5) == 15
    assert add(-3, 3) == 0
    assert add(2.5, 3.5) == 6.0


def test_subtraction():
    assert subtract(10, 4) == 6
    assert subtract(5, 10) == -5


def test_multiplication():
    assert multiply(3, 4) == 12
    assert multiply(0, 100) == 0


def test_division():
    assert divide(10, 2) == 5.0
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(10, 0)


def test_compute_average():
    assert compute_average([10.0, 20.0, 30.0]) == 20.0
    assert compute_average([]) == 0.0


def test_compute_standard_deviation():
    assert compute_standard_deviation([10.0]) == 0.0
    std = compute_standard_deviation([10.0, 20.0, 30.0])
    assert round(std, 2) == 10.0
