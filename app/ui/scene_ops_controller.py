from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QMimeData, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsItem, QGraphicsPolygonItem, QGraphicsTextItem

from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    DeleteSceneItemsCommand,
    HistoryCommand,
    SetAtomPositionsCommand,
    UpdateSceneItemCommand,
)
from ui.bond_style_logic import cycle_plain_bond_style
from ui.scene_item_state import ARROW_KINDS

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SceneOpsController:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def _rebuild_bond_graphics(self, bond_id: int, *, redraw_connected: bool) -> None:
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        for item in self.canvas.bond_items.get(bond_id, []):
            self.canvas.scene().removeItem(item)
        self.canvas.bond_items[bond_id] = []
        self.canvas._add_bond_graphics(bond_id)
        if redraw_connected:
            self.canvas._redraw_connected_bonds(bond.a, skip_bond_id=bond_id)
            self.canvas._redraw_connected_bonds(bond.b, skip_bond_id=bond_id)

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        if not isinstance(atom_id, int):
            return None
        bonds_to_remove = [
            i for i, bond in enumerate(self.canvas.model.bonds)
            if bond is not None and (bond.a == atom_id or bond.b == atom_id)
        ]
        before_smiles_input = self.canvas.last_smiles_input
        self.canvas.last_smiles_input = None
        mark_states = [self.canvas._mark_state_dict(mark) for mark in self.canvas._marks_by_atom.get(atom_id, [])]
        atom_state = self.canvas._atom_state_dict(atom_id)
        commands: list[HistoryCommand] = []
        for bond_id in sorted(bonds_to_remove, reverse=True):
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            bond_state = self.canvas._bond_state_dict(bond)
            self.canvas._remove_bond_by_id(bond_id)
            self.canvas._redraw_connected_bonds(bond.a)
            self.canvas._redraw_connected_bonds(bond.b)
            commands.append(
                DeleteBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=self.canvas.last_smiles_input,
                )
            )
        before_next_atom_id = self.canvas.model.next_atom_id
        self.canvas._remove_atom_only(atom_id)
        commands.append(
            DeleteAtomsCommand(
                atom_states={atom_id: atom_state},
                mark_states=mark_states,
                before_next_atom_id=before_next_atom_id,
                after_next_atom_id=self.canvas.model.next_atom_id,
                before_smiles_input=before_smiles_input,
                after_smiles_input=self.canvas.last_smiles_input,
            )
        )
        command: HistoryCommand = commands[0] if len(commands) == 1 else CompositeCommand(commands)
        if record:
            self.canvas._push_command(command)
        return command

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        before_smiles_input = self.canvas.last_smiles_input
        bond_state = self.canvas._bond_state_dict(bond)
        self.canvas.last_smiles_input = None
        self.canvas._remove_bond_by_id(bond_id)
        self.canvas._redraw_connected_bonds(bond.a)
        self.canvas._redraw_connected_bonds(bond.b)
        command = DeleteBondCommand(
            bond_id=bond_id,
            bond_state=bond_state,
            before_smiles_input=before_smiles_input,
            after_smiles_input=self.canvas.last_smiles_input,
        )
        if record:
            self.canvas._push_command(command)
        return command

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        state = self.canvas._ring_state_dict(item)
        command = DeleteSceneItemsCommand(item_states=[state], items=[item])
        self.canvas.remove_scene_item(item)
        if record:
            self.canvas._push_command(command)
        return command

    def delete_selected_items(self) -> bool:
        items = self.canvas.scene().selectedItems()
        if not items:
            return False
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        ring_items: list[QGraphicsPolygonItem] = []
        note_items: list[QGraphicsTextItem] = []
        mark_items: list[QGraphicsItem] = []
        arrow_items: list[QGraphicsItem] = []
        ts_bracket_items: list[QGraphicsItem] = []
        orbital_items: list[QGraphicsItem] = []
        other_items: list[QGraphicsItem] = []
        for item in items:
            kind = item.data(0)
            if kind == "atom":
                atom_id = item.data(1)
                if isinstance(atom_id, int):
                    atom_ids.add(atom_id)
            elif kind == "bond":
                bond_id = item.data(1)
                if isinstance(bond_id, int):
                    bond_ids.add(bond_id)
            elif kind == "ring":
                if isinstance(item, QGraphicsPolygonItem):
                    ring_items.append(item)
            elif kind == "note":
                if isinstance(item, QGraphicsTextItem):
                    note_items.append(item)
            elif kind == "mark":
                mark_items.append(item)
            elif kind in ARROW_KINDS:
                arrow_items.append(item)
            elif kind == "ts_bracket":
                ts_bracket_items.append(item)
            elif kind == "orbital":
                orbital_items.append(item)
            elif kind in {"handle", "note_box", "note_select"}:
                continue
            else:
                other_items.append(item)

        if (
            len(bond_ids) == 1
            and not atom_ids
            and not ring_items
            and not note_items
            and not mark_items
            and not arrow_items
            and not ts_bracket_items
            and not orbital_items
            and not other_items
        ):
            bond_id = next(iter(bond_ids))
            if 0 <= bond_id < len(self.canvas.model.bonds) and self.canvas.model.bonds[bond_id] is not None:
                self.delete_bond(bond_id, record=True)
                return True

        bonds_to_remove = set(bond_ids)
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a in atom_ids or bond.b in atom_ids:
                bonds_to_remove.add(bond_id)

        filtered_marks = []
        for item in mark_items:
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int) and atom_id in atom_ids:
                continue
            filtered_marks.append(item)
        mark_items = filtered_marks
        mark_states_for_atoms = []
        for atom_id in atom_ids:
            marks = self.canvas._marks_by_atom.get(atom_id, [])
            for mark in marks:
                mark_states_for_atoms.append(self.canvas._mark_state_dict(mark))

        before_smiles_input = self.canvas.last_smiles_input
        if bonds_to_remove or atom_ids:
            self.canvas.last_smiles_input = None
        commands: list[HistoryCommand] = []

        for bond_id in sorted(bonds_to_remove, reverse=True):
            if not (0 <= bond_id < len(self.canvas.model.bonds)):
                continue
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            bond_state = self.canvas._bond_state_dict(bond)
            self.canvas._remove_bond_by_id(bond_id)
            self.canvas._redraw_connected_bonds(bond.a)
            self.canvas._redraw_connected_bonds(bond.b)
            commands.append(
                DeleteBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=self.canvas.last_smiles_input,
                )
            )

        if atom_ids:
            atom_states = {atom_id: self.canvas._atom_state_dict(atom_id) for atom_id in atom_ids}
            before_next_atom_id = self.canvas.model.next_atom_id
            for atom_id in atom_ids:
                self.canvas._remove_atom_only(atom_id)
            commands.append(
                DeleteAtomsCommand(
                    atom_states=atom_states,
                    mark_states=mark_states_for_atoms,
                    before_next_atom_id=before_next_atom_id,
                    after_next_atom_id=self.canvas.model.next_atom_id,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=self.canvas.last_smiles_input,
                )
            )

        scene_items = []
        scene_items.extend(ring_items)
        scene_items.extend(note_items)
        scene_items.extend(mark_items)
        scene_items.extend(arrow_items)
        scene_items.extend(ts_bracket_items)
        scene_items.extend(orbital_items)
        scene_items.extend(other_items)
        if scene_items:
            if ts_bracket_items or orbital_items or arrow_items:
                self.canvas.clear_handles()
            scene_states = [self.canvas.scene_item_state(item) for item in scene_items]
            for item in scene_items:
                self.canvas.remove_scene_item(item)
            commands.append(DeleteSceneItemsCommand(item_states=scene_states, items=scene_items))

        if not commands:
            return False
        if len(commands) == 1:
            self.canvas._push_command(commands[0])
            return True
        self.canvas._push_command(CompositeCommand(commands))
        return True

    def flip_bond_direction(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        if bond.style not in {"wedge", "hash"}:
            return
        before_smiles_input = self.canvas.last_smiles_input
        before_state = self.canvas._bond_state_dict(bond)
        bond.a, bond.b = bond.b, bond.a
        self._rebuild_bond_graphics(bond_id, redraw_connected=True)
        after_state = self.canvas._bond_state_dict(bond)
        self.canvas._record_bond_update(
            bond_id,
            before_state,
            after_state,
            before_smiles_input,
            self.canvas.last_smiles_input,
        )

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        before_smiles_input = self.canvas.last_smiles_input
        before_state = self.canvas._bond_state_dict(bond)
        bond.style = style
        bond.order = order
        self._rebuild_bond_graphics(bond_id, redraw_connected=True)
        after_state = self.canvas._bond_state_dict(bond)
        self.canvas._record_bond_update(
            bond_id,
            before_state,
            after_state,
            before_smiles_input,
            self.canvas.last_smiles_input,
        )

    def cycle_bond_style(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return
        before_smiles_input = self.canvas.last_smiles_input
        before_state = self.canvas._bond_state_dict(bond)
        next_style, next_order = cycle_plain_bond_style(bond.style, bond.order)
        bond.style = next_style
        bond.order = next_order
        self._rebuild_bond_graphics(bond_id, redraw_connected=False)
        after_state = self.canvas._bond_state_dict(bond)
        self.canvas._record_bond_update(
            bond_id,
            before_state,
            after_state,
            before_smiles_input,
            self.canvas.last_smiles_input,
        )

    def _flip_bounds_for_item(self, item) -> QRectF | None:
        kind = item.data(0)
        if kind == "note":
            rect = item.sceneBoundingRect()
            return rect if rect.isValid() else None
        if kind in {"mark", "ts_bracket", "orbital"}:
            rect = item.sceneBoundingRect()
            return rect if rect.isValid() else None
        state = self.canvas.scene_item_state(item)
        if not state:
            return None
        if kind == "ring":
            points = [QPointF(x, y) for x, y in state.get("points", [])]
            return self.canvas._bounds_from_points(points)
        if kind in ARROW_KINDS:
            points = []
            start = state.get("start")
            end = state.get("end")
            control = state.get("control")
            if start is not None:
                points.append(QPointF(*start))
            if end is not None:
                points.append(QPointF(*end))
            if control is not None:
                points.append(QPointF(*control))
            return self.canvas._bounds_from_points(points)
        rect = item.sceneBoundingRect()
        return rect if rect.isValid() else None

    def _flip_center_for_selection(self, atom_ids: set[int], items: list[QGraphicsItem]) -> QPointF | None:
        xs = []
        ys = []
        for atom_id in atom_ids:
            atom = self.canvas.model.atoms.get(atom_id)
            if atom is None:
                continue
            xs.append(atom.x)
            ys.append(atom.y)
        for item in items:
            kind = item.data(0)
            if kind in {"atom", "bond"}:
                continue
            bounds = self._flip_bounds_for_item(item)
            if bounds is None:
                continue
            xs.extend([bounds.left(), bounds.right()])
            ys.extend([bounds.top(), bounds.bottom()])
        if not xs or not ys:
            return None
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

    def _flip_scene_item_state(
        self,
        item,
        before_state: dict,
        center: QPointF,
        horizontal: bool,
        transformed_atom_positions: dict[int, tuple[float, float]],
    ) -> dict:
        if not before_state:
            return {}
        kind = before_state.get("kind")
        after_state = dict(before_state)
        if kind == "ring":
            after_state["points"] = [
                (flipped.x(), flipped.y())
                for flipped in (
                    self.canvas._flip_point(QPointF(x, y), center, horizontal)
                    for x, y in before_state.get("points", [])
                )
            ]
            return after_state
        if kind == "note":
            rect = item.sceneBoundingRect()
            if rect.isValid():
                if horizontal:
                    after_state["x"] = center.x() - (rect.right() - center.x())
                    after_state["y"] = before_state.get("y", 0.0)
                else:
                    after_state["x"] = before_state.get("x", 0.0)
                    after_state["y"] = center.y() - (rect.bottom() - center.y())
            else:
                flipped = self.canvas._flip_point(
                    QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
                    center,
                    horizontal,
                )
                after_state["x"] = flipped.x()
                after_state["y"] = flipped.y()
            return after_state
        if kind == "mark":
            flipped = self.canvas._flip_point(
                QPointF(before_state.get("x", 0.0), before_state.get("y", 0.0)),
                center,
                horizontal,
            )
            after_state["x"] = flipped.x()
            after_state["y"] = flipped.y()
            atom_id = before_state.get("atom_id")
            if isinstance(atom_id, int):
                atom_x = atom_y = None
                if atom_id in transformed_atom_positions:
                    atom_x, atom_y = transformed_atom_positions[atom_id]
                else:
                    atom = self.canvas.model.atoms.get(atom_id)
                    if atom is not None:
                        atom_x = atom.x
                        atom_y = atom.y
                if atom_x is not None and atom_y is not None:
                    after_state["dx"] = flipped.x() - atom_x
                    after_state["dy"] = flipped.y() - atom_y
            return after_state
        if kind == "orbital":
            center_state = before_state.get("center")
            if center_state is not None:
                flipped = self.canvas._flip_point(QPointF(*center_state), center, horizontal)
                after_state["center"] = (flipped.x(), flipped.y())
            rotation = float(before_state.get("rotation", 0.0))
            after_state["rotation"] = 180.0 - rotation if horizontal else -rotation
            return after_state
        if kind == "ts_bracket":
            rect = self.canvas._ts_bracket_rect_from_state(before_state)
            if rect is None:
                return after_state
            flipped_rect = QRectF(
                self.canvas._flip_point(rect.topLeft(), center, horizontal),
                self.canvas._flip_point(rect.bottomRight(), center, horizontal),
            ).normalized()
            after_state["left"] = flipped_rect.left()
            after_state["top"] = flipped_rect.top()
            after_state["right"] = flipped_rect.right()
            after_state["bottom"] = flipped_rect.bottom()
            return after_state
        if kind in ARROW_KINDS:
            for key in ("start", "end", "control"):
                point = before_state.get(key)
                if point is None:
                    continue
                flipped = self.canvas._flip_point(QPointF(*point), center, horizontal)
                after_state[key] = (flipped.x(), flipped.y())
            return after_state
        return {}

    def _selected_atom_components_for_transform(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        component_key = (frozenset(atom_ids), self.canvas._graph_version)
        if component_key != self.canvas._selection_component_cache_signature:
            self.canvas._selection_component_cache_signature = component_key
            self.canvas._selection_component_cache = self.canvas._connected_components(atom_ids)
        return [set(component) for component in self.canvas._selection_component_cache]

    def _center_for_flip_group(self, atom_ids: set[int], items: list[QGraphicsItem]) -> QPointF | None:
        if atom_ids:
            return self.canvas._bounding_box_center_for_atoms(atom_ids)
        return self._flip_center_for_selection(set(), items)

    def flip_selected_items(self, horizontal: bool) -> None:
        items = self.canvas._selected_items_for_transform()
        atom_ids = self.canvas._selected_atom_ids_for_transform()
        if not atom_ids and not items:
            return

        commands: list[HistoryCommand] = []
        atom_components = self._selected_atom_components_for_transform(atom_ids)
        component_by_atom = {
            atom_id: index
            for index, component in enumerate(atom_components)
            for atom_id in component
        }
        group_items: list[list[QGraphicsItem]] = [[] for _ in atom_components]
        group_seen: list[set[QGraphicsItem]] = [set() for _ in atom_components]
        standalone_items: list[QGraphicsItem] = []
        standalone_seen: set[QGraphicsItem] = set()

        def assign_to_component(index: int, item: QGraphicsItem) -> None:
            if item in group_seen[index]:
                return
            group_seen[index].add(item)
            group_items[index].append(item)

        def assign_standalone(item: QGraphicsItem) -> None:
            if item in standalone_seen:
                return
            standalone_seen.add(item)
            standalone_items.append(item)

        for index, component in enumerate(atom_components):
            for atom_id in component:
                for mark in self.canvas._marks_by_atom.get(atom_id, []):
                    assign_to_component(index, mark)

        for item in items:
            kind = item.data(0)
            if kind in {"atom", "bond"}:
                continue
            if kind == "ring":
                ring_atom_ids = item.data(2)
                if isinstance(ring_atom_ids, list):
                    for atom_id in ring_atom_ids:
                        component_index = component_by_atom.get(atom_id)
                        if component_index is not None:
                            assign_to_component(component_index, item)
                            break
                    else:
                        assign_standalone(item)
                    continue
            if kind == "mark":
                data = item.data(1) or {}
                atom_id = data.get("atom_id")
                component_index = component_by_atom.get(atom_id) if isinstance(atom_id, int) else None
                if component_index is not None:
                    assign_to_component(component_index, item)
                else:
                    assign_standalone(item)
                continue
            assign_standalone(item)

        for component, component_items in zip(atom_components, group_items):
            center = self._center_for_flip_group(component, component_items)
            if center is None:
                continue
            before_positions = {}
            after_positions = {}
            transformed_atom_positions: dict[int, tuple[float, float]] = {}
            before_item_states = [(item, self.canvas.scene_item_state(item)) for item in component_items]
            for atom_id in component:
                atom = self.canvas.model.atoms.get(atom_id)
                if atom is None:
                    continue
                before_positions[atom_id] = (atom.x, atom.y)
                flipped = self.canvas._flip_point(QPointF(atom.x, atom.y), center, horizontal)
                after_positions[atom_id] = (flipped.x(), flipped.y())
                transformed_atom_positions[atom_id] = (flipped.x(), flipped.y())
            if before_positions and before_positions != after_positions:
                self.canvas.set_atom_positions(after_positions, update_selection=False)
                commands.append(
                    SetAtomPositionsCommand(
                        before_positions=before_positions,
                        after_positions=after_positions,
                        update_selection=True,
                    )
                )
            for item, before_state in before_item_states:
                after_state = self._flip_scene_item_state(
                    item,
                    before_state,
                    center,
                    horizontal,
                    transformed_atom_positions,
                )
                if not before_state or not after_state or before_state == after_state:
                    continue
                self.canvas.apply_scene_item_state(item, after_state)
                commands.append(UpdateSceneItemCommand(item, before_state, after_state))

        for item in standalone_items:
            center = self._center_for_flip_group(set(), [item])
            if center is None:
                continue
            before_state = self.canvas.scene_item_state(item)
            after_state = self._flip_scene_item_state(
                item,
                before_state,
                center,
                horizontal,
                {},
            )
            if not before_state or not after_state or before_state == after_state:
                continue
            self.canvas.apply_scene_item_state(item, after_state)
            commands.append(UpdateSceneItemCommand(item, before_state, after_state))

        if not commands:
            return
        self.canvas._update_selection_outline()
        if len(commands) == 1:
            self.canvas._push_command(commands[0])
            return
        self.canvas._push_command(CompositeCommand(commands))

    def _selection_payload_for_clipboard(self) -> dict | None:
        selected_items = self.canvas._selected_items_for_transform()
        explicit_atom_ids, bond_ids = self.canvas._selected_ids()
        atom_ids = set(explicit_atom_ids)
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.canvas.model.bonds)):
                continue
            bond = self.canvas.model.bonds[bond_id]
            if bond is None:
                continue
            atom_ids.add(bond.a)
            atom_ids.add(bond.b)

        atoms: list[dict] = []
        for atom_id in sorted(atom_ids):
            atom_state = self.canvas._atom_state_dict(atom_id)
            if not atom_state:
                continue
            atoms.append({"id": atom_id, **atom_state})

        bonds: list[dict] = []
        if atom_ids:
            for bond in self.canvas.model.bonds:
                if bond is None or bond.a not in atom_ids or bond.b not in atom_ids:
                    continue
                bonds.append(self.canvas._bond_state_dict(bond))

        rings: list[dict] = []
        for ring_item in self.canvas.ring_items:
            try:
                if ring_item.scene() is not self.canvas.scene():
                    continue
            except RuntimeError:
                continue
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list) or not ring_atom_ids:
                continue
            if not all(isinstance(atom_id, int) and atom_id in atom_ids for atom_id in ring_atom_ids):
                continue
            ring_state = self.canvas.scene_item_state(ring_item)
            if ring_state:
                rings.append(ring_state)

        marks: list[dict] = []
        seen_mark_items = set()
        for atom_id in sorted(atom_ids):
            for mark_item in list(self.canvas._marks_by_atom.get(atom_id, [])):
                try:
                    if mark_item.scene() is not self.canvas.scene():
                        continue
                except RuntimeError:
                    continue
                if mark_item in seen_mark_items:
                    continue
                mark_state = self.canvas.scene_item_state(mark_item)
                if not mark_state:
                    continue
                seen_mark_items.add(mark_item)
                marks.append(mark_state)
        for item in selected_items:
            if item.data(0) != "mark" or item in seen_mark_items:
                continue
            mark_state = self.canvas.scene_item_state(item)
            if not mark_state:
                continue
            seen_mark_items.add(item)
            marks.append(mark_state)

        scene_item_states: list[dict] = []
        for item in selected_items:
            kind = item.data(0)
            if kind in {"atom", "bond", "ring", "mark"}:
                continue
            state = self.canvas.scene_item_state(item)
            if state:
                scene_item_states.append(state)

        if not atoms and not marks and not rings and not scene_item_states:
            return None
        return {
            "format": "lightdraw-selection",
            "version": self.canvas.CLIPBOARD_SELECTION_VERSION,
            "atoms": atoms,
            "bonds": bonds,
            "rings": rings,
            "marks": marks,
            "scene_items": scene_item_states,
        }

    def _clipboard_selection_payload(self) -> tuple[dict | None, str | None]:
        payload_candidates: list[str] = []
        mime_data = QApplication.clipboard().mimeData()
        if mime_data is not None and mime_data.hasFormat(self.canvas.CLIPBOARD_SELECTION_MIME):
            try:
                payload_candidates.append(bytes(mime_data.data(self.canvas.CLIPBOARD_SELECTION_MIME)).decode("utf-8"))
            except UnicodeDecodeError:
                pass
        if (
            self.canvas._clipboard_selection_payload_json
            and mime_data is not None
            and mime_data.hasImage()
            and not mime_data.hasText()
            and self.canvas._clipboard_selection_payload_json not in payload_candidates
        ):
            payload_candidates.append(self.canvas._clipboard_selection_payload_json)
        for payload_json in payload_candidates:
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("format") != "lightdraw-selection":
                continue
            if payload.get("version") != self.canvas.CLIPBOARD_SELECTION_VERSION:
                continue
            return payload, payload_json
        return None, None

    def _select_pasted_content(self, atom_ids: set[int], scene_items: list[QGraphicsItem]) -> None:
        self.canvas.scene().blockSignals(True)
        try:
            self.canvas.scene().clearSelection()
        finally:
            self.canvas.scene().blockSignals(False)
        self.canvas.clear_note_selection()
        for atom_id in atom_ids:
            atom_item = self.canvas._atom_item_for_id(atom_id)
            if atom_item is not None:
                atom_item.setSelected(True)
        for item in scene_items:
            if item is None:
                continue
            if item.data(0) == "note" and isinstance(item, QGraphicsTextItem):
                self.canvas.select_note(item, additive=True)
            item.setSelected(True)
        self.canvas._update_selection_outline()

    @staticmethod
    def _copy_bounds_for_items(items: list[QGraphicsItem]) -> QRectF | None:
        bounds = None
        for item in items:
            rect = item.sceneBoundingRect()
            if not rect.isValid():
                continue
            bounds = rect if bounds is None else bounds.united(rect)
        return bounds

    def copy_selection_to_clipboard(self) -> bool:
        items = self.canvas._selection_items_for_copy()
        if not items:
            return False
        payload = self._selection_payload_for_clipboard()
        bounds = self._copy_bounds_for_items(items)
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return False
        pad = max(2.0, self.canvas.renderer.style.bond_line_width * 2.0)
        source = bounds.adjusted(-pad, -pad, pad, pad)
        items_set = set(items)
        hidden: list[QGraphicsItem] = []
        for item in self.canvas.scene().items(source):
            if item in items_set:
                continue
            if not item.isVisible():
                continue
            item.setVisible(False)
            hidden.append(item)
        try:
            scale = 1.0
            if hasattr(self.canvas, "devicePixelRatioF"):
                scale = max(1.0, float(self.canvas.devicePixelRatioF()))
            width = max(1, int(math.ceil(source.width() * scale)))
            height = max(1, int(math.ceil(source.height() * scale)))
            image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(scale)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            self.canvas.scene().render(painter, QRectF(0, 0, source.width(), source.height()), source)
            painter.end()
        finally:
            for item in hidden:
                item.setVisible(True)
        mime_data = QMimeData()
        mime_data.setImageData(image)
        if payload is not None:
            payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            mime_data.setData(self.canvas.CLIPBOARD_SELECTION_MIME, payload_json.encode("utf-8"))
            self.canvas._clipboard_selection_payload_json = payload_json
            self.canvas._clipboard_paste_source_json = payload_json
            self.canvas._clipboard_paste_count = 0
        else:
            self.canvas._clipboard_selection_payload_json = None
            self.canvas._clipboard_paste_source_json = None
            self.canvas._clipboard_paste_count = 0
        QApplication.clipboard().setMimeData(mime_data)
        return True

    def paste_selection_from_clipboard(self) -> bool:
        payload, payload_json = self._clipboard_selection_payload()
        if payload is None or payload_json is None:
            return False
        if payload_json == self.canvas._clipboard_paste_source_json:
            self.canvas._clipboard_paste_count += 1
        else:
            self.canvas._clipboard_paste_source_json = payload_json
            self.canvas._clipboard_paste_count = 1
        dx, dy = self.canvas._clipboard_paste_offset(
            self.canvas._clipboard_paste_count,
            self.canvas.renderer.style.bond_length_px,
        )

        atoms = payload.get("atoms", [])
        bonds = payload.get("bonds", [])
        rings = payload.get("rings", [])
        marks = payload.get("marks", [])
        scene_items = payload.get("scene_items", [])
        if not any((atoms, bonds, rings, marks, scene_items)):
            return False

        before_next_atom_id = self.canvas.model.next_atom_id
        before_bond_count = len(self.canvas.model.bonds)
        before_smiles_input = self.canvas.last_smiles_input
        atom_id_map: dict[int, int] = {}
        new_atom_ids: set[int] = set()
        added_scene_items: list[QGraphicsItem] = []

        for atom_state in atoms:
            if not isinstance(atom_state, dict):
                continue
            atom_id = atom_state.get("id")
            x = atom_state.get("x")
            y = atom_state.get("y")
            if not isinstance(atom_id, int) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                continue
            element = str(atom_state.get("element", "C"))
            new_atom_id = self.canvas.add_atom(element, float(x) + dx, float(y) + dy)
            atom_id_map[atom_id] = new_atom_id
            new_atom_ids.add(new_atom_id)
            color = atom_state.get("color")
            if isinstance(color, str):
                self.canvas.apply_atom_color(new_atom_id, color)
            if element.upper() == "C" and bool(atom_state.get("explicit_label", False)):
                self.canvas.add_or_update_atom_label(
                    new_atom_id,
                    element,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=True,
                )

        for bond_state in bonds:
            if not isinstance(bond_state, dict):
                continue
            atom_a = bond_state.get("a")
            atom_b = bond_state.get("b")
            if not isinstance(atom_a, int) or not isinstance(atom_b, int):
                continue
            if atom_a not in atom_id_map or atom_b not in atom_id_map:
                continue
            new_bond_id = self.canvas.add_bond(
                atom_id_map[atom_a],
                atom_id_map[atom_b],
                int(bond_state.get("order", 1)),
            )
            self.canvas._restore_bond_from_state(
                new_bond_id,
                {
                    "a": atom_id_map[atom_a],
                    "b": atom_id_map[atom_b],
                    "order": int(bond_state.get("order", 1)),
                    "style": bond_state.get("style", "single"),
                    "color": bond_state.get("color", "#000000"),
                },
            )

        for state_group in (rings, marks, scene_items):
            for state in state_group:
                translated_state = self.canvas._translated_scene_item_state(
                    state,
                    dx=dx,
                    dy=dy,
                    atom_id_map=atom_id_map,
                )
                if not translated_state:
                    continue
                item = self.canvas.create_scene_item_from_state(translated_state)
                if item is not None:
                    added_scene_items.append(item)

        if not atom_id_map and not added_scene_items:
            return False

        self._select_pasted_content(new_atom_ids, added_scene_items)
        self.canvas._record_additions(
            before_next_atom_id,
            before_bond_count,
            before_smiles_input,
            added_scene_items=added_scene_items,
        )
        return True


__all__ = ["SceneOpsController"]
