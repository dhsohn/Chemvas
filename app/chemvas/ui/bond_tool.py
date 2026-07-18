from __future__ import annotations

from PyQt6.QtCore import QLineF, QPointF, Qt

from chemvas.core.bond_tool_logic import (
    resolve_bond_endpoint_target,
    resolve_bond_press_target,
    resolve_bond_snap_target,
)
from chemvas.core.tool_overlay_logic import activate_tool_no_drag
from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    bold_double_style_for_style,
    style_for_existing_bond_overlay,
)
from chemvas.ui.bond_preview_access import (
    add_bond_preview_items_for,
    build_bond_preview_items_for,
    clear_bond_preview_items_for,
    update_bond_preview_items_for,
)
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_model_access import bond_for_id, model_for
from chemvas.ui.canvas_scene_items_state import selected_notes_for
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.selection_scene_access import (
    clear_scene_selection_for,
    scene_selected_items_for,
)
from chemvas.ui.selection_service_access import (
    clear_note_selection_for,
)
from chemvas.ui.structure_geometry_access import default_bond_endpoint_for
from chemvas.ui.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.tool_base import Tool


class BondTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("bond", canvas, context=context)
        self._start_pos: QPointF | None = None
        self._start_atom_id: int | None = None
        self._press_scene_pos: QPointF | None = None
        self._preview_items: list = []
        self._preview_signature: str | None = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        self._clear_preview_items()
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None

    def _clear_preview_items(self) -> None:
        if not self._preview_items:
            self._preview_signature = None
            return
        self._preview_items = clear_bond_preview_items_for(
            self.canvas, self._preview_items
        )
        self._preview_signature = None

    def _set_preview_items(self, start: QPointF, end: QPointF) -> None:
        settings = tool_settings_state_for(self.canvas)
        signature = f"{settings.active_bond_style}:{settings.active_bond_order}"
        if self._preview_items and self._preview_signature == signature:
            if update_bond_preview_items_for(
                self.canvas,
                self._preview_items,
                start,
                end,
                a_id=self._start_atom_id,
                b_id=None,
                style=settings.active_bond_style,
                order=settings.active_bond_order,
            ):
                return
        self._clear_preview_items()
        items = build_bond_preview_items_for(
            self.canvas, start, end, self._start_atom_id, None
        )
        if not items:
            return
        self._preview_items = add_bond_preview_items_for(self.canvas, items)
        self._preview_signature = signature

    def _apply_active_style_to_bond(self, bond_id: int) -> bool:
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return False
        active_bond_style = tool_settings_state_for(self.canvas).active_bond_style
        if active_bond_style in {"wedge", "hash"}:
            self.context.apply_bond_style(bond_id, active_bond_style, 1)
            return True
        if active_bond_style in BOLD_BOND_STYLES:
            if bond.order == 2:
                # Position is chosen from the shared double-bond context menu;
                # applying Bold again must not run the legacy in/out strip flip.
                next_style = bold_double_style_for_style(bond.style, bond.order)
            elif bond.style in {"bold_in", "bold"}:
                next_style = "bold_out"
            elif bond.style == "bold_out":
                next_style = "bold_in"
            else:
                next_style = "bold_in"
            self.context.apply_bond_style(bond_id, next_style, bond.order)
            return True
        if active_bond_style == "dotted":
            next_style, next_order = style_for_existing_bond_overlay(
                bond.style,
                bond.order,
                "dotted",
                1,
            )
            self.context.apply_bond_style(bond_id, next_style, next_order)
            return True
        self.context.cycle_bond_style(bond_id)
        return True

    def _clear_existing_selection(self) -> None:
        if scene_selected_items_for(self.canvas):
            clear_scene_selection_for(self.canvas)
        if selected_notes_for(self.canvas):
            clear_note_selection_for(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._clear_existing_selection()
        press_pos = self.context.scene_pos_from_event(event)
        atom_id = self.context.find_atom_near(
            press_pos.x(),
            press_pos.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        item = self.context.item_at_event(event)
        if item is None:
            item = self.context.preferred_structure_item_at_scene_pos(press_pos)
        nearby_bond_id = None
        if atom_id is None:
            nearby_bond_id = self.context.find_bond_near(
                press_pos,
                bond_length_px_for(self.canvas) * 0.35,
            )
        press_bond_id = resolve_bond_press_target(
            atom_id=atom_id,
            item_kind=item.data(0) if item is not None else None,
            item_bond_id=item.data(1) if item is not None else None,
            nearby_bond_id=nearby_bond_id,
            hover_bond_id=hover_state_for(self.canvas).bond_id,
        )
        if press_bond_id is not None:
            return self._apply_active_style_to_bond(press_bond_id)
        self._press_scene_pos = press_pos
        self._start_pos = self._snap_to_atom(self._press_scene_pos)
        self._set_preview_items(self._start_pos, self._start_pos)
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        current_pos = self._snap_to_atom(
            self.context.scene_pos_from_event(event),
            ignore_start=True,
        )
        snapped = self._snap_endpoint(self._start_pos, current_pos)
        self._set_preview_items(self._start_pos, snapped)
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        release_pos = self.context.scene_pos_from_event(event)
        end_pos = self._snap_to_atom(release_pos, ignore_start=True)
        end_pos = self._snap_endpoint(self._start_pos, end_pos)
        if self._press_scene_pos is not None:
            dist = QLineF(self._press_scene_pos, release_pos).length()
        else:
            dist = 0.0
        if dist < bond_length_px_for(self.canvas) * 0.1:
            end_pos = default_bond_endpoint_for(
                self.canvas, self._start_pos, self._start_atom_id
            )
        self._clear_preview_items()
        settings = tool_settings_state_for(self.canvas)
        add_bond_between_points_for(
            self.canvas,
            self._start_pos,
            end_pos,
            style=settings.active_bond_style,
            order=settings.active_bond_order,
        )
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None
        return True

    def _snap_to_atom(self, pos, ignore_start: bool = False):
        atom_id = self.context.find_atom_near(
            pos.x(),
            pos.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        bond_id = None
        if atom_id is None:
            bond_id = self.context.find_bond_near(
                pos, bond_length_px_for(self.canvas) * 0.2
            )
        target = resolve_bond_snap_target(
            model_for(self.canvas),
            pos=(pos.x(), pos.y()),
            atom_id=atom_id,
            bond_id=bond_id,
            start_atom_id=self._start_atom_id,
            ignore_start=ignore_start,
        )
        self._start_atom_id = target.start_atom_id
        return QPointF(*target.pos)

    def _snap_endpoint(self, start, end):
        atom_id = self.context.find_atom_near(
            end.x(),
            end.y(),
            bond_length_px_for(self.canvas) * 0.35,
        )
        target = resolve_bond_endpoint_target(
            model_for(self.canvas),
            start=(start.x(), start.y()),
            end=(end.x(), end.y()),
            atom_id=atom_id,
            start_atom_id=self._start_atom_id,
            snap_angle_step=tool_settings_state_for(self.canvas).snap_angle_step,
            bond_length=bond_length_px_for(self.canvas),
        )
        return QPointF(*target)


__all__ = ["BondTool"]
