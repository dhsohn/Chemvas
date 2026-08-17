from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from chemvas.bootstrap.document_render import MAX_DOCUMENT_BYTES, MAX_GRAPHICS_RECORDS
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
        graphics_records = _graphics_record_count(
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
        sys.stdout.write(_json_text(report))
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


def _graphics_record_count(state: Mapping[str, object]) -> int:
    model = state.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("Invalid Chemvas file.")
    atoms = model.get("atoms")
    bonds = model.get("bonds")
    if not isinstance(atoms, Mapping) or not isinstance(bonds, list):
        raise ValueError("Invalid Chemvas file.")
    total = len(atoms) + len(bonds)
    for key in (
        "ring_fills",
        "notes",
        "marks",
        "arrows",
        "ts_brackets",
        "shapes",
        "orbitals",
    ):
        records = state.get(key, [])
        if isinstance(records, list):
            total += len(records)
    return total


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
    previous_qt_platform = os.environ.get("QT_QPA_PLATFORM")
    previous_locale = {name: os.environ.get(name) for name in ("LC_ALL", "LANG")}
    os.environ["QT_QPA_PLATFORM"] = (
        "windows" if sys.platform == "win32" else "offscreen"
    )
    os.environ["LC_ALL"] = "C.UTF-8"
    os.environ["LANG"] = "C.UTF-8"
    try:
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication

        from chemvas.adapters.qt.renderer import Renderer
        from chemvas.ui.canvas_service_access import canvas_services_for
        from chemvas.ui.canvas_view import CanvasView
        from chemvas.ui.layout_qa_service import check_canvas_layout

        existing = QApplication.instance()
        if existing is not None and not isinstance(existing, QApplication):
            raise RuntimeError("check-layout requires a QApplication instance")
        application = existing or QApplication(["chemvas-check-layout"])
    finally:
        if previous_qt_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_qt_platform
        for name, value in previous_locale.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    restore_quit = application.quitOnLastWindowClosed()
    application.setQuitOnLastWindowClosed(False)
    canvas = None
    try:
        canvas = CanvasView(renderer=Renderer())
        service = canvas_services_for(canvas).document.canvas_document_session_service
        service.apply_state(state)
        return check_canvas_layout(canvas)
    finally:
        if canvas is not None:
            canvas.deleteLater()
            application.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        application.setQuitOnLastWindowClosed(restore_quit)


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = ["run"]
