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
        "if args[:5] == ['-m', 'pytest', '-q', '-ra', '--capture=tee-sys']:\n"
        "    assert len(args) == 6, args\n"
        "    target = pathlib.Path(os.environ['GATE_PROBE_OUTPUT']) / "
        "(pathlib.Path(args[5]).name + '.json')\n"
        "    target.write_text(json.dumps({'args': args, "
        "'qt': os.environ['QT_QPA_PLATFORM'], "
        "'jobs': os.environ['CHECK_JOBS']}), encoding='utf-8')\n"
        "    sys.exit(1 if pathlib.Path(args[5]).name == os.environ['GATE_PROBE_FAIL'] else 0)\n"
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
        ["-m", "pytest", "-q", "-ra", "--capture=tee-sys", path]
        for path in sorted(tests)
    ]
    for entry in observed:
        native = platform == "darwin" and "test_note_" in entry["args"][5]
        backend = (
            "windows" if platform == "win32" else "cocoa" if native else "offscreen"
        )
        assert entry["qt"] == backend
        assert entry["jobs"] == ("1" if native or platform == "win32" else "2")


# A stand-in interpreter for the gate's own .venv bootstrap. It reports the
# version it was written with, creates a stub environment for ``-m venv``,
# records ``-m pip install`` and every test file it is asked to run, and
# passes Ruff and mypy. Nothing real is installed or executed.
_STUB = """\
import json, os, pathlib, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ["STUB_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps({"exe": os.environ["STUB_EXE"], "args": args}) + "\\n")
if args[:1] == ["-c"]:
    if "version_info" in args[1]:
        print(os.environ["STUB_VERSION"])
    elif "sys.platform" in args[1]:
        print("linux")
    elif "samefile(sys.prefix" in args[1]:
        sys.exit(0 if os.environ.get("STUB_VENV") else 1)
    elif "sys.prefix" in args[1]:
        print("/stub/base/prefix")
    elif "import jsonschema, mypy" in args[1]:
        installed = pathlib.Path.cwd() / ".venv" / "installed"
        sys.exit(0 if os.environ.get("STUB_VENV") and installed.exists() else 1)
elif args[:2] == ["-m", "venv"]:
    target = pathlib.Path(args[2]) / "bin" / "python"
    target.parent.mkdir(parents=True)
    target.write_text(
        pathlib.Path(os.environ["STUB_EXE"]).read_text(encoding="utf-8")
        .replace("STUB_VENV= ", "STUB_VENV=1 ")
        .replace(os.environ["STUB_EXE"], str(target)),
        encoding="utf-8",
    )
    target.chmod(0o755)
elif args[:3] == ["-m", "pip", "install"]:
    assert os.environ.get("STUB_VENV"), "dependencies must go into the .venv"
    (pathlib.Path.cwd() / ".venv" / "installed").touch()
elif args[:2] in (["-m", "ruff"], ["-m", "mypy"], ["-m", "pytest"]):
    pass
else:
    raise AssertionError(args)
"""

_NAMES = ("python3.13", "python3.12", "python3", "python")


