import time
from typing import Dict, Optional

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QInputDialog

from core.history import (
    CompositeCommand,
    MoveAtomsCommand,
    MoveItemsCommand,
    UpdateSceneItemCommand,
)
from core.delete_tool_logic import build_delete_tool_history_command, erase_delete_tool_item
from core.bond_tool_logic import (
    resolve_bond_endpoint_target,
    resolve_bond_press_target,
    resolve_bond_snap_target,
)
from core.perspective_drag_logic import resolve_perspective_drag_update
from core.tool_overlay_logic import activate_tool_no_drag, clear_temporary_tool_overlay
from ui.bond_preview_renderer import (
    add_bond_preview_items as add_bond_preview_items_helper,
    clear_bond_preview_items as clear_bond_preview_items_helper,
)
from ui.atom_label_access import add_or_update_atom_label
from ui.bond_style_logic import style_for_existing_bond_overlay
from ui.perspective_tool_controller import PerspectiveToolController
from ui.selection_press_logic import SelectionPressContext, plan_selection_press
from core.text_tool_logic import (
    build_created_atom_command,
    normalize_text_symbol,
    plan_text_input,
    resolve_text_tool_target,
)


class Tool:
    def __init__(self, name: str) -> None:
        self.name = name

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def on_mouse_press(self, event) -> bool:
        return False

    def on_mouse_move(self, event) -> bool:
        return False

    def on_mouse_release(self, event) -> bool:
        return False


def _independent_selection_items(selection_items: list, atom_ids: set[int]) -> list:
    items: list = []
    seen = set()
    for item in selection_items:
        if item is None or item in seen:
            continue
        seen.add(item)
        kind = item.data(0)
        if kind in {"atom", "bond", "ring"}:
            continue
        if kind == "mark":
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int) and atom_id in atom_ids:
                continue
        items.append(item)
    return items


def _perspective_tool_controller_for(canvas) -> PerspectiveToolController:
    return PerspectiveToolController(canvas)


