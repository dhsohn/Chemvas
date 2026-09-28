from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtGui import QBrush, QFont, QPen

from chemvas.features.rendering import RenderMetrics


class Renderer(RenderMetrics):
    def bond_pen(self) -> QPen:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPen

        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.bond_line_width())
        # Round caps let the ends of two bonds meeting at an atom overlap into a
        # clean join instead of leaving the notch a flat cap cuts at each vertex.
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def dotted_bond_pen(self) -> QPen:
        from PyQt6.QtCore import Qt

        pen = self.bond_pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    def bold_bond_pen(self) -> QPen:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QPen

        pen = QPen(QColor(self.style.bond_color))
        pen.setWidthF(self.bold_bond_width())
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def atom_font(self) -> QFont:
        from PyQt6.QtGui import QFont

        font = QFont(self.style.font_family, self.atom_font_size_pt())
        return font

    def ring_fill_brush(self, color: str | None = None) -> QBrush:
        from PyQt6.QtGui import QBrush, QColor

        fill = QColor(color or self.style.ring_fill_color)
        fill.setAlphaF(self.style.ring_fill_alpha)
        return QBrush(fill)
