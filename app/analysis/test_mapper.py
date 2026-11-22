"""
Test Dependency Mapper.
Translates code change events and AST dependency graphs into affected test execution plans.
Governed by the safety principle:
"When dependencies cannot be verified safely, full-suite fallback is triggered."
"""

import ast
import os
from dataclasses import dataclass, field
from typing import Any

from app.analysis.change_analyzer import ChangeAnalysisResult, ChangeAnalyzer
from app.analysis.dependency_analyzer import ASTDependencyAnalyzer, DependencyGraph


@dataclass
class TestMappingResult:
    __test__ = False  # Prevent Pytest collection
    """Output plan from mapping changed files through the AST dependency graph."""
    changed_modules: list[str]
    affected_modules: list[str]
    affected_test_files: list[str]
    affected_test_identifiers: list[str]
    fallback_required: bool
    fallback_reason: str | None
    triggered_safety_rules: list[str] = field(default_factory=list)
    total_repository_tests: int = 0
    selected_tests_count: int = 0
    estimated_test_reduction_pct: float = 0.0


class TestDependencyMapper:
    __test__ = False  # Prevent Pytest collection

    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        self.change_analyzer = ChangeAnalyzer(root_dir)
        self.dep_analyzer = ASTDependencyAnalyzer(root_dir)

    def discover_all_test_functions(self, test_dirs: list[str] | None = None) -> list[str]:
        """
        Discovers all test function and class method identifiers
        (e.g. tests_sample_app/test_math.py::test_addition or tests/test_foo.py::TestClass::test_method).
        Handles:
        - Standalone functions (def test_...)
        - Async test functions (async def test_...)
        - Test classes (class Test...: def test_...)
        - Alternate test naming (test_*.py and *_test.py)
        - Ignores nested helpers inside test functions.
        - Deduplicates test identifiers.
        """
        test_dirs = test_dirs or ["tests", "tests_sample_app"]
        identifiers: list[str] = []
        seen: set[str] = set()

        for folder in test_dirs:
            full_folder = os.path.join(self.root_dir, folder)
            if not os.path.exists(full_folder):
                continue

            for root, _, files in os.walk(full_folder):
                for file in files:
                    if (file.startswith("test_") or file.endswith("_test.py")) and file.endswith(
                        ".py"
                    ):
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, self.root_dir).replace("\\", "/")
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                                tree = ast.parse(f.read(), filename=file_path)

                            for node in tree.body:
                                if isinstance(
                                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                                ) and node.name.startswith("test_"):
                                    ident = f"{rel_path}::{node.name}"
                                    if ident not in seen:
                                        seen.add(ident)
                                        identifiers.append(ident)
                                elif isinstance(node, ast.ClassDef) and (
                                    node.name.startswith("Test")
                                    or node.name.endswith("Test")
                                    or node.name.endswith("Tests")
                                ):
                                    for class_item in node.body:
                                        if isinstance(
                                            class_item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                        ) and class_item.name.startswith("test_"):
                                            ident = f"{rel_path}::{node.name}::{class_item.name}"
                                            if ident not in seen:
                                                seen.add(ident)
                                                identifiers.append(ident)
                        except (SyntaxError, OSError, ValueError):
                            if rel_path not in seen:
                                seen.add(rel_path)
                                identifiers.append(rel_path)

        return sorted(identifiers)

    def map_changes_to_tests(
        self,
        changed_file_entries: list[dict[str, Any]],
        dependency_graph: DependencyGraph | None = None,
    ) -> TestMappingResult:
        """
        Main mapping algorithm:
        1. Classifies file changes for safety sensitivity.
        2. Builds or inspects AST dependency graph.
        3. Identifies impacted modules and downstream tests.
        4. Validates safety constraints; falls back if unresolvable.
        """
        # Step 1: Change Analysis
        change_result: ChangeAnalysisResult = self.change_analyzer.analyze_changes(
            changed_file_entries
        )
        all_repo_tests = self.discover_all_test_functions()
        total_tests = len(all_repo_tests)

        safety_triggers: list[str] = list(change_result.sensitive_triggers)

        # Check Part 5 Safety Fallback triggers from file paths
        if change_result.has_migration_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 1: Database migration or schema modification detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_auth_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 2: Authentication or authorization changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_payment_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 3: Payment or billing code changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_crypto_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 4: Cryptographic or security-sensitive code changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_dependency_manifest_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 5: Dependency manifest changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_lock_file_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 6: Lock-file changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_ci_workflow_changes:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 7: CI/CD workflow or build configuration changes detected",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        if change_result.has_unsupported_files:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 8: Unknown or unsupported file types changed",
                triggered_safety_rules=safety_triggers,
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        # Step 2: Build / Query AST Dependency Graph
        graph = dependency_graph or self.dep_analyzer.build_graph()

        # Safety Rule 9: AST parsing failures
        if graph.parsing_errors:
            error_mods = list(graph.parsing_errors.keys())
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason=f"Safety Rule 9: AST parsing failure in {error_mods}",
                triggered_safety_rules=["AST_PARSING_FAILURE"],
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        # Safety Rule 10: Dynamic imports detected
        if graph.dynamic_imports_detected:
            dyn_mods = list(graph.dynamic_imports_detected.keys())
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason=f"Safety Rule 10: Unresolved dynamic imports in {dyn_mods}",
                triggered_safety_rules=["DYNAMIC_IMPORTS_DETECTED"],
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        # Safety Rule 11: Circular or disconnected dependency graph
        cycles = graph.find_cycles()
        if cycles:
            return TestMappingResult(
                changed_modules=[],
                affected_modules=[],
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason=f"Safety Rule 11: Circular dependency detected in graph: {cycles}",
                triggered_safety_rules=["RULE_11_CIRCULAR_OR_DISCONNECTED"],
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        # Step 3: Traverse Graph to find affected modules
        changed_modules: list[str] = [
            self.dep_analyzer._file_path_to_module(f) for f in change_result.python_files
        ]
        affected_modules: set[str] = set(changed_modules)

        for mod in changed_modules:
            dependents = graph.get_dependents(mod)
            affected_modules.update(dependents)

        # Step 4: Extract test files from affected modules
        affected_test_files: set[str] = set()
        for mod in affected_modules:
            node_data = graph.graph.nodes.get(mod, {})
            f_path = node_data.get("file_path", "")
            if f_path:
                rel = os.path.relpath(f_path, self.root_dir).replace("\\", "/")
                if (
                    rel.startswith(("tests/", "tests_"))
                    or "/tests/" in rel
                    or rel.endswith("_test.py")
                ):
                    affected_test_files.add(rel)

        # Also add directly changed test files
        for tf in change_result.test_files_changed:
            affected_test_files.add(tf)

        # Step 5: Filter specific test identifiers
        selected_identifiers: list[str] = [
            t_id
            for t_id in all_repo_tests
            if any(t_id.startswith(tf) for tf in affected_test_files)
        ]

        # Safety Rule 12: Changed code has no identified or mapped test cases
        unmapped_modules: list[str] = []
        for mod in changed_modules:
            node_data = graph.graph.nodes.get(mod, {})
            f_path = node_data.get("file_path", "")
            rel = os.path.relpath(f_path, self.root_dir).replace("\\", "/") if f_path else ""
            is_test_file = (
                rel.startswith(("tests/", "tests_"))
                or "/tests/" in rel
                or rel.endswith("_test.py")
                or os.path.basename(rel).startswith("test_")
            )
            if not is_test_file:
                mod_deps = graph.get_dependents(mod) | {mod}
                mod_has_test = any(
                    any(
                        (
                            graph.graph.nodes.get(dep, {}).get("file_path", "")
                            and os.path.relpath(
                                graph.graph.nodes[dep]["file_path"], self.root_dir
                            ).replace("\\", "/")
                            in t
                        )
                        for dep in mod_deps
                    )
                    for t in all_repo_tests
                )
                if not mod_has_test:
                    unmapped_modules.append(mod)

        if unmapped_modules:
            return TestMappingResult(
                changed_modules=changed_modules,
                affected_modules=sorted(affected_modules),
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason=f"Safety Rule 12: Changed code has no identified or mapped test cases for {unmapped_modules}",
                triggered_safety_rules=["RULE_12_UNMAPPED_TESTS"],
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        # Safety Rule 13: Empty selected test list when files changed
        if not selected_identifiers and change_result.total_files_changed > 0:
            return TestMappingResult(
                changed_modules=changed_modules,
                affected_modules=sorted(affected_modules),
                affected_test_files=[],
                affected_test_identifiers=all_repo_tests,
                fallback_required=True,
                fallback_reason="Safety Rule 13: Empty selected test list detected; falling back to full suite",
                triggered_safety_rules=["EMPTY_SELECTED_TEST_LIST"],
                total_repository_tests=total_tests,
                selected_tests_count=total_tests,
                estimated_test_reduction_pct=0.0,
            )

        reduction_pct = 0.0
        if total_tests > 0:
            reduction_pct = round(
                ((total_tests - len(selected_identifiers)) / total_tests) * 100.0, 1
            )

        return TestMappingResult(
            changed_modules=changed_modules,
            affected_modules=sorted(affected_modules),
            affected_test_files=sorted(affected_test_files),
            affected_test_identifiers=sorted(selected_identifiers),
            fallback_required=False,
            fallback_reason=None,
            triggered_safety_rules=[],
            total_repository_tests=total_tests,
            selected_tests_count=len(selected_identifiers),
            estimated_test_reduction_pct=reduction_pct,
        )
