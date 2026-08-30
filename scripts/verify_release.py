from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 1_048_576
ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*"([^"]+)"$', re.MULTILINE)


class ReleasePreflightError(RuntimeError):
    """A release tag is not proven safe to publish."""


def read_package_version(repo_root: Path) -> str:
    source = (repo_root / "app" / "chemvas" / "__init__.py").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if match is None:
        raise ReleasePreflightError("chemvas.__version__ could not be read")
    return match.group(1)


def validate_tag(tag: str, version: str) -> None:
    expected = f"v{version}"
    if tag != expected:
        raise ReleasePreflightError(
            f"release tag {tag!r} does not match package version {version!r}"
        )


def resolve_commit(repo_root: Path, revision: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{revision}^{{commit}}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleasePreflightError(f"release revision {revision!r} is not a commit")
    commit = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ReleasePreflightError("git returned an invalid release commit")
    return commit


def ensure_commit_on_main(
    repo_root: Path, commit: str, main_ref: str = "refs/remotes/origin/main"
) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, main_ref],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        raise ReleasePreflightError(
            f"release commit {commit} is not contained in {main_ref}"
        )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git merge-base failed"
        raise ReleasePreflightError(detail)


def workflow_runs_url(api_url: str, repository: str, commit: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ReleasePreflightError("GitHub repository must have owner/name form")
    query = urlencode(
        {
            "branch": "main",
            "event": "push",
            "head_sha": commit,
            "per_page": 100,
            "status": "completed",
        }
    )
    repo_path = quote(repository, safe="/")
    return (
        f"{api_url.rstrip('/')}/repos/{repo_path}/actions/workflows/ci.yml/runs?{query}"
    )


def fetch_workflow_runs(url: str, token: str) -> dict[str, Any]:
    if not token:
        raise ReleasePreflightError("GITHUB_TOKEN is required to verify main CI")
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "chemvas-release-preflight",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ReleasePreflightError("GitHub CI status could not be read") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReleasePreflightError("GitHub CI response exceeded the size limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleasePreflightError("GitHub CI response was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ReleasePreflightError("GitHub CI response was not an object")
    return payload


def successful_main_ci_run(
    payload: dict[str, Any], commit: str
) -> dict[str, Any] | None:
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ReleasePreflightError("GitHub CI response omitted workflow_runs")
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (
            run.get("head_sha") == commit
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ):
            return run
    return None


def verify_release(
    *,
    repo_root: Path,
    tag: str,
    revision: str,
    repository: str,
    token: str,
    api_url: str,
) -> dict[str, object]:
    version = read_package_version(repo_root)
    validate_tag(tag, version)
    commit = resolve_commit(repo_root, revision)
    ensure_commit_on_main(repo_root, commit)
    url = workflow_runs_url(api_url, repository, commit)
    run = successful_main_ci_run(fetch_workflow_runs(url, token), commit)
    if run is None:
        raise ReleasePreflightError(
            f"release commit {commit} has no successful completed main push CI run"
        )
    return {
        "ci_run_id": run.get("id"),
        "ci_run_url": run.get("html_url"),
        "commit": commit,
        "repository": repository,
        "tag": tag,
        "version": version,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed unless a Chemvas release tag is safe to publish"
    )
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify_release(
            repo_root=args.repo_root.resolve(),
            tag=args.tag,
            revision=args.commit,
            repository=args.repository,
            token=os.environ.get("GITHUB_TOKEN", ""),
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        )
    except ReleasePreflightError as exc:
        parser.exit(1, f"release preflight failed: {exc}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
