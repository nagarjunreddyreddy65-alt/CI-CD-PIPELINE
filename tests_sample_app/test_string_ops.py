"""Unit tests for sample_app.utils.string_ops."""

from sample_app.utils.string_ops import sanitize_string, slugify, truncate


def test_sanitize_string():
    assert sanitize_string("  hello world  \n") == "hello world"
    assert sanitize_string("") == ""


def test_slugify():
    assert slugify("Autonomous DevOps 2026!") == "autonomous-devops-2026"
    assert slugify("AI & Machine Learning") == "ai-machine-learning"


def test_truncate():
    assert truncate("Short string", 20) == "Short string"
    assert truncate("This is a very long string that needs truncation", 15) == "This is a ve..."
