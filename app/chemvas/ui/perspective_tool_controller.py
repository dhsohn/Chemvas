from __future__ import annotations

from chemvas.ui.handle_overlay_access import clear_handles_for
from chemvas.ui.tool_context import ToolContext


class PerspectiveToolController:
    def __init__(
        self,
        canvas,
        *,
        context: ToolContext,
    ) -> None:
        self.canvas = canvas
        self.hit_testing_service = context.hit_testing_service
        self.selection_controller = context.selection_controller
        self.selection_rotation_controller = context.selection_rotation_controller

    @staticmethod
    def axis_hint_for_item(item) -> int | None:
        if item is None or item.data(0) != "bond":
            return None
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return None
        return bond_id

    def _clear_handles(self) -> None:
        clear_handles_for(self.canvas)

    def _begin_selection_3d_rotation(
        self, *, axis_hint: int | None = None, press_pos=None
    ) -> bool:
        return bool(
            self.selection_rotation_controller.begin_selection_3d_rotation(
                axis_hint=axis_hint,
                press_pos=press_pos,
            )
        )

    def begin_selection_rotation(self, event) -> bool:
        self._clear_handles()
        press_pos = self.hit_testing_service.scene_pos_from_event(event)
        preferred_item = (
            self.selection_controller.preferred_structure_item_at_scene_pos(press_pos)
        )
        if not self.selection_controller.selection_hit_test(press_pos, snapshot=None):
            item = preferred_item or self.hit_testing_service.item_at_event(event)
            if item is None or not self.selection_controller.select_structure_for_item(
                item
            ):
                return False
            preferred_item = (
                self.selection_controller.preferred_structure_item_at_scene_pos(
                    press_pos
                )
            )
        axis_hint = self.axis_hint_for_item(preferred_item)
        return self._begin_selection_3d_rotation(
            axis_hint=axis_hint, press_pos=press_pos
        )


__all__ = ["PerspectiveToolController"]
