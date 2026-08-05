from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from chemvas.core.document_io import atomic_create_bytes, read_exact_document

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_GRAPHICS_RECORDS = 20_000
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_VECTOR_DIMENSION_POINTS = 14_400.0
MAX_RASTER_DIMENSION_PIXELS = 10_000
MAX_RASTER_PIXELS = 25_000_000
PNG_DPI_CHOICES = (150, 300, 600, 1200)


class _ExportPlan(Protocol):
    out_w_pt: float
    out_h_pt: float


@dataclass(frozen=True, slots=True)
class _RenderedDocument:
    content: bytes
    width_points: float
    height_points: float
    width_pixels: int | None
    height_pixels: int | None


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command != "render-document":
            parser.error("a command is required")
            return 2
        report = _render_document(
            Path(args.document),
            output=Path(args.output),
            background=str(args.background),
            dpi=int(args.dpi),
        )
        sys.stdout.write(_json_text(report))
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"chemvas: error: {exc}\n")
    return 2


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemvas",
        description="Render a Chemvas document without opening a desktop window.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    render_parser = subparsers.add_parser(
        "render-document",
        help="render a .chemvas document to a new SVG or PNG file",
    )
    render_parser.add_argument("document", help="input .chemvas document")
    render_parser.add_argument(
        "--output",
        required=True,
        help="new non-overwriting .svg or .png output path",
    )
    render_parser.add_argument(
        "--background",
        choices=("white", "transparent"),
        default="white",
        help="output background (default: white)",
    )
    render_parser.add_argument(
        "--dpi",
        choices=PNG_DPI_CHOICES,
        default=300,
        type=int,
        help="PNG resolution; SVG ignores this value (default: 300)",
    )
    return parser


def _render_document(
    source: Path,
    *,
    output: Path,
    background: str,
    dpi: int,
) -> dict[str, object]:
    output_format = _validate_paths(source, output)
    _validate_source_size(source)
    source_bytes, document = read_exact_document(source)
    if len(source_bytes) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"input document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")
    state = cast(Mapping[str, object], document.state)
    graphics_records = _graphics_record_count(state)
    if graphics_records > MAX_GRAPHICS_RECORDS:
        raise ValueError(
            "input document exceeds the "
            f"{MAX_GRAPHICS_RECORDS}-graphics-record render limit"
        )

    rendered = _render_offscreen(
        document.state,
        output_format=output_format,
        background=background,
        dpi=dpi,
    )
    atomic_create_bytes(output, rendered.content)
    output_sha256 = _sha256(rendered.content)
    return {
        "format": "chemvas-document-render-report",
        "version": 1,
        "source": str(source),
        "source_sha256": _sha256(source_bytes),
        "chemvas_document_version": int(document.payload["version"]),
        "output": str(output),
        "output_format": output_format,
        "output_sha256": output_sha256,
        "output_bytes": len(rendered.content),
        "written": True,
        "background": background,
        "dpi": dpi if output_format == "png" else None,
        "width_points": _report_number(rendered.width_points),
        "height_points": _report_number(rendered.height_points),
        "width_pixels": rendered.width_pixels,
        "height_pixels": rendered.height_pixels,
        "graphics_records": graphics_records,
    }


def _validate_paths(source: Path, output: Path) -> str:
    if source.suffix.lower() != ".chemvas":
        raise ValueError("input must use the .chemvas filename extension")
    if not source.is_file():
        raise ValueError(f"input document does not exist: {source}")
    output_format = output.suffix.lower().removeprefix(".")
    if output_format not in {"svg", "png"}:
        raise ValueError("output must use the .svg or .png filename extension")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")
    return output_format


def _validate_source_size(source: Path) -> None:
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"input document exceeds the {MAX_DOCUMENT_BYTES}-byte limit")


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


