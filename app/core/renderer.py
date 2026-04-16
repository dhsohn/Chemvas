from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen

from core.style_acs1996 import ACS1996Style


class Renderer:
    def __init__(self, style: ACS1996Style | None = None) -> None:
        self.style = style or ACS1996Style()

    def set_bond_length(self, length_px: float) -> None:
        self.style = replace(self.style, bond_length_px=length_px)

    def bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.style.bond_line_width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def dotted_bond_pen(self) -> QPen:
        pen = self.bond_pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def bold_bond_pen(self) -> QPen:
        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.style.bold_bond_width * 1.5)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def atom_font(self) -> QFont:
        font = QFont(self.style.font_family, self.style.font_size_pt)
        return font

    def ring_fill_brush(self, color: str | None = None) -> QBrush:
        fill = QColor(color or self.style.ring_fill_color)
        fill.setAlphaF(self.style.ring_fill_alpha)
        return QBrush(fill)
