from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPen,
    QPolygonF,
)

from ui.main_window_arrow_icon_renderer import MainWindowArrowIconRenderer
from ui.main_window_bond_icon_renderer import MainWindowBondIconRenderer
from ui.main_window_icon_canvas_style import MainWindowIconCanvasStyle
from ui.main_window_icon_pixmap_factory import MainWindowIconPixmapFactory
from ui.main_window_template_icon_renderer import MainWindowTemplateIconRenderer
from ui.main_window_tool_icon_renderer import MainWindowToolIconRenderer
from ui.main_window_utility_icon_renderer import MainWindowUtilityIconRenderer


class MainWindowIconFactory:
    ICON_SIZE = 30
    ICON_CONTENT_MIN = 5
    ICON_CONTENT_MAX = 25
    ICON_CENTER = ICON_SIZE // 2

    STROKE_COLOR = "#2f2f2c"
    MUTED_STROKE_COLOR = "#8c8c87"
    PALE_FILL_COLOR = "#ededeb"
    ACCENT_FILL_COLOR = "#d3d3ce"

    STROKE_FINE = 1.2
    STROKE_THIN = 1.6
    STROKE_REGULAR = 1.8
    STROKE_MOLECULE = 2.0
    STROKE_ACTIVE = 2.2

    def __init__(self, window, *, canvas_style=None) -> None:
        self._pixmap_icons = MainWindowIconPixmapFactory(default_size=self.ICON_SIZE)
        self._canvas_style = MainWindowIconCanvasStyle(window) if canvas_style is None else canvas_style
        self._bond_icons = MainWindowBondIconRenderer(
            canvas_style=self._canvas_style,
            icon_pen=self._icon_pen,
            renderer_icon_pen=self._renderer_icon_pen,
            icon_brush=self._icon_brush,
            stroke_active=self.STROKE_ACTIVE,
            stroke_thin=self.STROKE_THIN,
            stroke_regular=self.STROKE_REGULAR,
            stroke_molecule=self.STROKE_MOLECULE,
            icon_size=self.ICON_SIZE,
        )
        self._arrow_icons = MainWindowArrowIconRenderer(
            icon_pen=self._icon_pen,
            stroke_thin=self.STROKE_THIN,
            stroke_active=self.STROKE_ACTIVE,
            icon_content_min=self.ICON_CONTENT_MIN,
            icon_center=self.ICON_CENTER,
        )
        self._template_icons = MainWindowTemplateIconRenderer(
            icon_pen=self._icon_pen,
            stroke_regular=self.STROKE_REGULAR,
            stroke_thin=self.STROKE_THIN,
        )
        self._utility_icons = MainWindowUtilityIconRenderer(
            icon_pen=self._icon_pen,
            icon_brush=self._icon_brush,
            stroke_thin=self.STROKE_THIN,
            stroke_regular=self.STROKE_REGULAR,
        )
        self._tool_icons = MainWindowToolIconRenderer(
            icon_pen=self._icon_pen,
            icon_brush=self._icon_brush,
            stroke_fine=self.STROKE_FINE,
            stroke_thin=self.STROKE_THIN,
            stroke_regular=self.STROKE_REGULAR,
            stroke_molecule=self.STROKE_MOLECULE,
            stroke_active=self.STROKE_ACTIVE,
            icon_content_min=self.ICON_CONTENT_MIN,
            icon_content_max=self.ICON_CONTENT_MAX,
            icon_center=self.ICON_CENTER,
            pale_fill_color=self.PALE_FILL_COLOR,
            accent_fill_color=self.ACCENT_FILL_COLOR,
        )

    def _icon_color(self, color=None) -> QColor:
        return QColor(self.STROKE_COLOR if color is None else color)

    def _icon_pen(
        self,
        width: float | None = None,
        *,
        color=None,
        style: Qt.PenStyle | None = None,
    ) -> QPen:
        pen = QPen(self._icon_color(color))
        pen.setWidthF(self.STROKE_THIN if width is None else width)
        if style is not None:
            pen.setStyle(style)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def _icon_brush(self, color=None) -> QBrush:
        return QBrush(self._icon_color(color))

    def _renderer_icon_pen(self, pen: QPen) -> QPen:
        icon_pen = QPen(pen)
        icon_pen.setColor(self._icon_color())
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        icon_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return icon_pen

    def make_icon(self, painter_fn, size: int | None = None) -> QIcon:
        return self._pixmap_icons.make_icon(painter_fn, size=size)

    def icon_select(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_select)

    def icon_bond(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_bond)

    def icon_bond_bold(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_bold_bond)

    def icon_mark(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_mark)

    def icon_mark_plus(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_mark_plus)

    def icon_mark_minus(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_mark_minus)

    def icon_mark_radical(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_mark_radical)

    def icon_text(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_text)

    def benzene_icon_inner_segments(
        self,
        polygon: QPolygonF,
        center: QPointF,
        *,
        spacing_scale: float = 1.0,
    ) -> list[tuple[QPointF, QPointF]]:
        return self._bond_icons.benzene_icon_inner_segments(
            polygon,
            center,
            spacing_scale=spacing_scale,
        )

    def icon_ring(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_ring, size=self.ICON_SIZE)

    def icon_ring_fill(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_ring_fill)

    def icon_undo(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_undo)

    def icon_redo(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_redo)

    def icon_save(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_save)

    def icon_open(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_open)

    def icon_export_xyz(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_export_xyz)

    def icon_preview_panel(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_preview_panel)

    def icon_add_sheet(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_add_sheet)

    def icon_setup_sheet(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_setup_sheet)

    def icon_templates(self) -> QIcon:
        return self.make_icon(self._template_icons.draw_templates)

    def icon_info(self) -> QIcon:
        return self.make_icon(self._utility_icons.draw_info)

    def icon_bond_double(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_double_bond)

    def icon_bond_triple(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_triple_bond)

    def icon_bond_wedge(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_wedge_bond)

    def icon_bond_hash(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_hash_bond)

    def icon_bond_dotted(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_dotted_bond)

    def icon_bond_length(self) -> QIcon:
        return self.make_icon(self._bond_icons.draw_bond_length)

    def icon_arrow_preview(self, kind: str) -> QIcon:
        return self.make_icon(lambda painter: self._arrow_icons.draw_arrow_preview(painter, kind))

    def icon_arrow_preset(self, label: str) -> QIcon:
        return self.make_icon(lambda painter: self._arrow_icons.draw_arrow_preset(painter, label))

    def icon_arrow_width(self) -> QIcon:
        return self.make_icon(self._arrow_icons.draw_arrow_width_control)

    def icon_arrow_head_scale(self) -> QIcon:
        return self.make_icon(self._arrow_icons.draw_arrow_head_control)

    def icon_orbital_preview(self, kind: str) -> QIcon:
        return self.make_icon(lambda painter: self._tool_icons.draw_orbital_preview(painter, kind))

    def icon_template_preview(self, label: str) -> QIcon:
        return self.make_icon(lambda painter: self._template_icons.draw_template_preview(painter, label))

    def icon_flip_h(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_flip_h)

    def icon_flip_v(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_flip_v)

    def icon_arrow(self) -> QIcon:
        return self.make_icon(self._arrow_icons.draw_arrow)

    def icon_ts_bracket(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_ts_bracket)

    def icon_orbital(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_orbital)

    def icon_move(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_move)

    def icon_color(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_color)

    def icon_perspective(self) -> QIcon:
        return self.make_icon(self._tool_icons.draw_perspective)


__all__ = ["MainWindowIconFactory"]
