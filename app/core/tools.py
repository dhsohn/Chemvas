from typing import Dict, Optional

import math

from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QGraphicsLineItem, QInputDialog


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

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.RubberBandDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is not None and item.data(0) == "handle":
            self._active_handle = item
            return True
        if item is not None and item.data(0) in {"curved_single", "curved_double"}:
            self.canvas.show_curved_handles(item)
            return False
        self.canvas.clear_handles()
        return False

    def on_mouse_move(self, event) -> bool:
        if self._active_handle is None:
            return False
        self.canvas.update_handle_drag(self._active_handle, self.canvas.scene_pos_from_event(event))
        return True

    def on_mouse_release(self, event) -> bool:
        if self._active_handle is None:
            return False
        self._active_handle = None
        self.canvas._push_history()
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
        self._preview_item: QGraphicsLineItem | None = None

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        item = self.canvas.item_at_event(event)
        if item is not None and item.data(0) == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                if self.canvas.active_bond_style in {"wedge", "hash"}:
                    self.canvas.apply_bond_style(bond_id, self.canvas.active_bond_style, 1)
                else:
                    self.canvas.cycle_bond_style(bond_id)
                return True
        if self.canvas.hover_bond_id is not None:
            if self.canvas.active_bond_style in {"wedge", "hash"}:
                self.canvas.apply_bond_style(self.canvas.hover_bond_id, self.canvas.active_bond_style, 1)
            else:
                self.canvas.cycle_bond_style(self.canvas.hover_bond_id)
            return True
        self._press_scene_pos = self.canvas.scene_pos_from_event(event)
        self._start_pos = self._snap_to_atom(self._press_scene_pos)
        self._preview_item = QGraphicsLineItem()
        self._preview_item.setPen(self.canvas.renderer.bond_pen())
        self.canvas.scene().addItem(self._preview_item)
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None or self._preview_item is None:
            return False
        current_pos = self._snap_to_atom(self.canvas.scene_pos_from_event(event), ignore_start=True)
        snapped = self._snap_endpoint(self._start_pos, current_pos)
        self._preview_item.setLine(QLineF(self._start_pos, snapped))
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
            end_pos = self._default_click_bond_end(self._start_pos)
        if self._preview_item is not None:
            self.canvas.scene().removeItem(self._preview_item)
            self._preview_item = None
        self.canvas.add_bond_from_points(self._start_pos, end_pos)
        self._start_pos = None
        self._start_atom_id = None
        self._press_scene_pos = None
        return True

    def _default_click_bond_end(self, start: QPointF) -> QPointF:
        bond_len = self.canvas.renderer.style.bond_length_px
        angle = 0.0
        if self._start_atom_id is not None:
            atom = self.canvas.model.atoms.get(self._start_atom_id)
            if atom is not None:
                connected = [
                    bond
                    for bond in self.canvas.model.bonds
                    if bond is not None and (bond.a == self._start_atom_id or bond.b == self._start_atom_id)
                ]
                if connected:
                    vectors = []
                    for bond in connected:
                        other_id = bond.b if bond.a == self._start_atom_id else bond.a
                        other = self.canvas.model.atoms.get(other_id)
                        if other is None:
                            continue
                        dx = other.x - atom.x
                        dy = other.y - atom.y
                        length = math.hypot(dx, dy)
                        if length == 0:
                            continue
                        vectors.append((dx / length, dy / length))
                    if len(vectors) >= 2:
                        sx = sum(v[0] for v in vectors)
                        sy = sum(v[1] for v in vectors)
                        if math.hypot(sx, sy) > 1e-6:
                            angle = math.degrees(math.atan2(-sy, -sx))
                        else:
                            angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 90.0
                    elif vectors:
                        angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 120.0
        rad = math.radians(angle)
        return QPointF(start.x() + math.cos(rad) * bond_len, start.y() + math.sin(rad) * bond_len)

    def _snap_to_atom(self, pos, ignore_start: bool = False):
        atom_id = self.canvas.model.find_atom_near(
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
            atom_id = self.canvas.model.find_atom_near(pos.x(), pos.y(), pick_radius)
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
        if atom_id is None:
            if not text:
                return True
            atom_id = self.canvas.model.add_atom(text, pos.x(), pos.y())
        self.canvas.add_or_update_atom_label(atom_id, text)
        return True

    @staticmethod
    def _normalized_symbol(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if len(text) == 1:
            return text.upper()
        return text[0].upper() + text[1:].lower()


class BenzeneTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("benzene")
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

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
                self._start_pos = event.position()
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
        return True

    def on_mouse_move(self, event) -> bool:
        if self._start_pos is None:
            return False
        delta = event.position() - self._start_pos
        if self._drag_selection and self._selection_atom_ids:
            self.canvas.move_atoms(self._selection_atom_ids, delta.x(), delta.y())
        elif self._drag_item is not None:
            self.canvas.move_item(self._drag_item, delta.x(), delta.y())
        self._start_pos = event.position()
        self._moved = True
        return True

    def on_mouse_release(self, event) -> bool:
        if self._moved:
            self.canvas._push_history()
        self._drag_item = None
        self._start_pos = None
        self._moved = False
        self._drag_selection = False
        self._selection_atom_ids = set()
        return True


class DeleteTool(Tool):
    def __init__(self, canvas) -> None:
        super().__init__("delete")
        self.canvas = canvas
        self._erasing = False
        self._changed = False

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._erasing = True
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
        if self._changed:
            self.canvas._push_history()
        self._changed = False
        return True

    def _erase_at_event(self, event) -> None:
        item = self.canvas.item_at_event(event)
        if item is None:
            return
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                self.canvas.delete_atom(atom_id, record=False)
                self._changed = True
        elif kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                self.canvas.delete_bond(bond_id, record=False)
                self._changed = True
        elif kind == "ring":
            self.canvas.delete_ring(item)
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
            self.canvas.scene().removeItem(item)
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

    def activate(self) -> None:
        self.canvas.setDragMode(self.canvas.DragMode.NoDrag)

    def on_mouse_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self.canvas.begin_selection_3d_rotation():
            self._last_pos = event.globalPosition()
            return True
        self._last_pos = None
        return False

    def on_mouse_move(self, event) -> bool:
        if self._last_pos is None:
            return False
        current = event.globalPosition()
        delta = current - self._last_pos
        self.canvas.update_selection_3d_rotation(delta.x(), delta.y())
        self._last_pos = current
        return True

    def on_mouse_release(self, event) -> bool:
        self._last_pos = None
        self.canvas.end_selection_3d_rotation()
        return True


class ToolController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas
        self.tools: Dict[str, Tool] = {
            "select": SelectTool(canvas),
            "bond": BondTool(canvas),
            "text": TextTool(canvas),
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
