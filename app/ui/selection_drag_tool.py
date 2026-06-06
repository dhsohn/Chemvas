from __future__ import annotations

from core.history import CompositeCommand, MoveAtomsCommand
from PyQt6.QtCore import QPointF

from ui.canvas_model_access import bond_for_id
from ui.history_commands import MoveItemsCommand
from ui.move_access import move_atoms_for, move_item_for, shift_selection_outlines_for
from ui.selection_service_access import refresh_selection_outline_for


def independent_selection_items(selection_items: list, atom_ids: set[int]) -> list:
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


def atom_ids_with_bonds(canvas, atom_ids: set[int], bond_ids: set[int]) -> set[int]:
    expanded = set(atom_ids)
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is not None:
            expanded.add(bond.a)
            expanded.add(bond.b)
    return expanded


class SelectionDragMixin:
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
        self._selection_items = independent_selection_items(selection_items, self._selection_atom_ids)
        if self._selection_atom_ids:
            self._drag_bond_ids, self._drag_boundary_bond_ids = self.context.bond_sets_for_atoms(
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
            self.context.suspend_selection_outline(True)
            self._suspended_outline = True
        if self._selection_atom_ids:
            move_atoms_for(
                self.canvas,
                self._selection_atom_ids,
                delta.x(),
                delta.y(),
                bond_ids=self._drag_bond_ids,
                redraw_bond_ids=self._drag_boundary_bond_ids,
                update_selection=False,
            )
        for item in self._selection_items:
            move_item_for(self.canvas, item, delta.x(), delta.y(), update_selection=False)
        shift_selection_outlines_for(self.canvas, delta.x(), delta.y())
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
            self.context.suspend_selection_outline(False)
        if self._moved:
            refresh_selection_outline_for(self.canvas)
            command = self._build_move_command()
            if command is not None:
                self.context.push_history(command)


__all__ = ["SelectionDragMixin", "atom_ids_with_bonds", "independent_selection_items"]
