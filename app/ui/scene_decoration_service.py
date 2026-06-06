from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsTextItem

from ui.canvas_tool_settings_state import tool_settings_state_for
from ui.history_commands import AddSceneItemsCommand
from ui.mark_item_access import build_mark_item_for, set_mark_center_for
from ui.scene_decoration_build_access import (
    build_arrow_item_for,
    build_ts_bracket_item_for,
)
from ui.scene_item_access import attach_scene_item, create_scene_item_from_state
from ui.scene_item_state import (
    arrow_state_dict_for,
    mark_state_dict_for,
    orbital_state_dict_for,
    ts_bracket_state_dict_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneDecorationService:
    def __init__(self, canvas: CanvasView, *, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def add_mark(
        self,
        pos: QPointF,
        *,
        kind: str | None = None,
        atom_id: int | None = None,
        offset: QPointF | None = None,
        record: bool = True,
    ):
        kind = kind or tool_settings_state_for(self.canvas).mark_kind
        item = build_mark_item_for(self.canvas, kind)
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
        attach_scene_item(self.canvas, item)
        set_mark_center_for(self.canvas, item, pos)
        if record:
            self._push_add_scene_item(item, mark_state_dict_for(self.canvas, item))
        return item

    def add_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = build_arrow_item_for(self.canvas, start, end, kind)
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
        attach_scene_item(self.canvas, item)
        self._push_add_scene_item(item, arrow_state_dict_for(self.canvas, item))
        return item

    def add_ts_bracket(self, rect: QRectF):
        item = build_ts_bracket_item_for(self.canvas, rect)
        attach_scene_item(self.canvas, item)
        self._push_add_scene_item(item, ts_bracket_state_dict_for(self.canvas, item))
        return item

    def add_orbital(self, center: QPointF):
        group = create_scene_item_from_state(
            self.canvas,
            {
                "kind": "orbital",
                "orbital_kind": tool_settings_state_for(self.canvas).active_orbital_type,
                "center": (center.x(), center.y()),
                "scale": 1.0,
                "rotation": 0.0,
            },
        )
        if group is None:
            return None
        self._push_add_scene_item(group, orbital_state_dict_for(self.canvas, group))
        return group

    def _push_add_scene_item(self, item, state: dict) -> None:
        command = AddSceneItemsCommand(item_states=[state], items=[item])
        self.history.push(command)


__all__ = ["SceneDecorationService"]
