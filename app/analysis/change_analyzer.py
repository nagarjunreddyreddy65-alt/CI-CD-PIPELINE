"""
Change Analyzer Module.
Extracts changed files, classifies file types, and detects safety-sensitive modifications
(Database migrations, auth changes, billing changes, lock files, CI workflows, etc.).
"""

from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
import os
import re


@dataclass
class FileChange:
    """Represents an individual file modification in a commit or pull request."""
    path: str
    change_type: str  # ADDED, MODIFIED, DELETED, RENAMED
    lines_added: int = 0
    lines_deleted: int = 0
    old_path: Optional[str] = None
    is_sensitive: bool = False
    sensitive_category: Optional[str] = None


@dataclass
class ChangeAnalysisResult:
    """Consolidated findings from analyzing commit file changes."""
    total_files_changed: int
    total_lines_added: int
    total_lines_deleted: int
    files: List[FileChange]
    python_files: List[str]
    non_python_files: List[str]
    test_files_changed: List[str]
    sensitive_triggers: List[str] = field(default_factory=list)
    has_migration_changes: bool = False
    has_auth_changes: bool = False
    has_payment_changes: bool = False
    has_crypto_changes: bool = False
    has_dependency_manifest_changes: bool = False
    has_lock_file_changes: bool = False
    has_ci_workflow_changes: bool = False
    has_unsupported_files: bool = False

    @property
    def total_changed_files(self) -> int:
        return self.total_files_changed

    @property
    def is_sensitive(self) -> bool:
        return bool(self.sensitive_triggers) or (
            self.has_migration_changes or
            self.has_auth_changes or
            self.has_payment_changes or
            self.has_crypto_changes or
            self.has_dependency_manifest_changes or
            self.has_lock_file_changes or
            self.has_ci_workflow_changes or
            self.has_unsupported_files
        )

    @property
    def has_test_changes(self) -> bool:
        return len(self.test_files_changed) > 0



