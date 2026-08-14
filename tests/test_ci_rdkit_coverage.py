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
from pathlib import Path

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


def _gated_test_files() -> set[str]:
    gated = set()
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            # This guard names the patterns without being gated on RDKit.
            continue
        src = path.read_text(encoding="utf-8")
        if any(pattern in src for pattern in _GATE_PATTERNS):
            gated.add(f"tests/{path.name}")
    return gated


def _rdkit_job_files() -> set[str]:
    src = CI_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^  rdkit-smoke:.*?(?=^  \w[\w-]*:|\Z)", src)
    assert match, "could not find the rdkit-smoke job in .github/workflows/ci.yml"
    listed = set(re.findall(r"tests/test_\w+\.py", match.group(0)))
    # The job's comment names this guard; that reference is not a run entry.
    return listed - {f"tests/{Path(__file__).name}"}


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
