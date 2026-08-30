from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest
from scripts.verify_release import (
    ReleasePreflightError,
    ensure_commit_on_main,
    fetch_workflow_runs,
    read_package_version,
    resolve_commit,
    successful_main_ci_run,
    validate_tag,
    workflow_runs_url,
)

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_version_and_tag_must_match(tmp_path: Path) -> None:
    package = tmp_path / "app" / "chemvas"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '"""Package."""\n\n__version__ = "0.6.0"\n', encoding="utf-8"
    )

    assert read_package_version(tmp_path) == "0.6.0"
    validate_tag("v0.6.0", "0.6.0")
    with pytest.raises(ReleasePreflightError, match="does not match"):
        validate_tag("v0.5.1", "0.6.0")


def test_release_commit_must_be_contained_in_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "tests@example.invalid")
    _git(repo, "config", "user.name", "Chemvas Tests")
    (repo / "tracked.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "main")
    main_commit = resolve_commit(repo, "HEAD")
    ensure_commit_on_main(repo, main_commit, "main")
    _git(repo, "tag", "-a", "v0.6.0", "-m", "release", main_commit)
    tag_object = _git(repo, "rev-parse", "v0.6.0")
    assert tag_object != main_commit
    assert resolve_commit(repo, tag_object) == main_commit

    _git(repo, "switch", "-c", "side")
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    _git(repo, "add", "side.txt")
    _git(repo, "commit", "-m", "side")
    side_commit = resolve_commit(repo, "HEAD")
    with pytest.raises(ReleasePreflightError, match="not contained"):
        ensure_commit_on_main(repo, side_commit, "main")


def test_workflow_query_is_narrowed_to_completed_main_push_ci() -> None:
    commit = "a" * 40
    parsed = urlparse(
        workflow_runs_url("https://api.github.test", "owner/repo", commit)
    )

    assert parsed.path == "/repos/owner/repo/actions/workflows/ci.yml/runs"
    assert parse_qs(parsed.query) == {
        "branch": ["main"],
        "event": ["push"],
        "head_sha": [commit],
        "per_page": ["100"],
        "status": ["completed"],
    }


def test_only_exact_successful_main_push_run_is_accepted() -> None:
    commit = "b" * 40
    failed = {
        "id": 1,
        "head_sha": commit,
        "head_branch": "main",
        "event": "push",
        "status": "completed",
        "conclusion": "failure",
    }
    success = {**failed, "id": 2, "conclusion": "success"}

    assert (
        successful_main_ci_run({"workflow_runs": [failed, success]}, commit) == success
    )
    assert successful_main_ci_run({"workflow_runs": [failed]}, commit) is None


def test_malformed_workflow_response_fails_closed() -> None:
    with pytest.raises(ReleasePreflightError, match="workflow_runs"):
        successful_main_ci_run({}, "c" * 40)


def test_missing_github_token_fails_closed() -> None:
    with pytest.raises(ReleasePreflightError, match="GITHUB_TOKEN"):
        fetch_workflow_runs("https://api.github.test", "")
