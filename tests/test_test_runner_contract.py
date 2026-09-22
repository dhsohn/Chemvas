from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_test_files.sh"


def _runner_command(*files: Path) -> list[str]:
    bash = shutil.which("bash")
    assert bash is not None, "The shell gate requires Bash (Git Bash on Windows)"
    return [
        bash,
        RUNNER.as_posix(),
        "--python",
        Path(sys.executable).as_posix(),
        *(path.as_posix() for path in files),
    ]


def _run_runner(*files: Path, jobs: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["CHECK_JOBS"] = jobs

    return subprocess.run(
        _runner_command(*files),
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


def test_runner_reports_skip_reason(tmp_path) -> None:
    skipped = tmp_path / "test_skip.py"
    skipped.write_text(
        "import pytest\n"
        "@pytest.mark.skip(reason='native compiler unavailable')\n"
        "def test_native():\n    assert False\n",
        encoding="utf-8",
    )

    result = _run_runner(skipped, jobs="1")

    assert result.returncode == 0
    assert "1 skipped" in result.stdout
    assert "native compiler unavailable" in result.stdout


def test_runner_reports_failure_while_another_file_is_still_running(tmp_path) -> None:
    failing = tmp_path / "test_failure.py"
    waiting = tmp_path / "test_waiting.py"
    started = tmp_path / "started"
    release = tmp_path / "release"
    failing.write_text(
        "def test_failure():\n    assert False, 'immediate-failure-detail'\n",
        encoding="utf-8",
    )
    waiting.write_text(
        "import time\nfrom pathlib import Path\n"
        "def test_waiting():\n"
        f"    Path({started.as_posix()!r}).touch()\n"
        "    deadline = time.monotonic() + 30\n"
        f"    while not Path({release.as_posix()!r}).exists():\n"
        "        assert time.monotonic() < deadline\n"
        "        time.sleep(0.01)\n",
        encoding="utf-8",
    )
    log = tmp_path / "stderr.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            _runner_command(failing, waiting),
            cwd=ROOT,
            env={**os.environ, "CHECK_JOBS": "2"},
            stdout=subprocess.DEVNULL,
            stderr=output,
        )
        visible_while_running = False
        try:
            deadline = time.monotonic() + 10
            while process.poll() is None and time.monotonic() < deadline:
                if started.exists() and "immediate-failure-detail" in log.read_text():
                    visible_while_running = True
                    break
                time.sleep(0.01)
        finally:
            release.touch()
            process.wait(timeout=10)
    assert visible_while_running, log.read_text()
    assert process.returncode == 1
