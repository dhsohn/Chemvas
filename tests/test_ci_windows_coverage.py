"""GitHub keeps quick checks; platform suites belong to local make check."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def assert_quick_ci(workflow):
    jobs = workflow.split("jobs:\n", 1)[1]
    assert set(re.findall(r"(?m)^  ([\w-]+):", jobs)) == {
        "quality",
        "secret-scan",
        "package-smoke",
    }
    assert "matrix:" not in jobs
    assert "run_test_files.sh" not in jobs
    assert "scripts/check.sh" not in jobs
    for command in ("ruff check", "ruff format --check", "mypy", "verify_dist.py"):
        assert command in jobs


def test_ci_keeps_quick_checks_and_removes_os_suites():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert_quick_ci(workflow)
    assert "  push:\n    branches: [main]\n" in workflow
    assert "  pull_request:" in workflow
    assert not (ROOT / ".github/workflows/platform.yml").exists()
    assert not (ROOT / ".github/workflows/windows.yml").exists()


@pytest.mark.parametrize(
    "injection",
    [
        "  test:\n    runs-on: ubuntu-latest\n",
        "    strategy:\n      matrix: {}\n",
        "    run: bash scripts/check.sh\n",
    ],
)
def test_contract_rejects_reintroduced_slow_suites(injection):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    with pytest.raises(AssertionError):
        assert_quick_ci(workflow + injection)
