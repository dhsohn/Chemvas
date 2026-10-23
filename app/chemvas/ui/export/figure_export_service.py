"""Physical-size figure export from a drawing context, without an editor."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from chemvas.core.document_io import atomic_write_via_temp
from chemvas.features.export import (
    ExportPlan,
    points_for_mm,
    supports_minimum_font_check,
)
from chemvas.ui.export.export_guard_service import validate_export_budget
from chemvas.ui.export.export_readability_service import assess_export_readability
from chemvas.ui.export.export_render_service import (
    render_export_plan,
    resolve_export_plan,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.domain.document.groups import SceneGroup
    from chemvas.features.export import CdxmlLabelBindings, CdxmlTextLayoutReference
    from chemvas.ui.export.export_cdxml import LabelBindings
    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class FigureExportService:
    def __init__(
        self,
        context: SceneRenderContext,
        groups: Mapping[int, SceneGroup] | None = None,
    ) -> None:
        self.context = context
        self._groups = groups

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

    def _typed_label_bindings(
        self,
        items: Sequence[QGraphicsItem],
        label_bindings: CdxmlLabelBindings,
    ) -> LabelBindings:
        """Bind each sidecar entry to an exported atom and its exact label.

        The atom must exist, be visible and lie inside the export scope (the
        same closure and visibility rule ``preflight_cdxml`` uses), and its
        label must equal ``expected_label`` code point for code point. Only
        then is the stated meaning handed to the exporter, which still decides
        whether that meaning fits the label.
        """
        from chemvas.ui.export.export_cdxml import CdxmlLabelBinding
        from chemvas.ui.export.export_scope import export_item_closure

        exported_atom_ids: set[int] = set()
        for item in export_item_closure(list(items)):
            if item.data(0) == "atom" and item.isVisible():
                atom_id = item.data(1)
                if isinstance(atom_id, int):
                    exported_atom_ids.add(atom_id)
        atoms = self.context.model.atoms
        typed: dict[int, CdxmlLabelBinding] = {}
        for entry in label_bindings.entries:
            prefix = f"CDXML label binding for atom {entry.atom_id}"
            atom = atoms.get(entry.atom_id)
            if atom is None:
                raise ValueError(f"{prefix}: the atom is not in the document")
            if entry.atom_id not in exported_atom_ids:
                raise ValueError(
                    f"{prefix}: the atom is hidden or outside the export scope"
                )
            if atom.element != entry.expected_label:
                raise ValueError(
                    f"{prefix}: the document label {atom.element!r} is not the "
                    f"expected label {entry.expected_label!r}"
                )
            typed[entry.atom_id] = CdxmlLabelBinding(
                entry.meaning,
                element=entry.element,
                fragment=entry.fragment,
                author_note=entry.author_note,
            )
        return typed

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

    def preview_figure_export(
        self,
        *,
        scope: str = "sheet",
        selection: Sequence[QGraphicsItem] | None = None,
        sizing: str = "bond",
        target_width_mm: float | None = None,
        background: str = "transparent",
    ) -> tuple[QImage, ExportPlan]:
        """Render a bounded in-memory preview through the figure painting path."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage, QPainter

        from chemvas.ui.export.export_painting import paint_scene_region
        from chemvas.ui.export.export_scope import exported_scene

        items, plan = self._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing=sizing,
            target_width_mm=target_width_mm,
        )
        scale = min(720 / plan.out_w_pt, 480 / plan.out_h_pt)
        width = max(1, round(plan.out_w_pt * scale))
        height = max(1, round(plan.out_h_pt * scale))
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        with exported_scene(self.context.scene, items):
            painter = QPainter(image)
            try:
                paint_scene_region(
                    painter, self.context.scene, plan, width, height, background
                )
            finally:
                painter.end()
        return image, plan

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
        label_bindings: CdxmlLabelBindings | None = None,
        layout_reference: CdxmlTextLayoutReference | None = None,
    ) -> ExportPlan:
        if label_bindings is not None and fmt.lower() != "cdxml":
            raise ValueError(
                "CDXML label bindings apply to CDXML export only. No file was written."
            )
        if layout_reference is not None and fmt.lower() != "cdxml":
            raise ValueError("CDXML layout reference applies to CDXML export only")
        if layout_reference is not None and layout_reference.export_options != {
            "format": fmt.lower(),
            "scope": scope,
            "sizing": sizing,
            "background": background,
            "dpi": dpi,
            "width_mm": target_width_mm,
            "max_height_mm": max_height_mm,
            "min_font_pt": min_font_pt,
        }:
            raise ValueError("CDXML layout reference does not match export options")
        items, plan = self._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing=sizing,
            target_width_mm=target_width_mm,
        )
        fmt = fmt.lower()

        if fmt == "cdxml":
            from chemvas.ui.export.export_cdxml import (
                preflight_cdxml,
                serialize_cdxml,
            )

            if min_font_pt is not None:
                if not supports_minimum_font_check(fmt, scope):
                    raise ValueError(
                        "Minimum font checking requires whole-canvas SVG or PNG export."
                    )
            validate_export_budget(
                plan,
                output_format=fmt,
                dpi=dpi,
                max_height_mm=max_height_mm,
            )
            typed_bindings: LabelBindings | None = None
            documentary_contacts = None
            if label_bindings is not None:
                typed_bindings = self._typed_label_bindings(items, label_bindings)
                documentary_contacts = label_bindings.documentary_contacts or None
            preflight_cdxml(
                self.context,
                items,
                plan,
                background=background,
                groups=self._groups,
                label_bindings=typed_bindings,
                documentary_contacts=documentary_contacts,
            )
            cdxml_bytes = serialize_cdxml(
                self.context,
                items,
                plan,
                background=background,
                groups=self._groups,
                label_bindings=typed_bindings,
                documentary_contacts=documentary_contacts,
                layout_reference=layout_reference,
            )

            def write_cdxml(tmp: Path) -> None:
                tmp.write_bytes(cdxml_bytes)

            atomic_write_via_temp(Path(path), write_cdxml)
            return plan

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

        atomic_write_via_temp(Path(path), render_to_temp)
        return plan
