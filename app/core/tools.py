from typing import Dict, Optional

import time

import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QInputDialog

from core.history import (
    AddAtomsCommand,
    CompositeCommand,
    DeleteSceneItemsCommand,
    MoveAtomsCommand,
    MoveItemsCommand,
    SetSmilesInputCommand,
    UpdateSceneItemCommand,
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


class SelectTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("select")
        self.canvas = canvas
        self._active_handle = None
        self._handle_target = None
        self._handle_before_state = None
        self._drag_selection = False
        self._selection_atom_ids: set[int] = set()
        self._selection_items: list = []
        self._drag_bond_ids: set[int] = set()
        self._drag_boundary_bond_ids: set[int] = set()
        self._suspended_outline = False
        self._start_pos = None
        self._moved = False
        self._total_delta = QPointF(0.0, 0.0)
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.RubberBandDrag)

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
            selected = self.canvas.scene().selectedItems()
        atom_ids, bond_ids = self.canvas._selected_ids()
        for bond_id in bond_ids:
            if 0 <= bond_id < len(self.canvas.model.bonds):
                bond = self.canvas.model.bonds[bond_id]
                if bond is not None:
                    atom_ids.add(bond.a)
                    atom_ids.add(bond.b)
        selection_items = [
            sel
            for sel in selected
            if sel.data(0) not in {"selection_outline", "note_box", "note_select", "handle"}
        ]
        if not atom_ids and not selection_items:
            return False
        click_pos = press_pos
        for outline in self.canvas.selection_outlines:
            data = outline.data(2) or {}
            if data.get("kind") != "component":
                continue
            if not outline.contains(outline.mapFromScene(click_pos)):
                continue
            self._drag_selection = True
            self._selection_atom_ids = set(atom_ids)
            self._selection_items = selection_items
            if self._selection_atom_ids:
                self._drag_bond_ids, self._drag_boundary_bond_ids = self.canvas.bond_sets_for_atoms(
                    self._selection_atom_ids
                )
            else:
                self._drag_bond_ids = set()
                self._drag_boundary_bond_ids = set()
            self._start_pos = event.position()
            self._last_drag_time = 0.0
            self._total_delta = QPointF(0.0, 0.0)
            return True
        rects = []
        if atom_ids:
            for component in self.canvas._connected_components(atom_ids):
                bounds = self.canvas._bounds_for_atoms(component)
                if bounds is None:
                    continue
                min_x, min_y, max_x, max_y = bounds
                rects.append(QRectF(min_x, min_y, max_x - min_x, max_y - min_y))
        for sel in selection_items:
            kind = sel.data(0)
            if kind in {"atom", "bond", "ring"}:
                continue
            rects.append(sel.sceneBoundingRect())
        if rects:
            pad = self.canvas.renderer.style.bond_length_px * 0.1
            for rect in rects:
                padded = rect.adjusted(-pad, -pad, pad, pad)
                if not padded.contains(click_pos):
                    continue
                self._drag_selection = True
                self._selection_atom_ids = set(atom_ids)
                self._selection_items = selection_items
                if self._selection_atom_ids:
                    self._drag_bond_ids, self._drag_boundary_bond_ids = self.canvas.bond_sets_for_atoms(
                        self._selection_atom_ids
                    )
                else:
                    self._drag_bond_ids = set()
                    self._drag_boundary_bond_ids = set()
                self._start_pos = event.position()
                self._last_drag_time = 0.0
                self._total_delta = QPointF(0.0, 0.0)
                return True
        clicked_selection = False
        if item is not None:
            kind = item.data(0)
            if kind == "atom":
                atom_id = item.data(1)
                clicked_selection = isinstance(atom_id, int) and atom_id in atom_ids
            elif kind == "bond":
                bond_id = item.data(1)
                if isinstance(bond_id, int) and 0 <= bond_id < len(self.canvas.model.bonds):
                    bond = self.canvas.model.bonds[bond_id]
                    if bond is not None:
                        clicked_selection = bond.a in atom_ids or bond.b in atom_ids
            elif kind == "ring":
                ring_atom_ids = item.data(2)
                if isinstance(ring_atom_ids, list):
                    clicked_selection = any(atom_id in atom_ids for atom_id in ring_atom_ids)
            elif item.isSelected():
                clicked_selection = True
        if not clicked_selection:
            preferred = self.canvas.preferred_structure_item_at_scene_pos(press_pos)
            if preferred is None or preferred.data(0) not in {"atom", "bond", "ring"}:
                return False
            if not self._select_structure_item(preferred):
                return False
            item = preferred
            selected = self.canvas.scene().selectedItems()
            atom_ids, bond_ids = self.canvas._selected_ids()
            for bond_id in bond_ids:
                if 0 <= bond_id < len(self.canvas.model.bonds):
                    bond = self.canvas.model.bonds[bond_id]
                    if bond is not None:
                        atom_ids.add(bond.a)
                        atom_ids.add(bond.b)
            selection_items = [
                sel
                for sel in selected
                if sel.data(0) not in {"selection_outline", "note_box", "note_select", "handle"}
            ]
        self._drag_selection = True
        self._selection_atom_ids = set(atom_ids)
        self._selection_items = selection_items
        if self._selection_atom_ids:
            self._drag_bond_ids, self._drag_boundary_bond_ids = self.canvas.bond_sets_for_atoms(
                self._selection_atom_ids
            )
        else:
            self._drag_bond_ids = set()
            self._drag_boundary_bond_ids = set()
        self._start_pos = event.position()
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
        else:
            for item in self._selection_items:
                self.canvas.move_item(item, delta.x(), delta.y(), update_selection=False)
        self.canvas.shift_selection_outlines(delta.x(), delta.y())
        self._total_delta += delta
        self._moved = True

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
        if self._suspended_outline:
            self.canvas.suspend_selection_outline(False)
        if self._moved:
            self.canvas._update_selection_outline()
            if self._selection_atom_ids:
                command = MoveAtomsCommand(
                    atom_ids=set(self._selection_atom_ids),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                    bond_ids=set(self._drag_bond_ids) if self._drag_bond_ids else None,
                    redraw_bond_ids=set(self._drag_boundary_bond_ids) if self._drag_boundary_bond_ids else None,
                )
                self.canvas._push_command(command)
            else:
                command = MoveItemsCommand(
                    items=list(self._selection_items),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
                self.canvas._push_command(command)
        self._drag_selection = False
        self._selection_atom_ids = set()
        self._selection_items = []
        self._drag_bond_ids = set()
        self._drag_boundary_bond_ids = set()
        self._suspended_outline = False
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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def deactivate(self) -> None:
        self._clear_preview_items()
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None

    def _clear_preview_items(self) -> None:
        if not self._preview_items:
            self._preview_signature = None
            return
        for item in self._preview_items:
            try:
                if item.scene() is self.canvas.scene():
                    self.canvas.scene().removeItem(item)
            except RuntimeError:
                pass
        self._preview_items = []
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
        preview_color = QColor(120, 120, 120, 140)
        for item in items:
            if hasattr(item, "pen"):
                pen = item.pen()
                pen.setColor(preview_color)
                item.setPen(pen)
            if hasattr(item, "brush") and item.brush().style() != Qt.BrushStyle.NoBrush:
                brush = item.brush()
                brush.setColor(preview_color)
                item.setBrush(brush)
            item.setOpacity(0.5)
            item.setZValue(4.5)
            self.canvas.scene().addItem(item)
        self._preview_items = items
        self._preview_signature = signature

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        press_pos = self.canvas.scene_pos_from_event(event)
        atom_id = self.canvas.find_atom_near(
            press_pos.x(),
            press_pos.y(),
            self.canvas.renderer.style.bond_length_px * 0.35,
        )
        if atom_id is None:
            item = self.canvas.item_at_event(event)
            if item is not None and item.data(0) == "bond":
                bond_id = item.data(1)
                if isinstance(bond_id, int):
                    if self.canvas.active_bond_style in {"wedge", "hash"}:
                        self.canvas.apply_bond_style(bond_id, self.canvas.active_bond_style, 1)
                    elif self.canvas.active_bond_style in {"bold", "bold_in", "bold_out"}:
                        bond = self.canvas.model.bonds[bond_id]
                        if bond is not None:
                            if bond.style in {"bold_in", "bold"}:
                                next_style = "bold_out"
                            elif bond.style == "bold_out":
                                next_style = "bold_in"
                            else:
                                next_style = "bold_in"
                            self.canvas.apply_bond_style(bond_id, next_style, bond.order)
                    else:
                        self.canvas.cycle_bond_style(bond_id)
                    return True
            if self.canvas.hover_bond_id is not None:
                if self.canvas.active_bond_style in {"wedge", "hash"}:
                    self.canvas.apply_bond_style(self.canvas.hover_bond_id, self.canvas.active_bond_style, 1)
                elif self.canvas.active_bond_style in {"bold", "bold_in", "bold_out"}:
                    bond = self.canvas.model.bonds[self.canvas.hover_bond_id]
                    if bond is not None:
                        if bond.style in {"bold_in", "bold"}:
                            next_style = "bold_out"
                        elif bond.style == "bold_out":
                            next_style = "bold_in"
                        else:
                            next_style = "bold_in"
                        self.canvas.apply_bond_style(self.canvas.hover_bond_id, next_style, bond.order)
                else:
                    self.canvas.cycle_bond_style(self.canvas.hover_bond_id)
                return True
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
        if atom_id is None:
            bond_id = self.canvas._find_bond_near(pos, self.canvas.renderer.style.bond_length_px * 0.2)
            if bond_id is None:
                return pos
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                return pos
            a = self.canvas.model.atoms[bond.a]
            b = self.canvas.model.atoms[bond.b]
            da = (pos.x() - a.x) ** 2 + (pos.y() - a.y) ** 2
            db = (pos.x() - b.x) ** 2 + (pos.y() - b.y) ** 2
            target = a if da <= db else b
            return QPointF(target.x, target.y)
        if ignore_start and atom_id == self._start_atom_id:
            return pos
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return pos
        if not ignore_start:
            self._start_atom_id = atom_id
        return QPointF(atom.x, atom.y)

    def _snap_endpoint(self, start, end):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return end
        angle = math.degrees(math.atan2(dy, dx))
        step = self.canvas.snap_angle_step or 30
        snap_angle = round(angle / step) * step
        bond_len = self.canvas.renderer.style.bond_length_px
        rad = math.radians(snap_angle)
        return start + QPointF(math.cos(rad) * bond_len, math.sin(rad) * bond_len)


class TextTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("text")
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        pos = self.canvas.scene_pos_from_event(event)
        pick_radius = self.canvas.renderer.style.bond_length_px * 0.9
        bond_pick_radius = self.canvas.renderer.style.bond_length_px * 0.6
        atom_id = None
        if self.canvas.hover_atom_id is not None:
            atom_id = self.canvas.hover_atom_id
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is not None:
                pos = QPointF(atom.x, atom.y)
        item = self.canvas.item_at_event(event)
        if atom_id is None and item is not None and item.data(0) == "atom":
            data_id = item.data(1)
            if isinstance(data_id, int) and data_id in self.canvas.model.atoms:
                atom_id = data_id
                atom = self.canvas.model.atoms[atom_id]
                pos = QPointF(atom.x, atom.y)
        if atom_id is None and self.canvas.hover_bond_id is not None:
            bond = self.canvas.model.bonds[self.canvas.hover_bond_id]
            if bond is not None:
                a = self.canvas.model.atoms.get(bond.a)
                b = self.canvas.model.atoms.get(bond.b)
                if a is not None and b is not None:
                    da = (pos.x() - a.x) ** 2 + (pos.y() - a.y) ** 2
                    db = (pos.x() - b.x) ** 2 + (pos.y() - b.y) ** 2
                    atom_id = bond.a if da <= db else bond.b
                    atom = self.canvas.model.atoms[atom_id]
                    pos = QPointF(atom.x, atom.y)
        if atom_id is None:
            bond_id = self.canvas._find_bond_near(pos, bond_pick_radius)
            if bond_id is not None:
                bond = self.canvas.model.bonds[bond_id]
                if bond is not None:
                    a = self.canvas.model.atoms.get(bond.a)
                    b = self.canvas.model.atoms.get(bond.b)
                    if a is not None and b is not None:
                        da = (pos.x() - a.x) ** 2 + (pos.y() - a.y) ** 2
                        db = (pos.x() - b.x) ** 2 + (pos.y() - b.y) ** 2
                        atom_id = bond.a if da <= db else bond.b
                        atom = self.canvas.model.atoms[atom_id]
                        pos = QPointF(atom.x, atom.y)
        if atom_id is None:
            atom_id = self.canvas.find_atom_near(pos.x(), pos.y(), pick_radius)
        text = self._normalized_symbol(self.canvas.get_atom_symbol())
        if not text:
            initial = self.canvas.model.atoms[atom_id].element if atom_id is not None else ""
            text, ok = QInputDialog.getText(
                self.canvas,
                "Atom Label",
                "Enter atom symbol:",
                text=initial,
            )
            if not ok:
                return True
            text = self._normalized_symbol(text)
        created_atom = False
        if atom_id is None:
            if not text:
                return True
            before_smiles_input = self.canvas.last_smiles_input
            before_next_atom_id = self.canvas.model.next_atom_id
            atom_id = self.canvas.add_atom(text, pos.x(), pos.y())
            created_atom = True
        if created_atom:
            self.canvas.add_or_update_atom_label(atom_id, text, show_carbon=True, record=False)
            atom_state = self.canvas._atom_state_dict(atom_id)
            command = AddAtomsCommand(
                atom_states={atom_id: atom_state},
                before_next_atom_id=before_next_atom_id,
                after_next_atom_id=self.canvas.model.next_atom_id,
                before_smiles_input=before_smiles_input,
                after_smiles_input=self.canvas.last_smiles_input,
            )
            self.canvas._push_command(command)
        else:
            self.canvas.add_or_update_atom_label(atom_id, text, show_carbon=True)
        return True

    @staticmethod
    def _normalized_symbol(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text.isalpha() and len(text) <= 2:
            if len(text) == 1:
                return text.upper()
            return text[0].upper() + text[1:].lower()
        return text


class BenzeneTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("benzene")
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)
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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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


class MoveTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("move")
        self.canvas = canvas
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._drag_selection = False
        self._selection_atom_ids: set[int] = set()
        self._drag_bond_ids: set[int] = set()
        self._drag_boundary_bond_ids: set[int] = set()
        self._suspended_outline = False
        self._drag_interval = 1.0 / 60.0
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        selected = self.canvas.scene().selectedItems()
        if selected:
            atom_ids, bond_ids = self.canvas._selected_ids()
            for bond_id in bond_ids:
                if 0 <= bond_id < len(self.canvas.model.bonds):
                    bond = self.canvas.model.bonds[bond_id]
                    if bond is not None:
                        atom_ids.add(bond.a)
                        atom_ids.add(bond.b)
            if atom_ids:
                self._drag_selection = True
                self._selection_atom_ids = set(atom_ids)
                self._drag_bond_ids, self._drag_boundary_bond_ids = self.canvas.bond_sets_for_atoms(
                    self._selection_atom_ids
                )
                self._start_pos = event.position()
                self._last_drag_time = 0.0
                self._total_delta = QPointF(0.0, 0.0)
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
        }:
            return True
        self._drag_item = item
        self._start_pos = event.position()
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if self._drag_selection and self._selection_atom_ids:
            if not self._suspended_outline:
                self.canvas.suspend_selection_outline(True)
                self._suspended_outline = True
            self.canvas.move_atoms(
                self._selection_atom_ids,
                delta.x(),
                delta.y(),
                bond_ids=self._drag_bond_ids,
                redraw_bond_ids=self._drag_boundary_bond_ids,
                update_selection=False,
            )
            self.canvas.shift_selection_outlines(delta.x(), delta.y())
            self._moved = True
            self._total_delta += delta
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
        if self._suspended_outline:
            self.canvas.suspend_selection_outline(False)
        if self._moved:
            self.canvas._update_selection_outline()
            if self._drag_selection and self._selection_atom_ids:
                command = MoveAtomsCommand(
                    atom_ids=set(self._selection_atom_ids),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                    bond_ids=set(self._drag_bond_ids) if self._drag_bond_ids else None,
                    redraw_bond_ids=set(self._drag_boundary_bond_ids) if self._drag_boundary_bond_ids else None,
                )
                self.canvas._push_command(command)
            elif self._drag_item is not None:
                command = MoveItemsCommand(
                    items=[self._drag_item],
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
                self.canvas._push_command(command)
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._drag_selection = False
        self._selection_atom_ids = set()
        self._drag_bond_ids = set()
        self._drag_boundary_bond_ids = set()
        self._suspended_outline = False
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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
            self._commands.insert(
                0,
                SetSmilesInputCommand(
                    before_value=self._before_smiles_input,
                    after_value=self.canvas.last_smiles_input,
                ),
            )
            if len(self._commands) == 1:
                self.canvas._push_command(self._commands[0])
            else:
                self.canvas._push_command(CompositeCommand(self._commands))
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
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                command = self.canvas.delete_atom(atom_id, record=False)
                if command is not None:
                    self._commands.append(command)
                self._changed = True
        elif kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                command = self.canvas.delete_bond(bond_id, record=False)
                if command is not None:
                    self._commands.append(command)
                self._changed = True
        elif kind == "ring":
            command = self.canvas.delete_ring(item, record=False)
            if command is not None:
                self._commands.append(command)
            self._changed = True
        elif kind in {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "orbital",
            "note",
        }:
            state = self.canvas.scene_item_state(item)
            self.canvas.remove_scene_item(item)
            command = DeleteSceneItemsCommand(item_states=[state], items=[item])
            self._commands.append(command)
            self._changed = True
        else:
            state = self.canvas.scene_item_state(item)
            self.canvas.remove_scene_item(item)
            command = DeleteSceneItemsCommand(item_states=[state], items=[item])
            self._commands.append(command)
            self._changed = True


class ArrowTool(Tool):
    def __init__(self, canvas, mode: str = "auto") -> None:
        super().__init__("arrow")
        self.canvas = canvas
        self.mode = mode
        self._start_pos = None
        self._preview_item = None

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._start_pos = self.canvas.scene_pos_from_event(event)
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        current_pos = self.canvas.scene_pos_from_event(event)
        if self._preview_item is not None:
            self.canvas.scene().removeItem(self._preview_item)
        arrow_type = self.mode if self.mode != "auto" else self.canvas.active_arrow_type
        self._preview_item = self.canvas.preview_arrow(self._start_pos, current_pos, arrow_type)
        return True

    def on_mouse_release(self, event) -> bool:
        if self._start_pos is None:
            return False
        end_pos = self.canvas.scene_pos_from_event(event)
        if self._preview_item is not None:
            self.canvas.scene().removeItem(self._preview_item)
            self._preview_item = None
        arrow_type = self.mode if self.mode != "auto" else self.canvas.active_arrow_type
        self.canvas.add_arrow(self._start_pos, end_pos, arrow_type)
        self._start_pos = None
        return True


class OrbitalTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("orbital")
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is None:
            self.canvas.clear_handles()
            return True
        if item.data(0) == "handle":
            self._active_handle = item
            return True
        kind = item.data(0)
        if kind == "orbital":
            self.canvas.show_orbital_handles(item)
        elif kind in {"curved_single", "curved_double"}:
            self.canvas.show_curved_handles(item)
        else:
            self.canvas.clear_handles()
        return True


class MarkTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("mark")
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
        self.canvas.clear_handles()
        press_pos = self.canvas.scene_pos_from_event(event)
        if not self.canvas.selection_hit_test(press_pos):
            item = self.canvas.item_at_event(event)
            if item is None or not self.canvas.select_structure_for_item(item):
                return False
        axis_hint = self.canvas.bond_id_from_event(event)
        self._rotating = self.canvas.begin_selection_3d_rotation(axis_hint=axis_hint, press_pos=press_pos)
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
        delta_x = delta.x()
        delta_y = delta.y()
        if self.canvas._rotation_mode == "rigid" and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._axis_lock is None:
                if abs(delta_x) < 1e-9 and abs(delta_y) < 1e-9:
                    return True
                self._axis_lock = "x" if abs(delta_x) >= abs(delta_y) else "y"
            if self._axis_lock == "x":
                delta_y = 0.0
            else:
                delta_x = 0.0
        else:
            self._axis_lock = None
        self.canvas.update_selection_3d_rotation(delta_x, delta_y)
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
            "orbital": OrbitalTool(canvas),
            "perspective": PerspectiveTool(canvas),
        }
        self.active: Optional[Tool] = None

    def set_active(self, name: str) -> None:
        if self.active:
            self.active.deactivate()
        self.active = self.tools.get(name, self.tools["select"])
        self.active.activate()
