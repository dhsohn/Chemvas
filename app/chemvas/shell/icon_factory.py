from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.shell.icon_design import (
    draw_design_icon,
    has_design_icon,
)
from chemvas.shell.icon_pixmap_factory import MainWindowIconPixmapFactory

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon

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

    def __init__(self, window: object) -> None:
        self._pixmap_icons = MainWindowIconPixmapFactory(default_size=self.ICON_SIZE)

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

    def icon_ring(self) -> QIcon:
        return self.make_design_icon("benzene")

    def icon_ring_fill(self) -> QIcon:
        return self.make_design_icon("ring_fill")

    def icon_eraser(self) -> QIcon:
        return self.make_design_icon("eraser")

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

    def icon_arrow_preview(self, kind: str) -> QIcon:
        return self._design_icon(f"arrow_{kind}", "arrow_reaction")

    def icon_arrow_preset(self, label: str) -> QIcon:
        return self._design_icon(
            f"arrow_preset_{label.lower()}", "arrow_preset_default"
        )

    def icon_arrow_width(self) -> QIcon:
        return self.make_design_icon("arrow_width")

    def icon_arrow_head_scale(self) -> QIcon:
        return self.make_design_icon("arrow_head_scale")

    def icon_orbital_preview(self, kind: str) -> QIcon:
        return self._design_icon(f"orbital_{kind}", "orbital_s")

    def icon_orbital_phase(self, enabled: bool) -> QIcon:
        return self.make_design_icon(
            "orbital_phase_on" if enabled else "orbital_phase_off"
        )

    def icon_template_preview(self, label: str) -> QIcon:
        return self._design_icon(
            _TEMPLATE_ICON_BY_LABEL.get(label, "template_ring6"), "template_ring6"
        )

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

    def icon_color(self) -> QIcon:
        return self.make_design_icon("color")

    def icon_perspective(self) -> QIcon:
        return self.make_design_icon("perspective")


__all__ = ["MainWindowIconFactory"]
