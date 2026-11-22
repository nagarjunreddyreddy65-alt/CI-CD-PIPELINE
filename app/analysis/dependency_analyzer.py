"""
Python AST Dependency Analyzer.
Parses Python source code into Abstract Syntax Trees (AST), extracts static and dynamic imports,
and constructs a directed dependency graph using NetworkX.
"""

import ast
import os
from typing import Any

import networkx as nx

from app.core.logging import logger


class DynamicImportDetector(ast.NodeVisitor):
    """Detects unresolvable dynamic imports and dynamic evaluation constructs."""

    def __init__(self):
        self.dynamic_imports: list[dict[str, Any]] = []
        self.importlib_aliases: set[str] = {"importlib"}
        self.import_module_aliases: set[str] = {"import_module"}

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name == "importlib":
                self.importlib_aliases.add(alias.asname or "importlib")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    self.import_module_aliases.add(alias.asname or "import_module")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 1. Detect __import__(...)
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.dynamic_imports.append(
                {
                    "type": "__import__",
                    "line": node.lineno,
                    "reason": "Direct call to __import__()",
                }
            )
        # 2. Detect eval(...) or exec(...)
        elif isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self.dynamic_imports.append(
                {
                    "type": node.func.id,
                    "line": node.lineno,
                    "reason": f"Dynamic evaluation via {node.func.id}()",
                }
            )
        # 3. Detect importlib.import_module(...) or aliased_importlib.import_module(...)
        elif (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.importlib_aliases
            and node.func.attr == "import_module"
        ):
            self.dynamic_imports.append(
                {
                    "type": "importlib.import_module",
                    "line": node.lineno,
                    "reason": f"Dynamic module loading via {node.func.value.id}.import_module()",
                }
            )
        # 4. Detect direct or aliased call to import_module(...)
        elif isinstance(node.func, ast.Name) and node.func.id in self.import_module_aliases:
            self.dynamic_imports.append(
                {
                    "type": "importlib.import_module",
                    "line": node.lineno,
                    "reason": f"Dynamic module loading via imported function {node.func.id}()",
                }
            )
        self.generic_visit(node)


