from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from PyQt6.QtCore import QPointF

    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.scene.scene_render_context import SceneRenderContext


def rebuild_ring_fill_polygons(
    model: MoleculeModel,
    atom_ids: set[int],
    ring_items: Iterable[Any],
    *,
    point_factory=None,
    polygon_factory=None,
) -> None:
    """Re-fit every ring polygon that touches ``atom_ids`` to its atoms.

    A ring fill is a polygon over its member atoms, so any code that moves
    those atoms has to redraw it. This module owns the fitting; the move
    controller redraws through here rather than keeping its own copy.

    Rings whose atom list is not a list of live atoms are skipped rather than
    reported: a fill can outlive an atom, and a polygon of fewer than three
    points is not a shape.
    """

    if point_factory is None:
        from PyQt6.QtCore import QPointF

        point_factory = QPointF
    if polygon_factory is None:
        from PyQt6.QtGui import QPolygonF

        polygon_factory = QPolygonF
    for ring_item in ring_items:
        ring_atom_ids = ring_item.data(2)
        if not isinstance(ring_atom_ids, list):
            continue
        if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
            continue
        points = []
        for atom_id in ring_atom_ids:
            atom = model.atom_for_id(atom_id)
            if atom is None:
                continue
            points.append(point_factory(atom.x, atom.y))
        if len(points) >= 3:
            ring_item.setPolygon(polygon_factory(points))


class CanvasRingFillSceneService:
    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context

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
            self.context.model,
            atom_ids,
            self.context.state.ring_items() if ring_items is None else ring_items,
        )

    def create_ring_fill_item(self, points: list[QPointF], atom_ids: list[int]):
        from chemvas.ui.annotations.materialize import create_ring_item_from_state
        from chemvas.ui.scene.scene_selectability import make_item_selectable

        ring_item = create_ring_item_from_state(
            {
                "points": [(point.x(), point.y()) for point in points],
                "atom_ids": atom_ids,
            },
            document=self.context.state.ring_state,
            model_provider=lambda: self.context.model,
            ring_fill_brush_getter=lambda: self.context.renderer.ring_fill_brush(),
        )
        if ring_item is None:
            raise ValueError("A ring fill requires at least three points.")
        make_item_selectable(ring_item)
        return ring_item


__all__ = ["CanvasRingFillSceneService", "rebuild_ring_fill_polygons"]
