"""CI <-> test-tree synchronization guard for real-RDKit coverage.

The main CI test job installs the project without RDKit, so every test gated
on a real RDKit import skips there. The `rdkit-smoke` job installs RDKit and
is the only place those tests can execute — but it used to select tests by
the `real_rdkit_smoke` name prefix inside one file, so a gated test without
the prefix, or in any other file, ran in no CI job at all. That hole was
real: three consecutive fixes shipped with regression tests that CI never
executed, and two whole modules skipped in every run.

Following test_docs_sync: derive the expected set from the tree and assert
the workflow *contains* it, in both directions, so the file list in ci.yml
and the gates in tests/ cannot drift apart silently.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# The gate spellings this repository uses for "needs a real RDKit". A new
# spelling must be added here, which is the point: the guard makes adding a
# gated test without CI coverage a visible decision instead of a silent one.
_GATE_PATTERNS = (
    "_RealChem",  # try: from rdkit import Chem as _RealChem / skipUnless
    'find_spec("rdkit")',  # module-level pytestmark skipif
    'importorskip("rdkit")',
)
_SHELL_COMMAND_SEPARATORS = frozenset((";", "&&", "||", "|", "&"))


def _shell_tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _shell_commands(source: str) -> list[list[str]]:
    """Return argv-like logical lines from the repository's shell subset."""
    commands: list[list[str]] = []
    pending: list[str] = []
    for raw in source.splitlines():
        stripped = raw.strip()
        if not stripped and not pending:
            continue
        continued = stripped.endswith("\\")
        if continued:
            stripped = stripped[:-1].rstrip()
        pending.append(stripped)
        if continued:
            continue
        try:
            tokens = _shell_tokens(" ".join(pending))
        except ValueError as exc:
            raise AssertionError("could not parse a workflow run command") from exc
        if tokens:
            commands.append(tokens)
        pending = []
    if pending:
        try:
            tokens = _shell_tokens(" ".join(pending))
        except ValueError as exc:
            raise AssertionError("could not parse a workflow run command") from exc
        if tokens:
            commands.append(tokens)
    return commands


def _folded_block_source(lines: list[str]) -> str:
    """Approximate the simple, non-indented YAML folded scalars used here."""
    paragraphs: list[str] = []
    pending: list[str] = []
    for line in lines:
        if line:
            pending.append(line)
        elif pending:
            paragraphs.append(" ".join(pending))
            pending = []
    if pending:
        paragraphs.append(" ".join(pending))
    return "\n".join(paragraphs)


def _run_blocks(source: str) -> list[list[list[str]]]:
    """Return parsed commands grouped by YAML block-scalar ``run`` step.

    This is deliberately narrower than a YAML parser: the workflow contract
    uses simple shell ``run: |``/``run: >`` blocks. Both a mapping key below a
    named step and the valid inline-list ``- run:`` form are accepted.
    """
    lines = source.splitlines()
    blocks: list[list[list[str]]] = []
    index = 0
    while index < len(lines):
        header = re.match(
            r"^(?P<indent>\s*)(?:-\s+)?run:\s*(?P<style>[|>])[-+]?\s*$",
            lines[index],
        )
        if header is None:
            index += 1
            continue
        header_indent = len(header.group("indent"))
        index += 1
        block_lines: list[str] = []
        while index < len(lines):
            raw = lines[index]
            if raw.strip():
                indentation = len(raw) - len(raw.lstrip())
                if indentation <= header_indent:
                    break
            block_lines.append(raw.strip())
            index += 1
        block_source = (
            "\n".join(block_lines)
            if header.group("style") == "|"
            else _folded_block_source(block_lines)
        )
        blocks.append(_shell_commands(block_source))
    return blocks


def _run_block_commands(source: str) -> list[list[str]]:
    return [command for block in _run_blocks(source) for command in block]


