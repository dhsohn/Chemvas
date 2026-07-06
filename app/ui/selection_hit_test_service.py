from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.renderer_style_access import bond_length_px_for
from ui.selection_collection_access import selection_snapshot_for
from ui.selection_geometry_access import bounds_for_atoms_for
from ui.selection_hit_logic import (
    SelectionHitRequest,
    SelectionRect,
    selection_hit_matches,
)
from ui.selection_outline_service import OBJECT_OVERLAY_KINDS
from ui.selection_outline_state import selection_outlines_for

if TYPE_CHECKING:
    from ui.canvas_hit_testing_service import CanvasHitTestingService
    from ui.canvas_view import CanvasView
    from ui.selection_structure_service import SelectionStructureService


class SelectionHitTestService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hit_testing_service: CanvasHitTestingService,
        structure_service: SelectionStructureService,
        graph_service,
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.structure_service = structure_service
        self.graph_service = graph_service

    def selection_rects_for_snapshot(
        self,
        snapshot,
    ) -> tuple[SelectionRect, ...]:
        rects: list[SelectionRect] = []
        if snapshot.selected_atom_ids:
            for component in self.graph_service.connected_components(set(snapshot.selected_atom_ids)):
                bounds = bounds_for_atoms_for(self.canvas, component)
                if bounds is None:
                    continue
                min_x, min_y, max_x, max_y = bounds
                rects.append(SelectionRect(left=min_x, top=min_y, right=max_x, bottom=max_y))
        for item in snapshot.selection_items:
            if item.data(0) in {"atom", "bond", "ring"}:
                continue
            if item.data(0) in OBJECT_OVERLAY_KINDS:
                continue
            rect = item.sceneBoundingRect()
            rects.append(
                SelectionRect(
                    left=rect.left(),
                    top=rect.top(),
                    right=rect.right(),
                    bottom=rect.bottom(),
                )
            )
        return tuple(rects)

    def selection_hit_test(self, pos: QPointF, snapshot=None) -> bool:
        if snapshot is None:
            snapshot = selection_snapshot_for(self.canvas)
        if snapshot is None:
            return False
        outline_hit = False
        for outline in selection_outlines_for(self.canvas):
            data = outline.data(2) or {}
            if data.get("kind") not in {"component", "object", "group"}:
                continue
            if outline.contains(outline.mapFromScene(pos)):
                outline_hit = True
                break
        item = self.hit_testing_service.item_at_scene_pos(pos)
        hit, bond_atom_ids, ring_atom_ids = self.structure_service.structure_hit_from_item(item)
        return selection_hit_matches(
            SelectionHitRequest(
                point=(pos.x(), pos.y()),
                outline_hit=outline_hit,
                rects=self.selection_rects_for_snapshot(snapshot),
                pad=bond_length_px_for(self.canvas) * 0.1,
                hit=hit,
                selected_atom_ids=snapshot.selected_atom_ids,
                selected_bond_ids=snapshot.selected_bond_ids,
                bond_atom_ids=bond_atom_ids,
                ring_atom_ids=tuple(ring_atom_ids or ()),
                item_is_selected=bool(item is not None and item.isSelected()),
            )
        )


__all__ = ["SelectionHitTestService"]
