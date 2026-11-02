"""Combine one isolated test run and report line and branch coverage separately."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from coverage import Coverage
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR


def _commit_receipt(root: Path) -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "Commit: git unavailable"
    dirty = "dirty" if status.strip() else "clean"
    return f"Commit: {sha}; working tree {dirty}"


def main() -> None:
    output = Path(sys.argv[1]).resolve()
    scope = sys.argv[2]
    outcome = "passed" if sys.argv[3] == "0" else "FAILED (partial execution)"
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    coverage = Coverage(
        config_file=str(root / "pyproject.toml"), data_file=str(output / ".coverage")
    )
    coverage.combine(strict=True)
    coverage.save()
    coverage.json_report(outfile=str(output / "coverage.json"))
    coverage.html_report(directory=str(output / "html"), title=scope)
    with (output / "coverage.txt").open("w", encoding="utf-8") as report:
        coverage.report(file=report)
    totals = json.loads((output / "coverage.json").read_text(encoding="utf-8"))[
        "totals"
    ]
    python_version = sys.version.split()[0]
    summary = (
        f"Coverage: {scope}; tests {outcome}\n"
        f"{_commit_receipt(root)}\n"
        f"Python {python_version}; PyQt6 {PYQT_VERSION_STR}; Qt {QT_VERSION_STR}\n\n"
        "| Metric | Covered / total | Percent |\n"
        "| --- | ---: | ---: |\n"
    )
    for label, covered, total in (
        ("Lines", totals["covered_lines"], totals["num_statements"]),
        ("Branches", totals["covered_branches"], totals["num_branches"]),
    ):
        percent = f"{100 * covered / total:.2f}%" if total else "n/a"
        summary += f"| {label} | {covered} / {total} | {percent} |\n"
    summary += (
        "\nHTML Coverage columns combine lines and branches. "
        "Selected test files are not a full-suite baseline.\n"
    )
    (output / "SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"[coverage] Reports: {output}")
    if step_summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(step_summary).open("a", encoding="utf-8") as report:
            report.write(summary + "\n")


if __name__ == "__main__":
    main()