def _direct_runner_arguments(command: list[str]) -> list[str] | None:
    """Return args only for a runner invoked as this logical line's command."""
    if not command:
        return None
    if command[0].endswith("scripts/run_test_files.sh"):
        runner_index = 0
    elif (
        len(command) > 1
        and Path(command[0]).name in {"bash", "sh"}
        and command[1].endswith("scripts/run_test_files.sh")
    ):
        runner_index = 1
    else:
        return None
    arguments: list[str] = []
    for token in command[runner_index + 1 :]:
        if token in _SHELL_COMMAND_SEPARATORS:
            break
        arguments.append(token)
    return arguments


def _test_discovery_find_argv(command: list[str]) -> list[str] | None:
    """Extract the direct or mapfile-process-substitution test-tree ``find``."""
    if command[:2] in (["find", "tests"], ["find", "./tests"]):
        find_index = 0
    elif command and command[0] == "mapfile":
        try:
            find_index = next(
                index + 2
                for index in range(len(command) - 2)
                if command[index : index + 3] == ["<", "<(", "find"]
            )
        except StopIteration:
            return None
        if find_index + 1 >= len(command) or command[find_index + 1] not in {
            "tests",
            "./tests",
        }:
            return None
    else:
        return None
    argv: list[str] = []
    for token in command[find_index:]:
        if token in _SHELL_COMMAND_SEPARATORS or token == ")":
            break
        argv.append(token)
    return argv


def _is_recursive_test_discovery(argv: list[str]) -> bool:
    if argv[:4] not in (
        ["find", "tests", "-name", "test_*.py"],
        ["find", "./tests", "-name", "test_*.py"],
    ):
        return False
    index = 4
    while index < len(argv):
        if (
            argv[index : index + 2] != ["!", "-name"]
            or index + 2 >= len(argv)
            or re.fullmatch(r"test_[^/]+\.py", argv[index + 2]) is None
        ):
            return False
        index += 3
    return True


def _is_test_path_argument(token: str) -> bool:
    path = Path(token)
    return (
        token.startswith("tests/")
        and path.name.startswith("test_")
        and path.suffix == ".py"
    )


def _gated_test_files() -> set[str]:
    gated = set()
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.resolve() == Path(__file__).resolve():
            # This guard names the patterns without being gated on RDKit.
            continue
        src = path.read_text(encoding="utf-8")
        if any(pattern in src for pattern in _GATE_PATTERNS):
            gated.add(path.relative_to(ROOT).as_posix())
    return gated


def _rdkit_job_files() -> set[str]:
    src = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^  rdkit-smoke:.*?(?=^  \w[\w-]*:|\Z)", src)
    assert match, "could not find the rdkit-smoke job in .github/workflows/ci.yml"
    listed: set[str] = set()
    for block in _run_blocks(match.group(0)):
        # The census runner owns a dedicated step and must be its first command.
        # This deliberately excludes examples passed to echo, heredoc bodies,
        # later commands, and short-circuited ``false && bash ...`` text.
        arguments = _direct_runner_arguments(block[0]) if block else None
        if arguments is None:
            continue
        listed.update(token for token in arguments if _is_test_path_argument(token))
    return listed


def test_every_rdkit_gated_test_file_runs_in_the_rdkit_ci_job():
    gated = _gated_test_files()
    assert gated, "expected at least one RDKit-gated test file in tests/"
    missing = sorted(gated - _rdkit_job_files())
    assert not missing, (
        "These test files gate tests on a real RDKit, but the rdkit-smoke job "
        f"in ci.yml does not run them, so those tests run in no CI job: {missing}. "
        "Add each file to the job's run step."
    )


def test_the_rdkit_ci_job_lists_only_gated_files():
    stale = sorted(_rdkit_job_files() - _gated_test_files())
    assert not stale, (
        "The rdkit-smoke job lists test files that contain no real-RDKit gate: "
        f"{stale}. Remove them from ci.yml, or gate their tests, so the list "
        "stays an honest census."
    )


def _module_gated_test_files() -> set[str]:
    """Files whose every test gates on RDKit via a module-level pytestmark.

    In the main CI job, which installs no RDKit, such a file runs zero tests,
    so the job excludes it. A file with only per-test gates stays: its
    ungated tests are what the main job's coverage and 3.12 run exercise.
    """
    module_gated = set()
    for path in sorted(TESTS.rglob("test_*.py")):
        if path.resolve() == Path(__file__).resolve():
            # This guard mentions the gate spellings without carrying one.
            continue
        src = path.read_text(encoding="utf-8")
        if "pytestmark" in src and 'find_spec("rdkit")' in src:
            module_gated.add(path.relative_to(ROOT).as_posix())
    return module_gated


