from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath

from chemvas.domain.document import (
    Arrow,
    arrow_from_state,
)
from chemvas.features.annotations import arrow_label_html, arrow_label_position
from chemvas.features.rendering import (
    arrow_path_commands,
    new_arrow_record,
    normalized_arrow_control,
)
from chemvas.ui.canvas.graphics_items import (
    ArrowLabelItem,
    ArrowPathItem,
)
from chemvas.ui.scene.scene_record_ids import (
    bind_scene_record,
    new_scene_record_id,
)

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
        record = normalized_arrow_control(record)
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
            new_arrow_record(
                (start.x(), start.y()),
                (end.x(), end.y()),
                kind,
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
        style = self.context.state.text_style_state
        font = QFont(style.text_font_family, style.text_font_size)
        font.setWeight(style.text_font_weight)
        font.setItalic(style.text_italic)
        path = item.mapToScene(item.path())
        path_points = [
            (path.elementAt(i).x, path.elementAt(i).y)
            for i in range(path.elementCount())
        ]
        for side in ("above", "below"):
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
            top_left = QPointF(
                *arrow_label_position(
                    record,
                    path_points,
                    bond_spacing=self.context.renderer.style.bond_spacing_px,
                    side=side,
                    width=rect.width(),
                    height=rect.height(),
                )
            )
            child.setPos(item.mapFromScene(top_left))

    def arrow_pen(self, dotted: bool = False):
        pen = self.context.renderer.bond_pen()
        pen.setWidthF(self.settings.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


__all__ = ["ARROW_LABEL_ROLE", "ArrowRenderer"]
