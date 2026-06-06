from __future__ import annotations

from core.model import Atom
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPen

from ui.bond_graphics_access import ring_double_segments_for
from ui.main_window_canvas_ports import active_canvas_for_window
from ui.renderer_style_access import (
    bold_bond_pen_for,
    bond_length_px_for,
    bond_pen_for,
    dotted_bond_pen_for,
    hash_spacing_px_for,
)


class MainWindowIconCanvasStyle:
    def __init__(self, window) -> None:
        self._window = window

    @property
    def _canvas(self):
        return active_canvas_for_window(self._window)

    def bond_length_px(self) -> float:
        return bond_length_px_for(self._canvas)

    def bond_pen(self) -> QPen:
        return bond_pen_for(self._canvas)

    def bold_bond_pen(self) -> QPen:
        return bold_bond_pen_for(self._canvas)

    def dotted_bond_pen(self) -> QPen:
        return dotted_bond_pen_for(self._canvas)

    def hash_spacing_px(self) -> float:
        return hash_spacing_px_for(self._canvas)

    def ring_double_inner_segment(
        self,
        start: QPointF,
        end: QPointF,
        center: QPointF,
    ) -> tuple[float, float, float, float] | None:
        segments = ring_double_segments_for(
            self._canvas,
            Atom("C", start.x(), start.y()),
            Atom("C", end.x(), end.y()),
            center,
        )
        if segments is None:
            return None
        _outer_seg, inner_seg, _opposite_seg = segments
        return inner_seg


__all__ = ["MainWindowIconCanvasStyle"]
