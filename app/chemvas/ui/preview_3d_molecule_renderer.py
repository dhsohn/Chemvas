from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

if TYPE_CHECKING:
    from chemvas.features.insertion import Molecule3DScene
    from chemvas.ui.preview_3d_projection import ProjectedAtom


def preview_element_color(symbol: str) -> QColor:
    palette = {
        "H": QColor("#ededeb"),
        "C": QColor("#4a4a48"),
        "N": QColor("#4b73c4"),
        "O": QColor("#cc584d"),
        "S": QColor("#d0a532"),
        "P": QColor("#d7883d"),
        "F": QColor("#6ea36d"),
        "Cl": QColor("#5f955e"),
        "Br": QColor("#8b5c43"),
        "I": QColor("#7a5ca8"),
    }
    return palette.get(symbol, QColor("#cfcfca"))


def draw_projected_scene(
    painter: QPainter,
    scene: Molecule3DScene,
    projected_atoms: list[ProjectedAtom],
) -> None:
    bond_depths = []
    for bond in scene.bonds:
        if bond.a >= len(projected_atoms) or bond.b >= len(projected_atoms):
            continue
        ax, ay, az, _ = projected_atoms[bond.a]
        bx, by, bz, _ = projected_atoms[bond.b]
        bond_depths.append((az + bz, bond, (ax, ay), (bx, by)))
    for _, bond, start, end in sorted(bond_depths, key=lambda item: item[0]):
        width = 1.4 + max(0, bond.order - 1) * 1.0
        painter.setPen(
            QPen(
                QColor(60, 60, 58, 70),
                width + 1.8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawLine(
            QPointF(start[0] + 1.0, start[1] + 1.2), QPointF(end[0] + 1.0, end[1] + 1.2)
        )
        painter.setPen(
            QPen(
                QColor("#4a4a48"), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap
            )
        )
        painter.drawLine(QPointF(*start), QPointF(*end))

    atom_draws = []
    for index, atom in enumerate(scene.atoms):
        px, py, pz, radius = projected_atoms[index]
        atom_draws.append((pz, atom.symbol, px, py, radius))
    for _, symbol, px, py, radius in sorted(atom_draws, key=lambda item: item[0]):
        fill = preview_element_color(symbol)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(40, 40, 38, 35))
        painter.drawEllipse(QPointF(px + 1.1, py + 1.8), radius * 1.04, radius * 1.04)
        painter.setPen(QPen(QColor("#2a2a28"), 1.0))
        painter.setBrush(fill)
        painter.drawEllipse(QPointF(px, py), radius, radius)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 72))
        painter.drawEllipse(
            QPointF(px - radius * 0.28, py - radius * 0.32),
            radius * 0.33,
            radius * 0.24,
        )
        if symbol != "C" or radius >= 9.0:
            painter.save()
            painter.setPen(QColor("#1c1c1a"))
            font = painter.font()
            font.setPointSizeF(max(7.0, radius * 0.9))
            painter.setFont(font)
            text_rect = QRectF(px - radius, py - radius, radius * 2.0, radius * 2.0)
            painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), symbol)
            painter.restore()


__all__ = ["draw_projected_scene", "preview_element_color"]
