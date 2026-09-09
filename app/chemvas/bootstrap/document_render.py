from __future__ import annotations

import argparse
import hashlib
import math
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from chemvas.bootstrap.document_cli_shared import (
    MAX_DOCUMENT_BYTES,
    MAX_GRAPHICS_RECORDS,
    graphics_record_count,
    json_text,
    offscreen_canvas,
)
from chemvas.core.document_io import atomic_create_bytes, read_exact_document
from chemvas.ui.export_guard_service import (
    MAX_RASTER_DIMENSION_PIXELS,
    MAX_RASTER_PIXELS,
    MAX_VECTOR_DIMENSION_POINTS,
    validate_export_budget,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.features.export import ExportPlan

MAX_OUTPUT_BYTES = 64 * 1024 * 1024
PNG_DPI_CHOICES = (150, 300, 600, 1200)


@dataclass(frozen=True)
class _RenderedDocument:
    content: bytes
    width_points: float
    height_points: float
    width_pixels: int | None
    height_pixels: int | None
    font_readability: dict[str, object] | None = None


def run(argv: list[str]) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    try:
        # add_subparsers(required=True) with one registered subparser: argparse
        # has already exited for a missing or unknown command.
        report = _render_document(
            Path(args.document),
            output=Path(args.output),
            background=str(args.background),
            dpi=int(args.dpi),
            width_mm=args.width_mm,
            max_height_mm=args.max_height_mm,
            min_font_pt=args.min_font_pt,
        )
        sys.stdout.write(json_text(report))
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
        help="render a .chemvas document to a new SVG, PDF, or PNG file",
    )
    render_parser.add_argument("document", help="input .chemvas document")
    render_parser.add_argument(
        "--output",
        required=True,
        help="new non-overwriting .svg, .pdf, or .png output path",
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
        help="PNG/PDF resolution; SVG ignores this value (default: 300)",
    )
    render_parser.add_argument(
        "--width-mm",
        type=_positive_finite_number,
        help="physical output width in mm, preserving aspect ratio (default: bond sizing)",
    )
    render_parser.add_argument(
        "--max-height-mm",
        type=_positive_finite_number,
        help="reject output taller than this height in mm; never shrink to fit",
    )
    render_parser.add_argument(
        "--min-font-pt",
        type=_positive_finite_number,
        help="SVG/PNG only: reject glyphs below this final point size, including scripts",
    )
    return parser


def _positive_finite_number(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return number


def _render_document(
    source: Path,
    *,
    output: Path,
    background: str,
    dpi: int,
    width_mm: float | None = None,
    max_height_mm: float | None = None,
    min_font_pt: float | None = None,
) -> dict[str, object]:
    output_format = _validate_paths(source, output)
    if output_format == "pdf" and min_font_pt is not None:
        raise ValueError("--min-font-pt supports SVG and PNG output only")
    source_bytes, document = read_exact_document(source, max_bytes=MAX_DOCUMENT_BYTES)
    state = cast("Mapping[str, object]", document.state)
    graphics_records = graphics_record_count(state)
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
        width_mm=width_mm,
        max_height_mm=max_height_mm,
        min_font_pt=min_font_pt,
    )
    atomic_create_bytes(output, rendered.content)
    output_sha256 = _sha256(rendered.content)
    report: dict[str, object] = {
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
        "dpi": dpi if output_format in {"png", "pdf"} else None,
        "width_points": _report_number(rendered.width_points),
        "height_points": _report_number(rendered.height_points),
        "width_pixels": rendered.width_pixels,
        "height_pixels": rendered.height_pixels,
        "graphics_records": graphics_records,
    }
    if rendered.font_readability is not None:
        report["font_readability"] = rendered.font_readability
    return report


def _validate_paths(source: Path, output: Path) -> str:
    if source.suffix.lower() != ".chemvas":
        raise ValueError("input must use the .chemvas filename extension")
    if not source.is_file():
        raise ValueError(f"input document does not exist: {source}")
    output_format = output.suffix.lower().removeprefix(".")
    if output_format not in {"svg", "pdf", "png"}:
        raise ValueError("output must use the .svg, .pdf, or .png filename extension")
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"output parent directory does not exist: {output.parent}")
    return output_format


def _render_offscreen(
    state: dict[str, Any],
    *,
    output_format: str,
    background: str,
    dpi: int,
    width_mm: float | None = None,
    max_height_mm: float | None = None,
    min_font_pt: float | None = None,
) -> _RenderedDocument:
    with offscreen_canvas(state, command="render-document") as (canvas, service):
        plan = cast(
            "ExportPlan",
            service.plan_figure_export(
                scope="sheet", sizing="bond", target_width_mm=width_mm
            ),
        )
        width_pixels, height_pixels = validate_export_budget(
            plan,
            output_format=output_format,
            dpi=dpi,
            max_height_mm=None if output_format == "pdf" else max_height_mm,
        )
        output_plan = plan
        if output_format == "pdf":
            from PyQt6.QtCore import QSizeF
            from PyQt6.QtGui import QPageSize

            # Match the native PDF writer's whole-point page dimensions.
            page_size = QPageSize(
                QSizeF(plan.out_w_pt, plan.out_h_pt), QPageSize.Unit.Point
            ).sizePoints()
            output_plan = replace(
                plan,
                out_w_pt=float(page_size.width()),
                out_h_pt=float(page_size.height()),
            )
            validate_export_budget(
                output_plan,
                output_format=output_format,
                dpi=dpi,
                max_height_mm=max_height_mm,
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
                target_width_mm=width_mm,
                editable_svg=False,
            )
            rendered_size = rendered_path.stat().st_size
            if rendered_size > MAX_OUTPUT_BYTES:
                raise ValueError(
                    f"rendered output exceeds the {MAX_OUTPUT_BYTES}-byte limit"
                )
            content = rendered_path.read_bytes()
        font_readability = None
        if min_font_pt is not None:
            from chemvas.ui.export_readability_service import assess_export_readability

            font_readability = assess_export_readability(
                canvas,
                plan,
                minimum_font_pt=min_font_pt,
                output_format=output_format,
                dpi=dpi,
                width_pixels=width_pixels,
                height_pixels=height_pixels,
            )
        return _RenderedDocument(
            content=content,
            width_points=float(output_plan.out_w_pt),
            height_points=float(output_plan.out_h_pt),
            width_pixels=width_pixels,
            height_pixels=height_pixels,
            font_readability=font_readability,
        )


def _report_number(value: float) -> float:
    return round(value, 6)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


__all__ = [
    "MAX_OUTPUT_BYTES",
    "MAX_RASTER_DIMENSION_PIXELS",
    "MAX_RASTER_PIXELS",
    "MAX_VECTOR_DIMENSION_POINTS",
    "PNG_DPI_CHOICES",
    "run",
]
