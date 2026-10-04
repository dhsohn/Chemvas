"""Pin the native Windows lane and exercise its missing-tool rejection."""

from __future__ import annotations

import os
import re
import runpy
import shlex
import struct
import sys
from pathlib import Path
from textwrap import dedent

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PLATFORM_WORKFLOW = ROOT / ".github" / "workflows" / "platform.yml"
FILES = (
    "tests/test_windows_bundle.py",
    "tests/test_windows_installer.py",
    "tests/test_application_cli.py",
)


def _job_env(job: str) -> str:
    """Return a job's own ``env:`` entries; a step's env is indented deeper."""
    match = re.search(r"(?m)^    env:\n((?:      .*\n)+)", job)
    return match.group(1) if match else ""


def test_macos_and_windows_run_the_full_host_gate_on_demand() -> None:
    assert "platform-tests:" not in WORKFLOW.read_text(encoding="utf-8")
    workflow = PLATFORM_WORKFLOW.read_text(encoding="utf-8")
    trigger = re.search(r"(?ms)^on:\n(.*?)^\S", workflow)
    assert trigger
    assert re.findall(r"(?m)^  (\w+):", trigger.group(1)) == ["workflow_dispatch"]
    match = re.search(r"(?ms)^  platform-tests:.*?(?=^  \w[\w-]*:|\Z)", workflow)
    assert match, "macOS and Windows must run the common suite"
    job = match.group(0)
    hosts = re.search(r"(?m)^        os: \[(.+)\]$", job)
    assert hosts
    assert {host.strip() for host in hosts.group(1).split(",")} == {
        "macos-15",
        "windows-2025",
    }
    assert "    name: Common tests (${{ matrix.os }})\n" in job
    assert "    runs-on: ${{ matrix.os }}\n" in job
    # Without it the gate would build its own .venv instead of using the
    # interpreter the job set up and provisioned. Only the job's env reaches
    # the gate step.
    assert re.search(r"(?m)^      PYTHON_BIN: python$", _job_env(job))
    assert "continue-on-error:" not in job
    assert not re.search(r"(?m)^\s*if:", job)
    step = re.search(
        r"(?m)^      - name: Run the host platform gate\n"
        r"        shell: bash\n        run: \|\n((?:          .*\n)+)",
        job,
    )
    assert step
    assert shlex.split(dedent(step.group(1))) == [
        "bash",
        "scripts/check.sh",
    ]


def test_each_pull_request_commit_runs_once() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    trigger = re.search(r"(?ms)^on:\n(.*?)^\S", workflow)
    assert trigger
    # A push to a pull request branch would repeat the pull_request run.
    assert re.findall(r"(?m)^  (\w+):", trigger.group(1)) == ["push", "pull_request"]
    assert "  push:\n    branches: [main]\n" in trigger.group(1)
    # Cancelling a run leaves cancelled required checks on its commit, and a
    # stacked pull request reruns the same commit when its base moves, so a
    # superseded run is left to finish.
    assert "concurrency:" not in workflow


def test_python_bin_in_a_step_env_is_not_the_jobs() -> None:
    job = (
        "  platform-tests:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - name: Install Python dependencies\n"
        "        env:\n"
        "          PYTHON_BIN: python\n"
        '        run: python -m pip install -e ".[dev]"\n'
    )
    assert _job_env(job) == ""


def _windows_job() -> str:
    match = re.search(
        r"(?ms)^  windows-native:.*?(?=^  \w[\w-]*:|\Z)",
        WORKFLOW.read_text(encoding="utf-8"),
    )
    assert match, "Windows native tests must have a dedicated CI job"
    return match.group(0)


def _step_source(name: str, shell: str) -> str:
    match = re.search(
        rf"(?m)^      - name: {re.escape(name)}\n"
        rf"        shell: {shell}\n        run: \|\n"
        r"((?:(?:          .*|)\n)+)",
        _windows_job(),
    )
    assert match, f"Missing executable {name} step"
    return dedent(match.group(1))