class ChangeAnalyzer:
    """
    Parses commit diffs and inspects modified file paths against deterministic safety categories.
    """

    # Sensitive path heuristics matching Part 5 Safety Policy
    MIGRATION_PATTERNS = [
        re.compile(r"(?i)migrations/.*\.py$"),
        re.compile(r"(?i)alembic/.*\.py$"),
        re.compile(r"(?i).*\.sql$"),
        re.compile(r"(?i)app/database/models\.py$"),
    ]

    AUTH_PATTERNS = [
        re.compile(r"(?i).*/auth/.*\.py$"),
        re.compile(r"(?i).*auth.*\.py$"),
        re.compile(r"(?i).*security.*\.py$"),
        re.compile(r"(?i).*jwt.*\.py$"),
        re.compile(r"(?i).*permission.*\.py$"),
    ]

    PAYMENT_PATTERNS = [
        re.compile(r"(?i).*/billing/.*\.py$"),
        re.compile(r"(?i).*payment.*\.py$"),
        re.compile(r"(?i).*invoice.*\.py$"),
        re.compile(r"(?i).*stripe.*\.py$"),
    ]

    CRYPTO_PATTERNS = [
        re.compile(r"(?i).*crypto.*\.py$"),
        re.compile(r"(?i).*cipher.*\.py$"),
        re.compile(r"(?i).*certificate.*$"),
        re.compile(r"(?i).*\.(pem|key|crt|cert)$"),
    ]

    DEPENDENCY_MANIFEST_PATTERNS = [
        re.compile(r"(?i)^requirements.*\.txt$"),
        re.compile(r"(?i)^pyproject\.toml$"),
        re.compile(r"(?i)^setup\.(py|cfg)$"),
        re.compile(r"(?i)^Pipfile$"),
    ]

    LOCK_FILE_PATTERNS = [
        re.compile(r"(?i)^uv\.lock$"),
        re.compile(r"(?i)^poetry\.lock$"),
        re.compile(r"(?i)^Pipfile\.lock$"),
        re.compile(r"(?i)^package-lock\.json$"),
    ]

    CI_WORKFLOW_PATTERNS = [
        re.compile(r"(?i)^\.github/workflows/.*\.ya?ml$"),
        re.compile(r"(?i)^Dockerfile.*$"),
        re.compile(r"(?i)^docker-compose.*\.ya?ml$"),
        re.compile(r"(?i)^\.gitlab-ci\.yml$"),
    ]

    TEST_PATTERNS = [
        re.compile(r"(?i)^tests/.*\.py$"),
        re.compile(r"(?i)^tests_.*\.py$"),
        re.compile(r"(?i).*/tests/.*\.py$"),
        re.compile(r"(?i).*test_.*\.py$"),
        re.compile(r"(?i).*_test\.py$"),
    ]

    # File extensions that can be safely parsed or handled
    SUPPORTED_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or os.getcwd()

    def classify_file(self, file_path: str) -> Dict[str, Any]:
        """Classifies a file path for sensitivity, language, and test association."""
        norm_path = file_path.replace("\\", "/").lstrip("/")
        ext = os.path.splitext(norm_path)[1].lower()

        categories: List[str] = []

        if any(p.search(norm_path) for p in self.MIGRATION_PATTERNS):
            categories.append("DATABASE_MIGRATION")
        if any(p.search(norm_path) for p in self.AUTH_PATTERNS):
            categories.append("AUTH_SECURITY")
        if any(p.search(norm_path) for p in self.PAYMENT_PATTERNS):
            categories.append("PAYMENT_BILLING")
        if any(p.search(norm_path) for p in self.CRYPTO_PATTERNS):
            categories.append("CRYPTOGRAPHIC")
        if any(p.search(norm_path) for p in self.DEPENDENCY_MANIFEST_PATTERNS):
            categories.append("DEPENDENCY_MANIFEST")
        if any(p.search(norm_path) for p in self.LOCK_FILE_PATTERNS):
            categories.append("LOCK_FILE")
        if any(p.search(norm_path) for p in self.CI_WORKFLOW_PATTERNS):
            categories.append("CI_WORKFLOW")

        is_test = any(p.search(norm_path) for p in self.TEST_PATTERNS)
        is_python = ext == ".py"
        is_unsupported = ext not in self.SUPPORTED_EXTENSIONS and bool(ext)

        return {
            "path": norm_path,
            "extension": ext,
            "is_python": is_python,
            "is_test": is_test,
            "is_sensitive": len(categories) > 0,
            "sensitive_categories": categories,
            "is_unsupported": is_unsupported,
        }

    def analyze_changes(self, file_entries: List[Dict[str, Any]]) -> ChangeAnalysisResult:
        """
        Analyzes a list of file changes from git diff.
        Expected entry format:
        {"path": "sample_app/utils/math_ops.py", "change_type": "MODIFIED", "lines_added": 5, "lines_deleted": 1}
        """
        file_changes: List[FileChange] = []
        python_files: List[str] = []
        non_python_files: List[str] = []
        test_files_changed: List[str] = []
        sensitive_triggers: Set[str] = set()

        total_added = 0
        total_deleted = 0

        has_migration = False
        has_auth = False
        has_payment = False
        has_crypto = False
        has_dependency = False
        has_lock = False
        has_ci = False
        has_unsupported = False

        for entry in file_entries:
            path = (entry.get("path") or entry.get("file_path") or "").strip()
            if not path:
                continue

            change_type = entry.get("change_type", "MODIFIED").upper()
            added = int(entry.get("lines_added", 0))
            deleted = int(entry.get("lines_deleted", 0))
            old_path = entry.get("old_path")

            total_added += added
            total_deleted += deleted

            info = self.classify_file(path)

            if info["is_python"]:
                python_files.append(info["path"])
            else:
                non_python_files.append(info["path"])

            if info["is_test"]:
                test_files_changed.append(info["path"])

            if info["is_unsupported"]:
                has_unsupported = True
                sensitive_triggers.add("UNSUPPORTED_FILE_TYPE")

            cats = info["sensitive_categories"]
            for cat in cats:
                sensitive_triggers.add(cat)
                if cat == "DATABASE_MIGRATION":
                    has_migration = True
                elif cat == "AUTH_SECURITY":
                    has_auth = True
                elif cat == "PAYMENT_BILLING":
                    has_payment = True
                elif cat == "CRYPTOGRAPHIC":
                    has_crypto = True
                elif cat == "DEPENDENCY_MANIFEST":
                    has_dependency = True
                elif cat == "LOCK_FILE":
                    has_lock = True
                elif cat == "CI_WORKFLOW":
                    has_ci = True

            change_obj = FileChange(
                path=info["path"],
                change_type=change_type,
                lines_added=added,
                lines_deleted=deleted,
                old_path=old_path,
                is_sensitive=info["is_sensitive"] or info["is_unsupported"],
                sensitive_category=",".join(cats) if cats else (
                    "UNSUPPORTED" if info["is_unsupported"] else None
                ),
            )
            file_changes.append(change_obj)

        return ChangeAnalysisResult(
            total_files_changed=len(file_changes),
            total_lines_added=total_added,
            total_lines_deleted=total_deleted,
            files=file_changes,
            python_files=python_files,
            non_python_files=non_python_files,
            test_files_changed=test_files_changed,
            sensitive_triggers=sorted(list(sensitive_triggers)),
            has_migration_changes=has_migration,
            has_auth_changes=has_auth,
            has_payment_changes=has_payment,
            has_crypto_changes=has_crypto,
            has_dependency_manifest_changes=has_dependency,
            has_lock_file_changes=has_lock,
            has_ci_workflow_changes=has_ci,
            has_unsupported_files=has_unsupported,
        )