def _main_job_excluded_files() -> set[str]:
    src = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^  test:.*?(?=^  \w[\w-]*:|\Z)", src)
    assert match, "could not find the test job in .github/workflows/ci.yml"
    excluded_names = _main_job_exclusion_names(match.group(0))
    return {
        path.relative_to(ROOT).as_posix()
        for path in TESTS.rglob("test_*.py")
        if path.name in excluded_names
    }


def _main_job_exclusion_names(source: str | None = None) -> set[str]:
    if source is None:
        source = CI_WORKFLOW.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  test:.*?(?=^  \w[\w-]*:|\Z)", source)
        assert match, "could not find the test job in .github/workflows/ci.yml"
        source = match.group(0)
    excluded: set[str] = set()
    for block in _run_blocks(source):
        if not block:
            continue
        argv = _test_discovery_find_argv(block[0])
        if argv is None:
            continue
        for index in range(2, len(argv) - 2):
            if argv[index : index + 2] != ["!", "-name"]:
                continue
            name = argv[index + 2]
            if re.fullmatch(r"test_[^/]+\.py", name):
                excluded.add(name)
    return excluded


def test_every_module_gated_file_is_excluded_from_the_main_job():
    module_gated = _module_gated_test_files()
    assert module_gated, "expected at least one module-gated RDKit test file"
    missing = sorted(module_gated - _main_job_excluded_files())
    assert not missing, (
        "These test files gate every test on RDKit at module level, so the "
        f"main job runs them for zero tests: {missing}. Exclude each from the "
        "job's find command."
    )


def test_the_main_job_excludes_only_module_gated_files():
    stale = sorted(_main_job_excluded_files() - _module_gated_test_files())
    missing_files = sorted(
        _main_job_exclusion_names() - {path.name for path in TESTS.rglob("test_*.py")}
    )
    assert not stale and not missing_files, (
        "The main test job excludes files that are not module-gated on RDKit: "
        f"{stale + missing_files}. Their ungated tests would silently leave the main job's "
        "matrix and coverage; remove the exclusions."
    )


def test_local_and_main_ci_test_discovery_is_recursive():
    local_gate = (ROOT / "scripts" / "check.sh").read_text(encoding="utf-8")
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^  test:.*?(?=^  \w[\w-]*:|\Z)", workflow)
    assert match, "could not find the test job in .github/workflows/ci.yml"

    command_sources = (
        ("local gate", _shell_commands(local_gate)),
        (
            "main CI job",
            [block[0] for block in _run_blocks(match.group(0)) if block],
        ),
    )
    for label, commands in command_sources:
        discoveries = [
            argv
            for command in commands
            if (argv := _test_discovery_find_argv(command)) is not None
        ]
        assert len(discoveries) == 1, (
            f"{label} must have exactly one executable test-tree find command"
        )
        assert _is_recursive_test_discovery(discoveries[0]), (
            f"{label} must discover test files recursively without -maxdepth"
        )


def test_nested_test_with_the_guard_basename_is_still_counted(tmp_path, monkeypatch):
    tests = tmp_path / "tests"
    nested = tests / "package" / Path(__file__).name
    nested.parent.mkdir(parents=True)
    nested.write_text(
        'pytestmark = pytest.mark.skipif(find_spec("rdkit") is None)\n',
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "TESTS", tests)

    expected = {f"tests/package/{Path(__file__).name}"}
    assert _gated_test_files() == expected
    assert _module_gated_test_files() == expected


def test_run_block_parser_accepts_inline_literal_and_folded_steps():
    source = """steps:
  - run: |
      bash scripts/run_test_files.sh tests/test_literal.py
  - run: >
      bash scripts/run_test_files.sh tests/test_folded.py
"""

    assert _run_block_commands(source) == [
        ["bash", "scripts/run_test_files.sh", "tests/test_literal.py"],
        ["bash", "scripts/run_test_files.sh", "tests/test_folded.py"],
    ]


