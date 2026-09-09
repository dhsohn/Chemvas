"""Draw two complete, symbolic comparison rows through public Chemvas commands.

R1–R4 are abstract fragment labels, not specified molecules. The two explicitly
authored bond exchanges are drawing examples, not reaction or selectivity claims.
Outputs are editable native documents plus SVG/PNG at one physical scale.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from publication_scheme import command, compose, document_command, sha256, write_json

BOND_UNITS = 20.0
BOND_MM = 5.0
MM_PER_UNIT = BOND_MM / BOND_UNITS
BODY_FONT = 10
SCRIPT_FONT = 13
RENDERER_METRIC = BODY_FONT * 20.0 / 12.0
WIDTH_LIMIT_MM = 85.0
HEIGHT_LIMIT_MM = 100.0


def caption(text: str, index: int) -> dict:
    return {
        "x": 0,
        "y": 60,
        "style": {"font_size": BODY_FONT},
        "runs": [
            {"text": text},
            {
                "text": str(index),
                "style": {"vertical_align": "sub", "font_size": SCRIPT_FONT},
            },
        ],
    }


def composition() -> tuple[dict, list[dict]]:
    atoms, bonds, notes, rows, arrows = [], [], [], [], []
    # Every side contains every fragment once. Connectivity is explicitly supplied;
    # the layout engine neither predicts these products nor infers reaction rows.
    products = ((1, 3, 2, 4), (1, 4, 2, 3))
    for row_index, product in enumerate(products):
        blocks = []
        for column, fragments in enumerate(((1, 2, 3, 4), product)):
            offset = len(atoms)
            x, y = column * 210.0, row_index * 120.0
            for local_id, fragment in enumerate(fragments):
                atoms.append(
                    {
                        "id": offset + local_id,
                        "element": f"R{fragment}",
                        "x": x + (0, BOND_UNITS, 56, 56 + BOND_UNITS)[local_id],
                        "y": y,
                        "explicit_label": True,
                        "color": "#000000",
                    }
                )
            bonds.extend(
                {
                    "a": offset + a,
                    "b": offset + b,
                    "order": 1,
                    "style": "single",
                    "color": "#000000",
                }
                for a, b in ((0, 1), (2, 3))
            )
            plus = len(notes)
            notes.append(
                {
                    "x": x + 33,
                    "y": y - 9,
                    "text": "+",
                    "style": {"font_size": BODY_FONT},
                }
            )
            label = len(notes)
            notes.append(caption("Input" if column == 0 else "Output", row_index + 1))
            blocks.append(
                {
                    "atoms": list(range(offset, offset + 4)),
                    "items": [["notes", plus]],
                    "captions": [label],
                }
            )
        arrows.append(
            {
                "kind": "arrow",
                "start": [120, row_index * 120],
                "end": [175, row_index * 120],
                "color": "#000000",
                "labels": {"above": f"case {row_index + 1}", "below": "symbolic only"},
            }
        )
        rows.append(
            {"column_group": "comparison", "blocks": blocks, "arrows": [row_index]}
        )
    return (
        {
            "atoms": atoms,
            "bonds": bonds,
            "notes": notes,
            "arrows": arrows,
            "settings": {
                "bond_length_px": RENDERER_METRIC,
                "text_font_size": BODY_FONT,
                "text_font_family": "Arial",
            },
        },
        rows,
    )


def build(directory: Path) -> dict:
    directory.mkdir(parents=False, exist_ok=False)
    payload, rows = composition()
    source = compose(directory, "comparison-source", payload)
    request = directory / "comparison-layout.json"
    write_json(
        request,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": sha256(source),
            "rows": rows,
            "gap": 10,
            "row_gap": 24,
            "caption_gap": 12,
            "caption_alignment": "structure",
            "arrow_color": "#000000",
        },
    )
    final = directory / "comparison.chemvas"
    layout = command("layout-document", source, "--layout", request, "--output", final)
    write_json(directory / "comparison-layout-report.json", layout)
    write_json(directory / "comparison-graph.json", command("inspect-document", final))
    # A warning is a nonzero exit, so command() stops before rendering. Passing
    # collision checks still does not establish visual or scientific suitability.
    source_sha256 = sha256(final)
    qa = document_command("check-layout", final, source_sha256)
    layout_report = directory / "comparison-check.json"
    write_json(layout_report, qa)
    probe = document_command(
        "render-document",
        final,
        source_sha256,
        "--output",
        directory / "comparison-probe.svg",
    )
    scene_width = probe["width_points"] / (14.4 / RENDERER_METRIC)
    width_mm = scene_width * MM_PER_UNIT
    if width_mm > WIDTH_LIMIT_MM:
        raise ValueError(
            f"drawing needs {width_mm:.3f} mm; reorganize it, do not shrink it"
        )
    exports = {}
    for extension in ("svg", "png"):
        path = directory / f"comparison.{extension}"
        report = document_command(
            "render-document",
            final,
            source_sha256,
            "--output",
            path,
            "--width-mm",
            width_mm,
            "--max-height-mm",
            HEIGHT_LIMIT_MM,
            "--min-font-pt",
            6,
            "--dpi",
            600,
        )
        write_json(directory / f"comparison-{extension}-report.json", report)
        exports[extension] = report
    manifest = {
        "format": "chemvas-publication-comparison",
        "version": 1,
        "synthetic_example_only": True,
        "document": final.name,
        "source_sha256": source_sha256,
        "layout_check": {"report": layout_report.name, "sha256": sha256(layout_report)},
        "bond_units": BOND_UNITS,
        "bond_mm": BOND_MM,
        "mm_per_unit": MM_PER_UNIT,
        "body_font_native_pt": BODY_FONT,
        "script_font_native_pt": SCRIPT_FONT,
        "embed_width_mm": width_mm,
        "width_limit_mm": WIDTH_LIMIT_MM,
        "height_limit_mm": HEIGHT_LIMIT_MM,
        "exports": exports,
    }
    write_json(directory / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new output directory (parent must exist)",
    )
    args = parser.parse_args()
    try:
        manifest = build(args.output_dir.resolve())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        parser.exit(2, f"publication comparison: {exc}\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
