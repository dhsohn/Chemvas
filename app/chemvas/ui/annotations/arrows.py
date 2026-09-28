from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath

from chemvas.domain.document import (
    ARC_KIND_SWEEPS,
    VALID_CURVED_ARROW_KINDS,
    Arrow,
    arrow_from_state,
)
from chemvas.features.annotations import arrow_label_html, arrow_label_normal
from chemvas.features.rendering import (
    arc_midpoint,
    arrow_path_commands,
)
from chemvas.ui.canvas.graphics_items import (
    ArrowLabelItem,
    ArrowPathItem,
)
from chemvas.ui.scene.scene_record_ids import (
    bind_scene_record,
    new_scene_record_id,
)
from chemvas.ui.selection.selection_handles import default_curved_control

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PyQt6.QtWidgets import QGraphicsPathItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext

# Role of the child text items that carry an arrow's labels. Hit testing maps
# the role back to the parent arrow, and export collects it so the label
# widens the figure bounds.
ARROW_LABEL_ROLE = "arrow_label"
ARROW_ID_ROLE = 3


class ArrowRenderer:
    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context

    @property
    def settings(self):
        return self.context.state.tool_settings_state

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = self.build_arrow_item(start, end, kind)
        self.context.scene.addItem(item)
        return item

    def record(self, item: QGraphicsPathItem) -> Arrow:
        record = self.context.state.arrow_state.records.get(item.data(ARROW_ID_ROLE))
        if record is None:
            raise RuntimeError("arrow item has no record; its state cannot be read")
        return record

    def discard_record(self, item: QGraphicsPathItem) -> None:
        self.context.state.arrow_state.records.pop(item.data(ARROW_ID_ROLE), None)

    def set_record(self, item: QGraphicsPathItem, record: Arrow) -> None:
        """The sole mutation path for document arrows, including their paint."""
        if record.kind in VALID_CURVED_ARROW_KINDS and record.control is None:
            control = default_curved_control(
                QPointF(*record.start), QPointF(*record.end)
            )
            record = replace(
                record,
                control=(control.x(), control.y()),
                double=record.kind == "curved_double",
            )
        elif record.kind not in VALID_CURVED_ARROW_KINDS and record.control is not None:
            record = replace(record, control=None)
        state = self.context.state.arrow_state
        record_id = item.data(ARROW_ID_ROLE)
        if record_id is None:
            record_id = new_scene_record_id()
            item.setData(ARROW_ID_ROLE, record_id)
            bind_scene_record(item, state, record_id)
        previous = state.records.get(record_id)
        state.records[record_id] = record
        try:
            self.render_record(item, record)
        except Exception:
            if previous is None:
                state.records.pop(record_id, None)
            else:
                state.records[record_id] = previous
            raise

    def create_from_state(self, state: Mapping[str, object]) -> ArrowPathItem:
        item = ArrowPathItem()
        self.set_record(item, arrow_from_state(state))
        return item

    def render_record(self, item: QGraphicsPathItem, record: Arrow) -> None:
        start, end = QPointF(*record.start), QPointF(*record.end)
        rebuilt = self._build_arrow_graphics(
            start,
            end,
            record.kind,
            record.mirrored,
            control=None if record.control is None else QPointF(*record.control),
            double=record.double,
        )
        item.setPos(0.0, 0.0)
        item.setPath(rebuilt.path())
        pen = rebuilt.pen()
        if record.color is not None:
            pen.setColor(QColor(record.color))
        item.setPen(pen)
        item.setBrush(rebuilt.brush())
        item.setData(0, record.kind)
        self.render_labels(item)

    def build_arrow_item(
        self, start: QPointF, end: QPointF, kind: str, mirrored: bool = False
    ):
        item = ArrowPathItem()
        self.set_record(
            item,
            Arrow(
                kind="arrow" if kind == "reaction" else kind,
                start=(start.x(), start.y()),
                end=(end.x(), end.y()),
                mirrored=mirrored,
            ),
        )
        return item

    def _build_arrow_path(
        self,
        start: QPointF,
        end: QPointF,
        kind: str,
        *,
        control: QPointF | None = None,
        double: bool = False,
        mirrored: bool = False,
    ) -> QPainterPath:
        style = self.context.renderer.style
        commands = arrow_path_commands(
            (start.x(), start.y()),
            (end.x(), end.y()),
            kind,
            bond_length=style.bond_length_px,
            bond_spacing=style.bond_spacing_px
            if kind.startswith("equilibrium")
            else 0.0,
            wave_spacing=self.context.renderer.bond_spacing()
            if kind == "line_wavy"
            else 0.0,
            line_width=self.settings.arrow_line_width,
            head_scale=self.settings.arrow_head_scale,
            control=None if control is None else (control.x(), control.y()),
            double=double,
            mirrored=mirrored,
        )
        path = QPainterPath()
        for command, coordinates in commands:
            if command == "M":
                path.moveTo(*coordinates)
            elif command == "L":
                path.lineTo(*coordinates)
            else:
                path.quadTo(*coordinates)
        return path

    def _build_arrow_graphics(
        self,
        start: QPointF,
        end: QPointF,
        kind: str,
        mirrored: bool = False,
        *,
        control: QPointF | None = None,
        double: bool = False,
    ):
        item = ArrowPathItem(
            self._build_arrow_path(
                start,
                end,
                kind,
                control=control,
                double=double,
                mirrored=mirrored,
            )
        )
        item.setPen(
            self.context.renderer.bold_bond_pen()
            if kind == "line_bold"
            else self.arrow_pen(dotted=kind in {"dotted", "line_dashed"})
        )
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_curved_arrow_path(
        self,
        start: QPointF,
        end: QPointF,
        control: QPointF,
        double: bool,
    ) -> QPainterPath:
        """Use the same path owner when dragging an existing curve's handles."""
        return self._build_arrow_path(
            start,
            end,
            "curved_double" if double else "curved_single",
            control=control,
            double=double,
        )

    def render_labels(self, item: QGraphicsPathItem) -> None:
        """Draw label children from the record and current document typography."""
        record = self.record(item)
        for child in list(item.childItems()):
            if child.data(0) == ARROW_LABEL_ROLE:
                child.setParentItem(None)
                scene = child.scene()
                if scene is not None:
                    scene.removeItem(child)
        if not record.labels:
            return
        labels = dict(record.labels)
        start, end = QPointF(*record.start), QPointF(*record.end)
        control = None if record.control is None else QPointF(*record.control)
        kind = record.kind
        if isinstance(control, QPointF):
            # Midpoint of the quadratic curve at t = 0.5.
            mid = QPointF(
                0.25 * start.x() + 0.5 * control.x() + 0.25 * end.x(),
                0.25 * start.y() + 0.5 * control.y() + 0.25 * end.y(),
            )
        elif kind in ARC_KIND_SWEEPS:
            sweep_degrees, bulge_left = ARC_KIND_SWEEPS[kind]
            mid = QPointF(
                *arc_midpoint(
                    (start.x(), start.y()),
                    (end.x(), end.y()),
                    sweep_degrees=sweep_degrees,
                    bulge_left=bulge_left,
                )
            )
        else:
            mid = QPointF((start.x() + end.x()) * 0.5, (start.y() + end.y()) * 0.5)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        nx, ny = arrow_label_normal(dx, dy)
        style = self.context.state.text_style_state
        font = QFont(style.text_font_family, style.text_font_size)
        font.setWeight(style.text_font_weight)
        font.setItalic(style.text_italic)
        # Measure how far the arrow's own strokes (harpoons, barbs) reach
        # from the axis along the normal, so the label clears them at any
        # bond length; a curved arrow's or arc's chord ends are not part of
        # that, since their labels sit at the curve midpoint instead.
        path = item.mapToScene(item.path())
        arrow_extent = 0.0
        if not isinstance(control, QPointF) and kind not in ARC_KIND_SWEEPS:
            for index in range(path.elementCount()):
                element = path.elementAt(index)
                offset = (element.x - mid.x()) * nx + (element.y - mid.y()) * ny
                arrow_extent = max(arrow_extent, abs(offset))
        gap = arrow_extent + self.context.renderer.style.bond_spacing_px
        for side, sign in (("above", 1.0), ("below", -1.0)):
            text = labels.get(side)
            if not text:
                continue
            child = ArrowLabelItem(item)
            child.setData(0, ARROW_LABEL_ROLE)
            child.setData(1, side)
            child.setFont(font)
            child.setDefaultTextColor(QColor(record.color or style.text_color))
            child.setHtml(arrow_label_html(text))
            rect = child.boundingRect()
            # Half of the label box projected onto the normal, so a vertical
            # arrow clears the label's width and a horizontal one its height.
            half_extent = abs(nx) * rect.width() * 0.5 + abs(ny) * rect.height() * 0.5
            distance = gap + half_extent
            center = QPointF(
                mid.x() + nx * sign * distance, mid.y() + ny * sign * distance
            )
            top_left = QPointF(
                center.x() - rect.width() * 0.5, center.y() - rect.height() * 0.5
            )
            child.setPos(item.mapFromScene(top_left))

    def arrow_pen(self, dotted: bool = False):
        pen = self.context.renderer.bond_pen()
        pen.setWidthF(self.settings.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


__all__ = ["ARROW_LABEL_ROLE", "ArrowRenderer"]
