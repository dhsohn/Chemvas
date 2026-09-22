"""The local gate discovers each test path intact on the host shell."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
@pytest.mark.parametrize(
    "failing", [None, "test_root.py", "test_note_formatting_workflows.py"]
)
def test_gate_routes_every_file_and_propagates_failures(tmp_path, platform, failing):
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
    tests = [
        "tests/test_root.py",
        "tests/nested folder/test_nested.py",
        "tests/test_note_formatting_workflows.py",
        "tests/test_note_appearance_workflows.py",
    ]
    for name in tests:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    output = tmp_path / "observed"
    output.mkdir()
    interpreter = tmp_path / "python-probe"
    probe = tmp_path / "python_probe.py"
    probe.write_text(
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "if args[:4] == ['-m', 'pytest', '-q', '-ra']:\n"
        "    assert len(args) == 5, args\n"
        "    target = pathlib.Path(os.environ['GATE_PROBE_OUTPUT']) / "
        "(pathlib.Path(args[4]).name + '.json')\n"
        "    target.write_text(json.dumps({'args': args, "
        "'qt': os.environ['QT_QPA_PLATFORM'], "
        "'jobs': os.environ['CHECK_JOBS']}), encoding='utf-8')\n"
        "    sys.exit(1 if pathlib.Path(args[4]).name == os.environ['GATE_PROBE_FAIL'] else 0)\n"
        "elif args == ['-c', 'import sys; print(sys.platform)']:\n"
        "    sys.stdout.buffer.write((os.environ['GATE_PROBE_PLATFORM'] + chr(13) + chr(10)).encode())\n"
        "elif args[:1] == ['-c'] or args[:2] in "
        "(['-m', 'ruff'], ['-m', 'mypy']):\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError(args)\n",
        encoding="utf-8",
    )
    interpreter.write_text(
        "#!/usr/bin/env bash\nexec "
        + shlex.quote(Path(sys.executable).as_posix())
        + " "
        + shlex.quote(probe.as_posix())
        + ' "$@"\n',
        encoding="utf-8",
    )
    interpreter.chmod(0o755)
    result = subprocess.run(
        [bash, "scripts/check.sh"],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHON_BIN": interpreter.as_posix(),
            "FACTORY_MACHINE_CONTRACT_REPO": str(validator.parents[1]),
            "CHECK_JOBS": "2",
            "GATE_PROBE_OUTPUT": str(output),
            "GATE_PROBE_PLATFORM": platform,
            "GATE_PROBE_FAIL": failing or "",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == (1 if failing else 0), result.stdout + result.stderr
    observed = [json.loads(path.read_text()) for path in output.glob("*.json")]
    assert sorted(entry["args"] for entry in observed) == [
        ["-m", "pytest", "-q", "-ra", path] for path in sorted(tests)
    ]
    for entry in observed:
        native = platform == "darwin" and "test_note_" in entry["args"][4]
        assert entry["qt"] == ("cocoa" if native else "offscreen")
        assert entry["jobs"] == ("1" if native else "2")
