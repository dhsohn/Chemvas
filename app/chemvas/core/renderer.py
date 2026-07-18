from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen

from chemvas.core.style_acs1996 import ACS1996Style


class Renderer:
    BASE_BOND_LENGTH_PX = 20.0

    def __init__(self, style: ACS1996Style | None = None) -> None:
        self.style = style or ACS1996Style()

    def set_bond_length(self, length_px: float) -> None:
        self.style = replace(self.style, bond_length_px=length_px)

    def metric_scale(self) -> float:
        if self.style.bond_length_px <= 0:
            return 1.0
        return self.style.bond_length_px / self.BASE_BOND_LENGTH_PX

    def scaled_style_metric(self, value: float) -> float:
        return value * self.metric_scale()

    def bond_line_width(self) -> float:
        return self.scaled_style_metric(self.style.bond_line_width)

    def bold_bond_width(self) -> float:
        return self.scaled_style_metric(self.style.bold_bond_width)

    def bond_spacing(self) -> float:
        return self.scaled_style_metric(self.style.bond_spacing_px)

    def hash_spacing(self) -> float:
        return self.scaled_style_metric(self.style.hash_spacing_px)

    def atom_font_size_pt(self) -> int:
        return max(1, round(self.scaled_style_metric(float(self.style.font_size_pt))))

    def bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.bond_line_width())
        # Round caps let the ends of two bonds meeting at an atom overlap into a
        # clean join instead of leaving the notch a flat cap cuts at each vertex.
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def dotted_bond_pen(self) -> QPen:
        pen = self.bond_pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def bold_bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.bold_bond_width())
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def atom_font(self) -> QFont:
        font = QFont(self.style.font_family, self.atom_font_size_pt())
        return font

    def ring_fill_brush(self, color: str | None = None) -> QBrush:
        fill = QColor(color or self.style.ring_fill_color)
        fill.setAlphaF(self.style.ring_fill_alpha)
        return QBrush(fill)
