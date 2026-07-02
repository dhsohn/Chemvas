from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from ui.bracket_types import BRACKET_KIND_VALUES
from ui.canvas_callback_state import callback_state_for
from ui.canvas_insert_state import insert_state_for
from ui.canvas_tool_settings_state import set_tool_setting_for, tool_settings_state_for
from ui.canvas_window_access import history_service_for_canvas
from ui.history_commands import UpdateSceneItemCommand
from ui.scene_item_access import apply_scene_item_state
from ui.scene_item_state import shape_state_dict_for
from ui.selection_collection_access import selected_scene_items_for
from ui.selection_service_access import refresh_selection_outline_for
from ui.shape_geometry import SHAPE_KINDS, STROKE_STYLES


class CanvasToolModeController:
    MARK_KINDS: ClassVar[set[str]] = {"plus", "minus", "circled_plus", "circled_minus", "radical"}

    def __init__(
        self,
        canvas: Any,
        *,
        insert_controller=None,
        hover_refresh: Callable[..., None] | None = None,
        set_active_tool: Callable[[str], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.insert_controller = insert_controller
        self._hover_refresh = hover_refresh or (lambda **_kwargs: None)
        self._set_active_tool = set_active_tool or (lambda _name: None)

    @property
    def settings(self):
        return tool_settings_state_for(self.canvas)

    def _cancel_active_insert_modes(self) -> None:
        insert_controller = self.insert_controller
        if insert_controller is None:
            return
        insert_state = insert_state_for(self.canvas)
        if insert_state.template_active:
            insert_controller.cancel_template_insert()
        if insert_state.smiles_active:
            insert_controller.cancel_smiles_insert()

    def _emit_tool_changed(self) -> None:
        callback = callback_state_for(self.canvas).tool_change
        if callback is not None:
            callback()

    def _refresh_tool_mode(self) -> None:
        refresh_selection_outline_for(self.canvas)
        self._emit_tool_changed()
        self._refresh_hover_for_tool_change()

    def _refresh_hover_for_tool_change(self) -> None:
        try:
            self._hover_refresh(render_insert_preview=True)
        except TypeError as exc:
            if "render_insert_preview" not in str(exc):
                raise
            self._hover_refresh()

    def set_tool(self, tool_name: str) -> None:
        self._cancel_active_insert_modes()
        self._set_active_tool(tool_name)
        if tool_name == "benzene" and self.insert_controller is not None:
            self.insert_controller.begin_ring_template_insert(6, "benzene")
        self._refresh_tool_mode()

    def set_mark_kind(self, kind: str) -> None:
        if kind not in self.MARK_KINDS:
            return
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "mark_kind", kind)
        self._set_active_tool("mark")
        self._refresh_tool_mode()

    def set_bond_style(self, style: str, order: int) -> None:
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_bond_style", style)
        set_tool_setting_for(self.canvas, "active_bond_order", order)
        self._set_active_tool("bond")
        self._refresh_tool_mode()

    def set_arrow_type(self, arrow_type: str) -> None:
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_arrow_type", arrow_type)
        self._set_active_tool("arrow")
        self._refresh_tool_mode()

    def set_bracket_type(self, bracket_type: str) -> None:
        if bracket_type not in BRACKET_KIND_VALUES:
            return
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_bracket_type", bracket_type)
        self._set_active_tool("ts_bracket")
        self._refresh_tool_mode()

    def set_orbital_type(self, orbital_type: str) -> None:
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_orbital_type", orbital_type)
        self._set_active_tool("orbital")
        self._refresh_tool_mode()

    def set_orbital_phase_enabled(self, enabled: bool) -> None:
        set_tool_setting_for(self.canvas, "orbital_phase_enabled", enabled)

    def set_shape_type(self, shape_type: str) -> None:
        if shape_type not in SHAPE_KINDS:
            return
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "active_shape_type", shape_type)
        self._set_active_tool("shape")
        self._refresh_tool_mode()

    def _selected_shape_items(self) -> list:
        return [
            item
            for item in selected_scene_items_for(self.canvas, excluded_kinds=set())
            if item.data(0) == "shape"
        ]

    def _apply_shape_stroke_to_selected(self, stroke_style: str) -> bool:
        shapes = self._selected_shape_items()
        if not shapes:
            return False
        history = history_service_for_canvas(self.canvas)
        for item in shapes:
            before = shape_state_dict_for(self.canvas, item)
            new_state = dict(before)
            new_state["stroke_style"] = stroke_style
            apply_scene_item_state(self.canvas, item, new_state)
            after = shape_state_dict_for(self.canvas, item)
            if before != after and history is not None:
                history.push(UpdateSceneItemCommand(item, before, after))
        refresh_selection_outline_for(self.canvas)
        return True

    def set_shape_stroke(self, stroke_style: str) -> None:
        if stroke_style not in STROKE_STYLES:
            return
        self._cancel_active_insert_modes()
        applied = self._apply_shape_stroke_to_selected(stroke_style)
        # "none" only ever strips the border off an already-drawn shape; it never
        # becomes the default, so freshly drawn shapes always keep a visible border.
        if stroke_style != "none":
            set_tool_setting_for(self.canvas, "active_shape_stroke", stroke_style)
        if not applied:
            self._set_active_tool("shape")
        self._refresh_tool_mode()

    def set_arrow_line_width(self, width: float) -> None:
        set_tool_setting_for(self.canvas, "arrow_line_width", max(0.5, float(width)))

    def get_arrow_line_width(self) -> float:
        return self.settings.arrow_line_width

    def set_arrow_head_scale(self, scale: float) -> None:
        set_tool_setting_for(self.canvas, "arrow_head_scale", max(0.1, min(0.8, scale)))

    def get_arrow_head_scale(self) -> float:
        return self.settings.arrow_head_scale

    def set_curved_snap(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).curved_snap = bool(enabled)

    def get_curved_snap(self) -> bool:
        return tool_settings_state_for(self.canvas).curved_snap

    def set_curved_snap_step(self, step: float) -> None:
        tool_settings_state_for(self.canvas).curved_snap_step = max(0.05, float(step))

    def get_curved_snap_step(self) -> float:
        return tool_settings_state_for(self.canvas).curved_snap_step

    def set_curved_symmetry(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).curved_symmetry = bool(enabled)

    def get_curved_symmetry(self) -> bool:
        return tool_settings_state_for(self.canvas).curved_symmetry

    def set_orbital_snap_enabled(self, enabled: bool) -> None:
        tool_settings_state_for(self.canvas).orbital_snap_enabled = bool(enabled)

    def get_orbital_snap_enabled(self) -> bool:
        return tool_settings_state_for(self.canvas).orbital_snap_enabled

    def set_orbital_snap_step(self, step: int) -> None:
        tool_settings_state_for(self.canvas).orbital_snap_step = max(1, int(step))

    def get_orbital_snap_step(self) -> int:
        return tool_settings_state_for(self.canvas).orbital_snap_step

    def set_atom_symbol(self, symbol: str) -> None:
        set_tool_setting_for(self.canvas, "atom_symbol", symbol.strip())

    def get_atom_symbol(self) -> str:
        return self.settings.atom_symbol

    def set_snap_angle_step(self, step: int) -> None:
        self._cancel_active_insert_modes()
        set_tool_setting_for(self.canvas, "snap_angle_step", step)
        self._set_active_tool("bond")
        refresh_selection_outline_for(self.canvas)

__all__ = ["CanvasToolModeController"]
