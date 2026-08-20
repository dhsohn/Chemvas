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
from chemvas.core.document_io import ChemvasDocument, parse_document
from chemvas.domain.json_io import strict_json_loads

MAX_LAYOUT_WORK_UNITS = 10_000


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source = Path(args.document)
        _validate_source(source)
        source_bytes, document = _read_layout_document(source)
        graphics_records = graphics_record_count(
            cast(Mapping[str, object], document.state)
        )
        if graphics_records > MAX_GRAPHICS_RECORDS:
            raise ValueError(
                f"input document exceeds the {MAX_GRAPHICS_RECORDS}-graphics-record layout limit"
            )
        layout_work_units = _layout_work_units(
            cast(Mapping[str, object], document.state)
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
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"input document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")


def _read_layout_document(source: Path) -> tuple[bytes, ChemvasDocument]:
    with source.open("rb") as stream:
        source_bytes = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(source_bytes) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"input document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")
    try:
        payload = strict_json_loads(source_bytes)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Chemvas file.") from exc
    return source_bytes, parse_document(payload)


def _layout_work_units(state: Mapping[str, object]) -> int:
    notes = state.get("notes", [])
    shapes = state.get("shapes", [])
    if not isinstance(notes, list) or not isinstance(shapes, list):
        raise ValueError("Invalid Chemvas file.")
    note_count = len(notes)
    shape_count = len(shapes)
    return (
        note_count * (note_count - 1) // 2
        + note_count * shape_count
        + note_count
        + shape_count
    )


def _check_offscreen(state: dict[str, Any]) -> dict[str, object]:
    with offscreen_canvas(state, command="check-layout", pin_locale=True) as (
        canvas,
        _,
    ):
        from chemvas.ui.layout_qa_service import check_canvas_layout

        return check_canvas_layout(canvas)


__all__ = ["run"]
