#!/usr/bin/env python3
"""Render the figures embedded in the CLI, layout and publication guides.

Every figure is the output of a documented public command run on a small
synthetic input written by this script, so the pictures show exactly what the
commands do. The publication figures come from the two runnable examples.
Run with the development environment (RDKit is not needed) and an empty output
directory, review the PNGs, then copy them to ``docs/images/``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
FIGURE_WIDTH_MM = 70.0
FIGURE_DPI = 300


def chemvas(*arguments: str, cwd: Path) -> dict:
    """Run one public command and return its JSON report."""
    completed = subprocess.run(
        [sys.executable, "-m", "chemvas", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def render(document: Path, figure: Path, *, width_mm: float = FIGURE_WIDTH_MM) -> None:
    chemvas(
        "render-document",
        str(document),
        "--output",
        str(figure),
        "--width-mm",
        str(width_mm),
        "--dpi",
        str(FIGURE_DPI),
        cwd=document.parent,
    )


def source_hash(document: Path) -> str:
    return chemvas("inspect-document", str(document), cwd=document.parent)[
        "source_sha256"
    ]


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# --- AGENT_CLI.md -----------------------------------------------------------


def compose_figure(work: Path, out: Path) -> Path:
    """The minimal composition from the guide, composed and rendered."""
    composition = write_json(
        work / "scheme.json",
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {
                    "id": 0,
                    "element": "O",
                    "x": 72.0,
                    "y": 72.0,
                    "explicit_label": True,
                    "formal_charge": -1,
                },
                {"id": 1, "element": "P", "x": 92.0, "y": 72.0, "formal_charge": 1},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
            "notes": [
                {
                    "text": "Condition",
                    "x": 64.0,
                    "y": 108.0,
                    "style": {
                        "font_size": 12,
                        "font_weight": 700,
                        "italic": False,
                        "color": "#245caa",
                    },
                }
            ],
        },
    )
    document = work / "scheme.chemvas"
    chemvas("compose-document", str(composition), "--output", str(document), cwd=work)
    render(document, out / "cli-compose.png", width_mm=45.0)
    return document


def template_figure(work: Path, out: Path, document: Path) -> Path:
    """The insert-template request from the guide on the composed document."""
    request = write_json(
        work / "ring.json",
        {
            "format": "chemvas-template-insertion",
            "version": 1,
            "source_sha256": source_hash(document),
            "ring_size": 6,
            "style": "benzene",
            "position": [200, 120],
            "anchor": {"kind": "free"},
        },
    )
    added = work / "ring-added.chemvas"
    chemvas(
        "insert-template",
        str(document),
        "--request",
        str(request),
        "--output",
        str(added),
        cwd=work,
    )
    render(added, out / "cli-insert-template.png")
    return added


def patch_figure(work: Path, out: Path, document: Path) -> None:
    """A Graph Patch of the guide's shape: add an oxygen to a ring carbon and
    make that bond double."""
    inspection = chemvas("inspect-document", str(document), cwd=work)
    ring_atoms = [atom for atom in inspection["atoms"] if atom["element"] == "C"]
    pivot = max(ring_atoms, key=lambda atom: atom["x"])
    new_id = inspection["next_atom_id"]
    patch = write_json(
        work / "patch.json",
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": inspection["source_sha256"],
            "operations": [
                {
                    "op": "add_atom",
                    "atom_id": new_id,
                    "element": "O",
                    "x": pivot["x"] + 20.0,
                    "y": pivot["y"],
                    "color": "#000000",
                    "explicit_label": True,
                },
                {
                    "op": "add_bond",
                    "a": pivot["id"],
                    "b": new_id,
                    "order": 1,
                    "style": "single",
                    "color": "#000000",
                },
                {
                    "op": "update_bond",
                    "a": pivot["id"],
                    "b": new_id,
                    "changes": {"order": 2, "style": "double"},
                },
            ],
        },
    )
    revised = work / "revised.chemvas"
    chemvas(
        "apply-patch", str(document), str(patch), "--output", str(revised), cwd=work
    )
    render(document, out / "cli-apply-patch-before.png")
    render(revised, out / "cli-apply-patch-after.png")


# --- SCHEME_LAYOUT.md -------------------------------------------------------


def _chain(first_id: int, x: float, y: float) -> tuple[list[dict], list[dict]]:
    """Three carbons in a zigzag starting at (x, y)."""
    atoms = [
        {"id": first_id, "element": "C", "x": x, "y": y},
        {"id": first_id + 1, "element": "C", "x": x + 17.3, "y": y - 10.0},
        {
            "id": first_id + 2,
            "element": "O",
            "x": x + 34.6,
            "y": y,
            "explicit_label": True,
        },
    ]
    bonds = [
        {"a": first_id, "b": first_id + 1, "order": 1},
        {"a": first_id + 1, "b": first_id + 2, "order": 1},
    ]
    return atoms, bonds


def arrange_figures(work: Path, out: Path) -> None:
    """The arrange request from the guide: two structures with captions, a TS
    bracket on the second and one connecting arrow, before and after."""
    atoms_a, bonds_a = _chain(0, 0.0, 0.0)
    atoms_b, bonds_b = _chain(3, 150.0, 22.0)
    source = write_json(
        work / "arrange-source.json",
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms_a + atoms_b,
            "bonds": bonds_a + bonds_b,
            "notes": [
                {"text": "reactant", "x": -20.0, "y": 34.0},
                {"text": "0.0 kcal/mol", "x": -20.0, "y": 50.0},
                {"text": "TS", "x": 158.0, "y": 70.0},
                {"text": "+12.3 kcal/mol", "x": 158.0, "y": 86.0},
            ],
            "arrows": [{"kind": "arrow", "start": [60.0, 0.0], "end": [120.0, 0.0]}],
            "ts_brackets": [
                {
                    "bracket_kind": "square_pair",
                    "left": 140.0,
                    "top": -4.0,
                    "right": 196.0,
                    "bottom": 46.0,
                }
            ],
        },
    )
    scheme = work / "arrange-source.chemvas"
    chemvas("compose-document", str(source), "--output", str(scheme), cwd=work)
    layout = write_json(
        work / "layout.json",
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": source_hash(scheme),
            "gap": 12,
            "row_gap": 24,
            "caption_gap": 8,
            "line_gap": 4,
            "rows": [
                {
                    "blocks": [
                        {"atoms": [0, 1, 2], "captions": [0, 1], "anchor_atom": 0},
                        {
                            "atoms": [3, 4, 5],
                            "captions": [2, 3],
                            "anchor_atom": 3,
                            "items": [["ts_brackets", 0]],
                        },
                    ],
                    "arrows": [0],
                }
            ],
        },
    )
    arranged = work / "arranged.chemvas"
    chemvas(
        "layout-document",
        str(scheme),
        "--layout",
        str(layout),
        "--output",
        str(arranged),
        cwd=work,
    )
    render(scheme, out / "cli-layout-arrange-before.png")
    render(arranged, out / "cli-layout-arrange-after.png")


def align_y_figures(work: Path, out: Path) -> None:
    """The align-y request from the guide: the second block floats above the
    first and has a separate ion as its own part."""
    atoms_a, bonds_a = _chain(0, 0.0, 0.0)
    atoms_b, bonds_b = _chain(3, 110.0, -38.0)
    atoms_b.append(
        {
            "id": 6,
            "element": "Cl",
            "x": 170.0,
            "y": -60.0,
            "explicit_label": True,
            "formal_charge": -1,
        }
    )
    source = write_json(
        work / "align-source.json",
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms_a + atoms_b,
            "bonds": bonds_a + bonds_b,
            "notes": [
                {"text": "reactant", "x": -14.0, "y": 34.0},
                {"text": "product", "x": 112.0, "y": 34.0},
            ],
        },
    )
    scheme = work / "floating.chemvas"
    chemvas("compose-document", str(source), "--output", str(scheme), cwd=work)
    layout = write_json(
        work / "align-y.json",
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "mode": "align-y",
            "source_sha256": source_hash(scheme),
            "rows": [
                {
                    "reference_blocks": [0],
                    "blocks": [
                        {"atoms": [0, 1, 2], "captions": [0]},
                        {
                            "atoms": [3, 4, 5, 6],
                            "captions": [1],
                            "parts": [[3, 4, 5], [6]],
                        },
                    ],
                }
            ],
        },
    )
    aligned = work / "aligned.chemvas"
    chemvas(
        "layout-document",
        str(scheme),
        "--layout",
        str(layout),
        "--output",
        str(aligned),
        cwd=work,
    )
    render(scheme, out / "cli-layout-align-y-before.png")
    render(aligned, out / "cli-layout-align-y-after.png")


def wrap_figure(work: Path, out: Path) -> None:
    """Four blocks in one row wrapped under a ``max_row_width`` budget."""
    atoms: list[dict] = []
    bonds: list[dict] = []
    notes: list[dict] = []
    arrows: list[dict] = []
    for index in range(4):
        x = index * 110.0
        chain_atoms, chain_bonds = _chain(index * 3, x, 0.0)
        atoms += chain_atoms
        bonds += chain_bonds
        notes.append({"text": f"state {index + 1}", "x": x - 6.0, "y": 34.0})
        if index < 3:
            arrows.append(
                {"kind": "arrow", "start": [x + 52.0, 0.0], "end": [x + 96.0, 0.0]}
            )
    source = write_json(
        work / "pathway-source.json",
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms,
            "bonds": bonds,
            "notes": notes,
            "arrows": arrows,
        },
    )
    scheme = work / "pathway.chemvas"
    chemvas("compose-document", str(source), "--output", str(scheme), cwd=work)
    layout = write_json(
        work / "wrap.json",
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": source_hash(scheme),
            "max_row_width": 320,
            "rows": [
                {
                    "blocks": [
                        {"atoms": [0, 1, 2], "captions": [0]},
                        {"atoms": [3, 4, 5], "captions": [1]},
                        {"atoms": [6, 7, 8], "captions": [2]},
                        {"atoms": [9, 10, 11], "captions": [3]},
                    ],
                    "arrows": [0, 1, 2],
                }
            ],
        },
    )
    wrapped = work / "wrapped.chemvas"
    chemvas(
        "layout-document",
        str(scheme),
        "--layout",
        str(layout),
        "--output",
        str(wrapped),
        cwd=work,
    )
    render(scheme, out / "cli-layout-wrap-before.png", width_mm=110.0)
    render(wrapped, out / "cli-layout-wrap-after.png")


# --- PUBLICATION_SCHEMES.md -------------------------------------------------


def publication_figures(work: Path, out: Path) -> None:
    """The final PNGs of the two runnable publication examples."""
    for script, names in (
        ("publication_scheme.py", ("pair.png", "independent-parts.png")),
        ("publication_comparison.py", ("comparison.png",)),
    ):
        target = work / script.replace(".py", "")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "examples" / script),
                "--output-dir",
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for name in names:
            shutil.copyfile(target / name, out / f"publication-{name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "--output-dir must be empty; existing artifacts are never replaced"
        )
    work = output / "work"
    work.mkdir()
    figures = output / "figures"
    figures.mkdir()
    composed = compose_figure(work, figures)
    with_ring = template_figure(work, figures, composed)
    patch_figure(work, figures, with_ring)
    arrange_figures(work, figures)
    align_y_figures(work, figures)
    wrap_figure(work, figures)
    publication_figures(work, figures)
    for figure in sorted(figures.iterdir()):
        print(f"{figure.name}: {figure.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
