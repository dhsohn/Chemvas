"""Combine one isolated test run and report line and branch coverage separately."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from coverage import Coverage


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
    rdkit = "installed" if importlib.util.find_spec("rdkit") else "not installed"
    summary = (
        f"Coverage: {scope}; tests {outcome}; RDKit {rdkit}\n\n"
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
