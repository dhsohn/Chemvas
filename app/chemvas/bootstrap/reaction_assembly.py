from __future__ import annotations

import argparse
import hashlib
import math
import stat
import sys
from pathlib import Path

from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import atomic_create_bytes
from chemvas.features.reaction_assembly import (
    MAX_ASSEMBLE_REACTION_BYTES,
    assemble_reaction_cdxml,
)


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source = Path(args.input)
        output = Path(args.output)
        _validate_source(source)
        _validate_output(output)
        raw = _read_source(source)
        max_width_pt = args.max_width_pt
        assembled = assemble_reaction_cdxml(raw)
        if max_width_pt is not None:
            if not math.isfinite(max_width_pt) or max_width_pt <= 0:
                raise ValueError("--max-width-pt must be positive and finite")
            width = _svg_width(assembled)
            if width > max_width_pt:
                assembled = assemble_reaction_cdxml(raw, max_width_pt=max_width_pt)
                width = _svg_width(assembled)
            if width > max_width_pt:
                raise ValueError(
                    f"assembled SVG width {width:.2f} pt exceeds {max_width_pt:g} pt"
                )
        atomic_create_bytes(output, assembled)
        report = {
            "format": "chemvas-assemble-reaction-report",
            "version": 1,
            "input": str(source),
            "output": str(output),
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "output_sha256": hashlib.sha256(assembled).hexdigest(),
            "written": True,
        }
        if max_width_pt is not None:
            report["max_width_pt"] = max_width_pt
            report["svg_width_pt"] = width
        sys.stdout.write(json_text(report))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _svg_width(raw: bytes) -> float:
    from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
    from chemvas.features.cdxml_document import parse_cdxml_document
    from chemvas.ui.export.figure_export_service import FigureExportService

    state = parse_cdxml_document(raw).state
    with offscreen_document_scene(state, command="assemble-reaction") as context:
        return float(FigureExportService(context).plan_figure_export().out_w_pt)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Assemble a one-step native reaction CDXML from role references.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser(
        "assemble-reaction",
        help="layout a normalized one-step reaction and write native CDXML",
    )
    command.add_argument("input", help="normalized reaction .cdxml input")
    command.add_argument("--output", required=True, help="assembled .cdxml output path")
    command.add_argument(
        "--max-width-pt",
        type=float,
        default=None,
        help=(
            "pack the reaction row to fit within a painted SVG width (points); "
            "reject the layout when contour clearance cannot reach the limit"
        ),
    )
    return parser


def _read_source(path: Path) -> bytes:
    source_stat = path.stat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError(f"input must be a regular file: {path}")
    with path.open("rb") as stream:
        raw = stream.read(MAX_ASSEMBLE_REACTION_BYTES + 1)
    if len(raw) > MAX_ASSEMBLE_REACTION_BYTES:
        raise ValueError("reaction input exceeds the byte limit")
    if not raw:
        raise ValueError("reaction input is empty")
    return raw


def _validate_source(path: Path) -> None:
    if path.suffix.lower() != ".cdxml":
        raise ValueError("input must use the .cdxml filename extension")
    if not path.is_file():
        raise ValueError(f"input does not exist: {path}")


def _validate_output(path: Path) -> None:
    if path.suffix.lower() != ".cdxml":
        raise ValueError("output must use the .cdxml filename extension")
    if path.exists():
        raise ValueError(f"output already exists: {path}")