def test_rdkit_job_comment_cannot_claim_an_unexecuted_test(tmp_path, monkeypatch):
    tests = tmp_path / "tests"
    gated = tests / "package" / "test_new_rdkit.py"
    gated.parent.mkdir(parents=True)
    gated.write_text(
        'pytestmark = pytest.mark.skipif(find_spec("rdkit") is None)\n',
        encoding="utf-8",
    )
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """jobs:
  rdkit-smoke:
    steps:
      # Covered by tests/package/test_new_rdkit.py
      - run: |
          echo no-tests-run
  next-job:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "TESTS", tests)
    monkeypatch.setitem(globals(), "CI_WORKFLOW", workflow)

    assert _gated_test_files() == {"tests/package/test_new_rdkit.py"}
    assert _rdkit_job_files() == set()


@pytest.mark.parametrize(
    "command",
    (
        "echo bash scripts/run_test_files.sh tests/package/test_new_rdkit.py",
        "false && bash scripts/run_test_files.sh tests/package/test_new_rdkit.py",
    ),
)
def test_nonexecuted_runner_text_cannot_satisfy_the_census(
    tmp_path, monkeypatch, command
):
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        f"""jobs:
  rdkit-smoke:
    steps:
      - name: No real runner
        run: |
          {command}
  next-job:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "CI_WORKFLOW", workflow)

    assert _rdkit_job_files() == set()


def test_path_in_a_later_shell_command_is_not_a_runner_argument(tmp_path, monkeypatch):
    tests = tmp_path / "tests"
    gated = tests / "package" / "test_new_rdkit.py"
    gated.parent.mkdir(parents=True)
    gated.write_text(
        'pytestmark = pytest.mark.skipif(find_spec("rdkit") is None)\n',
        encoding="utf-8",
    )
    workflow = tmp_path / "ci.yml"
    workflow.write_text(
        """jobs:
  rdkit-smoke:
    steps:
      - run: |
          bash scripts/run_test_files.sh --python python; echo tests/package/test_new_rdkit.py
  next-job:
    runs-on: ubuntu-latest
""",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "TESTS", tests)
    monkeypatch.setitem(globals(), "CI_WORKFLOW", workflow)

    assert _rdkit_job_files() == set()


def test_main_job_comment_cannot_create_an_exclusion():
    source = """  test:
    steps:
      - run: |
          find tests -name 'test_*.py' |
            sort
      # Keep an eye on ! -name 'test_not_really_excluded.py'
"""

    assert _main_job_exclusion_names(source) == set()


@pytest.mark.parametrize(
    "command",
    (
        "false && find tests -name 'test_*.py' ! -name 'test_dead.py'",
        "echo '<' '<(' find tests -name 'test_*.py' ! -name 'test_echo.py'",
    ),
)
def test_nonexecuted_find_text_cannot_create_an_exclusion(command):
    source = f"""  test:
    steps:
      - run: |
          {command}
"""

    assert _main_job_exclusion_names(source) == set()


def test_recursive_discovery_cannot_be_satisfied_by_a_comment(tmp_path, monkeypatch):
    good = "mapfile -t files < <(find tests -name 'test_*.py' | sort)\n"
    bad = (
        "# find tests -name 'test_*.py'\n"
        "mapfile -t files < <(find tests -mindepth 1 -maxdepth 1 "
        "-name 'test_*.py' | sort)\n"
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    local_gate = scripts / "check.sh"
    workflow = tmp_path / "ci.yml"
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "CI_WORKFLOW", workflow)

    for local_source, ci_source in ((bad, good), (good, bad)):
        local_gate.write_text(local_source, encoding="utf-8")
        indented_ci_source = "".join(
            f"          {line}\n" for line in ci_source.splitlines()
        )
        workflow.write_text(
            f"""jobs:
  test:
    steps:
      - run: |
{indented_ci_source}  next-job:
    runs-on: ubuntu-latest
""",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError, match="recursively without -maxdepth"):
            test_local_and_main_ci_test_discovery_is_recursive()