def _write_stub(
    path: Path, probe: Path, log: Path, version: str, *, venv: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/usr/bin/env bash\n"
        f"STUB_VENV={'1' if venv else ''} STUB_EXE={shlex.quote(path.as_posix())} "
        f"STUB_VERSION={shlex.quote(version)} STUB_LOG={shlex.quote(log.as_posix())} "
        f"exec {shlex.quote(Path(sys.executable).as_posix())} "
        f'{shlex.quote(probe.as_posix())} "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _bootstrap_tree(tmp_path: Path, versions: dict[str, str]):
    if sys.platform == "win32":
        pytest.skip("the stub interpreters are POSIX shell scripts")
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("the shell gate requires Bash")
    root = Path(__file__).resolve().parents[1]
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    for name in ("check.sh", "run_test_files.sh"):
        shutil.copyfile(root / "scripts" / name, tree / "scripts" / name)
    (tree / "pyproject.toml").write_text(
        '[project]\nname = "probe"\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    workflow = tree / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs: {}\n", encoding="utf-8")
    (tree / "tests").mkdir()
    (tree / "tests" / "test_probe.py").touch()
    validator = tmp_path / "contract" / "scripts" / "validate.py"
    validator.parent.mkdir(parents=True)
    validator.touch()
    probe = tmp_path / "python_probe.py"
    probe.write_text(_STUB, encoding="utf-8")
    log = tmp_path / "calls.jsonl"
    log.touch()
    bin_dir = tmp_path / "bin"
    for name, version in versions.items():
        _write_stub(bin_dir / name, probe, log, version)
    home = tmp_path / "home"
    home.mkdir()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHON_BIN", "VIRTUAL_ENV")
    }
    environment.update(
        PATH=os.pathsep.join((bin_dir.as_posix(), os.environ.get("PATH", ""))),
        HOME=home.as_posix(),
        FACTORY_MACHINE_CONTRACT_REPO=validator.parents[1].as_posix(),
        CHECK_JOBS="1",
    )

    def run(*, without: tuple[str, ...] = ()):
        result = subprocess.run(
            [bash, "scripts/check.sh"],
            cwd=tree,
            env={
                key: value for key, value in environment.items() if key not in without
            },
            capture_output=True,
            text=True,
            timeout=30,
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        log.write_text("")
        return result, calls

    return tree, bin_dir, run


def test_gate_bootstraps_a_local_venv_from_a_supported_interpreter(tmp_path):
    # The first names on PATH are too old; the gate must pass over them.
    tree, bin_dir, run = _bootstrap_tree(
        tmp_path,
        {
            "python3.13": "3.11",
            "python3.12": "3.10",
            "python3": "3.12",
            "python": "3.9",
        },
    )
    venv_python = (tree / ".venv" / "bin" / "python").as_posix()

    result, calls = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Creating .venv with {bin_dir.as_posix()}/python3 (Python 3.12)" in (
        result.stdout
    )
    assert {
        "exe": (bin_dir / "python3").as_posix(),
        "args": ["-m", "venv", str(tree / ".venv")],
    } in calls
    assert [call["exe"] for call in calls if call["args"][:2] == ["-m", "pip"]] == [
        venv_python
    ]
    assert {
        call["exe"]
        for call in calls
        if call["args"][:2] in (["-m", "pytest"], ["-m", "mypy"])
    } == {venv_python}

    # A valid .venv is reused, and its extras stay installed while
    # pyproject.toml is unchanged.
    result, calls = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Creating .venv" not in result.stdout
    assert not [
        call for call in calls if call["args"][:2] in (["-m", "venv"], ["-m", "pip"])
    ]

    # A dependency change reinstalls the extras into the same .venv.
    with (tree / "pyproject.toml").open("a", encoding="utf-8") as handle:
        handle.write("# changed\n")
    result, calls = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert [call["exe"] for call in calls if call["args"][:2] == ["-m", "pip"]] == [
        venv_python
    ]


def test_gate_refuses_a_local_venv_from_an_unsupported_interpreter(tmp_path):
    tree, _, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.13"))
    stale = tree / ".venv" / "bin" / "python"
    _write_stub(stale, tmp_path / "python_probe.py", tmp_path / "calls.jsonl", "3.10")

    result, calls = run()
    assert result.returncode == 1
    assert "runs Python 3.10, but the project requires >=3.12" in result.stderr
    assert "Remove .venv so the gate can recreate it, or set PYTHON_BIN." in (
        result.stderr
    )
    # Only the version probe ran: nothing was created or installed.
    assert [call["args"][0] for call in calls] == ["-c"]
    assert stale.exists()


def test_gate_names_what_it_tried_when_no_interpreter_is_supported(tmp_path):
    tree, bin_dir, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.10"))
    for directory in ("/usr/local/bin", "/opt/homebrew/bin", "/opt/conda/bin"):
        for name in _NAMES:
            candidate = Path(directory) / name
            if not os.access(candidate, os.X_OK):
                continue
            probe = subprocess.run(
                [candidate, "-c", "import sys; print(sys.version_info >= (3, 12))"],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.stdout.strip() == "True":
                pytest.skip(f"{candidate} is a supported interpreter on this host")

    result, calls = run()
    assert result.returncode == 1
    assert "no Python interpreter satisfies requires-python >=3.12." in result.stderr
    for name in _NAMES:
        assert f"[check]   {bin_dir.as_posix()}/{name} (3.10)" in result.stderr
    assert "Install Python 3.12 or newer, or set PYTHON_BIN." in result.stderr
    assert not (tree / ".venv").exists()
    assert not [call for call in calls if call["args"][:1] != ["-c"]]


def test_gate_bootstraps_without_home(tmp_path):
    tree, bin_dir, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.13"))

    result, _ = run(without=("HOME",))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tree / ".venv" / "bin" / "python").exists()


def _assert_linked_venv_refused(result, calls, link: Path) -> None:
    assert result.returncode == 1
    assert f"{link} is a symbolic link to " in result.stderr
    assert "Remove the link so the gate can create .venv here" in result.stderr
    # Nothing ran through or into the linked environment.
    assert calls == []
    assert link.is_symlink()


def test_gate_refuses_a_linked_venv_and_leaves_its_target_alone(tmp_path):
    tree, _, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.13"))
    shared = tmp_path / "other-checkout" / ".venv"
    _write_stub(
        shared / "bin" / "python",
        tmp_path / "python_probe.py",
        tmp_path / "calls.jsonl",
        "3.13",
        venv=True,
    )
    link = tree / ".venv"
    link.symlink_to(shared, target_is_directory=True)

    result, calls = run()
    _assert_linked_venv_refused(result, calls, link)
    assert sorted(path.name for path in shared.iterdir()) == ["bin"]


def test_gate_refuses_a_broken_venv_link_without_removing_it(tmp_path):
    tree, _, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.13"))
    link = tree / ".venv"
    link.symlink_to(tmp_path / "missing", target_is_directory=True)

    result, calls = run()
    _assert_linked_venv_refused(result, calls, link)
    assert not (tmp_path / "missing").exists()


def test_gate_refuses_a_venv_whose_python_runs_from_elsewhere(tmp_path):
    tree, _, run = _bootstrap_tree(tmp_path, dict.fromkeys(_NAMES, "3.13"))
    # A supported interpreter placed in .venv that is not a virtual
    # environment rooted there, such as a copied or linked base Python.
    _write_stub(
        tree / ".venv" / "bin" / "python",
        tmp_path / "python_probe.py",
        tmp_path / "calls.jsonl",
        "3.13",
    )

    result, calls = run()
    assert result.returncode == 1
    assert "runs from /stub/base/prefix, not from " in result.stderr
    assert not [call for call in calls if call["args"][:1] == ["-m"]]
