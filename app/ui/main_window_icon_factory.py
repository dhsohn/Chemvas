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
from ui.main_window_design_icon_renderer import draw_design_icon, has_design_icon
from ui.main_window_icon_canvas_style import MainWindowIconCanvasStyle
from ui.main_window_icon_pixmap_factory import MainWindowIconPixmapFactory
from ui.main_window_palette import PALETTE
from ui.main_window_template_icon_renderer import MainWindowTemplateIconRenderer
from ui.main_window_tool_icon_renderer import MainWindowToolIconRenderer
from ui.main_window_utility_icon_renderer import MainWindowUtilityIconRenderer

_TEMPLATE_ICON_BY_LABEL: dict[str, str] = {
    "Benzene": "template_benzene",
    "Cyclopropane": "template_ring3",
    "Cyclobutane": "template_ring4",
    "Cyclopentane": "template_ring5",
    "Cyclohexane (Chair)": "template_chair",
    "Cyclohexane (Chair, flipped)": "template_chair_flip",
    "Cycloheptane": "template_ring7",
    "Cyclooctane": "template_ring8",
}


class MainWindowIconFactory:
    ICON_SIZE = 30
    ICON_CONTENT_MIN = 5
    ICON_CONTENT_MAX = 25
    ICON_CENTER = ICON_SIZE // 2

    STROKE_COLOR = PALETTE["icon"]
    MUTED_STROKE_COLOR = PALETTE["icon_muted"]
    PALE_FILL_COLOR = PALETTE["icon_pale_fill"]
    ACCENT_FILL_COLOR = PALETTE["icon_accent_fill"]

    # Stroke weights are kept in a tight band so every icon reads as one set.
    # Line work converges on ~1.8; only bond/ring glyphs stay a touch heavier
    # (molecule) so they echo the canvas bond weight.
    STROKE_FINE = 1.7
    STROKE_THIN = 1.8
    STROKE_REGULAR = 1.8
    STROKE_MOLECULE = 2.0
    STROKE_ACTIVE = 2.0

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

    # Logical sizes the design icons are actually displayed at: 16px in the
    # context options bar, 18px in the toolbars, plus the 30px base. Rendering an
    # exact pixmap per size keeps small icons crisp instead of downscaling one.
    DESIGN_ICON_SIZES = (16, 18, ICON_SIZE)

    def make_design_icon(self, name: str) -> QIcon:
        return self._pixmap_icons.make_sized_icon(
            lambda painter, size: draw_design_icon(painter, name, size=size),
            self.DESIGN_ICON_SIZES,
        )

    def _design_icon(self, name: str, fallback: str) -> QIcon:
        return self.make_design_icon(name if has_design_icon(name) else fallback)

    def icon_select(self) -> QIcon:
        return self.make_design_icon("move")

    def icon_bond(self) -> QIcon:
        return self.make_design_icon("bond")

    def icon_bond_bold(self) -> QIcon:
        return self.make_design_icon("bond_bold")

    def icon_mark(self) -> QIcon:
        return self.make_design_icon("atom_orbit")

    def icon_mark_plus(self) -> QIcon:
        return self.make_design_icon("plus")

    def icon_mark_minus(self) -> QIcon:
        return self.make_design_icon("minus")

    def icon_mark_circled_plus(self) -> QIcon:
        return self.make_design_icon("circled_plus")

    def icon_mark_circled_minus(self) -> QIcon:
        return self.make_design_icon("circled_minus")

    def icon_mark_radical(self) -> QIcon:
        return self.make_design_icon("radical")

    def icon_text(self) -> QIcon:
        return self.make_design_icon("atom")

    def icon_note(self) -> QIcon:
        return self.make_design_icon("note")

    def icon_font(self) -> QIcon:
        return self.make_design_icon("font")

    def icon_text_bold(self) -> QIcon:
        return self.make_design_icon("text_bold")

    def icon_text_italic(self) -> QIcon:
        return self.make_design_icon("text_italic")

    def icon_text_superscript(self) -> QIcon:
        return self.make_design_icon("text_superscript")

    def icon_text_subscript(self) -> QIcon:
        return self.make_design_icon("text_subscript")

    def icon_text_size_increase(self) -> QIcon:
        return self.make_design_icon("text_size_increase")

    def icon_text_size_decrease(self) -> QIcon:
        return self.make_design_icon("text_size_decrease")

    def icon_align_left(self) -> QIcon:
        return self.make_design_icon("align_left")

    def icon_align_center(self) -> QIcon:
        return self.make_design_icon("align_center")

    def icon_align_right(self) -> QIcon:
        return self.make_design_icon("align_right")

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
        return self.make_design_icon("benzene")

    def icon_ring_fill(self) -> QIcon:
        return self.make_design_icon("ring_fill")

    def icon_undo(self) -> QIcon:
        return self.make_design_icon("undo")

    def icon_redo(self) -> QIcon:
        return self.make_design_icon("redo")

    def icon_save(self) -> QIcon:
        return self.make_design_icon("save")

    def icon_open(self) -> QIcon:
        return self.make_design_icon("open")

    def icon_preview_panel(self) -> QIcon:
        return self.make_design_icon("panel_right")

    def icon_add_canvas(self) -> QIcon:
        return self.make_design_icon("canvas")

    def icon_setup_sheet(self) -> QIcon:
        return self.make_design_icon("sheet")

    def icon_templates(self) -> QIcon:
        return self.make_design_icon("templates")

    def icon_info(self) -> QIcon:
        return self.make_design_icon("info")

    def icon_bond_double(self) -> QIcon:
        return self.make_design_icon("bond_double")

    def icon_bond_triple(self) -> QIcon:
        return self.make_design_icon("bond_triple")

    def icon_bond_wedge(self) -> QIcon:
        return self.make_design_icon("wedge")

    def icon_bond_hash(self) -> QIcon:
        return self.make_design_icon("hash")

    def icon_bond_dotted(self) -> QIcon:
        return self.make_design_icon("bond_dotted")

    def icon_bond_length(self) -> QIcon:
        return self.make_design_icon("bond_length")

    def icon_arrow_preview(self, kind: str) -> QIcon:
        return self._design_icon(f"arrow_{kind}", "arrow_reaction")

    def icon_arrow_preset(self, label: str) -> QIcon:
        return self._design_icon(f"arrow_preset_{label.lower()}", "arrow_preset_default")

    def icon_arrow_width(self) -> QIcon:
        return self.make_design_icon("arrow_width")

    def icon_arrow_head_scale(self) -> QIcon:
        return self.make_design_icon("arrow_head_scale")

    def icon_orbital_preview(self, kind: str) -> QIcon:
        return self._design_icon(f"orbital_{kind}", "orbital_s")

    def icon_orbital_phase(self, enabled: bool) -> QIcon:
        return self.make_design_icon("orbital_phase_on" if enabled else "orbital_phase_off")

    def icon_template_preview(self, label: str) -> QIcon:
        return self._design_icon(_TEMPLATE_ICON_BY_LABEL.get(label, "template_ring6"), "template_ring6")

    def icon_flip_h(self) -> QIcon:
        return self.make_design_icon("flip_h")

    def icon_flip_v(self) -> QIcon:
        return self.make_design_icon("flip_v")

    def icon_rotate(self) -> QIcon:
        return self.make_design_icon("rotate")

    def icon_arrow(self) -> QIcon:
        return self.make_design_icon("arrow")

    def icon_ts_bracket(self) -> QIcon:
        return self.make_design_icon("bracket")

    def icon_bracket_preview(self, kind: str) -> QIcon:
        return self._design_icon(f"bracket_{kind}", "bracket_square_pair")

    def icon_orbital(self) -> QIcon:
        return self.make_design_icon("orbital")

    def icon_shape(self) -> QIcon:
        return self.make_design_icon("shape")

    def icon_shape_kind(self, kind: str) -> QIcon:
        return self._design_icon(f"shape_{kind}", "shape_circle")

    def icon_shape_stroke(self, style: str) -> QIcon:
        return self._design_icon(f"stroke_{style}", "stroke_solid")

    def icon_move(self) -> QIcon:
        return self.make_design_icon("move")

    def icon_color(self) -> QIcon:
        return self.make_design_icon("color")

    def icon_perspective(self) -> QIcon:
        return self.make_design_icon("perspective")


__all__ = ["MainWindowIconFactory"]
