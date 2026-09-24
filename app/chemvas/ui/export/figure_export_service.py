"""Physical-size figure export from a drawing context, without an editor."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from chemvas.core.document_io import atomic_write_via_temp
from chemvas.features.export import (
    ExportPlan,
    points_for_mm,
    render_export_plan,
    resolve_export_plan,
    supports_minimum_font_check,
)
from chemvas.ui.export.export_guard_service import validate_export_budget
from chemvas.ui.export.export_readability_service import assess_export_readability

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class FigureExportService:
    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context

    def _figure_export_parameters(
        self,
        *,
        scope: str,
        selection: Sequence[QGraphicsItem] | None,
        sizing: str,
        target_width_mm: float | None,
    ) -> tuple[list[QGraphicsItem] | None, float, float, float | None]:
        style = self.context.renderer.style
        pad = max(2.0, style.bond_line_width * 2.0)
        items = None
        if scope == "selection":
            if not selection:
                raise ValueError("Select something to export, or choose Whole canvas.")
            items = list(selection)
        unit_scale = 1.0
        target_width_pt = None
        if sizing == "custom" and target_width_mm is None:
            raise ValueError("Custom width sizing requires a target width in mm.")
        if target_width_mm is not None:
            if (
                isinstance(target_width_mm, bool)
                or not math.isfinite(target_width_mm)
                or target_width_mm <= 0.0
            ):
                raise ValueError("target width must be a positive finite number")
            target_width_pt = points_for_mm(target_width_mm)
        elif sizing == "bond":
            if style.bond_length_px > 0:
                unit_scale = style.bond_length_pt / style.bond_length_px
        elif sizing == "col1":
            target_width_pt = points_for_mm(84.0)
        elif sizing == "col2":
            target_width_pt = points_for_mm(174.0)
        return items, pad, unit_scale, target_width_pt

    def _resolve_figure_export(
        self,
        *,
        scope: str,
        selection: Sequence[QGraphicsItem] | None,
        sizing: str,
        target_width_mm: float | None,
    ) -> tuple[list[QGraphicsItem], ExportPlan]:
        items, pad, unit_scale, target_width_pt = self._figure_export_parameters(
            scope=scope,
            selection=selection,
            sizing=sizing,
            target_width_mm=target_width_mm,
        )
        return resolve_export_plan(
            self.context.scene,
            items=items,
            margin=pad,
            unit_scale=unit_scale,
            target_width_pt=target_width_pt,
        )

    def plan_figure_export(
        self,
        *,
        scope: str = "sheet",
        selection: Sequence[QGraphicsItem] | None = None,
        sizing: str = "bond",
        target_width_mm: float | None = None,
    ) -> ExportPlan:
        return self._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing=sizing,
            target_width_mm=target_width_mm,
        )[1]

    def export_figure(
        self,
        path: str,
        *,
        fmt: str = "svg",
        scope: str = "sheet",
        selection: Sequence[QGraphicsItem] | None = None,
        dpi: int = 300,
        background: str = "transparent",
        sizing: str = "bond",
        target_width_mm: float | None = None,
        max_height_mm: float | None = None,
        min_font_pt: float | None = None,
        after_render: Callable[[Path], None] | None = None,
    ) -> ExportPlan:
        items, plan = self._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing=sizing,
            target_width_mm=target_width_mm,
        )
        fmt = fmt.lower()
        if min_font_pt is not None:
            if not supports_minimum_font_check(fmt, scope):
                raise ValueError(
                    "Minimum font checking requires whole-canvas SVG or PNG export."
                )
            if (
                isinstance(min_font_pt, bool)
                or not math.isfinite(min_font_pt)
                or min_font_pt <= 0.0
            ):
                raise ValueError("minimum font size must be a positive finite number")
        width_pixels, height_pixels = validate_export_budget(
            plan, output_format=fmt, dpi=dpi, max_height_mm=max_height_mm
        )

        def render_to_temp(tmp: Path) -> None:
            try:
                str(tmp).encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError(
                    "The destination folder cannot be represented as UTF-8. "
                    "Choose another folder. No file was written."
                ) from None
            render_export_plan(
                self.context.scene,
                str(tmp),
                fmt=fmt,
                items=items,
                plan=plan,
                dpi=dpi,
                background=background,
                title="Chemvas drawing",
            )
            if tmp.stat().st_size == 0:
                raise ValueError(
                    "The renderer produced an empty file. No file was written."
                )
            if min_font_pt is not None:
                assess_export_readability(
                    self.context,
                    plan,
                    minimum_font_pt=min_font_pt,
                    output_format=fmt,
                    dpi=dpi,
                    width_pixels=width_pixels,
                    height_pixels=height_pixels,
                )
            if after_render is not None:
                after_render(tmp)

        atomic_write_via_temp(Path(path), render_to_temp)
        return plan
