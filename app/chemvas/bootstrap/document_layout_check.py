from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    MAX_GRAPHICS_RECORDS,
    graphics_record_count,
    json_text,
    offscreen_document_scene,
    validate_source_document,
)
from chemvas.core.document_io import read_exact_document

MAX_LAYOUT_TEXT_CHARACTERS = 100_000


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source = Path(args.document)
        validate_source_document(source)
        document = read_exact_document(source, max_bytes=MAX_DOCUMENT_BYTES).document
        graphics_records = graphics_record_count(
            cast("Mapping[str, object]", document.state)
        )
        if graphics_records > MAX_GRAPHICS_RECORDS:
            raise ValueError(
                f"input document exceeds the {MAX_GRAPHICS_RECORDS}-graphics-record layout limit"
            )
        _validate_layout_text_budget(document.state)
        analysis = _check_offscreen(document.state, sheet_only=args.sheet_only)
        report = {
            "format": "chemvas-layout-check-report",
            "version": 1,
            "source": str(source),
            "source_sha256": document.source_sha256,
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
    check.add_argument(
        "--sheet-only",
        action="store_true",
        help="check all visible content against the sheet without pairwise collision checks",
    )
    return parser


def _validate_layout_text_budget(state: Mapping[str, object]) -> None:
    # Bound shaping before opening Qt. Collision work is measured from actual
    # painted bounds in the scene, rather than all possible document pairs.
    def characters(value: object) -> int:
        if isinstance(value, str):
            return len(value)
        if isinstance(value, Mapping):
            return sum(characters(child) for child in value.values())
        if isinstance(value, list):
            return sum(characters(child) for child in value)
        return 0

    count = sum(
        characters(state.get(key)) for key in ("model", "notes", "marks", "arrows")
    )
    if count > MAX_LAYOUT_TEXT_CHARACTERS:
        raise ValueError(
            f"input document exceeds the layout text limit of {MAX_LAYOUT_TEXT_CHARACTERS} characters"
        )


def _check_offscreen(
    state: dict[str, Any], *, sheet_only: bool = False
) -> dict[str, object]:
    with offscreen_document_scene(
        state, command="check-layout", pin_locale=True
    ) as context:
        from chemvas.ui.export.layout_qa_service import check_scene_layout

        return check_scene_layout(context, sheet_only=sheet_only)


__all__ = ["run"]