def _render_offscreen(
    state: dict[str, Any],
    *,
    output_format: str,
    background: str,
    dpi: int,
) -> _RenderedDocument:
    previous_qt_platform = os.environ.get("QT_QPA_PLATFORM")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication

        from chemvas.adapters.qt.renderer import Renderer
        from chemvas.ui.canvas_service_access import canvas_services_for
        from chemvas.ui.canvas_view import CanvasView

        existing_application = QApplication.instance()
        if existing_application is not None and not isinstance(
            existing_application, QApplication
        ):
            raise RuntimeError("render-document requires a QApplication instance")
        application = existing_application or QApplication(["chemvas-render-document"])
    finally:
        if previous_qt_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_qt_platform
    restore_quit_on_last_window = application.quitOnLastWindowClosed()
    application.setQuitOnLastWindowClosed(False)
    canvas = None
    try:
        canvas = CanvasView(renderer=Renderer())
        service = canvas_services_for(canvas).document.canvas_document_session_service
        service.apply_state(state)
        plan = cast(_ExportPlan, service.plan_figure_export())
        width_pixels, height_pixels = _validate_render_budget(
            plan,
            output_format=output_format,
            dpi=dpi,
        )
        with tempfile.TemporaryDirectory(prefix="chemvas-render-document-") as raw_tmp:
            rendered_path = Path(raw_tmp) / f"rendered.{output_format}"
            service.export_figure(
                str(rendered_path),
                fmt=output_format,
                scope="sheet",
                dpi=dpi,
                background=background,
                sizing="bond",
                editable_svg=False,
            )
            rendered_size = rendered_path.stat().st_size
            if rendered_size > MAX_OUTPUT_BYTES:
                raise ValueError(
                    f"rendered output exceeds the {MAX_OUTPUT_BYTES}-byte limit"
                )
            content = rendered_path.read_bytes()
        return _RenderedDocument(
            content=content,
            width_points=float(plan.out_w_pt),
            height_points=float(plan.out_h_pt),
            width_pixels=width_pixels,
            height_pixels=height_pixels,
        )
    finally:
        if canvas is not None:
            canvas.deleteLater()
            application.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        application.setQuitOnLastWindowClosed(restore_quit_on_last_window)


def _validate_render_budget(
    plan: _ExportPlan,
    *,
    output_format: str,
    dpi: int,
) -> tuple[int | None, int | None]:
    width_points = float(plan.out_w_pt)
    height_points = float(plan.out_h_pt)
    if (
        width_points <= 0.0
        or height_points <= 0.0
        or width_points > MAX_VECTOR_DIMENSION_POINTS
        or height_points > MAX_VECTOR_DIMENSION_POINTS
    ):
        raise ValueError(
            "rendered dimensions must be positive and no larger than "
            f"{MAX_VECTOR_DIMENSION_POINTS:g} points per side"
        )
    if output_format != "png":
        return None, None

    width_pixels = max(1, round(width_points / 72.0 * dpi))
    height_pixels = max(1, round(height_points / 72.0 * dpi))
    if (
        width_pixels > MAX_RASTER_DIMENSION_PIXELS
        or height_pixels > MAX_RASTER_DIMENSION_PIXELS
        or width_pixels * height_pixels > MAX_RASTER_PIXELS
    ):
        raise ValueError(
            "PNG render exceeds the "
            f"{MAX_RASTER_DIMENSION_PIXELS}-pixel side or "
            f"{MAX_RASTER_PIXELS}-pixel area limit"
        )
    return width_pixels, height_pixels


def _report_number(value: float) -> float:
    return round(value, 6)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = [
    "MAX_DOCUMENT_BYTES",
    "MAX_GRAPHICS_RECORDS",
    "MAX_OUTPUT_BYTES",
    "MAX_RASTER_DIMENSION_PIXELS",
    "MAX_RASTER_PIXELS",
    "MAX_VECTOR_DIMENSION_POINTS",
    "PNG_DPI_CHOICES",
    "run",
]
