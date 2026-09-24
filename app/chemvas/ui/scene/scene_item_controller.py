from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.document import VALID_ARROW_KINDS, arrow_from_state
from chemvas.ui.annotations.materialize import (
    create_scene_item_from_state as create_scene_item_from_state_helper,
)
from chemvas.ui.annotations.records import record_shape_state, record_ts_bracket_state
from chemvas.ui.annotations.state import (
    apply_scene_item_state as apply_scene_item_state_helper,
)
from chemvas.ui.scene.note_item_access import new_note_item_for
from chemvas.ui.scene.scene_item_lifecycle_service import SceneItemLifecycleService

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView


class SceneItemController:
    def __init__(
        self, canvas: CanvasView, *, graph_service, lifecycle_service=None
    ) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.lifecycle_service = (
            lifecycle_service
            if lifecycle_service is not None
            else SceneItemLifecycleService(canvas, graph_service=graph_service)
        )

    def create_scene_item_from_state(self, state: dict):
        item = create_scene_item_from_state_helper(
            self.canvas.render_context,
            state,
            note_item_factory=lambda: new_note_item_for(self.canvas),
        )
        if item is not None:
            self.attach_scene_item(item)
        return item

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
        if state.get("kind") == "shape" and item.data(0) == "shape":
            record_shape_state(self.canvas, item, state)
            return
        if state.get("kind") == "ts_bracket" and item.data(0) == "ts_bracket":
            record_ts_bracket_state(self.canvas, item, state)
            return
        if state.get("kind") in VALID_ARROW_KINDS:
            self.canvas.render_context.arrows.set_record(item, arrow_from_state(state))
            return
        context = self.canvas.render_context
        decorations = context.decorations
        apply_scene_item_state_helper(
            item,
            state,
            model_atoms=self.canvas.model.atoms,
            note_style_applier=lambda note: (
                self.canvas.services.note_controller.apply_note_style(note)
            ),
            mark_center_setter=decorations.set_mark_center,
            mark_color_setter=decorations.apply_mark_color,
        )


__all__ = ["SceneItemController"]
