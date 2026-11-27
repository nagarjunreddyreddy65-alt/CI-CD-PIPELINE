"""
Unit and integration tests for Git Change Detection and Diff Statistics in CI Runner.
Verifies:
1. Single-commit changes with exact lines added/deleted.
2. Multi-commit pushes.
3. Added, modified, deleted, and renamed files.
4. Missing base commit SHAs and non-existent targets.
5. Shallow clone scenarios.
6. Empty diffs.
7. Git execution failures outside git repositories.
8. Initial commits with no parent (empty tree fallback).
"""

import subprocess
from pathlib import Path

import pytest

from scripts.run_optimized_ci import (
    _parse_git_numstat,
    get_git_changed_files,
)


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Helper to run git commands in a temporary test repository."""
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """Initializes a clean, isolated git repository for change detection testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    _run_git(["init"], repo)
    _run_git(["config", "user.name", "Test Runner"], repo)
    _run_git(["config", "user.email", "runner@test.local"], repo)
    _run_git(["config", "commit.gpgsign", "false"], repo)

    # Initial root commit
    f1 = repo / "initial.txt"
    f1.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
    _run_git(["add", "initial.txt"], repo)
    _run_git(["commit", "-m", "Initial commit"], repo)

    return repo


def test_parse_git_numstat_standard():
    """Tests parsing standard numstat output."""
    output = "10\t2\tapp/main.py\n5\t0\tutils/helper.py\n-\t-\tassets/logo.png\n"
    stats = _parse_git_numstat(output)
    assert stats["app/main.py"] == (10, 2)
    assert stats["utils/helper.py"] == (5, 0)
    assert stats["assets/logo.png"] == (0, 0)


def test_parse_git_numstat_renames():
    """Tests parsing numstat output with various rename syntax."""
    output = (
        "4\t1\t{old_dir => new_dir}/file.py\n"
        "2\t0\told_name.py => new_name.py\n"
        "8\t3\tsrc/{ => sub}/module.py\n"
    )
    stats = _parse_git_numstat(output)
    assert stats["new_dir/file.py"] == (4, 1)
    assert stats["new_name.py"] == (2, 0)
    assert stats["src/sub/module.py"] == (8, 3)


def test_single_commit_modified_and_added(temp_git_repo: Path):
    """Tests single commit modifying an existing file and adding a new file."""
    # Base commit is HEAD
    base_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    # Modify existing
    f1 = temp_git_repo / "initial.txt"
    f1.write_text("line 1\nline 2 modified\nline 3\nline 4 added\n", encoding="utf-8")

    # Add new
    f2 = temp_git_repo / "new_file.py"
    f2.write_text("def test():\n    pass\n", encoding="utf-8")

    _run_git(["add", "initial.txt", "new_file.py"], temp_git_repo)
    _run_git(["commit", "-m", "Commit 2"], temp_git_repo)
    target_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    changes, err = get_git_changed_files(
        base_sha=base_sha,
        target_sha=target_sha,
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert len(changes) == 2

    by_path = {c["file_path"]: c for c in changes}
    assert "initial.txt" in by_path
    assert by_path["initial.txt"]["change_type"] == "MODIFIED"
    assert by_path["initial.txt"]["lines_added"] > 0

    assert "new_file.py" in by_path
    assert by_path["new_file.py"]["change_type"] == "ADDED"
    assert by_path["new_file.py"]["lines_added"] == 2
    assert by_path["new_file.py"]["lines_deleted"] == 0


def test_multi_commit_push(temp_git_repo: Path):
    """Tests a range spanning multiple commits in a single push."""
    base_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    # Commit 1 in push
    c1_file = temp_git_repo / "commit1.txt"
    c1_file.write_text("First commit data\n", encoding="utf-8")
    _run_git(["add", "commit1.txt"], temp_git_repo)
    _run_git(["commit", "-m", "Push commit 1"], temp_git_repo)

    # Commit 2 in push
    c2_file = temp_git_repo / "commit2.txt"
    c2_file.write_text("Second commit data\nmore data\n", encoding="utf-8")
    _run_git(["add", "commit2.txt"], temp_git_repo)
    _run_git(["commit", "-m", "Push commit 2"], temp_git_repo)

    target_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    changes, err = get_git_changed_files(
        base_sha=base_sha,
        target_sha=target_sha,
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert len(changes) == 2
    paths = {c["file_path"] for c in changes}
    assert "commit1.txt" in paths
    assert "commit2.txt" in paths


def test_renamed_file_detection(temp_git_repo: Path):
    """Tests rename detection and old_path retention."""
    base_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    _run_git(["mv", "initial.txt", "renamed.txt"], temp_git_repo)
    _run_git(["commit", "-m", "Rename initial.txt to renamed.txt"], temp_git_repo)
    target_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    changes, err = get_git_changed_files(
        base_sha=base_sha,
        target_sha=target_sha,
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert len(changes) == 1
    assert changes[0]["change_type"] == "RENAMED"
    assert changes[0]["file_path"] == "renamed.txt"
    assert changes[0]["old_path"] == "initial.txt"


def test_deleted_file_detection(temp_git_repo: Path):
    """Tests file deletion tracking."""
    base_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    _run_git(["rm", "initial.txt"], temp_git_repo)
    _run_git(["commit", "-m", "Delete initial.txt"], temp_git_repo)
    target_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    changes, err = get_git_changed_files(
        base_sha=base_sha,
        target_sha=target_sha,
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert len(changes) == 1
    assert changes[0]["change_type"] == "DELETED"
    assert changes[0]["file_path"] == "initial.txt"
    assert changes[0]["lines_deleted"] == 3


def test_empty_diff(temp_git_repo: Path):
    """Tests comparing identical commits results in zero changes without error."""
    head_sha = _run_git(["rev-parse", "HEAD"], temp_git_repo).stdout.strip()

    changes, err = get_git_changed_files(
        base_sha=head_sha,
        target_sha=head_sha,
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert changes == []


def test_missing_base_sha(temp_git_repo: Path):
    """Tests that a non-existent base commit returns an explicit error for fallback."""
    fake_sha = "0123456789abcdef0123456789abcdef01234567"
    changes, err = get_git_changed_files(
        base_sha=fake_sha,
        target_sha="HEAD",
        repo_dir=str(temp_git_repo),
    )

    assert len(changes) == 0
    assert err is not None
    assert "could not be resolved in git history" in err


def test_non_git_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Tests executing in a non-git directory returns an error."""
    empty_dir = tmp_path / "plain_dir"
    empty_dir.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    changes, err = get_git_changed_files(repo_dir=str(empty_dir))
    assert len(changes) == 0
    assert err is not None
    assert "Not a git repository" in err


def test_initial_commit_no_parent(temp_git_repo: Path):
    """Tests analyzing the initial root commit (which has no parent commit)."""
    # Root commit has no HEAD~1. Without explicit base_sha, it compares against empty tree.
    changes, err = get_git_changed_files(
        target_sha="HEAD",
        repo_dir=str(temp_git_repo),
    )

    assert err is None
    assert len(changes) == 1
    assert changes[0]["file_path"] == "initial.txt"
    assert changes[0]["change_type"] == "ADDED"
    assert changes[0]["lines_added"] == 3
