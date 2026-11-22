"""Mathematical operations and statistical calculations."""

from typing import List, Union, Optional
import math


def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """Returns the sum of two numbers."""
    return a + b


def subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """Returns the difference of two numbers."""
    return a - b


def multiply(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """Returns the product of two numbers."""
    return a * b


def divide(a: Union[int, float], b: Union[int, float]) -> float:
    """Returns the quotient of two numbers. Raises ValueError on division by zero."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return float(a) / float(b)


def compute_average(values: List[float]) -> float:
    """Computes the arithmetic mean of a list of floats."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def compute_standard_deviation(values: List[float]) -> float:
    """Computes sample standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = compute_average(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)
