"""The local gate discovers each test path intact on the host shell."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def test_default_gate_passes_nested_paths_with_spaces_to_isolated_runner(tmp_path):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("the shell gate requires Bash")
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("check.sh", "run_test_files.sh"):
        shutil.copyfile(root / "scripts" / name, scripts / name)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs: {}\n", encoding="utf-8")
    validator = tmp_path / "contract" / "scripts" / "validate.py"
    validator.parent.mkdir(parents=True)
    validator.touch()
    tests = ["tests/test_root.py", "tests/nested folder/test_nested.py"]
    for name in tests:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    output = tmp_path / "observed"
    output.mkdir()
    interpreter = tmp_path / "python-probe"
    interpreter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:3] == ['-m', 'pytest', '-q']:\n"
        "    assert len(args) == 4, args\n"
        "    target = pathlib.Path(os.environ['GATE_PROBE_OUTPUT']) / "
        "(pathlib.Path(args[3]).name + '.json')\n"
        "    target.write_text(json.dumps(args), encoding='utf-8')\n"
        "elif args[:1] == ['-c'] or args[:2] in "
        "(['-m', 'ruff'], ['-m', 'mypy']):\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError(args)\n",
        encoding="utf-8",
    )
    interpreter.chmod(0o755)
    result = subprocess.run(
        [bash, "scripts/check.sh"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHON_BIN": str(interpreter),
            "FACTORY_MACHINE_CONTRACT_REPO": str(validator.parents[1]),
            "CHECK_JOBS": "2",
            "GATE_PROBE_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = [json.loads(path.read_text()) for path in output.glob("*.json")]
    assert sorted(observed) == [["-m", "pytest", "-q", path] for path in sorted(tests)]
