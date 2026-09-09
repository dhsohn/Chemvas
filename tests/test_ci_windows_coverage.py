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
FILES = (
    "tests/test_windows_bundle.py",
    "tests/test_windows_installer.py",
    "tests/test_application_cli.py",
)


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
