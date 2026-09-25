from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    MAX_GRAPHICS_RECORDS,
    encode_cli_document,
    graphics_record_count,
    json_text,
    offscreen_canvas,
    read_json_request,
)
from chemvas.core.document_io import atomic_create_bytes, read_exact_document
from chemvas.domain.document import (
    build_normalized_document_payload,
)
from chemvas.features.scheme_layout import validate_layout_request

MAX_LAYOUT_BYTES = 1024 * 1024


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        source, layout, output = (
            Path(args.document),
            Path(args.layout),
            Path(args.output),
        )
        _validate_paths(source, layout, output)
        _source_bytes, document = read_exact_document(
            source, max_bytes=MAX_DOCUMENT_BYTES
        )
        source_sha256 = cast("str", document.source_sha256)
        layout_bytes, raw_request = read_json_request(
            layout,
            max_bytes=MAX_LAYOUT_BYTES,
            limit_message=f"layout request exceeds the {MAX_LAYOUT_BYTES}-byte limit",
            invalid_message="Invalid Chemvas scheme layout JSON file.",
        )
        state = cast("dict[str, Any]", document.state)
        if graphics_record_count(state) > MAX_GRAPHICS_RECORDS:
            raise ValueError(
                f"input document exceeds the {MAX_GRAPHICS_RECORDS}-graphics-record layout limit"
            )
        request = validate_layout_request(
            state, raw_request, source_sha256=source_sha256
        )
        with offscreen_canvas(state, command="layout-document", pin_locale=True) as (
            canvas,
            _,
        ):
            from chemvas.ui.dialogs.scheme_layout_service import arrange_canvas

            candidate, analysis = arrange_canvas(canvas, state, request)
        version = int(document.payload["version"])
        payload = build_normalized_document_payload(candidate, version)
        output_bytes = encode_cli_document(
            payload, max_bytes=MAX_DOCUMENT_BYTES, description="laid-out document"
        )
        atomic_create_bytes(output, output_bytes)
        sys.stdout.write(
            json_text(
                {
                    "format": "chemvas-scheme-layout-report",
                    "version": 1,
                    "source": str(source),
                    "source_sha256": source_sha256,
                    "layout_sha256": hashlib.sha256(layout_bytes).hexdigest(),
                    "output": str(output),
                    "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                    "chemvas_document_version": version,
                    "written": True,
                    **analysis,
                }
            )
        )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Arrange explicit scheme blocks without changing molecular geometry.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "layout-document", help="align structures and captions in a new document"
    )
    command.add_argument("document", help="input .chemvas document")
    command.add_argument(
        "--layout", required=True, help="source-pinned scheme layout v1 JSON"
    )
    command.add_argument(
        "--output", required=True, help="new non-overwriting .chemvas path"
    )
    return parser


def _validate_paths(source: Path, layout: Path, output: Path) -> None:
    if source.suffix.lower() != ".chemvas" or not source.is_file():
        raise ValueError("input must be an existing .chemvas document")
    if layout.suffix.lower() != ".json" or not layout.is_file():
        raise ValueError("layout must be an existing .json request")
    if output.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")


__all__ = ["run"]
