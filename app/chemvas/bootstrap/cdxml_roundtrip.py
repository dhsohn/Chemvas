"""Headless product entry point for measured native CDXML diagnostics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chemvas.bootstrap.document_cli_shared import json_text
from chemvas.core.document_io import atomic_create_bytes
from chemvas.features.export import (
    MAX_CDXML_CONSUMER_BYTES,
    inspect_cdxml_roundtrip,
    recover_native_cdxml_palette,
)


def _read(path: str) -> bytes:
    source = Path(path)
    if source.suffix.lower() != ".cdxml":
        raise ValueError("input must use the .cdxml filename extension")
    with source.open("rb") as handle:
        raw = handle.read(MAX_CDXML_CONSUMER_BYTES + 1)
    if len(raw) > MAX_CDXML_CONSUMER_BYTES:
        raise ValueError("CDXML input exceeds the byte limit")
    return raw


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="chemvas")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser(
        "review-cdxml",
        help="inspect native font changes and eight-bit palette stability",
    )
    review.add_argument(
        "producer", help="original producer CDXML with exact eight-bit RGB"
    )
    review.add_argument(
        "--native",
        help="known first native SaveAs CDXML; save history and edit intent cannot be detected",
    )
    review.add_argument(
        "--recover-palette",
        metavar="NEW_CDXML",
        help=(
            "create a new CDXML with exact palette numbers; requires --native from "
            "ChemDraw 25.0.2.14; requires exact measured writer values and known "
            "first-save provenance; preserves other bytes, not a whole-document fidelity pass"
        ),
    )
    args = parser.parse_args(argv)
    try:
        producer = _read(args.producer)
        native = None if args.native is None else _read(args.native)
        if args.recover_palette is not None:
            if native is None:
                raise ValueError("--recover-palette requires --native")
            output = Path(args.recover_palette)
            if output.suffix.lower() != ".cdxml":
                raise ValueError("output must use the .cdxml filename extension")
            content, report = recover_native_cdxml_palette(producer, native)
            atomic_create_bytes(output, content)
            report["output"] = str(output)
        else:
            report = inspect_cdxml_roundtrip(producer, native)
        sys.stdout.write(json_text(report))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2
