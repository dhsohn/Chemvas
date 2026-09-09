from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    MAX_GRAPHICS_RECORDS,
    graphics_record_count,
    json_text,
    offscreen_canvas,
)
from chemvas.core.document_io import read_exact_document

MAX_LAYOUT_WORK_UNITS = 10_000


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source = Path(args.document)
        _validate_source(source)
        source_bytes, document = read_exact_document(
            source, max_bytes=MAX_DOCUMENT_BYTES
        )
        graphics_records = graphics_record_count(
            cast("Mapping[str, object]", document.state)
        )
        if graphics_records > MAX_GRAPHICS_RECORDS:
            raise ValueError(
                f"input document exceeds the {MAX_GRAPHICS_RECORDS}-graphics-record layout limit"
            )
        layout_work_units = _layout_work_units(
            cast("Mapping[str, object]", document.state)
        )
        if layout_work_units > MAX_LAYOUT_WORK_UNITS:
            raise ValueError(
                f"input document exceeds the layout work limit of {MAX_LAYOUT_WORK_UNITS}"
            )
        analysis = _check_offscreen(document.state)
        report = {
            "format": "chemvas-layout-check-report",
            "version": 1,
            "source": str(source),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "chemvas_document_version": int(document.payload["version"]),
            **analysis,
        }
        sys.stdout.write(json_text(report))
        return 0 if bool(analysis["ok"]) else 1
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Check Chemvas layout without editing the document.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser(
        "check-layout",
        help="report deterministic layout warnings",
    )
    check.add_argument("document", help="input .chemvas document")
    return parser


def _validate_source(source: Path) -> None:
    if source.suffix.lower() != ".chemvas":
        raise ValueError("input must use the .chemvas filename extension")
    if not source.is_file():
        raise ValueError(f"input document does not exist: {source}")


def _layout_work_units(state: Mapping[str, object]) -> int:
    notes = state.get("notes", [])
    shapes = state.get("shapes", [])
    arrows = state.get("arrows", [])
    marks = state.get("marks", [])
    if not all(isinstance(records, list) for records in (notes, shapes, arrows, marks)):
        raise ValueError("Invalid Chemvas file.")
    model = state.get("model")
    if not isinstance(model, Mapping) or not isinstance(model.get("atoms"), Mapping):
        raise ValueError("Invalid Chemvas file.")
    bonds = model.get("bonds")
    if not isinstance(bonds, list):
        raise ValueError("Invalid Chemvas file.")
    # render_model creates no label for an implicit C. Count all other atoms,
    # including explicit C, regardless of color, clipping or derived typography.
    label_count = sum(
        1
        for atom in model["atoms"].values()
        if atom["element"].upper() != "C" or bool(atom.get("explicit_label", False))
    )
    note_count = len(cast("list[object]", notes))
    shape_count = len(cast("list[object]", shapes))
    arrow_count = len(cast("list[object]", arrows))
    arrow_label_count = sum(
        bool(text)
        for arrow in cast("list[Mapping[str, Any]]", arrows)
        for text in arrow.get("labels", {}).values()
    )
    bond_count = len(bonds)
    charge_count = sum(
        mark.get("kind") in {"plus", "minus"} and type(mark.get("atom_id")) is int
        for mark in cast("list[Mapping[str, object]]", marks)
    )
    text_count = note_count + label_count + arrow_label_count
    return (
        text_count * (text_count - 1) // 2
        + (note_count + arrow_label_count) * shape_count
        + arrow_count * (label_count + arrow_label_count + bond_count)
        # Count incident and invisible pairs too: this pre-Qt bound must not
        # depend on clipping, label placement or graphical visibility.
        + (label_count + charge_count + arrow_label_count) * bond_count
        + len(cast("list[object]", marks))
        + text_count
        + shape_count
        + arrow_count
        + bond_count
    )


def _check_offscreen(state: dict[str, Any]) -> dict[str, object]:
    with offscreen_canvas(state, command="check-layout", pin_locale=True) as (
        canvas,
        _,
    ):
        from chemvas.ui.layout_qa_service import check_canvas_layout

        return check_canvas_layout(canvas)


__all__ = ["run"]