class ImportVisitor(ast.NodeVisitor):
    """Extracts all module imports, relative imports, and called functions/classes."""

    def __init__(self, current_module: str):
        self.current_module = current_module
        self.imported_modules: set[str] = set()
        self.imported_symbols: dict[str, str] = {}  # symbol -> module

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imported_modules.add(alias.name)
            as_name = alias.asname or alias.name
            self.imported_symbols[as_name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        base_module = node.module or ""
        # Handle relative imports (e.g. from . import utils)
        if node.level > 0:
            parts = self.current_module.split(".")
            if len(parts) >= node.level:
                prefix = ".".join(parts[: -node.level])
                base_module = f"{prefix}.{base_module}".strip(".")
            else:
                base_module = base_module.strip(".")

        if base_module:
            self.imported_modules.add(base_module)

        for alias in node.names:
            full_name = f"{base_module}.{alias.name}" if base_module else alias.name
            as_name = alias.asname or alias.name
            self.imported_symbols[as_name] = full_name
            self.imported_modules.add(full_name)

        self.generic_visit(node)


class DependencyGraph:
    """Directed dependency graph modeling module import dependencies."""

    def __init__(self):
        # DiGraph edge (A, B) means module A depends on (imports) module B
        self.graph = nx.DiGraph()
        self.parsing_errors: dict[str, str] = {}
        self.dynamic_imports_detected: dict[str, list[dict[str, Any]]] = {}

    def add_module(self, module_name: str, file_path: str):
        """Adds a module node with its filesystem path."""
        self.graph.add_node(module_name, file_path=file_path)

    def add_dependency(self, source_module: str, target_module: str):
        """Adds a dependency edge: source_module -> target_module."""
        self.graph.add_edge(source_module, target_module)

    def get_dependents(self, module_name: str) -> set[str]:
        """
        Returns all modules that directly or indirectly depend on module_name.
        If B imports A, then changing A affects B (reverse traversal of dependency edge).
        """
        if module_name not in self.graph:
            return set()
        # Predecessors in nx.DiGraph where edges are A -> B (A imports B) are modules that import A
        return set(nx.ancestors(self.graph, module_name))

    def find_cycles(self) -> list[list[str]]:
        """Finds all simple cycles in the directed dependency graph."""
        try:
            return list(nx.simple_cycles(self.graph))
        except (nx.NetworkXError, ValueError) as e:
            logger.warning(f"Failed to compute graph cycles: {e}")
            return []

    def is_acyclic(self) -> bool:
        """Verifies that the dependency graph contains no circular import cycles."""
        return nx.is_directed_acyclic_graph(self.graph)

    def has_unresolved_or_errors(self) -> bool:
        """Checks if any file failed to parse or contains unresolvable dynamic imports."""
        return bool(self.parsing_errors) or bool(self.dynamic_imports_detected)


class ASTDependencyAnalyzer:
    """
    Parses Python modules in a repository, resolves internal imports,
    and constructs a comprehensive DependencyGraph.
    """

    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)

    def _file_path_to_module(self, file_path: str) -> str:
        """Converts a relative file path (sample_app/utils/math_ops.py) to module format (sample_app.utils.math_ops)."""
        rel = os.path.relpath(file_path, self.root_dir).replace("\\", "/")
        rel = rel.removesuffix(".py")
        rel = rel.removesuffix("/__init__")
        return rel.replace("/", ".")

    def parse_python_file(
        self, file_path: str, current_module: str
    ) -> tuple[set[str], list[dict[str, Any]]]:
        """
        Parses a single Python file into an AST, returning imported modules
        and any detected dynamic imports.
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in {file_path} at line {e.lineno}: {e.msg}") from e

        # Check for dynamic imports (__import__, importlib, eval, exec)
        dynamic_detector = DynamicImportDetector()
        dynamic_detector.visit(tree)

        # Extract static imports
        import_visitor = ImportVisitor(current_module)
        import_visitor.visit(tree)

        return import_visitor.imported_modules, dynamic_detector.dynamic_imports

    def build_graph(self, target_dirs: list[str] | None = None) -> DependencyGraph:
        """
        Scans Python files in target directories, parses each into an AST,
        and constructs the full NetworkX directed dependency graph.
        """
        dep_graph = DependencyGraph()
        module_path_map: dict[str, str] = {}
        target_dirs = target_dirs or ["app", "sample_app", "tests", "tests_sample_app"]

        # 1. Discover all Python files and register nodes
        for folder in target_dirs:
            full_folder = os.path.join(self.root_dir, folder)
            if not os.path.exists(full_folder):
                continue

            for root, _, files in os.walk(full_folder):
                for file in files:
                    if file.endswith(".py"):
                        full_path = os.path.join(root, file)
                        mod_name = self._file_path_to_module(full_path)
                        dep_graph.add_module(mod_name, full_path)
                        module_path_map[mod_name] = full_path

        # 2. Parse dependencies for each registered module
        for mod_name, file_path in module_path_map.items():
            try:
                imports, dynamic_imports = self.parse_python_file(file_path, mod_name)
                if dynamic_imports:
                    dep_graph.dynamic_imports_detected[mod_name] = dynamic_imports

                # Match imports against known internal modules
                for imp in imports:
                    # Direct match
                    if imp in module_path_map:
                        dep_graph.add_dependency(mod_name, imp)
                    else:
                        # Check prefix match (e.g. sample_app.utils.math_ops.add -> sample_app.utils.math_ops)
                        parts = imp.split(".")
                        for i in range(len(parts) - 1, 0, -1):
                            prefix = ".".join(parts[:i])
                            if prefix in module_path_map:
                                dep_graph.add_dependency(mod_name, prefix)
                                break
            except (SyntaxError, ValueError, OSError, UnicodeDecodeError) as e:
                logger.error(f"Failed to parse AST for {file_path}: {e}")
                dep_graph.parsing_errors[mod_name] = str(e)

        return dep_graph
