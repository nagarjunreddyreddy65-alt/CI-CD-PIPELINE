"""Mathematical operations and statistical calculations."""

import math


def add(a: float, b: float) -> int | float:
    """Returns the sum of two numbers."""
    return a + b


def subtract(a: float, b: float) -> int | float:
    """Returns the difference of two numbers."""
    return a - b


def multiply(a: float, b: float) -> int | float:
    """Returns the product of two numbers."""
    return a * b


def divide(a: float, b: float) -> float:
    """Returns the quotient of two numbers. Raises ValueError on division by zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return float(a) / float(b)


def compute_average(values: list[float]) -> float:
    """Computes the arithmetic mean of a list of floats."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def compute_standard_deviation(values: list[float]) -> float:
    """Computes sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = compute_average(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)
