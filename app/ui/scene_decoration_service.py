from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsTextItem

from core.history import AddSceneItemsCommand
from ui.scene_item_restore import (
    create_orbital_item_from_state as create_orbital_item_from_state_helper,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneDecorationService:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def add_mark(
        self,
        pos: QPointF,
        *,
        kind: str | None = None,
        atom_id: int | None = None,
        offset: QPointF | None = None,
        record: bool = True,
    ):
        kind = kind or self.canvas.mark_kind
        item = self.canvas._build_mark_item(kind)
        if item is None:
            return None
        data = {"kind": kind, "atom_id": atom_id}
        if offset is not None:
            data["dx"] = offset.x()
            data["dy"] = offset.y()
        if isinstance(item, QGraphicsTextItem):
            data["text"] = item.toPlainText()
        item.setData(0, "mark")
        item.setData(1, data)
        self.canvas._make_selectable(item)
        self.canvas.scene().addItem(item)
        self.canvas.mark_items.append(item)
        if atom_id is not None:
            self.canvas._marks_by_atom.setdefault(atom_id, []).append(item)
        self.canvas._set_mark_center(item, pos)
        if record:
            self._push_add_scene_item(item, self.canvas._mark_state_dict(item))
        return item

    def add_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = self.canvas._build_arrow_item(start, end, kind)
        scene_kind = "arrow" if kind == "reaction" else kind
        item.setData(0, scene_kind)
        data = item.data(2) or {}
        if scene_kind in {"curved_single", "curved_double"}:
            data.update(
                {
                    "start": start,
                    "end": end,
                    "double": scene_kind == "curved_double",
                }
            )
        else:
            data = {"start": start, "end": end, "control": None, "double": False}
        item.setData(2, data)
        self.canvas._make_selectable(item)
        self.canvas.scene().addItem(item)
        self.canvas.arrow_items.append(item)
        self._push_add_scene_item(item, self.canvas._arrow_state_dict(item))
        return item

    def add_ts_bracket(self, rect: QRectF):
        item = self.canvas._build_ts_bracket_item(rect)
        self.canvas._make_selectable(item)
        self.canvas.scene().addItem(item)
        self.canvas.ts_bracket_items.append(item)
        self._push_add_scene_item(item, self.canvas._ts_bracket_state_dict(item))
        return item

    def add_orbital(self, center: QPointF):
        group = create_orbital_item_from_state_helper(
            {
                "kind": "orbital",
                "orbital_kind": self.canvas.active_orbital_type,
                "center": (center.x(), center.y()),
                "scale": 1.0,
                "rotation": 0.0,
            },
            build_orbital_items=self.canvas._build_orbital_items,
            orbital_base_handle_dist=self.canvas.renderer.style.bond_length_px * 0.8,
        )
        if group is None:
            return None
        self.canvas._scene_item_controller.restore_scene_item(group)
        self._push_add_scene_item(group, self.canvas._orbital_state_dict(group))
        return group

    def _push_add_scene_item(self, item, state: dict) -> None:
        command = AddSceneItemsCommand(item_states=[state], items=[item])
        self.canvas._push_command(command)