class _SelectionDragMixin:
    def _reset_selection_drag_state(self) -> None:
        self._drag_selection = False
        self._selection_atom_ids: set[int] = set()
        self._selection_items: list = []
        self._drag_bond_ids: set[int] = set()
        self._drag_boundary_bond_ids: set[int] = set()
        self._suspended_outline = False

    def _begin_selection_drag(self, atom_ids: set[int], selection_items: list, start_pos) -> bool:
        if not atom_ids and not selection_items:
            return False
        self._drag_selection = True
        self._selection_atom_ids = set(atom_ids)
        self._selection_items = _independent_selection_items(selection_items, self._selection_atom_ids)
        if self._selection_atom_ids:
            self._drag_bond_ids, self._drag_boundary_bond_ids = self.canvas.bond_sets_for_atoms(
                self._selection_atom_ids
            )
        else:
            self._drag_bond_ids = set()
            self._drag_boundary_bond_ids = set()
        self._start_pos = start_pos
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if not self._drag_selection:
            return
        if not self._suspended_outline:
            self.canvas.suspend_selection_outline(True)
            self._suspended_outline = True
        if self._selection_atom_ids:
            self.canvas.move_atoms(
                self._selection_atom_ids,
                delta.x(),
                delta.y(),
                bond_ids=self._drag_bond_ids,
                redraw_bond_ids=self._drag_boundary_bond_ids,
                update_selection=False,
            )
        for item in self._selection_items:
            self.canvas.move_item(item, delta.x(), delta.y(), update_selection=False)
        self.canvas.shift_selection_outlines(delta.x(), delta.y())
        self._total_delta += delta
        self._moved = True

    def _build_move_command(self):
        commands = []
        if self._selection_atom_ids:
            commands.append(
                MoveAtomsCommand(
                    atom_ids=set(self._selection_atom_ids),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                    bond_ids=set(self._drag_bond_ids) if self._drag_bond_ids else None,
                    redraw_bond_ids=set(self._drag_boundary_bond_ids) if self._drag_boundary_bond_ids else None,
                )
            )
        if self._selection_items:
            commands.append(
                MoveItemsCommand(
                    items=list(self._selection_items),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
            )
        if not commands:
            return None
        if len(commands) == 1:
            return commands[0]
        return CompositeCommand(commands)

    def _commit_selection_drag(self) -> None:
        if self._suspended_outline:
            self.canvas.suspend_selection_outline(False)
        if self._moved:
            self.canvas._update_selection_outline()
            command = self._build_move_command()
            if command is not None:
                self.canvas._push_command(command)


class SelectTool(_SelectionDragMixin, Tool):
    def __init__(self, canvas) -> None:
        super().__init__("select")
        self.canvas = canvas
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state = None
        self._reset_selection_drag_state()
        self._start_pos = None
        self._moved = False
        self._total_delta = QPointF(0.0, 0.0)
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.RubberBandDrag)

    def _selection_drag_context(self, snapshot=None) -> tuple[set[int], list]:
        if snapshot is None:
            snapshot = self.canvas._selection_snapshot()
        if snapshot is None:
            return set(), []
        return set(snapshot.selected_atom_ids), list(snapshot.selection_items)

    def _select_structure_item(self, item) -> bool:
        if item is None:
            return False
        kind = item.data(0)
        self.canvas.scene().clearSelection()
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return False
            atom_item = self.canvas.atom_items.get(atom_id) or self.canvas.atom_dots.get(atom_id)
            if atom_item is None:
                return False
            atom_item.setSelected(True)
            return True
        if kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return False
            bond_items = self.canvas.bond_items.get(bond_id, [])
            if not bond_items:
                return False
            for bond_item in bond_items:
                bond_item.setSelected(True)
            return True
        if kind == "ring":
            item.setSelected(True)
            return True
        return False

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            item = self.canvas.item_at_event(event)
            if self.canvas.toggle_item_selection(item):
                return True
        item = self.canvas.item_at_event(event)
        if item is not None and item.data(0) == "handle":
            self._active_handle = item
            self._handle_target = item.data(2)
            self._handle_before_state = self.canvas.scene_item_state(self._handle_target)
            return True
        if item is not None and item.data(0) in {"curved_single", "curved_double"}:
            self.canvas.show_curved_handles(item)
            return False
        self.canvas.clear_handles()
        press_pos = self.canvas.scene_pos_from_event(event)
        selected = self.canvas.scene().selectedItems()
        if not selected:
            preferred = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
            if preferred is None or preferred.data(0) not in {"atom", "bond", "ring"}:
                return False
            if not self._select_structure_item(preferred):
                return False
            item = preferred
        snapshot = self.canvas._selection_snapshot()
        atom_ids, selection_items = self._selection_drag_context(snapshot)
        preferred = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
        decision = plan_selection_press(
            SelectionPressContext(
                has_selection_target=bool(atom_ids or selection_items),
                hits_current_selection=self.canvas.selection_hit_test(press_pos, snapshot=snapshot),
                has_preferred_structure=bool(
                    preferred is not None and preferred.data(0) in {"atom", "bond", "ring"}
                ),
            )
        )
        if decision.action == "ignore":
            return False
        if decision.action == "reselect_preferred_and_drag":
            if preferred is None or preferred.data(0) not in {"atom", "bond", "ring"}:
                return False
            if not self._select_structure_item(preferred):
                return False
            item = preferred
            snapshot = self.canvas._selection_snapshot()
            atom_ids, selection_items = self._selection_drag_context(snapshot)
            if not atom_ids and not selection_items:
                return False
        return self._begin_selection_drag(atom_ids, selection_items, event.position())

    def on_mouse_move(self, event) -> bool:
        if self._active_handle is not None:
            self.canvas.update_handle_drag(self._active_handle, self.canvas.scene_pos_from_event(event))
            return True
        if self._start_pos is None:
            return False
        if self._drag_selection:
            now = time.monotonic()
            if now - self._last_drag_time < self._drag_interval:
                return True
            self._last_drag_time = now
        delta = event.position() - self._start_pos
        self._apply_drag_delta(delta)
        self._start_pos = event.position()
        return True

    def on_mouse_release(self, event) -> bool:
        if self._active_handle is not None:
            target = self._handle_target
            before_state = self._handle_before_state
            after_state = self.canvas.scene_item_state(target)
            self._active_handle = None
            self._handle_target = None
            self._handle_before_state = None
            if before_state and after_state and before_state != after_state:
                command = UpdateSceneItemCommand(target, before_state, after_state)
                self.canvas._push_command(command)
            return True
        if self._start_pos is None and not self._drag_selection:
            return False
        if self._start_pos is not None and self._drag_selection:
            delta = event.position() - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                self._apply_drag_delta(delta)
                self._start_pos = event.position()
        self._commit_selection_drag()
        self._reset_selection_drag_state()
        self._start_pos = None
        self._moved = False
        self._total_delta = QPointF(0.0, 0.0)
        return True


class RotateTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("rotate")
        self.canvas = canvas
        self._last_pos = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = event.position()
            return True
        return False

    def on_mouse_move(self, event) -> bool:
        if self._last_pos is None:
            return False
        current_pos = event.position()
        delta_x = current_pos.x() - self._last_pos.x()
        self.canvas.rotate_view(delta_x * 0.3)
        self._last_pos = current_pos
        return True

    def on_mouse_release(self, event) -> bool:
        self._last_pos = None
        return False


class BondTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("bond")
        self.canvas = canvas
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None
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
        self._preview_items = clear_bond_preview_items_helper(self.canvas.scene(), self._preview_items)
        self._preview_signature = None

    def _set_preview_items(self, start: QPointF, end: QPointF) -> None:
        signature = f"{self.canvas.active_bond_style}:{self.canvas.active_bond_order}"
        if self._preview_items and self._preview_signature == signature:
            if self.canvas.update_bond_preview_items(
                self._preview_items,
                start,
                end,
                self._start_atom_id,
                None,
                self.canvas.active_bond_style,
                self.canvas.active_bond_order,
            ):
                return
        self._clear_preview_items()
        items = self.canvas._build_bond_preview_items(start, end, self._start_atom_id, None)
        if not items:
            return
        self._preview_items = add_bond_preview_items_helper(self.canvas.scene(), items)
        self._preview_signature = signature

    def _apply_active_style_to_bond(self, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return False
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return False
        if self.canvas.active_bond_style in {"wedge", "hash"}:
            self.canvas.apply_bond_style(bond_id, self.canvas.active_bond_style, 1)
            return True
        if self.canvas.active_bond_style in {"bold", "bold_in", "bold_out"}:
            if bond.style in {"bold_in", "bold"}:
                next_style = "bold_out"
            elif bond.style == "bold_out":
                next_style = "bold_in"
            else:
                next_style = "bold_in"
            self.canvas.apply_bond_style(bond_id, next_style, bond.order)
            return True
        if self.canvas.active_bond_style == "dotted":
            next_style, next_order = style_for_existing_bond_overlay(
                bond.style,
                bond.order,
                "dotted",
                1,
            )
            self.canvas.apply_bond_style(bond_id, next_style, next_order)
            return True
        self.canvas.cycle_bond_style(bond_id)
        return True

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        press_pos = self.canvas.scene_pos_from_event(event)
        atom_id = self.canvas.find_atom_near(
            press_pos.x(),
            press_pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        item = self.canvas.item_at_event(event)
        if item is None and hasattr(self.canvas, "preferred_structure_item_at_scene_pos"):
            item = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
        nearby_bond_id = None
        if atom_id is None and hasattr(self.canvas, "_find_bond_near"):
            nearby_bond_id = self.canvas._find_bond_near(
                press_pos,
                self.canvas.renderer.style.bond_length_px * 0.35,
            )
        press_bond_id = resolve_bond_press_target(
            atom_id=atom_id,
            item_kind=item.data(0) if item is not None else None,
            item_bond_id=item.data(1) if item is not None else None,
            nearby_bond_id=nearby_bond_id,
            hover_bond_id=self.canvas.hover_bond_id,
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
        current_pos = self._snap_to_atom(self.canvas.scene_pos_from_event(event), ignore_start=True)
        snapped = self._snap_endpoint(self._start_pos, current_pos)
        self._set_preview_items(self._start_pos, snapped)
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        release_pos = self.canvas.scene_pos_from_event(event)
        end_pos = self._snap_to_atom(release_pos, ignore_start=True)
        end_pos = self._snap_endpoint(self._start_pos, end_pos)
        if self._press_scene_pos is not None:
            dist = QLineF(self._press_scene_pos, release_pos).length()
        else:
            dist = 0.0
        if dist < self.canvas.renderer.style.bond_length_px * 0.1:
            end_pos = self.canvas._default_bond_endpoint(self._start_pos, self._start_atom_id)
        self._clear_preview_items()
        self.canvas.add_bond_from_points(self._start_pos, end_pos)
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None
        return True

    def _snap_to_atom(self, pos, ignore_start: bool = False):
        atom_id = self.canvas.find_atom_near(
            pos.x(),
            pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        bond_id = None
        if atom_id is None and hasattr(self.canvas, "_find_bond_near"):
            bond_id = self.canvas._find_bond_near(pos, self.canvas.renderer.style.bond_length_px * 0.2)
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
        atom_id = self.canvas.find_atom_near(
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
            snap_angle_step=self.canvas.snap_angle_step,
            bond_length=self.canvas.renderer.style.bond_length_px,
        )
        return QPointF(*target)


class TextTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("text")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        pick_radius = self.canvas.renderer.style.bond_length_px * 0.9
        bond_pick_radius = self.canvas.renderer.style.bond_length_px * 0.6
        item = self.canvas.item_at_event(event)
        item_atom_id = None
        if item is not None and item.data(0) == "atom":
            data_id = item.data(1)
            if isinstance(data_id, int):
                item_atom_id = data_id
        nearby_bond_id = None
        nearby_atom_id = None
        if self.canvas.hover_atom_id is None and item_atom_id is None:
            nearby_bond_id = self.canvas._find_bond_near(pos, bond_pick_radius)
            nearby_atom_id = self.canvas.find_atom_near(pos.x(), pos.y(), pick_radius)
        target = resolve_text_tool_target(
            self.canvas.model,
            pos=(pos.x(), pos.y()),
            hover_atom_id=self.canvas.hover_atom_id,
            item_atom_id=item_atom_id,
            hover_bond_id=self.canvas.hover_bond_id,
            nearby_bond_id=nearby_bond_id,
            nearby_atom_id=nearby_atom_id,
        )
        atom_id = target.atom_id
        pos = QPointF(*target.pos)
        existing_element = self.canvas.model.atoms[atom_id].element if atom_id is not None else ""
        input_plan = plan_text_input(self.canvas.get_atom_symbol(), existing_element=existing_element)
        text = input_plan.text
        if input_plan.needs_prompt:
            text, ok = QInputDialog.getText(
                self.canvas,
                "Atom Label",
                "Enter atom symbol:",
                text=input_plan.initial,
            )
            if not ok:
                return True
            text = normalize_text_symbol(text)
        created_atom = False
        if atom_id is None:
            if not text:
                return True
            before_smiles_input = self.canvas.last_smiles_input
            before_next_atom_id = self.canvas.model.next_atom_id
            atom_id = self.canvas.add_atom(text, pos.x(), pos.y())
            created_atom = True
        if created_atom:
            add_or_update_atom_label(self.canvas, atom_id, text, show_carbon=True, record=False)
            atom_state = self.canvas._atom_state_dict(atom_id)
            command = build_created_atom_command(
                atom_id=atom_id,
                atom_state=atom_state,
                before_next_atom_id=before_next_atom_id,
                after_next_atom_id=self.canvas.model.next_atom_id,
                before_smiles_input=before_smiles_input,
                after_smiles_input=self.canvas.last_smiles_input,
            )
            self.canvas._push_command(command)
        else:
            add_or_update_atom_label(self.canvas, atom_id, text, show_carbon=True)
        return True

    @staticmethod
    def _normalized_symbol(text: str) -> str:
        return normalize_text_symbol(text)


class BenzeneTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("benzene")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)
        self.canvas._clear_benzene_preview()

    def deactivate(self) -> None:
        self.canvas._clear_benzene_preview()

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        if self.canvas.hover_bond_id is not None:
            self.canvas.add_benzene_ring(pos, attach_bond_id=self.canvas.hover_bond_id)
        elif self.canvas.hover_atom_id is not None:
            self.canvas.add_benzene_ring(pos, attach_atom_id=self.canvas.hover_atom_id)
        else:
            self.canvas.add_benzene_ring(pos)
        self.canvas._clear_benzene_preview()
        return True

    def on_mouse_move(self, event) -> bool:
        if event.buttons() != Qt.MouseButton.NoButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        attach_bond_id = self.canvas.hover_bond_id
        attach_atom_id = None if attach_bond_id is not None else self.canvas.hover_atom_id
        self.canvas._render_benzene_preview(
            pos,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )
        return True


class ColorTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("color")
        self.canvas = canvas
        self._last_color = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        targets = []
        if item is not None:
            targets = [item]
        else:
            targets = [sel for sel in self.canvas.scene().selectedItems() if sel.data(0) in {"bond", "atom", "ring"}]
            if not targets:
                return True
        color = QColor(self._last_color or self.canvas.renderer.style.atom_color)
        if not color.isValid():
            return True
        for target in targets:
            self.canvas.apply_color_to_item(target, color)
        return True


class FlipTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("flip")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is None:
            return True
        bond_id = item.data(1)
        if isinstance(bond_id, int):
            self.canvas.flip_bond_direction(bond_id)
        return True


class EditBondTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("edit_bond")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        bond_id = None
        if item is not None and item.data(0) == "bond":
            bond_id = item.data(1)
        if not isinstance(bond_id, int):
            bond_id = self.canvas.bond_id_from_event(event)
        if isinstance(bond_id, int):
            self.canvas.cycle_bond_style(bond_id)
        return True


class MoveTool(_SelectionDragMixin, Tool):
    def __init__(self, canvas) -> None:
        super().__init__("move")
        self.canvas = canvas
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._reset_selection_drag_state()
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        selected = self.canvas._selected_items_for_transform()
        if selected:
            atom_ids, bond_ids = self.canvas._selected_ids()
            for bond_id in bond_ids:
                if 0 <= bond_id < len(self.canvas.model.bonds):
                    bond = self.canvas.model.bonds[bond_id]
                    if bond is not None:
                        atom_ids.add(bond.a)
                        atom_ids.add(bond.b)
            selection_items = _independent_selection_items(selected, atom_ids)
            if self._begin_selection_drag(atom_ids, selection_items, event.position()):
                return True
        if item is None:
            return True
        kind = item.data(0)
        if kind not in {
            "atom",
            "bond",
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "orbital",
            "ts_bracket",
        }:
            return True
        self._drag_item = item
        self._start_pos = event.position()
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if self._drag_selection:
            super()._apply_drag_delta(delta)
        elif self._drag_item is not None:
            self.canvas.move_item(self._drag_item, delta.x(), delta.y())
            self._moved = True
            self._total_delta += delta

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        if self._drag_selection or self._drag_item is not None:
            now = time.monotonic()
            if now - self._last_drag_time < self._drag_interval:
                return True
            self._last_drag_time = now
        delta = event.position() - self._start_pos
        self._apply_drag_delta(delta)
        self._start_pos = event.position()
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is not None and (self._drag_selection or self._drag_item is not None):
            delta = event.position() - self._start_pos
            if abs(delta.x()) > 1e-6 or abs(delta.y()) > 1e-6:
                self._apply_drag_delta(delta)
                self._start_pos = event.position()
        if self._moved:
            if self._drag_selection:
                self._commit_selection_drag()
            elif self._drag_item is not None:
                self.canvas._update_selection_outline()
                command = MoveItemsCommand(
                    items=[self._drag_item],
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
                self.canvas._push_command(command)
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._reset_selection_drag_state()
        self._total_delta = QPointF(0.0, 0.0)
        return True


class DeleteTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("delete")
        self.canvas = canvas
        self._erasing = False
        self._changed = False
        self._commands = []
        self._before_smiles_input = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._erasing = True
        self._commands = []
        self._before_smiles_input = self.canvas.last_smiles_input
        self._erase_at_event(event)
        return True

    def on_mouse_move(self, event) -> bool:
        if not self._erasing:
            return False
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._erase_at_event(event)
            return True
        return False

    def on_mouse_release(self, event) -> bool:
        self._erasing = False
        if self._changed and self._commands:
            command = build_delete_tool_history_command(
                self._commands,
                before_smiles_input=self._before_smiles_input,
                after_smiles_input=self.canvas.last_smiles_input,
            )
            if command is not None:
                self.canvas._push_command(command)
        self._changed = False
        self._commands = []
        self._before_smiles_input = None
        return True

    def _erase_at_event(self, event) -> None:
        item = self.canvas.item_at_event(event)
        if item is None:
            return
        try:
            if item.scene() is not self.canvas.scene():
                return
        except RuntimeError:
            return
        changed, command = erase_delete_tool_item(self.canvas, item)
        if not changed:
            return
        if command is not None:
            self._commands.append(command)
        self._changed = True


class _PreviewDragTool(Tool):
    def __init__(self, name: str, canvas) -> None:
        super().__init__(name)
        self.canvas = canvas
        self._start_pos = None
        self._preview_item = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        self._clear_preview()
        self._start_pos = None

    def _clear_preview(self) -> None:
        self._preview_item = clear_temporary_tool_overlay(self.canvas, preview_item=self._preview_item)

    def _build_preview(self, current_pos):
        raise NotImplementedError

    def _commit_drag(self, end_pos) -> None:
        raise NotImplementedError

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start_pos = self.canvas.scene_pos_from_event(event)
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        current_pos = self.canvas.scene_pos_from_event(event)
        self._clear_preview()
        self._preview_item = self._build_preview(current_pos)
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        end_pos = self.canvas.scene_pos_from_event(event)
        self._clear_preview()
        self._commit_drag(end_pos)
        self._start_pos = None
        return True


class ArrowTool(_PreviewDragTool):
    def __init__(self, canvas, mode: str = "auto") -> None:
        super().__init__("arrow", canvas)
        self.mode = mode

    def _arrow_type(self) -> str:
        return self.mode if self.mode != "auto" else self.canvas.active_arrow_type

    def _build_preview(self, current_pos):
        return self.canvas.preview_arrow(self._start_pos, current_pos, self._arrow_type())

    def _commit_drag(self, end_pos) -> None:
        self.canvas.add_arrow(self._start_pos, end_pos, self._arrow_type())


class TSBracketTool(_PreviewDragTool):
    def __init__(self, canvas) -> None:
        super().__init__("ts_bracket", canvas)

    def _build_preview(self, current_pos):
        return self.canvas.preview_ts_bracket(self._start_pos, current_pos)

    def _commit_drag(self, end_pos) -> None:
        self.canvas.add_ts_bracket_from_points(self._start_pos, end_pos)


class OrbitalTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("orbital")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        self.canvas.add_orbital(pos)
        return True


class TransformTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("transform")
        self.canvas = canvas
        self._active_handle = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def deactivate(self) -> None:
        clear_temporary_tool_overlay(self.canvas, clear_handles=True)
        self._active_handle = None

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is None:
            clear_temporary_tool_overlay(self.canvas, clear_handles=True)
            self._active_handle = None
            return True
        if item.data(0) == "handle":
            self._active_handle = item
            return True
        self._active_handle = None
        kind = item.data(0)
        if kind == "orbital":
            self.canvas.show_orbital_handles(item)
        elif kind in {"curved_single", "curved_double"}:
            self.canvas.show_curved_handles(item)
        else:
            clear_temporary_tool_overlay(self.canvas, clear_handles=True)
        return True


class MarkTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("mark")
        self.canvas = canvas

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        atom_id = self.canvas.find_atom_near(
            pos.x(),
            pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        if atom_id is not None:
            self.canvas.add_mark_for_atom(atom_id, pos)
        else:
            self.canvas.add_mark(pos)
        return True


class NoteTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("note")
        self.canvas = canvas
        self._active_handle = None

    def activate(self) -> None:
        activate_tool_no_drag(self.canvas)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is not None and item.data(0) == "note":
            modifiers = event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                self.canvas.toggle_note_selection(item)
                return True
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                self.canvas.select_note(item, additive=True)
                return True
            self.canvas.select_note(item, additive=False)
            self.canvas.begin_note_edit(item)
            return True
        pos = self.canvas.scene_pos_from_event(event)
        self.canvas.clear_note_selection()
        item = self.canvas.add_text_note(pos, "")
        self.canvas.begin_note_edit(item)
        return True

    def on_mouse_move(self, event) -> bool:
        return False

    def on_mouse_release(self, event) -> bool:
        self._active_handle = None
        return False


class PerspectiveTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("perspective")
        self.canvas = canvas
        self._last_pos = None
        self._rotating = False
        self._axis_lock = None

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.RubberBandDrag)

    def deactivate(self) -> None:
        self._last_pos = None
        self._rotating = False
        self._axis_lock = None

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            item = self.canvas.item_at_event(event)
            if self.canvas.toggle_item_selection(item):
                return True
        self._rotating = _perspective_tool_controller_for(self.canvas).begin_selection_rotation(event)
        if self._rotating:
            self._last_pos = event.position()
            self._axis_lock = None
        else:
            self._last_pos = None
        return self._rotating

    def on_mouse_move(self, event) -> bool:
        if self._last_pos is None or not self._rotating:
            return self._rotating
        current = event.position()
        delta = current - self._last_pos
        update = resolve_perspective_drag_update(
            delta_x=delta.x(),
            delta_y=delta.y(),
            axis_lock=self._axis_lock,
            rotation_mode=self.canvas._rotation_mode,
            shift_pressed=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
        )
        self._axis_lock = update.axis_lock
        if not update.should_update:
            return True
        self.canvas.update_selection_3d_rotation(update.delta_x, update.delta_y)
        self._last_pos = current
        return True

    def on_mouse_release(self, event) -> bool:
        self._last_pos = None
        self._axis_lock = None
        if self._rotating:
            self.canvas.end_selection_3d_rotation()
        self._rotating = False
        return True


class ToolController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.tools: Dict[str, Tool] = {
            "select": SelectTool(canvas),
            "bond": BondTool(canvas),
            "text": TextTool(canvas),
            "mark": MarkTool(canvas),
            "benzene": BenzeneTool(canvas),
            "color": ColorTool(canvas),
            "flip": FlipTool(canvas),
            "move": MoveTool(canvas),
            "arrow": ArrowTool(canvas, "auto"),
            "equilibrium": ArrowTool(canvas, "equilibrium"),
            "ts_bracket": TSBracketTool(canvas),
            "orbital": OrbitalTool(canvas),
            "perspective": PerspectiveTool(canvas),
        }
        self.active: Optional[Tool] = None

    def set_active(self, name: str) -> None:
        if self.active:
            self.active.deactivate()
        self.active = self.tools.get(name, self.tools["select"])
        self.active.activate()
