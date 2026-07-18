from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
)

from chemvas.features.annotations import (
    DEFAULT_SHAPE_KIND,
    DEFAULT_STROKE_STYLE,
    LEGACY_TS_BRACKET_KIND,
    normalized_bracket_kind,
    normalized_shape_kind,
    normalized_stroke_style,
    pen_style_for_stroke,
    shape_path,
)
from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.graphics_items import (
    AtomDotItem,
    AtomLabelItem,
    NoSelectLineItem,
    NoSelectPathItem,
)
from chemvas.ui.mark_item_access import mark_selection_radius_for
from chemvas.ui.renderer_style_access import (
    atom_color_for,
    atom_font_for,
    bond_color_for,
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
    font_family_for,
    orbital_alpha_for,
    orbital_negative_color_for,
    orbital_positive_color_for,
)
from chemvas.ui.scene_item_access import add_item_to_canvas_scene


def _radial_orbital_lobes(
    angles_and_phases: tuple[tuple[float, bool], ...],
    rx: float,
    ry: float,
) -> tuple[tuple[float, float, float, float, bool], ...]:
    return tuple(
        (
            math.cos(math.radians(angle)) * 1.1,
            math.sin(math.radians(angle)) * 1.1,
            rx,
            ry,
            positive,
        )
        for angle, positive in angles_and_phases
    )


# Ellipse lobes per orbital kind as (dx, dy, rx, ry, positive_phase), all in
# units of the base radius around the placement center. mo_antibonding also
# paints a nodal line between its lobes (handled in build_orbital_items).
_ORBITAL_LOBE_SPECS: dict[str, tuple[tuple[float, float, float, float, bool], ...]] = {
    "s": ((0.0, 0.0, 1.0, 1.0, True),),
    "p": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, False)),
    "sp": ((-1.2, 0.0, 1.2, 0.7, True), (0.6, 0.0, 0.6, 0.4, False)),
    "sp2": _radial_orbital_lobes(
        ((0.0, True), (120.0, True), (240.0, True)), 0.75, 0.5
    ),
    "sp3": _radial_orbital_lobes(
        ((45.0, True), (135.0, True), (225.0, True), (315.0, True)), 0.7, 0.45
    ),
    "d": _radial_orbital_lobes(
        ((45.0, True), (135.0, False), (225.0, True), (315.0, False)), 0.7, 0.45
    ),
    "mo_bonding": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, True)),
    "mo_antibonding": ((-1.0, 0.0, 1.0, 0.7, True), (1.0, 0.0, 1.0, 0.7, False)),
}


class _ChargeCircleMarkItem(NoSelectPathItem):
    def __init__(self, path: QPainterPath, *, hit_padding: float = 0.0) -> None:
        super().__init__(path)
        self._hit_padding = max(0.0, float(hit_padding))

    def boundingRect(self):
        rect = super().boundingRect()
        if self._hit_padding <= 0.0:
            return rect
        return rect.adjusted(
            -self._hit_padding,
            -self._hit_padding,
            self._hit_padding,
            self._hit_padding,
        )

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self._hit_padding * 2.0))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())


