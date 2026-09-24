from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath

from chemvas.domain.document import (
    ARC_KIND_SWEEPS,
    VALID_ARC_KINDS,
    VALID_CURVED_ARROW_KINDS,
    VALID_LINE_KINDS,
    Arrow,
    arrow_from_state,
)
from chemvas.features.annotations import arrow_label_html, arrow_label_normal
from chemvas.features.rendering import arc_midpoint, arc_points, wavy_line_points
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
        rebuilt = self._build_arrow_graphics(start, end, record.kind, record.mirrored)
        if record.kind in VALID_CURVED_ARROW_KINDS and record.control is not None:
            rebuilt.setPath(
                self.build_curved_arrow_path(
                    start, end, QPointF(*record.control), record.double
                )
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

    def _build_arrow_graphics(
        self, start: QPointF, end: QPointF, kind: str, mirrored: bool = False
    ):
        if kind in VALID_LINE_KINDS:
            return self.build_line_item(start, end, kind)
        if kind in VALID_ARC_KINDS:
            return self.build_arc_arrow(start, end, kind)
        if kind == "equilibrium":
            return self.build_equilibrium_item(start, end, mirrored=mirrored)
        if kind == "equilibrium_forward":
            return self.build_equilibrium_item(
                start, end, favored="forward", mirrored=mirrored
            )
        if kind == "equilibrium_reverse":
            return self.build_equilibrium_item(
                start, end, favored="reverse", mirrored=mirrored
            )
        if kind == "resonance":
            return self.build_double_head_arrow(start, end)
        if kind == "curved_single":
            return self.build_curved_arrow(start, end, double=False)
        if kind == "curved_double":
            return self.build_curved_arrow(start, end, double=True)
        if kind == "inhibit":
            return self.build_inhibition_arrow(start, end)
        if kind == "dotted":
            return self.build_dotted_arrow(start, end)
        return self.build_single_head_arrow(start, end)

    def build_single_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_double_head_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        self.add_arrow_head(path, end, start, double=False)
        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_dotted_arrow(self, start: QPointF, end: QPointF):
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(path, start, end, double=False)
        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen(dotted=True))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_arc_arrow(self, start: QPointF, end: QPointF, kind: str):
        sweep_degrees, bulge_left = ARC_KIND_SWEEPS[kind]
        points = arc_points(
            (start.x(), start.y()),
            (end.x(), end.y()),
            sweep_degrees=sweep_degrees,
            bulge_left=bulge_left,
        )
        path = QPainterPath()
        path.moveTo(*points[0])
        for x, y in points[1:]:
            path.lineTo(x, y)
        # The head follows the arc's final tangent, not the chord.
        self.add_arrow_head(path, QPointF(*points[-2]), end, double=False)
        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_line_item(self, start: QPointF, end: QPointF, kind: str):
        path = QPainterPath()
        if kind == "line_wavy":
            # One half-wave per bond spacing keeps the wave in step with the
            # ACS bond metrics, so it scales with the document like a bond.
            spacing = self.context.renderer.bond_spacing()
            points = wavy_line_points(
                (start.x(), start.y()),
                (end.x(), end.y()),
                half_wavelength=spacing,
                amplitude=spacing * 0.5,
            )
            path.moveTo(*points[0])
            for x, y in points[1:]:
                path.lineTo(x, y)
        else:
            path.moveTo(start)
            path.lineTo(end)
        item = ArrowPathItem(path)
        if kind == "line_bold":
            item.setPen(self.context.renderer.bold_bond_pen())
        else:
            item.setPen(self.arrow_pen(dotted=kind == "line_dashed"))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_curved_arrow(self, start: QPointF, end: QPointF, double: bool):
        control = default_curved_control(start, end)
        item = ArrowPathItem(self.build_curved_arrow_path(start, end, control, double))
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_curved_arrow_path(
        self, start: QPointF, end: QPointF, control: QPointF, double: bool
    ) -> QPainterPath:
        """The same quadratic path and heads for creation and later edits."""
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self.add_arrow_head(path, control, end, double=False)
            self.add_arrow_head(path, control, start, double=False)
        else:
            self.add_arrow_head(path, control, end, double=False)
        return path

    def build_inhibition_arrow(self, start: QPointF, end: QPointF):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        bar = self.context.renderer.style.bond_length_px * 0.2

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        bar_start = QPointF(end.x() - nx * bar, end.y() - ny * bar)
        bar_end = QPointF(end.x() + nx * bar, end.y() + ny * bar)
        path.moveTo(bar_start)
        path.lineTo(bar_end)
        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def build_equilibrium_item(
        self,
        start: QPointF,
        end: QPointF,
        favored: str | None = None,
        *,
        mirrored: bool = False,
    ):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        # Keep the shafts one bond spacing apart, with room for thick strokes.
        offset = max(
            self.context.renderer.style.bond_spacing_px * 0.5,
            self.settings.arrow_line_width,
        )
        if mirrored:
            offset = -offset
        forward_start = QPointF(start.x() - nx * offset, start.y() - ny * offset)
        forward_end = QPointF(end.x() - nx * offset, end.y() - ny * offset)
        reverse_start = QPointF(end.x() + nx * offset, end.y() + ny * offset)
        reverse_end = QPointF(start.x() + nx * offset, start.y() + ny * offset)
        # A favored direction keeps that harpoon full length and shortens the
        # other one to half, centred on the arrow, the way ChemDraw draws it.
        if favored == "forward":
            reverse_start, reverse_end = self._centered_half(reverse_start, reverse_end)
        elif favored == "reverse":
            forward_start, forward_end = self._centered_half(forward_start, forward_end)

        path = QPainterPath()
        self.add_harpoon(path, forward_start, forward_end, mirrored=mirrored)
        self.add_harpoon(path, reverse_start, reverse_end, mirrored=mirrored)

        item = ArrowPathItem(path)
        item.setPen(self.arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    @staticmethod
    def _centered_half(start: QPointF, end: QPointF) -> tuple[QPointF, QPointF]:
        mid_x = (start.x() + end.x()) * 0.5
        mid_y = (start.y() + end.y()) * 0.5
        return (
            QPointF(
                mid_x + (start.x() - mid_x) * 0.5, mid_y + (start.y() - mid_y) * 0.5
            ),
            QPointF(mid_x + (end.x() - mid_x) * 0.5, mid_y + (end.y() - mid_y) * 0.5),
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

    def add_harpoon(
        self,
        path: QPainterPath,
        start: QPointF,
        end: QPointF,
        *,
        mirrored: bool = False,
    ) -> None:
        path.moveTo(start)
        path.lineTo(end)
        self.add_arrow_head(
            path, start, end, double=False, half=True, mirrored=mirrored
        )

    def add_arrow_head(
        self,
        path: QPainterPath,
        start: QPointF,
        end: QPointF,
        double: bool,
        half: bool = False,
        mirrored: bool = False,
    ) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = (
            self.context.renderer.style.bond_length_px * self.settings.arrow_head_scale
        )
        head_angle = math.radians(-25 if mirrored else 25)
        offsets = [0.0]
        if double:
            offset_mag = max(1.4, self.settings.arrow_line_width * 1.2)
            offsets = [-offset_mag, offset_mag]
        for offset in offsets:
            dx = math.cos(angle + math.pi / 2) * offset
            dy = math.sin(angle + math.pi / 2) * offset
            tip = QPointF(end.x() + dx, end.y() + dy) if double else end
            right = QPointF(
                tip.x() - head_len * math.cos(angle + head_angle),
                tip.y() - head_len * math.sin(angle + head_angle),
            )
            # A half head keeps the barb on the side the line was offset toward,
            # so an equilibrium pair carries both barbs on the outside and reads
            # as the conventional harpoon arrow rather than two full heads.
            if half:
                path.moveTo(right)
                path.lineTo(tip)
                continue
            left = QPointF(
                tip.x() - head_len * math.cos(angle - head_angle),
                tip.y() - head_len * math.sin(angle - head_angle),
            )
            path.moveTo(left)
            path.lineTo(tip)
            path.lineTo(right)

    def arrow_pen(self, dotted: bool = False):
        pen = self.context.renderer.bond_pen()
        pen.setWidthF(self.settings.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen


__all__ = ["ARROW_LABEL_ROLE", "ArrowRenderer"]
