from __future__ import annotations

import math

from PyQt6.QtCore import QPointF


class CanvasMarkSceneService:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def add_mark_for_atom(
        self,
        atom_id: int,
        click_pos: QPointF,
        *,
        kind: str | None = None,
        record: bool = True,
    ):
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return None
        kind = kind or self.canvas.mark_kind
        offset = self.mark_offset_from_click(atom_id, click_pos, kind=kind)
        center = QPointF(atom.x + offset.x(), atom.y + offset.y())
        return self.canvas.add_mark(center, kind=kind, atom_id=atom_id, offset=offset, record=record)

    def mark_offset_from_click(self, atom_id: int, click_pos: QPointF, *, kind: str | None = None) -> QPointF:
        atom = self.canvas.model.atoms.get(atom_id)
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
        target = self.canvas.renderer.style.bond_length_px * 0.2
        mark_kind = kind or self.canvas.mark_kind
        label_target = self.canvas._mark_target_distance_for_atom(atom_id, direction_x, direction_y, mark_kind)
        if label_target > target:
            target += (label_target - target) * 0.25
        return QPointF(direction_x * target, direction_y * target)

    def remove_mark_item(self, item) -> None:
        if item in self.canvas.mark_items:
            self.canvas.mark_items.remove(item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int):
            marks = self.canvas._marks_by_atom.get(atom_id)
            if marks is not None and item in marks:
                marks.remove(item)
            if marks is not None and not marks:
                self.canvas._marks_by_atom.pop(atom_id, None)
        self.canvas.scene().removeItem(item)

    def remove_marks_for_atom(self, atom_id: int) -> None:
        marks = self.canvas._marks_by_atom.pop(atom_id, [])
        for item in list(marks):
            if item in self.canvas.mark_items:
                self.canvas.mark_items.remove(item)
            self.canvas.scene().removeItem(item)

    def mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        *,
        kind: str | None = None,
    ) -> QPointF:
        if atom_id is None:
            return QPointF(pos)
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return QPointF(pos)
        if not hasattr(self.canvas, "_mark_target_distance_for_atom") and hasattr(self.canvas, "_mark_offset_from_click"):
            offset = self.canvas._mark_offset_from_click(atom_id, pos, kind=kind)
        else:
            offset = self.mark_offset_from_click(atom_id, pos, kind=kind)
        return QPointF(atom.x + offset.x(), atom.y + offset.y())


def canvas_mark_scene_service_for(canvas) -> CanvasMarkSceneService:
    service = getattr(canvas, "_canvas_mark_scene_service", None)
    required = (
        "add_mark_for_atom",
        "mark_offset_from_click",
        "remove_mark_item",
        "remove_marks_for_atom",
        "mark_center_for_pointer",
    )
    if isinstance(service, CanvasMarkSceneService) and service.canvas is canvas:
        return service
    if service is not None and all(hasattr(service, name) for name in required):
        return service
    return CanvasMarkSceneService(canvas)


__all__ = ["CanvasMarkSceneService", "canvas_mark_scene_service_for"]
