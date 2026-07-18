from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
)

from chemvas.features.selection import (
    SelectionRect,
    StructureHit,
)
from chemvas.ui.scene_group_operations import group_selection_targets_for
from chemvas.ui.selection_collection_access import selected_ids_for
from chemvas.ui.selection_scene_access import set_scene_items_selected_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas_view import CanvasView
    from chemvas.ui.selection_hit_test_service import SelectionHitTestService
    from chemvas.ui.selection_note_service import SelectionNoteService
    from chemvas.ui.selection_outline_service import SelectionOutlineService
    from chemvas.ui.selection_preference_service import SelectionPreferenceService
    from chemvas.ui.selection_structure_service import SelectionStructureService


class SelectionController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        hit_testing_service: CanvasHitTestingService,
        structure_service: SelectionStructureService,
        preference_service: SelectionPreferenceService,
        outline_service: SelectionOutlineService,
        note_service: SelectionNoteService,
        hit_test_service: SelectionHitTestService,
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.structure_service = structure_service
        self.preference_service = preference_service
        self.outline_service = outline_service
        self.note_service = note_service
        self.hit_test_service = hit_test_service

    def structure_hit_from_item(
        self, item
    ) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
        return self.structure_service.structure_hit_from_item(item)

    def structure_item_for_hit(self, hit: StructureHit):
        return self.structure_service.structure_item_for_hit(hit)

    def selected_ids(self) -> tuple[set[int], set[int]]:
        return selected_ids_for(self.canvas)

    def selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        return self.structure_service.selection_targets_for_item(item)

    def toggle_item_selection(self, item) -> bool:
        targets = self.structure_service.selection_targets_for_item(item)
        if not targets:
            return False
        targets = group_selection_targets_for(self.canvas, targets)
        note_targets = [target for target in targets if target.data(0) == "note"]
        scene_targets = [target for target in targets if target.data(0) != "note"]
        # Notes carry their own selection state, so they never contribute to
        # the toggle decision and are routed through the note service; their Qt
        # flags are mirrored afterwards since attached notes are Qt-selectable.
        should_select = (
            not any(target.isSelected() for target in scene_targets)
            if scene_targets
            else None
        )
        set_scene_items_selected_for(self.canvas, scene_targets, bool(should_select))
        applied = self.note_service.apply_group_note_toggle(note_targets, should_select)
        if note_targets and applied is not None:
            set_scene_items_selected_for(self.canvas, note_targets, applied)
        self.update_selection_outline()
        return True

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        return self.preference_service.preferred_structure_hit_at_scene_pos(pos)

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        return self.preference_service.preferred_structure_item_at_scene_pos(pos)

    def select_structure_for_item(self, item) -> bool:
        result = self.structure_service.select_structure_for_item(item)
        if result.update_outline:
            self.update_selection_outline()
        return result.selected

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        self.note_service.select_note(item, additive=additive)

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        self.note_service.toggle_note_selection(item)

    def clear_note_selection(self) -> None:
        self.note_service.clear_note_selection()

    def update_note_selection_box(self, item: QGraphicsTextItem) -> None:
        self.note_service.update_note_selection_box(item)

    def selection_rects_for_snapshot(
        self,
        snapshot,
    ) -> tuple[SelectionRect, ...]:
        return self.hit_test_service.selection_rects_for_snapshot(snapshot)

    def selection_hit_test(self, pos: QPointF, snapshot=None) -> bool:
        return self.hit_test_service.selection_hit_test(pos, snapshot=snapshot)

    def update_selection_outline(self) -> None:
        self.outline_service.update_selection_outline()

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        self.outline_service.shift_selection_outlines(dx, dy)

    def selection_line_stroke_path(
        self,
        start: QPointF,
        end: QPointF,
        width: float,
    ) -> QPainterPath:
        return self.outline_service.selection_line_stroke_path(start, end, width)

    def selection_path_for_bond_item(
        self, item, width: float | None = None
    ) -> QPainterPath:
        return self.outline_service.selection_path_for_bond_item(item, width=width)

    def selection_path_for_bond(self, bond_id: int) -> QPainterPath:
        return self.outline_service.selection_path_for_bond(bond_id)

    def selection_path_for_object_item(self, item) -> QPainterPath:
        return self.outline_service.selection_path_for_object_item(item)

    def add_selection_object_overlay(self, item, color: QColor) -> None:
        self.outline_service.add_selection_object_overlay(item, color)

    def add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
        atom_pad: float,
    ) -> None:
        self.outline_service.add_selection_component_overlay(
            atom_ids, bond_ids, color, atom_pad
        )

    def selection_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        return self.outline_service.selection_center_for_atoms(atom_ids)

    def selection_center_marker_enabled(self) -> bool:
        return self.outline_service.selection_center_marker_enabled()

    def add_selection_center_marker(self, center: QPointF) -> None:
        self.outline_service.add_selection_center_marker(center)


__all__ = ["SelectionController"]