def test_windows_job_is_native_x64_with_python_qt_and_test_dependencies() -> None:
    job = _windows_job()
    assert "    runs-on: windows-2025\n" in job
    assert "    timeout-minutes: 15\n" in job
    assert "      QT_QPA_PLATFORM: offscreen\n" in job
    assert '          python-version: "3.13"\n          architecture: x64\n' in job
    assert '        run: python -m pip install -e ".[dev]"\n' in job
    assert "continue-on-error:" not in job
    assert not re.search(r"(?m)^\s*if:", job)


def test_native_compiler_preflight_precedes_exact_separate_process_runner() -> None:
    job = _windows_job()
    assert job.index("Require native Inno Setup compiler") < job.index(
        "Run Windows test files in separate processes"
    )
    source = _step_source("Run Windows test files in separate processes", "bash")
    commands = [
        shlex.split(line)
        for line in source.replace("\\\n", "").splitlines()
        if line.strip()
    ]
    assert commands == [
        [
            "python",
            "-c",
            'import runpy, sys; sys.exit(0 if runpy.run_path("tests/test_windows_installer.py")["ISCC"] else "Native compiler tests would be skipped")',
        ],
        ["bash", "scripts/run_test_files.sh", "--python", "python", *FILES],
    ]
    assert all((ROOT / path).is_file() for path in FILES)
    installer_tests = (ROOT / FILES[1]).read_text(encoding="utf-8")
    assert (
        'ISCC = shutil.which("ISCC") if sys.platform == "win32" else None'
        in installer_tests
    )
    assert (
        '@pytest.mark.skipif(ISCC is None, reason="Native Windows ISCC compiler is not on PATH")'
        in installer_tests
    )
    assert (
        "def test_native_compiler_accepts_bundle_and_rejects_invalid_inputs("
        in installer_tests
    )


@pytest.mark.parametrize("compiler", [None, "ISCC.exe"])
def test_actual_consumer_preflight_refuses_skipped_native_tests(monkeypatch, compiler):
    source = _step_source("Run Windows test files in separate processes", "bash")
    command = shlex.split(source.splitlines()[0])
    calls = []

    def load_installer_tests(path):
        calls.append(path)
        return {"ISCC": compiler}

    monkeypatch.setattr(runpy, "run_path", load_installer_tests)
    with pytest.raises(SystemExit) as result:
        exec(compile(command[2], str(WORKFLOW), "exec", optimize=2), {})
    assert calls == ["tests/test_windows_installer.py"]
    assert result.value.code == (
        0 if compiler else "Native compiler tests would be skipped"
    )


@pytest.mark.parametrize(
    ("platform", "pointer_bytes", "has_compiler", "error"),
    [
        ("win32", 8, True, None),
        ("win32", 8, False, "Required Inno Setup compiler is missing"),
        ("linux", 8, True, "Windows x64 Python is required"),
        ("win32", 4, True, "Windows x64 Python is required"),
    ],
)
def test_actual_ci_preflight_rejects_missing_compiler_or_wrong_runtime(
    tmp_path, monkeypatch, platform, pointer_bytes, has_compiler, error
) -> None:
    compiler = tmp_path / "Program Files (x86)" / "Inno Setup 6" / "ISCC.exe"
    compiler.parent.mkdir(parents=True)
    if has_compiler:
        compiler.write_bytes(b"compiler-presence fixture, never executed")
    github_path = tmp_path / "github-path"
    monkeypatch.setenv("ProgramFiles(x86)", str(compiler.parent.parent))
    monkeypatch.setenv("GITHUB_PATH", str(github_path))
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(struct, "calcsize", lambda _: pointer_bytes)
    source = _step_source("Require native Inno Setup compiler", "python")
    if error:
        with pytest.raises(SystemExit, match=error):
            exec(compile(source, str(WORKFLOW), "exec"), {})
        assert not github_path.exists()
    else:
        exec(compile(source, str(WORKFLOW), "exec"), {})
        assert github_path.read_text(encoding="utf-8") == str(compiler.parent) + "\n"
    assert os.environ["GITHUB_PATH"] == str(github_path)
