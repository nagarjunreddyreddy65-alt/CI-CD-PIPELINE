"""
Unit tests for ASTDependencyAnalyzer.
Verifies AST parsing, dynamic import detection, and NetworkX dependency graph traversal.
"""

import os
import tempfile

import pytest

from app.analysis.dependency_analyzer import ASTDependencyAnalyzer


@pytest.fixture
def analyzer():
    return ASTDependencyAnalyzer(root_dir=os.getcwd())


def test_parse_valid_python_imports(analyzer):
    code = """
import os
import sys
from sample_app.utils import math_ops
from sample_app.analytics.metrics_calculator import calculate_percentiles as calc_p
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        imports, dynamic = analyzer.parse_python_file(temp_path, "temp_mod")
        assert "os" in imports
        assert "sys" in imports
        assert "sample_app.utils.math_ops" in imports
        assert len(dynamic) == 0
    finally:
        os.remove(temp_path)


def test_detect_dynamic_imports(analyzer):
    code = """
import os
mod = __import__('dynamic_module')
eval('print(123)')
import importlib
dyn = importlib.import_module('secret_module')
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        _imports, dynamic = analyzer.parse_python_file(temp_path, "dyn_mod")
        assert len(dynamic) == 3
        types = [d["type"] for d in dynamic]
        assert "__import__" in types
        assert "eval" in types
        assert "importlib.import_module" in types
    finally:
        os.remove(temp_path)


def test_syntax_error_handling(analyzer):
    bad_code = "def invalid_syntax(:"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(bad_code)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Syntax error"):
            analyzer.parse_python_file(temp_path, "bad_mod")
    finally:
        os.remove(temp_path)


def test_networkx_graph_construction(analyzer):
    graph = analyzer.build_graph(target_dirs=["sample_app", "tests_sample_app"])

    assert graph.graph.number_of_nodes() > 5
    assert graph.graph.number_of_edges() > 0

    # sample_app.analytics.metrics_calculator imports sample_app.utils.math_ops
    # When math_ops changes, dependents must include metrics_calculator!
    dependents = graph.get_dependents("sample_app.utils.math_ops")
    assert "sample_app.analytics.metrics_calculator" in dependents
