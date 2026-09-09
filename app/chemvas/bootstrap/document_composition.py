from __future__ import annotations

import argparse
import hashlib
import stat
import sys
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import atomic_create_bytes
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    build_document_payload,
    normalize_json_numbers,
)
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.document_composition import compose_document_state

MAX_COMPOSITION_BYTES = 1024 * 1024


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        request = Path(args.composition)
        output = Path(args.output)
        _validate_request(request)
        _validate_output(output)
        composition = _read_composition(request)
        state = compose_document_state(
            composition,
            image_source_reader=lambda source: _read_image_source(
                request.parent, source
            ),
        )
        payload = cast(
            "dict[str, Any]",
            normalize_json_numbers(build_document_payload(state, CANVAS_FILE_VERSION)),
        )
        output_bytes = json_text(payload).encode("utf-8")
        if len(output_bytes) > MAX_DOCUMENT_BYTES:
            raise ValueError(f"document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")
        atomic_create_bytes(output, output_bytes)
        model = cast("dict[str, object]", state["model"])
        report = {
            "format": "chemvas-document-composition-report",
            "version": 1,
            "composition": str(request),
            "output": str(output),
            "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "chemvas_document_version": CANVAS_FILE_VERSION,
            "atom_count": len(cast("dict[object, object]", model["atoms"])),
            "bond_count": len(cast("list[object]", model["bonds"])),
            "image_count": len(cast("list[object]", state.get("images", []))),
            "written": True,
        }
        sys.stdout.write(json_text(report))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Create a canonical Chemvas document from a strict composition.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    compose = subparsers.add_parser(
        "compose-document",
        help="create a new canonical .chemvas document",
    )
    compose.add_argument("composition", help="input composition v1 JSON file")
    compose.add_argument("--output", required=True, help="new .chemvas output path")
    return parser


def _read_composition(path: Path) -> object:
    with path.open("rb") as stream:
        raw = stream.read(MAX_COMPOSITION_BYTES + 1)
    if len(raw) > MAX_COMPOSITION_BYTES:
        raise ValueError(f"composition exceeds the {MAX_COMPOSITION_BYTES}-byte limit")
    try:
        return strict_json_loads(raw)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid Chemvas composition JSON file.") from exc


def _read_image_source(base_directory: Path, source: str) -> bytes:
    path = Path(source)
    if not path.is_absolute():
        path = base_directory / path
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Image source must use the .png, .jpg, or .jpeg extension.")
    source_stat = path.stat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError(f"Image source must be a regular file: {path}")
    if source_stat.st_size > MAX_IMAGE_BYTES:
        raise ValueError("Image source exceeds the 16 MiB byte limit.")
    with path.open("rb") as stream:
        data = stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image source exceeds the 16 MiB byte limit.")
    return data


def _validate_request(path: Path) -> None:
    if path.suffix.lower() != ".json":
        raise ValueError("composition input must use the .json filename extension")
    if not path.is_file():
        raise ValueError(f"composition does not exist: {path}")


def _validate_output(path: Path) -> None:
    if path.suffix.lower() != ".chemvas":
        raise ValueError("output must use the .chemvas filename extension")
    if path.exists() or path.is_symlink():
        raise ValueError(f"output path already exists: {path}")
    if not path.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {path.parent}")


__all__ = ["MAX_COMPOSITION_BYTES", "run"]
