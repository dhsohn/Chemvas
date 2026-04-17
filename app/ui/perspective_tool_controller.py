from __future__ import annotations


class PerspectiveToolController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    @staticmethod
    def axis_hint_for_item(item) -> int | None:
        if item is None or item.data(0) != "bond":
            return None
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return None
        return bond_id

    def begin_selection_rotation(self, event) -> bool:
        self.canvas.clear_handles()
        press_pos = self.canvas.scene_pos_from_event(event)
        preferred_item = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
        if not self.canvas.selection_hit_test(press_pos):
            item = preferred_item or self.canvas.item_at_event(event)
            if item is None or not self.canvas.select_structure_for_item(item):
                return False
            preferred_item = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
        axis_hint = self.axis_hint_for_item(preferred_item)
        return self.canvas.begin_selection_3d_rotation(axis_hint=axis_hint, press_pos=press_pos)


__all__ = ["PerspectiveToolController"]
