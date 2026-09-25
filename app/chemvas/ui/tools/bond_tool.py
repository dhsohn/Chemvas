from __future__ import annotations

from typing import override

from PyQt6.QtCore import QLineF, QPointF, Qt

from chemvas.features.rendering import (
    BOLD_BOND_STYLES,
    is_dotted_double_bond_style,
    style_for_existing_bond_overlay,
)
from chemvas.ui.canvas.canvas_window_access import notify_error_for
from chemvas.ui.insert.preview_scene_renderer import clear_scene_items
from chemvas.ui.molecule.bond_preview_access import (
    add_bond_preview_items_for,
    build_bond_preview_items_for,
    update_bond_preview_items_for,
)
from chemvas.ui.molecule.structure_geometry_access import default_bond_endpoint_for
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.selection.selection_queries import scene_selected_items_for
from chemvas.ui.tools.bond_tool_logic import (
    resolve_bond_endpoint_target,
    resolve_bond_press_target,
    resolve_bond_snap_target,
)
from chemvas.ui.tools.tool_base import Tool
from chemvas.ui.tools.tool_overlay_logic import activate_tool_no_drag


class BondTool(Tool):
    def __init__(self, canvas, *, context=None) -> None:
        super().__init__("bond", canvas, context=context)
        self._start_pos: QPointF | None = None
        self._start_atom_id: int | None = None
        self._press_scene_pos: QPointF | None = None
        self._preview_items: list = []
        self._preview_signature: str | None = None
        self._angle_guide: tuple[tuple[float, float], tuple[float, float]] | None = None

    @property
    @override
    def angle_guide(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        return self._angle_guide

    @property
    @override
    def has_active_gesture(self) -> bool:
        return self._start_pos is not None

    @override
    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    @override
    def deactivate(self) -> None:
        self._clear_preview_items()
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None

    def _clear_preview_items(self) -> None:
        if self._angle_guide is not None:
            self._angle_guide = None
            self.canvas.viewport().update()
        if not self._preview_items:
            self._preview_signature = None
            return
        self._preview_items = clear_scene_items(
            self.canvas.scene(), self._preview_items
        )
        self._preview_signature = None

    def _set_preview_items(self, start: QPointF, end: QPointF) -> None:
        settings = self.canvas.runtime_state.tool_settings_state
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
        bond = self.canvas.model.bond_for_id(bond_id)
        if bond is None:
            return False
        settings = self.canvas.runtime_state.tool_settings_state
        active_bond_style = settings.active_bond_style
        if bond.style == "double_either" and (
            active_bond_style in BOLD_BOND_STYLES or active_bond_style == "dotted"
        ):
            notify_error_for(
                self.canvas,
                "This appearance change would erase unknown double-bond stereo. "
                "Choose Double (2) first to clear it explicitly.",
            )
            return True
        if active_bond_style in {"wedge", "hash"}:
            self.context.apply_bond_style(bond_id, active_bond_style, 1)
            return True
        if active_bond_style in BOLD_BOND_STYLES:
            next_style, next_order = style_for_existing_bond_overlay(
                bond.style, bond.order, active_bond_style, settings.active_bond_order
            )
            self.context.apply_bond_style(bond_id, next_style, next_order)
            return True
        if active_bond_style == "dotted":
            next_style, next_order = style_for_existing_bond_overlay(
                bond.style,
                bond.order,
                "dotted",
                1,
            )
            if bond.order == 2 and not is_dotted_double_bond_style(
                next_style, next_order
            ):
                notify_error_for(
                    self.canvas,
                    "Dotted overlay needs an inner or outer plain double bond. "
                    "Choose Double, then its position, and try Dotted again.",
                )
                return True
            self.context.apply_bond_style(bond_id, next_style, next_order)
            return True
        if active_bond_style in {"single", "double", "triple"}:
            if (bond.style, bond.order) != (
                active_bond_style,
                settings.active_bond_order,
            ):
                self.context.apply_bond_style(
                    bond_id, active_bond_style, settings.active_bond_order
                )
            return True
        self.context.cycle_bond_style(bond_id)
        return True

    def _clear_existing_selection(self) -> None:
        if scene_selected_items_for(self.canvas):
            self.canvas.services.selection.clear_scene_selection()
        if self.canvas.runtime_state.selection_state.selected_notes:
            self.canvas.services.selection.clear_note_selection()

    @override
    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._clear_existing_selection()
        press_pos = self.context.scene_pos_from_event(event)
        atom_id = self.context.find_atom_near(
            press_pos.x(),
            press_pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        item = self.context.item_at_event(event)
        if item is None:
            item = self.context.preferred_structure_item_at_scene_pos(press_pos)
        nearby_bond_id = None
        if atom_id is None:
            nearby_bond_id = self.context.find_bond_near(
                press_pos,
                self.canvas.renderer.style.bond_length_px * 0.35,
            )
        press_bond_id = resolve_bond_press_target(
            atom_id=atom_id,
            item_kind=item.data(0) if item is not None else None,
            item_bond_id=item.data(1) if item is not None else None,
            nearby_bond_id=nearby_bond_id,
            hover_bond_id=self.canvas.runtime_state.hover_preview_state.bond_id,
        )
        if press_bond_id is not None:
            return self._apply_active_style_to_bond(press_bond_id)
        self._press_scene_pos = press_pos
        self._start_pos = self._snap_to_atom(self._press_scene_pos)
        self._set_preview_items(self._start_pos, self._start_pos)
        return True

    @override
    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        current_pos = self._snap_to_atom(
            self.context.scene_pos_from_event(event),
            ignore_start=True,
        )
        snapped = self._snap_endpoint(self._start_pos, current_pos)
        self._set_preview_items(self._start_pos, snapped)
        # Atom targets keep their exact geometry; they are not angle snaps.
        target_atom = self.context.find_atom_near(
            snapped.x(), snapped.y(), self.canvas.renderer.style.bond_length_px * 0.35
        )
        self._angle_guide = (
            ((self._start_pos.x(), self._start_pos.y()), (snapped.x(), snapped.y()))
            if target_atom is None and snapped != self._start_pos
            else None
        )
        self.canvas.viewport().update()
        return True

    @override
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
        if dist < self.canvas.renderer.style.bond_length_px * 0.1:
            end_pos = default_bond_endpoint_for(
                self.canvas, self._start_pos, self._start_atom_id
            )
        self._clear_preview_items()
        settings = self.canvas.runtime_state.tool_settings_state
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
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        bond_id = None
        if atom_id is None:
            bond_id = self.context.find_bond_near(
                pos, self.canvas.renderer.style.bond_length_px * 0.2
            )
        target = resolve_bond_snap_target(
            self.canvas.model,
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
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        target = resolve_bond_endpoint_target(
            self.canvas.model,
            start=(start.x(), start.y()),
            end=(end.x(), end.y()),
            atom_id=atom_id,
            start_atom_id=self._start_atom_id,
            snap_angle_step=self.canvas.runtime_state.tool_settings_state.snap_angle_step,
            bond_length=self.canvas.renderer.style.bond_length_px,
        )
        return QPointF(*target)


__all__ = ["BondTool"]
