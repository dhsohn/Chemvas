from __future__ import annotations

from typing import TYPE_CHECKING

from ui.canvas_model_access import atoms_for
from ui.handle_mutation_access import set_curved_arrow_path_for
from ui.mark_item_access import (
    build_mark_item_for,
    set_mark_center_for,
)
from ui.note_item_access import apply_note_style_for, new_note_item_for
from ui.renderer_style_access import (
    bond_color_for,
    bond_length_px_for,
    ring_fill_brush_for,
)
from ui.scene_decoration_build_access import (
    build_arrow_item_for,
    build_orbital_items_for,
    build_shape_item_for,
    build_ts_bracket_item_for,
    ts_bracket_path_for,
)
from ui.scene_item_lifecycle_service import SceneItemLifecycleService
from ui.scene_item_restore import (
    create_arrow_item_from_state as create_arrow_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_mark_item_from_state as create_mark_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_note_item_from_state as create_note_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_orbital_item_from_state as create_orbital_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_ring_item_from_state as create_ring_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_scene_item_from_state as create_scene_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_shape_item_from_state as create_shape_item_from_state_helper,
)
from ui.scene_item_restore import (
    create_ts_bracket_item_from_state as create_ts_bracket_item_from_state_helper,
)
from ui.scene_item_state import apply_scene_item_state as apply_scene_item_state_helper

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneItemController:
    def __init__(self, canvas: CanvasView, *, graph_service, lifecycle_service=None) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.lifecycle_service = (
            lifecycle_service
            if lifecycle_service is not None
            else SceneItemLifecycleService(canvas, graph_service=graph_service)
        )

    def _orbital_base_handle_dist(self) -> float:
        return bond_length_px_for(self.canvas) * 0.8

    def _ring_fill_brush(self):
        return ring_fill_brush_for(self.canvas)

    def _new_note_item(self):
        return new_note_item_for(self.canvas)

    def _apply_note_style(self, item) -> None:
        apply_note_style_for(self.canvas, item)

    def _build_mark_item(self, kind: str):
        return build_mark_item_for(self.canvas, kind)

    def _set_mark_center(self, item, center) -> None:
        set_mark_center_for(self.canvas, item, center)

    def _build_arrow_item(self, start, end, kind: str):
        return build_arrow_item_for(self.canvas, start, end, kind)

    def _set_curved_arrow_path(self, item, start, end, control, double: bool) -> None:
        set_curved_arrow_path_for(self.canvas, item, start, end, control, double)

    def _build_ts_bracket_item(self, rect, bracket_kind: str | None = None):
        return build_ts_bracket_item_for(self.canvas, rect, bracket_kind)

    def _build_shape_item(self, rect, shape_kind=None, stroke_style=None, fill=None):
        return build_shape_item_for(self.canvas, rect, shape_kind, stroke_style, fill=fill)

    def _build_orbital_items(self, center, kind: str):
        return build_orbital_items_for(self.canvas, center, kind)

    def _ts_bracket_path(self, rect, bracket_kind: str | None = None):
        return ts_bracket_path_for(self.canvas, rect, bracket_kind)

    def restore_ring_from_state(self, ring_state: dict):
        item = create_ring_item_from_state_helper(
            ring_state,
            ring_fill_brush_getter=self._ring_fill_brush,
        )
        self.attach_scene_item(item)
        return item

    def restore_note_from_state(self, note_state: dict):
        item = create_note_item_from_state_helper(
            note_state,
            note_item_factory=self._new_note_item,
            note_style_applier=self._apply_note_style,
        )
        self.attach_scene_item(item)
        return item

    def restore_mark_from_state(self, mark_state: dict):
        item = create_mark_item_from_state_helper(
            mark_state,
            model_atoms=atoms_for(self.canvas),
            build_mark_item=self._build_mark_item,
            set_mark_center=self._set_mark_center,
        )
        self.attach_scene_item(item)
        return item

    def restore_arrow_from_state(self, arrow_state: dict):
        item = create_arrow_item_from_state_helper(
            arrow_state,
            build_arrow_item=self._build_arrow_item,
            set_curved_arrow_path=self._set_curved_arrow_path,
        )
        self.attach_scene_item(item)
        return item

    def restore_ts_bracket_from_state(self, ts_bracket_state: dict):
        item = create_ts_bracket_item_from_state_helper(
            ts_bracket_state,
            build_ts_bracket_item=self._build_ts_bracket_item,
        )
        self.attach_scene_item(item)
        return item

    def restore_shape_from_state(self, shape_state: dict):
        item = create_shape_item_from_state_helper(
            shape_state,
            build_shape_item=self._build_shape_item,
        )
        self.attach_scene_item(item)
        return item

    def restore_orbital_from_state(self, orbital_state: dict):
        group = create_orbital_item_from_state_helper(
            orbital_state,
            build_orbital_items=self._build_orbital_items,
            orbital_base_handle_dist=self._orbital_base_handle_dist(),
        )
        self.attach_scene_item(group)
        return group

    def create_scene_item_from_state(self, state: dict):
        item = create_scene_item_from_state_helper(
            state,
            model_atoms=atoms_for(self.canvas),
            note_item_factory=self._new_note_item,
            note_style_applier=self._apply_note_style,
            build_mark_item=self._build_mark_item,
            set_mark_center=self._set_mark_center,
            ring_fill_brush_getter=self._ring_fill_brush,
            build_arrow_item=self._build_arrow_item,
            set_curved_arrow_path=self._set_curved_arrow_path,
            build_ts_bracket_item=self._build_ts_bracket_item,
            build_shape_item=self._build_shape_item,
            build_orbital_items=self._build_orbital_items,
            orbital_base_handle_dist=self._orbital_base_handle_dist(),
        )
        if item is not None:
            self.attach_scene_item(item)
            return item
        return None

    def bond_ids_for_ring_item(self, item) -> set[int]:
        return self.lifecycle_service.bond_ids_for_ring_item(item)

    def refresh_bond_geometry_for_ring_item(self, item) -> None:
        self.lifecycle_service.refresh_bond_geometry_for_ring_item(item)

    def attach_scene_item(self, item) -> None:
        self.lifecycle_service.attach_scene_item(item)

    def restore_scene_item(self, item) -> None:
        self.lifecycle_service.restore_scene_item(item)

    def remove_scene_item(self, item) -> None:
        self.lifecycle_service.remove_scene_item(item)

    def apply_scene_item_state(self, item, state: dict) -> None:
        apply_scene_item_state_helper(
            item,
            state,
            model_atoms=atoms_for(self.canvas),
            note_style_applier=self._apply_note_style,
            mark_center_setter=self._set_mark_center,
            ring_fill_brush_getter=self._ring_fill_brush,
            ts_bracket_path_builder=self._ts_bracket_path,
            bond_color=bond_color_for(self.canvas),
            build_arrow_item=self._build_arrow_item,
            set_curved_arrow_path=self._set_curved_arrow_path,
            orbital_base_handle_dist=self._orbital_base_handle_dist(),
            build_shape_item=self._build_shape_item,
        )


__all__ = ["SceneItemController"]
