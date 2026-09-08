"""Measure the visible glyphs in a whole-canvas export, without changing them."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QFont,
    QPainter,
    QPicture,
    QTextCharFormat,
    QTextLayout,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
)

from chemvas.features.export import (
    ExportPlan,
    collect_export_items,
    export_item_closure,
    svg_viewport_size_points,
)
from chemvas.ui.canvas_scene_items_state import (
    arrow_items_for,
    mark_items_for,
    note_items_for,
    ts_bracket_items_for,
)
from chemvas.ui.graphics_items import AtomLabelItem, ExportTextItem
from chemvas.ui.scene_item_access import canvas_scene_for

if TYPE_CHECKING:
    from collections.abc import Iterator

    from PyQt6.QtGui import QGlyphRun, QPainterPath


@dataclass(frozen=True)
class _GlyphSize:
    pixels: float
    glyphs: int
    script: bool


class _AtomFontPainter(QPainter):
    """Read the fonts from the existing custom atom-label paint runs."""

    def __init__(self, picture: QPicture) -> None:
        super().__init__(picture)
        self.runs: list[tuple[str, QFont]] = []
        self.outlined = False

    @override
    def drawText(self, *args: Any) -> Any:
        _point, text = args
        if self.pen().color().alpha() > 0:
            self.runs.append((str(text), QFont(self.font())))

    @override
    def drawPath(self, path: QPainterPath) -> None:
        self.outlined = True


def _shaped_sizes(text: str, font: QFont, *, script: bool) -> Iterator[_GlyphSize]:
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    for run in layout.glyphRuns(0, len(text)):
        size = _run_size(run, script=script)
        if size is not None:
            yield size


def _run_size(run: QGlyphRun, *, script: bool) -> _GlyphSize | None:
    font = run.rawFont()
    if (
        not font.isValid()
        or not math.isfinite(font.pixelSize())
        or font.pixelSize() <= 0
    ):
        raise ValueError("cannot measure an invalid resolved glyph font")
    glyphs = run.glyphIndexes()
    if 0 in glyphs:
        raise ValueError("cannot certify a missing glyph")
    visible = sum(
        count
        for glyph, count in Counter(glyphs).items()
        if not font.pathForGlyph(glyph).isEmpty()
    )
    if visible == 0:
        return None
    return _GlyphSize(font.pixelSize(), visible, script)


def _rich_text_sizes(item: QGraphicsTextItem) -> Iterator[_GlyphSize]:
    document = item.document()
    if document is None:
        raise ValueError("cannot measure text without a Qt document")
    item.boundingRect()  # Force the same lazy layout used by painting/export.
    block = document.begin()
    while block.isValid():
        layout = block.layout()
        if layout is None:
            raise ValueError("cannot measure a text block without its Qt layout")
        fragments = block.begin()
        while not fragments.atEnd():
            fragment = fragments.fragment()
            format_ = fragment.charFormat()
            brush = format_.foreground()
            color = (
                item.defaultTextColor()
                if brush.style() == Qt.BrushStyle.NoBrush
                else brush.color()
            )
            if color.alpha() > 0 and fragment.text().strip():
                runs = layout.glyphRuns(
                    fragment.position() - block.position(), fragment.length()
                )
                if not runs:
                    raise ValueError(
                        "cannot measure visible text without shaped glyphs"
                    )
                script = format_.verticalAlignment() in {
                    QTextCharFormat.VerticalAlignment.AlignSubScript,
                    QTextCharFormat.VerticalAlignment.AlignSuperScript,
                }
                for run in runs:
                    size = _run_size(run, script=script)
                    if size is not None:
                        yield size
            fragments += 1
        block = block.next()


def _atom_sizes(item: AtomLabelItem) -> Iterator[_GlyphSize]:
    if item.defaultTextColor().alpha() == 0 or not item.toPlainText().strip():
        return
    picture = QPicture()
    painter = _AtomFontPainter(picture)
    try:
        item.paint(painter, QStyleOptionGraphicsItem(), None)
    finally:
        painter.end()
    if painter.outlined:
        raise ValueError("cannot measure an atom label already in outline-only mode")
    if not painter.runs:
        yield from _rich_text_sizes(item)
        return
    for text, font in painter.runs:
        yield from _shaped_sizes(text, font, script=font != item.font())


def _item_sizes(item: QGraphicsItem) -> Iterator[_GlyphSize]:
    if isinstance(item, AtomLabelItem):
        yield from _atom_sizes(item)
    elif isinstance(item, ExportTextItem):
        yield from _rich_text_sizes(item)
        for text, font, color in item.export_list_marker_runs():
            if color.alpha() > 0 and text.strip():
                yield from _shaped_sizes(text, font, script=False)
    elif isinstance(item, QGraphicsTextItem):
        if any(_rich_text_sizes(item)):
            raise ValueError("text does not expose the canonical export typography")
    elif item.data(0) == "ts_bracket":
        data = item.data(1)
        if not isinstance(data, dict) or data.get("bracket_kind") not in {
            "dagger",
            "double_dagger",
        }:
            return
        getter = getattr(item, "export_glyph_run", None)
        run = getter() if callable(getter) else None
        if run is None or not isinstance(item, QGraphicsPathItem):
            raise ValueError("cannot measure a TS glyph without its construction font")
        text, font = run
        brush = item.brush()
        if brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0:
            yield from _shaped_sizes(text, font, script=False)


def _uniform_scene_scale(item: QGraphicsItem) -> float:
    ancestor: QGraphicsItem | None = item
    while ancestor is not None:
        if ancestor.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations:
            raise ValueError("font measurement does not support view-dependent text")
        ancestor = ancestor.parentItem()
    transform = item.sceneTransform()
    x = math.hypot(transform.m11(), transform.m12())
    y = math.hypot(transform.m21(), transform.m22())
    dot = transform.m11() * transform.m21() + transform.m12() * transform.m22()
    if (
        not transform.isAffine()
        or not all(
            math.isfinite(value) for value in (x, y, dot, transform.determinant())
        )
        or x <= 0.0
        or transform.determinant() <= 0.0
        or not math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)
        or not math.isclose(dot, 0.0, abs_tol=1e-9 * x * y)
    ):
        raise ValueError(
            "font measurement requires a finite uniform-scale/rotation transform"
        )
    return x


def _output_scale(
    plan: ExportPlan,
    *,
    output_format: str,
    dpi: int,
    width_pixels: int | None,
    height_pixels: int | None,
) -> float:
    if output_format == "svg":
        width, height = svg_viewport_size_points(plan)
        # The SVG viewport preserves the viewBox aspect ratio. The scene paint
        # also preserves its source aspect ratio, so apply both exact fits.
        scale = min(plan.out_w_pt / plan.source_w, plan.out_h_pt / plan.source_h)
        scale *= min(width / plan.out_w_pt, height / plan.out_h_pt)
    elif (
        output_format == "png"
        and width_pixels is not None
        and height_pixels is not None
    ):
        scale = (
            min(width_pixels / plan.source_w, height_pixels / plan.source_h) * 72 / dpi
        )
    else:
        raise ValueError("font measurement requires resolved SVG or PNG dimensions")
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("font measurement requires a positive finite output scale")
    return scale


def _references(canvas: Any) -> dict[QGraphicsItem, dict[str, object]]:
    references: dict[QGraphicsItem, dict[str, object]] = {}
    for kind, items in (
        ("note", note_items_for(canvas)),
        ("mark", mark_items_for(canvas)),
        ("arrow", arrow_items_for(canvas)),
        ("ts_bracket", ts_bracket_items_for(canvas)),
    ):
        for index, item in enumerate(items):
            references[item] = {"kind": kind, "index": index}
    return references


def assess_export_readability(
    canvas: Any,
    plan: ExportPlan,
    *,
    minimum_font_pt: float,
    output_format: str,
    dpi: int,
    width_pixels: int | None,
    height_pixels: int | None,
) -> dict[str, object]:
    """Reject undersized/unmeasurable glyphs; report resolved em sizes, not ink height."""
    if not math.isfinite(minimum_font_pt) or minimum_font_pt <= 0:
        raise ValueError("minimum font size must be a positive finite number")
    scale = _output_scale(
        plan,
        output_format=output_format,
        dpi=dpi,
        width_pixels=width_pixels,
        height_pixels=height_pixels,
    )
    references = _references(canvas)
    coverage: dict[str, dict[str, int | float]] = {}
    minimum: float | None = None
    witness: dict[str, object] | None = None
    items = export_item_closure(collect_export_items(canvas_scene_for(canvas)))
    for item in items:
        if not item.isVisible() or item.effectiveOpacity() <= 0:
            continue
        reference = references.get(item)
        if item.data(0) == "atom":
            reference = {"kind": "atom", "id": item.data(1)}
        elif item.data(0) == "arrow_label":
            parent = item.parentItem()
            reference = {
                **(references.get(parent, {}) if parent is not None else {}),
                "part": "label",
            }
        reference = reference or {"kind": str(item.data(0))}
        try:
            sizes = list(_item_sizes(item))
            if not sizes:
                continue
            item_scale = _uniform_scene_scale(item) * scale
            for size in sizes:
                points = size.pixels * item_scale
                kind = str(reference["kind"]) + ("_script" if size.script else "")
                row = coverage.setdefault(
                    kind, {"runs": 0, "glyphs": 0, "minimum_pt": points}
                )
                row["runs"] += 1
                row["glyphs"] += size.glyphs
                row["minimum_pt"] = min(row["minimum_pt"], points)
                if minimum is None or points < minimum:
                    minimum = points
                    witness = {**reference, "script": size.script}
        except ValueError as exc:
            raise ValueError(
                f"font readability unavailable for {reference}: {exc}"
            ) from exc
    if minimum is not None and minimum < minimum_font_pt:
        raise ValueError(
            f"minimum visible font is {minimum:.6f} pt at {witness}; "
            f"below --min-font-pt {minimum_font_pt:g}; output was not resized"
        )
    return {
        "minimum_required_pt": minimum_font_pt,
        "minimum_font_pt": minimum,
        "minimum_witness": witness,
        "status": "passed" if minimum is not None else "no-visible-text",
        "measurement": "resolved native glyph em after item and physical-output transforms",
        "scope": "visible atom labels, scripts, notes including automatic numbering, arrow labels, charge text and TS glyphs",
        "exclusions": "whitespace, transparent/hidden text, non-font paths and decoration strokes",
        "coverage": coverage,
        "scene_to_output_pt": scale,
    }


__all__ = ["assess_export_readability"]
