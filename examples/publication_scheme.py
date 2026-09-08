"""Build two synthetic, editable figures using only public Chemvas commands.

Run with the Python environment in which Chemvas is installed. This is an
illustrative drawing recipe, not chemical evidence or a user-document converter.
All generated files go into a NEW directory; existing outputs are never reused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

# One example print profile, not universal journal defaults. Qt resolves point
# fonts to device pixels; final exports therefore include measured font reports.
BOND_UNITS = 40.0
BOND_MM = 5.0
BODY_FONT = 17
SCRIPT_FONT = (
    22  # Qt reduces a native sub/superscript run again; leave rounding margin.
)
RENDERER_METRIC = BODY_FONT * 20.0 / 12.0
MM_PER_UNIT = BOND_MM / BOND_UNITS


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: object) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "chemvas", *(str(arg) for arg in args)],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(
            f"Chemvas command failed ({args[0]}): {result.stderr or result.stdout}"
        )
    return json.loads(result.stdout)


def compose(directory: Path, name: str, payload: dict) -> Path:
    request = directory / f"{name}.composition.json"
    output = directory / f"{name}.chemvas"
    write_json(
        request, {"format": "chemvas-document-composition", "version": 1, **payload}
    )
    command("compose-document", request, "--output", output)
    return output


def template_fragment(directory: Path) -> tuple[list, list, list]:
    seed = compose(
        directory,
        "seed",
        {
            "atoms": [],
            "bonds": [],
            "settings": {"bond_length_px": BOND_UNITS},
        },
    )
    request = directory / "benzene.template.json"
    write_json(
        request,
        {
            "format": "chemvas-template-insertion",
            "version": 1,
            "source_sha256": sha256(seed),
            "ring_size": 6,
            "style": "benzene",
            "position": [-100, -60],
            "anchor": {"kind": "free"},
        },
    )
    ring = directory / "benzene.chemvas"
    command("insert-template", seed, "--request", request, "--output", ring)
    graph = command("inspect-document", ring)
    atoms = graph["atoms"]
    center = [sum(atom[key] for atom in atoms) / 6 for key in ("x", "y")]
    reference = max(atoms, key=lambda atom: (atom["x"], -atom["y"]))
    dx, dy = reference["x"] - center[0], reference["y"] - center[1]
    length = math.hypot(dx, dy)
    dx, dy = dx / length * BOND_UNITS, dy / length * BOND_UNITS
    operations = []
    for atom_id, element, factor in ((6, "O", 1), (7, "Me", 2)):
        operations.append(
            {
                "op": "add_atom",
                "atom_id": atom_id,
                "element": element,
                "x": reference["x"] + factor * dx,
                "y": reference["y"] + factor * dy,
                "color": "#000000",
                "explicit_label": True,
            }
        )
    for a, b in ((reference["id"], 6), (6, 7)):
        operations.append(
            {
                "op": "add_bond",
                "a": a,
                "b": b,
                "order": 1,
                "style": "single",
                "color": "#000000",
            }
        )
    operations.append(
        {
            "op": "set_terminal_angle",
            "pivot_id": 6,
            "reference_id": reference["id"],
            "terminal_id": 7,
            "angle_degrees": 120,
        }
    )
    patch = directory / "methoxy.patch.json"
    write_json(
        patch,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": sha256(ring),
            "operations": operations,
        },
    )
    fragment = directory / "methoxy.chemvas"
    command("apply-patch", ring, patch, "--output", fragment)
    graph = command("inspect-document", fragment)
    # This seed is created above and contains only this graph and ring metadata.
    # inspect-document is a graph inventory, not a lossless document serializer.
    # Preserve native ring membership: bonds alone omit inner-double-bond context.
    native = json.loads(fragment.read_text(encoding="utf-8"))
    fills = [
        {key: fill[key] for key in ("atom_ids", "color", "alpha")}
        for fill in native["state"]["ring_fills"]
    ]
    atoms = [
        {
            key: atom[key]
            for key in ("id", "element", "x", "y", "color", "explicit_label")
        }
        for atom in graph["atoms"]
    ]
    return atoms, graph["bonds"], fills


def label(index: int) -> dict:
    return {
        "x": 0,
        "y": 240,
        "style": {"font_size": BODY_FONT},
        "runs": [
            {"text": "A"},
            {
                "text": str(index + 1),
                "style": {
                    "vertical_align": "sub",
                    "font_size": SCRIPT_FONT,
                },
            },
            {
                "text": "a",
                "style": {
                    "vertical_align": "super",
                    "font_size": SCRIPT_FONT,
                },
            },
        ],
    }


def figure(directory: Path, name: str, fragment: tuple, multipart: bool) -> dict:
    base_atoms, base_bonds, base_fills = fragment
    atoms, bonds, fills = [], [], []
    for copy_index in range(3 if multipart else 2):
        offset = len(atoms)
        tx = copy_index * 140
        ty = -25 if copy_index == 2 else 0
        atoms.extend(
            {
                **atom,
                "id": atom["id"] + offset,
                "x": atom["x"] + tx,
                "y": atom["y"] + ty,
            }
            for atom in base_atoms
        )
        bonds.extend(
            {**bond, "a": bond["a"] + offset, "b": bond["b"] + offset}
            for bond in base_bonds
        )
        fills.extend(
            {**fill, "atom_ids": [i + offset for i in fill["atom_ids"]]}
            for fill in base_fills
        )
    blocks = [
        {"atoms": list(range(8)), "captions": [0]},
        {"atoms": list(range(8, len(atoms))), "captions": [1]},
    ]
    source = compose(
        directory,
        f"{name}-source",
        {
            "atoms": atoms,
            "bonds": bonds,
            "ring_fills": fills,
            "notes": [label(0), label(1)],
            "settings": {
                "bond_length_px": RENDERER_METRIC,
                "text_font_size": BODY_FONT,
                "text_font_family": "Arial",
            },
        },
    )
    arranged = directory / f"{name}-arranged.chemvas"
    request = directory / f"{name}-arrange.json"
    write_json(
        request,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": sha256(source),
            "gap": 20,
            "caption_gap": 28,
            "rows": [{"blocks": blocks}],
        },
    )
    command("layout-document", source, "--layout", request, "--output", arranged)
    if multipart:
        blocks[1]["parts"] = [list(range(8, 16)), list(range(16, 24))]
    request = directory / f"{name}-align-y.json"
    write_json(
        request,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "mode": "align-y",
            "source_sha256": sha256(arranged),
            "rows": [{"blocks": blocks, "reference_blocks": [0]}],
        },
    )
    final = directory / f"{name}.chemvas"
    alignment = command(
        "layout-document", arranged, "--layout", request, "--output", final
    )
    write_json(directory / f"{name}-alignment-report.json", alignment)
    qa = command("check-layout", final)
    write_json(directory / f"{name}-layout-report.json", qa)
    # Probe the padded export box. The existing ACS preset uses 14.4 pt per
    # renderer bond metric. Derive each figure's width from ONE physical scale,
    # never stretch every figure to the same width or shrink a long pathway.
    probe = command(
        "render-document", final, "--output", directory / f"{name}-probe.svg"
    )
    scene_width = probe["width_points"] / (14.4 / RENDERER_METRIC)
    width_mm = scene_width * MM_PER_UNIT
    outputs = {}
    for extension in ("svg", "png"):
        path = directory / f"{name}.{extension}"
        report = command(
            "render-document",
            final,
            "--output",
            path,
            "--width-mm",
            width_mm,
            "--max-height-mm",
            105,
            "--min-font-pt",
            6,
            "--dpi",
            600,
        )
        write_json(directory / f"{name}-{extension}-report.json", report)
        outputs[extension] = report
    return {
        "document": final.name,
        "source_sha256": sha256(final),
        "embed_width_mm": width_mm,
        "exports": outputs,
    }


def build(directory: Path) -> dict:
    directory.mkdir(parents=False, exist_ok=False)
    fragment = template_fragment(directory)
    figures = [
        figure(directory, "pair", deepcopy(fragment), False),
        figure(directory, "independent-parts", deepcopy(fragment), True),
    ]
    manifest = {
        "format": "chemvas-publication-example",
        "version": 1,
        "synthetic_example_only": True,
        "bond_units": BOND_UNITS,
        "bond_mm": BOND_MM,
        "mm_per_unit": MM_PER_UNIT,
        "body_font_native_pt": BODY_FONT,
        "script_font_native_pt": SCRIPT_FONT,
        "figure_height_limit_mm": 105,
        "figures": figures,
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
        parser.exit(2, f"publication recipe: {exc}\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
