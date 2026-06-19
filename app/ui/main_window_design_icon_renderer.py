from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer

from ui.main_window_palette import PALETTE

_ICON_COLOR = PALETTE["icon"]

_SVG_BY_NAME: dict[str, str] = {
    "select": '<path d="M14 4 L5 13 L9 13 L8 20 L19 9 L13 9 Z"/>',
    "bond": '<line x1="5" y1="17" x2="19" y2="7"/>',
    "bond_double": '<line x1="4" y1="15" x2="18" y2="5"/><line x1="6" y1="19" x2="20" y2="9"/>',
    "bond_triple": (
        '<line x1="3" y1="14" x2="17" y2="4"/>'
        '<line x1="5" y1="17" x2="19" y2="7"/>'
        '<line x1="7" y1="20" x2="21" y2="10"/>'
    ),
    "wedge": '<path d="M5 18 L18 5 L20 8 Z"/>',
    "hash": (
        '<line x1="6" y1="16.5" x2="7.5" y2="14.5"/>'
        '<line x1="8.5" y1="15.2" x2="10.6" y2="12.4"/>'
        '<line x1="11.2" y1="13.7" x2="13.8" y2="10.3"/>'
        '<line x1="14.4" y1="12" x2="17.4" y2="8"/>'
    ),
    "benzene": (
        '<polygon points="12,3 19.5,7.5 19.5,16.5 12,21 4.5,16.5 4.5,7.5"/>'
        '<circle cx="12" cy="12" r="4.2"/>'
    ),
    "arrow": '<line x1="3" y1="12" x2="20" y2="12"/><polyline points="15,7 20.5,12 15,17"/>',
    "bracket": '<path d="M9 4 H6 V20 H9"/><path d="M15 4 H18 V20 H15"/>',
    "orbital": '<ellipse cx="8" cy="12" rx="5" ry="7"/><ellipse cx="16" cy="12" rx="5" ry="7"/>',
    "atom": '<path d="M6 6 H18 M12 6 V19 M9 19 H15"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    "redo": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>',
    "save": (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
        '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
        '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
    ),
    "open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    "panel_right": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
    "sheet": (
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
        '<path d="M9 15h6"/><path d="M12 18v-6"/>'
    ),
    "flip_h": (
        '<path d="m3 7 5 5-5 5V7"/><path d="m21 7-5 5 5 5V7"/>'
        '<path d="M12 20v2"/><path d="M12 14v2"/><path d="M12 8v2"/><path d="M12 2v2"/>'
    ),
    "flip_v": (
        '<path d="m17 3-5 5-5-5h10"/><path d="m17 21-5-5-5 5h10"/>'
        '<path d="M4 12H2"/><path d="M10 12H8"/><path d="M16 12h-2"/><path d="M22 12h-2"/>'
    ),
    "perspective": (
        '<path d="m15.194 13.707 3.814 1.86-1.86 3.814"/>'
        '<path d="M16.47214 7.52786 A 5 10 0 1 0 13 21.79796"/>'
        '<path d="M21.79796 11 A 10 5 0 1 0 19 15.57071"/>'
    ),
    "color": (
        '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z"/>'
        '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>'
        '<circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>'
        '<circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>'
        '<circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>'
    ),
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "move": (
        '<path d="M12 2v20"/><path d="m15 19-3 3-3-3"/><path d="m19 9 3 3-3 3"/>'
        '<path d="M2 12h20"/><path d="m5 9-3 3 3 3"/><path d="m9 5 3-3 3 3"/>'
    ),
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "circled_plus": '<circle cx="12" cy="12" r="9"/><path d="M12 7.2v9.6"/><path d="M7.2 12h9.6"/>',
    "circled_minus": '<circle cx="12" cy="12" r="9"/><path d="M7.2 12h9.6"/>',
}


def _svg_document(name: str, color: str) -> str:
    fill = "currentColor" if name == "wedge" else "none"
    width = "1.6" if name == "hash" else "1.8"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="currentColor" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round" color="{color}">'
        f"{_SVG_BY_NAME[name]}</svg>"
    )


def draw_design_icon(painter: QPainter, name: str, *, color: str | None = None) -> None:
    renderer = QSvgRenderer(QByteArray(_svg_document(name, color or _ICON_COLOR).encode("utf-8")))
    renderer.render(painter, QRectF(3.0, 3.0, 24.0, 24.0))


__all__ = ["draw_design_icon"]
