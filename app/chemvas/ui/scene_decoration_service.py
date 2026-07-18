from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsTextItem

from chemvas.domain.transactions import HistoryAuthoritySnapshot
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.history_commands import (
    AddSceneItemsCommand,
    _run_rollback_step,
)
from chemvas.ui.mark_item_access import build_mark_item_for, set_mark_center_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_decoration_build_access import (
    build_arrow_item_for,
    build_orbital_items_for,
    build_shape_item_for,
    build_ts_bracket_item_for,
)
from chemvas.ui.scene_item_access import (
    attach_scene_item,
    remove_scene_item,
)
from chemvas.ui.scene_item_restore import create_orbital_item_from_state
from chemvas.ui.scene_item_state import (
    arrow_state_dict_for,
    mark_state_dict_for,
    orbital_state_dict_for,
    shape_state_dict_for,
    ts_bracket_state_dict_for,
)
from chemvas.ui.transactions.scene_item_attach import SceneItemAttachSnapshot

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


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
        with self._scene_add_transaction(snapshot_history=record) as track:
            kind = kind or tool_settings_state_for(self.canvas).mark_kind
            item = build_mark_item_for(self.canvas, kind)
            if item is None:
                return None
            data: dict[str, object] = {"kind": kind, "atom_id": atom_id}
            if offset is not None:
                data["dx"] = offset.x()
                data["dy"] = offset.y()
            if isinstance(item, QGraphicsTextItem):
                data["text"] = item.toPlainText()
            item.setData(0, "mark")
            item.setData(1, data)
            track(item)
            attach_scene_item(self.canvas, item)
            set_mark_center_for(self.canvas, item, pos)
            if record:
                self._push_add_scene_item(item, mark_state_dict_for(self.canvas, item))
        return item

    def add_arrow(self, start: QPointF, end: QPointF, kind: str):
        with self._scene_add_transaction() as track:
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
            track(item)
            attach_scene_item(self.canvas, item)
            self._push_add_scene_item(item, arrow_state_dict_for(self.canvas, item))
        return item

    def add_ts_bracket(self, rect: QRectF, *, bracket_kind: str | None = None):
        with self._scene_add_transaction() as track:
            bracket_kind = (
                bracket_kind or tool_settings_state_for(self.canvas).active_bracket_type
            )
            item = build_ts_bracket_item_for(self.canvas, rect, bracket_kind)
            track(item)
            attach_scene_item(self.canvas, item)
            self._push_add_scene_item(
                item, ts_bracket_state_dict_for(self.canvas, item)
            )
        return item

    def add_shape(
        self,
        rect: QRectF,
        *,
        shape_kind: str | None = None,
        stroke_style: str | None = None,
    ):
        with self._scene_add_transaction() as track:
            settings = tool_settings_state_for(self.canvas)
            shape_kind = shape_kind or settings.active_shape_type
            stroke_style = stroke_style or settings.active_shape_stroke
            item = build_shape_item_for(self.canvas, rect, shape_kind, stroke_style)
            if item is None:
                return None
            track(item)
            attach_scene_item(self.canvas, item)
            self._push_add_scene_item(item, shape_state_dict_for(self.canvas, item))
        return item

    def add_orbital(self, center: QPointF):
        with self._scene_add_transaction() as track:
            group = create_orbital_item_from_state(
                {
                    "orbital_kind": tool_settings_state_for(
                        self.canvas
                    ).active_orbital_type,
                    "center": (center.x(), center.y()),
                    "scale": 1.0,
                    "rotation": 0.0,
                },
                build_orbital_items=partial(
                    build_orbital_items_for,
                    self.canvas,
                ),
                orbital_base_handle_dist=bond_length_px_for(self.canvas) * 0.8,
            )
            if group is None:
                return None
            track(group)
            attach_scene_item(self.canvas, group)
            self._push_add_scene_item(group, orbital_state_dict_for(self.canvas, group))
        return group

    def _push_add_scene_item(self, item, state: dict) -> None:
        command = AddSceneItemsCommand(item_states=[state], items=[item])
        self.history.push(command)

    @contextmanager
    def _scene_add_transaction(
        self,
        *,
        snapshot_history: bool = True,
    ) -> Iterator[Callable[[object], object]]:
        history_snapshot = (
            HistoryAuthoritySnapshot.capture(self.history) if snapshot_history else None
        )
        item_snapshot: SceneItemAttachSnapshot | None = None

        def track(item: object) -> object:
            nonlocal item_snapshot
            item_snapshot = SceneItemAttachSnapshot.capture(self.canvas, item)
            return item

        try:
            yield track
            if item_snapshot is not None:
                item_snapshot.release()
        except BaseException as original_error:
            self._rollback_failed_add(
                item_snapshot,
                history_snapshot=history_snapshot,
                original_error=original_error,
            )
            raise

    def _rollback_failed_add(
        self,
        item_snapshot: SceneItemAttachSnapshot | None,
        *,
        history_snapshot: HistoryAuthoritySnapshot | None,
        original_error: BaseException,
    ) -> None:
        if item_snapshot is not None:
            _run_rollback_step(
                original_error,
                "removing the item created by a failed scene add",
                partial(remove_scene_item, self.canvas, item_snapshot.item),
            )
            item_snapshot.restore(original_error, phase="a failed scene add")
        if history_snapshot is not None:
            history_snapshot.restore(original_error, phase="scene add")


__all__ = ["SceneDecorationService"]
