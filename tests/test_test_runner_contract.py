from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_test_files.sh"


def _run_runner(*files: Path, jobs: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CHECK_JOBS"] = jobs

    return subprocess.run(
        [
            "bash",
            str(RUNNER),
            "--python",
            sys.executable,
            *(str(path) for path in files),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_runner_rejects_zero_concurrency() -> None:
    result = _run_runner(Path(__file__), jobs="0")

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == ("[tests] ERROR: CHECK_JOBS must be a positive integer.\n")


def test_runner_caps_an_arbitrarily_large_positive_concurrency(tmp_path) -> None:
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_pass():\n    assert True\n", encoding="utf-8")

    result = _run_runner(passing, jobs="18446744073709551616")

    assert result.returncode == 0
    assert "[tests] 1 files, 8 at a time" in result.stdout


def test_runner_keeps_recursive_path_failure_logs_distinct(tmp_path) -> None:
    nested = tmp_path / "tests" / "a" / "test_b.py"
    flat = tmp_path / "tests" / "a_test_b.py"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        "def test_nested():\n    assert False, 'nested-marker'\n", encoding="utf-8"
    )
    flat.write_text(
        "def test_flat():\n    assert False, 'flat-marker'\n", encoding="utf-8"
    )

    result = _run_runner(nested, flat, jobs="1")

    assert result.returncode == 1
    assert "nested-marker" in result.stderr
    assert "flat-marker" in result.stderr
