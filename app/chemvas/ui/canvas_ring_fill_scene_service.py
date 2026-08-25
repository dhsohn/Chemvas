from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPen, QPolygonF

from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.graphics_items import RING_FILL_Z_VALUE, NoSelectPolygonItem
from chemvas.ui.renderer_style_access import ring_fill_brush_for
from chemvas.ui.scene_selectability import make_item_selectable


def rebuild_ring_fill_polygons(
    canvas,
    atom_ids: set[int],
    ring_items: Iterable[Any],
) -> None:
    """Re-fit every ring polygon that touches ``atom_ids`` to its atoms.

    A ring fill is a polygon over its member atoms, so any code that moves
    those atoms has to redraw it. This module owns the fitting; the move
    controller redraws through here rather than keeping its own copy.

    Rings whose atom list is not a list of live atoms are skipped rather than
    reported: a fill can outlive an atom, and a polygon of fewer than three
    points is not a shape.
    """

    for ring_item in ring_items:
        ring_atom_ids = ring_item.data(2)
        if not isinstance(ring_atom_ids, list):
            continue
        if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
            continue
        points = []
        for atom_id in ring_atom_ids:
            atom = atom_for_id(canvas, atom_id)
            if atom is None:
                continue
            points.append(QPointF(atom.x, atom.y))
        if len(points) >= 3:
            ring_item.setPolygon(QPolygonF(points))


class CanvasRingFillSceneService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def update_ring_fills_for_atoms(
        self,
        atom_ids: set[int],
        *,
        ring_items: tuple[Any, ...] | None = None,
    ) -> None:
        # The guard is this entry point's own: it spares the registry read and
        # every `data(2)` call when nothing moved. `move_rings_for_atoms` has no
        # equivalent because its only caller already returns on an empty set.
        if not atom_ids:
            return
        rebuild_ring_fill_polygons(
            self.canvas,
            atom_ids,
            ring_items_for(self.canvas) if ring_items is None else ring_items,
        )

    def create_ring_fill_item(self, points: list[QPointF], atom_ids: list[int]):
        polygon = QPolygonF(points)
        ring_item = NoSelectPolygonItem(polygon)
        ring_item.setBrush(ring_fill_brush_for(self.canvas))
        ring_item.setPen(QPen(Qt.PenStyle.NoPen))
        ring_item.setData(0, "ring")
        ring_item.setData(2, list(atom_ids))
        ring_item.setZValue(RING_FILL_Z_VALUE)
        make_item_selectable(ring_item)
        return ring_item


__all__ = ["CanvasRingFillSceneService", "rebuild_ring_fill_polygons"]