class CanvasSceneDecorationBuildService:
    def __init__(self, canvas, *, arrow_build_service=None) -> None:
        self.canvas = canvas
        self.arrow_build_service = arrow_build_service or CanvasArrowBuildService(
            canvas
        )

    def build_mark_item(self, kind: str):
        selection_radius = mark_selection_radius_for(self.canvas)
        if kind == "radical":
            radius = max(1.2, bond_line_width_for(self.canvas) * 0.7)
            hit_padding = max(0.0, selection_radius - radius)
            item = AtomDotItem(
                -radius, -radius, radius * 2.0, radius * 2.0, hit_padding=hit_padding
            )
            item.setBrush(QColor(atom_color_for(self.canvas)))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            return item
        if kind in {"plus", "minus"}:
            text_item = AtomLabelItem(hit_radius=selection_radius)
            text_item.setFont(atom_font_for(self.canvas))
            text_item.setDefaultTextColor(QColor(atom_color_for(self.canvas)))
            text_item.setPlainText("+" if kind == "plus" else "-")
            return text_item
        if kind in {"circled_plus", "circled_minus"}:
            return self._build_circled_charge_mark(kind, selection_radius)
        return None

    def _build_circled_charge_mark(self, kind: str, selection_radius: float):
        radius = max(4.0, QFontMetricsF(atom_font_for(self.canvas)).height() * 0.26)
        stroke_width = max(0.9, bond_line_width_for(self.canvas) * 0.65)
        symbol_extent = radius * 0.48
        path = QPainterPath()
        path.addEllipse(QRectF(-radius, -radius, radius * 2.0, radius * 2.0))
        path.moveTo(-symbol_extent, 0.0)
        path.lineTo(symbol_extent, 0.0)
        if kind == "circled_plus":
            path.moveTo(0.0, -symbol_extent)
            path.lineTo(0.0, symbol_extent)
        item = _ChargeCircleMarkItem(
            path, hit_padding=max(0.0, selection_radius - radius)
        )
        pen = QPen(
            QColor(atom_color_for(self.canvas)), stroke_width, Qt.PenStyle.SolidLine
        )
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        return item

    def mark_center(self, item) -> QPointF:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            return QPointF(
                item.pos().x() + rect.center().x(), item.pos().y() + rect.center().y()
            )
        return item.pos()

    def set_mark_center(self, item, center: QPointF) -> None:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            item.setPos(center.x() - rect.center().x(), center.y() - rect.center().y())
            return
        item.setPos(center)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        return self.arrow_build_service.preview_arrow(start, end, kind)

    def build_arrow_item(
        self, start: QPointF, end: QPointF, kind: str
    ) -> QGraphicsPathItem:
        return self.arrow_build_service.build_arrow_item(start, end, kind)

    def build_single_head_arrow(
        self, start: QPointF, end: QPointF
    ) -> QGraphicsPathItem:
        return self.arrow_build_service.build_single_head_arrow(start, end)

    def build_double_head_arrow(
        self, start: QPointF, end: QPointF
    ) -> QGraphicsPathItem:
        return self.arrow_build_service.build_double_head_arrow(start, end)

    def build_dotted_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_dotted_arrow(start, end)

    def build_curved_arrow(
        self, start: QPointF, end: QPointF, double: bool
    ) -> QGraphicsPathItem:
        return self.arrow_build_service.build_curved_arrow(start, end, double)

    def build_inhibition_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_inhibition_arrow(start, end)

    def build_equilibrium_item(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return self.arrow_build_service.build_equilibrium_item(start, end)

    def add_arrow_head(
        self, path: QPainterPath, start: QPointF, end: QPointF, double: bool
    ) -> None:
        self.arrow_build_service.add_arrow_head(path, start, end, double)

    def ts_bracket_rect_from_points(self, start: QPointF, end: QPointF) -> QRectF:
        rect = QRectF(start, end).normalized()
        min_width = bond_length_px_for(self.canvas) * 1.8
        min_height = bond_length_px_for(self.canvas) * 2.4
        if rect.width() < 4.0 and rect.height() < 4.0:
            return QRectF(
                start.x() - min_width / 2.0,
                start.y() - min_height / 2.0,
                min_width,
                min_height,
            )
        center = rect.center()
        width = max(rect.width(), min_width)
        height = max(rect.height(), min_height)
        return QRectF(
            center.x() - width / 2.0, center.y() - height / 2.0, width, height
        )

    def ts_bracket_stroke_width(self) -> float:
        return max(0.8, bond_line_width_for(self.canvas) * 0.58)

    def _add_square_bracket_lines(
        self, path: QPainterPath, rect: QRectF, hook: float, *, left: bool
    ) -> None:
        if left:
            x = rect.left()
            path.moveTo(x + hook, rect.top())
            path.lineTo(x, rect.top())
            path.lineTo(x, rect.bottom())
            path.lineTo(x + hook, rect.bottom())
            return
        x = rect.right()
        path.moveTo(x - hook, rect.top())
        path.lineTo(x, rect.top())
        path.lineTo(x, rect.bottom())
        path.lineTo(x - hook, rect.bottom())

    def _add_parenthesis_lines(
        self, path: QPainterPath, rect: QRectF, hook: float, *, left: bool
    ) -> None:
        top = rect.top()
        bottom = rect.bottom()
        middle = rect.center().y()
        control = rect.height() * 0.22
        outer_x = rect.left() if left else rect.right()
        inner_x = outer_x + hook if left else outer_x - hook
        path.moveTo(inner_x, top)
        path.cubicTo(outer_x, top + control, outer_x, middle - control, outer_x, middle)
        path.cubicTo(
            outer_x, middle + control, outer_x, bottom - control, inner_x, bottom
        )

    def _add_brace_lines(
        self, path: QPainterPath, rect: QRectF, hook: float, *, left: bool
    ) -> None:
        top = rect.top()
        bottom = rect.bottom()
        mid = rect.center().y()
        quarter = rect.height() / 4.0
        sign = 1.0 if left else -1.0
        outer_x = rect.left() if left else rect.right()
        inner_x = outer_x + sign * hook
        waist_x = outer_x + sign * hook * 0.18
        shoulder_x = outer_x + sign * hook * 0.62
        path.moveTo(inner_x, top)
        path.cubicTo(
            outer_x, top, outer_x, top + quarter * 0.55, waist_x, top + quarter
        )
        path.cubicTo(
            shoulder_x,
            top + quarter * 1.32,
            shoulder_x,
            mid - quarter * 0.35,
            outer_x,
            mid,
        )
        path.cubicTo(
            shoulder_x,
            mid + quarter * 0.35,
            shoulder_x,
            bottom - quarter * 1.32,
            waist_x,
            bottom - quarter,
        )
        path.cubicTo(outer_x, bottom - quarter * 0.55, outer_x, bottom, inner_x, bottom)

    def _stroked_bracket_lines(self, rect: QRectF, bracket_kind: str) -> QPainterPath:
        rect = QRectF(rect).normalized()
        hook = min(rect.width() * 0.18, bond_length_px_for(self.canvas) * 0.55)
        hook = max(hook, bond_length_px_for(self.canvas) * 0.28)
        bracket_lines = QPainterPath()
        if bracket_kind in {"square_pair", LEGACY_TS_BRACKET_KIND, "square_left"}:
            self._add_square_bracket_lines(bracket_lines, rect, hook, left=True)
            if bracket_kind in {"square_pair", LEGACY_TS_BRACKET_KIND}:
                self._add_square_bracket_lines(bracket_lines, rect, hook, left=False)
        elif bracket_kind in {"parentheses_pair", "parenthesis_left"}:
            self._add_parenthesis_lines(bracket_lines, rect, hook, left=True)
            if bracket_kind == "parentheses_pair":
                self._add_parenthesis_lines(bracket_lines, rect, hook, left=False)
        elif bracket_kind in {"braces_pair", "brace_left"}:
            self._add_brace_lines(bracket_lines, rect, hook, left=True)
            if bracket_kind == "braces_pair":
                self._add_brace_lines(bracket_lines, rect, hook, left=False)

        stroker = QPainterPathStroker()
        stroker.setWidth(self.ts_bracket_stroke_width())
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return stroker.createStroke(bracket_lines)

    def _add_bracket_symbol(
        self, path: QPainterPath, rect: QRectF, symbol: str, *, align_right: bool
    ) -> QPainterPath:
        font = QFont(font_family_for(self.canvas))
        font.setPixelSize(
            max(
                10,
                round(
                    min(rect.height() * 0.62, bond_length_px_for(self.canvas) * 1.35)
                ),
            )
        )
        x = (
            rect.right() + rect.width() * 0.035
            if align_right
            else rect.center().x() - font.pixelSize() * 0.2
        )
        y = rect.center().y() + font.pixelSize() * 0.36
        path.addText(
            x,
            y,
            font,
            symbol,
        )
        return path

    def ts_bracket_path(
        self, rect: QRectF, bracket_kind: str = LEGACY_TS_BRACKET_KIND
    ) -> QPainterPath:
        rect = QRectF(rect).normalized()
        bracket_kind = normalized_bracket_kind(
            bracket_kind, default=LEGACY_TS_BRACKET_KIND
        )
        if bracket_kind == "dagger":
            path = QPainterPath()
            return self._add_bracket_symbol(path, rect, "\u2020", align_right=False)
        if bracket_kind == "double_dagger":
            path = QPainterPath()
            return self._add_bracket_symbol(path, rect, "\u2021", align_right=False)

        path = self._stroked_bracket_lines(rect, bracket_kind)
        if bracket_kind == LEGACY_TS_BRACKET_KIND:
            self._add_bracket_symbol(path, rect, "\u2021", align_right=True)
        return path

    def build_ts_bracket_item(
        self,
        rect: QRectF,
        bracket_kind: str = LEGACY_TS_BRACKET_KIND,
    ) -> QGraphicsPathItem:
        normalized = QRectF(rect).normalized()
        bracket_kind = normalized_bracket_kind(
            bracket_kind, default=LEGACY_TS_BRACKET_KIND
        )
        item = NoSelectPathItem(self.ts_bracket_path(normalized, bracket_kind))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(bond_color_for(self.canvas))))
        item.setData(0, "ts_bracket")
        item.setData(1, {"rect": normalized, "bracket_kind": bracket_kind})
        return item

    def preview_ts_bracket(
        self,
        start: QPointF,
        end: QPointF,
        bracket_kind: str = LEGACY_TS_BRACKET_KIND,
    ):
        item = self.build_ts_bracket_item(
            self.ts_bracket_rect_from_points(start, end), bracket_kind
        )
        preview_color = QColor(120, 120, 120, 140)
        item.setBrush(QBrush(preview_color))
        return add_item_to_canvas_scene(self.canvas, item)

    # --- Free decorative shapes (circle / ellipse / rounded rect / rect) ---
    # Shapes sit behind structures/arrows/text (default z 0) so a shape drawn
    # over existing content never obscures it.
    SHAPE_Z_VALUE = -10.0

    def shape_rect_from_points(self, start: QPointF, end: QPointF) -> QRectF:
        rect = QRectF(start, end).normalized()
        min_size = bond_length_px_for(self.canvas) * 1.2
        if rect.width() < 4.0 and rect.height() < 4.0:
            return QRectF(
                start.x() - min_size / 2.0,
                start.y() - min_size / 2.0,
                min_size,
                min_size,
            )
        return rect

    def shape_stroke_width(self) -> float:
        return max(1.4, bond_line_width_for(self.canvas))

    def shape_pen(self, stroke_style: str = DEFAULT_STROKE_STYLE) -> QPen:
        pen = QPen(QColor(bond_color_for(self.canvas)))
        pen.setWidthF(self.shape_stroke_width())
        pen.setStyle(pen_style_for_stroke(stroke_style))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def build_shape_item(
        self,
        rect: QRectF,
        shape_kind: str = DEFAULT_SHAPE_KIND,
        stroke_style: str = DEFAULT_STROKE_STYLE,
        *,
        fill: QColor | None = None,
    ) -> QGraphicsPathItem:
        normalized = QRectF(rect).normalized()
        shape_kind = normalized_shape_kind(shape_kind)
        stroke_style = normalized_stroke_style(stroke_style)
        item = NoSelectPathItem(shape_path(normalized, shape_kind))
        item.setPen(self.shape_pen(stroke_style))
        # A transparent solid fill keeps the whole interior clickable (so it can be
        # moved/coloured/deleted by clicking inside) while painting nothing.
        item.setBrush(
            QBrush(QColor(0, 0, 0, 0)) if fill is None else QBrush(QColor(fill))
        )
        item.setData(0, "shape")
        item.setData(
            1,
            {
                "rect": normalized,
                "shape_kind": shape_kind,
                "stroke_style": stroke_style,
            },
        )
        item.setZValue(self.SHAPE_Z_VALUE)
        return item

    def preview_shape(
        self,
        start: QPointF,
        end: QPointF,
        shape_kind: str = DEFAULT_SHAPE_KIND,
        stroke_style: str = DEFAULT_STROKE_STYLE,
    ):
        item = self.build_shape_item(
            self.shape_rect_from_points(start, end), shape_kind, stroke_style
        )
        pen = item.pen()
        pen.setColor(QColor(120, 120, 120, 180))
        if pen.style() == Qt.PenStyle.NoPen:
            # Borderless shapes still need drag feedback; the dashed guide
            # exists only in the preview and disappears on commit.
            pen.setStyle(Qt.PenStyle.DashLine)
        item.setPen(pen)
        return add_item_to_canvas_scene(self.canvas, item)

    def build_orbital_items(self, center: QPointF, kind: str):
        radius = bond_length_px_for(self.canvas) * 0.35
        pen = bond_pen_for(self.canvas)
        pos_color = QColor(orbital_positive_color_for(self.canvas))
        neg_color = QColor(orbital_negative_color_for(self.canvas))
        pos_color.setAlphaF(orbital_alpha_for(self.canvas))
        neg_color.setAlphaF(orbital_alpha_for(self.canvas))
        phase_enabled = tool_settings_state_for(self.canvas).orbital_phase_enabled

        items: list[QGraphicsItem] = []
        for dx, dy, rx_factor, ry_factor, positive in _ORBITAL_LOBE_SPECS.get(kind, ()):
            cx = center.x() + dx * radius
            cy = center.y() + dy * radius
            rx = rx_factor * radius
            ry = ry_factor * radius
            item = QGraphicsEllipseItem(cx - rx, cy - ry, rx * 2, ry * 2)
            item.setPen(pen)
            if phase_enabled:
                item.setBrush(pos_color if positive else neg_color)
            items.append(item)
        if kind == "mo_antibonding":
            node = NoSelectLineItem(
                center.x(),
                center.y() - radius * 0.8,
                center.x(),
                center.y() + radius * 0.8,
            )
            node.setPen(pen)
            items.append(node)
        return items

    def arrow_pen(self, dotted: bool = False):
        return self.arrow_build_service.arrow_pen(dotted=dotted)


__all__ = ["CanvasSceneDecorationBuildService"]
