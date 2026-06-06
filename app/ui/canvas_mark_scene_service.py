from __future__ import annotations

import math

from PyQt6.QtCore import QPointF

from ui.canvas_geometry_access import mark_target_distance_for_atom_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import atom_for_id
from ui.canvas_scene_items_state import remove_scene_item_from_collection_for
from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.renderer_style_access import bond_length_px_for
from ui.scene_item_access import remove_item_from_canvas_scene


class CanvasMarkSceneService:
    def __init__(self, canvas, *, scene_decoration_service=None) -> None:
        self.canvas = canvas
        self.marks = mark_registry_for(canvas)
        self.scene_decoration_service = scene_decoration_service

    def add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None = None,
        record: bool = True,
    ):
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return None
        kind = kind or tool_settings_state_for(self.canvas).mark_kind
        offset = self.mark_offset_from_click(atom_id, click_pos, kind=kind)
        center = QPointF(atom.x + offset.x(), atom.y + offset.y())
        if self.scene_decoration_service is None:
            return None
        return self.scene_decoration_service.add_mark(
            center,
            kind=kind,
            atom_id=atom_id,
            offset=offset,
            record=record,
        )

    def mark_offset_from_click(self, atom_id: int, click_pos: QPointF, *, kind: str | None = None) -> QPointF:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return QPointF(0.0, 0.0)
        dx = click_pos.x() - atom.x
        dy = click_pos.y() - atom.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx = 1.0
            dy = -1.0
            length = math.hypot(dx, dy)
        direction_x = dx / length
        direction_y = dy / length
        target = bond_length_px_for(self.canvas) * 0.2
        mark_kind = kind or tool_settings_state_for(self.canvas).mark_kind
        label_target = mark_target_distance_for_atom_for(self.canvas, atom_id, direction_x, direction_y, mark_kind)
        if label_target > target:
            target += (label_target - target) * 0.25
        return QPointF(direction_x * target, direction_y * target)

    def remove_mark_item(self, item) -> None:
        remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int):
            marks = self.marks.get_for_atom(atom_id)
            if marks is not None and item in marks:
                marks.remove(item)
            if marks is not None and not marks:
                self.marks.by_atom.pop(atom_id, None)
        remove_item_from_canvas_scene(self.canvas, item)

    def remove_marks_for_atom(self, atom_id: int) -> None:
        marks = self.marks.pop_for_atom(atom_id)
        for item in list(marks):
            remove_scene_item_from_collection_for(self.canvas, "mark_items", item)
            remove_item_from_canvas_scene(self.canvas, item)

    def mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        *,
        kind: str | None = None,
    ) -> QPointF:
        if atom_id is None:
            return QPointF(pos)
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return QPointF(pos)
        offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
        return QPointF(atom.x + offset.x(), atom.y + offset.y())


__all__ = ["CanvasMarkSceneService"]
