from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.history_commands import MoveItemsCommand as MoveItemsCommand


class HistoryCommand:
    def undo(self, canvas) -> None:
        raise NotImplementedError

    def redo(self, canvas) -> None:
        raise NotImplementedError


def _history_canvas_port(name: str):
    return getattr(import_module("ui.history_canvas_access"), name)


def _set_last_smiles_input(canvas, value: str | None) -> None:
    _history_canvas_port("set_last_smiles_input_for_history")(canvas, value)


@dataclass
class CompositeCommand(HistoryCommand):
    commands: list[HistoryCommand] = field(default_factory=list)

    def undo(self, canvas) -> None:
        for command in reversed(self.commands):
            command.undo(canvas)

    def redo(self, canvas) -> None:
        for command in self.commands:
            command.redo(canvas)


@dataclass
class MoveAtomsCommand(HistoryCommand):
    atom_ids: set[int]
    dx: float
    dy: float
    bond_ids: set[int] | None = None
    redraw_bond_ids: set[int] | None = None

    def undo(self, canvas) -> None:
        _history_canvas_port("move_atoms_for_history")(
            canvas,
            self.atom_ids,
            -self.dx,
            -self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )

    def redo(self, canvas) -> None:
        _history_canvas_port("move_atoms_for_history")(
            canvas,
            self.atom_ids,
            self.dx,
            self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )


@dataclass
class SetAtomPositionsCommand(HistoryCommand):
    before_positions: dict[int, tuple[float, float]]
    after_positions: dict[int, tuple[float, float]]
    update_selection: bool = True
    before_coords_3d: dict[int, tuple[float, float, float]] | None = None
    after_coords_3d: dict[int, tuple[float, float, float]] | None = None
    restore_projection_state: bool = False
    before_projection_center_3d: tuple[float, float, float] | None = None
    after_projection_center_3d: tuple[float, float, float] | None = None
    before_projection_anchor_2d: tuple[float, float] | None = None
    after_projection_anchor_2d: tuple[float, float] | None = None

    def _apply(
        self,
        canvas,
        positions: dict[int, tuple[float, float]],
        coords_3d: dict[int, tuple[float, float, float]] | None,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
    ) -> None:
        if self.restore_projection_state:
            _history_canvas_port("restore_projection_state_for_history")(
                canvas,
                projection_center_3d,
                projection_anchor_2d,
            )
        if coords_3d is None:
            _history_canvas_port("set_atom_positions_for_history")(
                canvas,
                positions,
                update_selection=self.update_selection,
            )
            return
        _history_canvas_port("set_atom_positions_for_history")(
            canvas,
            positions,
            update_selection=self.update_selection,
            coords_3d=coords_3d,
        )

    def undo(self, canvas) -> None:
        self._apply(
            canvas,
            self.before_positions,
            self.before_coords_3d,
            self.before_projection_center_3d,
            self.before_projection_anchor_2d,
        )

    def redo(self, canvas) -> None:
        self._apply(
            canvas,
            self.after_positions,
            self.after_coords_3d,
            self.after_projection_center_3d,
            self.after_projection_anchor_2d,
        )


@dataclass
class SetRingPolygonsCommand(HistoryCommand):
    ring_items: list
    before_polygons: list[list[tuple[float, float]]]
    after_polygons: list[list[tuple[float, float]]]

    def undo(self, canvas) -> None:
        _history_canvas_port("set_ring_polygons_for_history")(canvas, self.ring_items, self.before_polygons)

    def redo(self, canvas) -> None:
        _history_canvas_port("set_ring_polygons_for_history")(canvas, self.ring_items, self.after_polygons)


@dataclass
class UpdateBondLengthCommand(HistoryCommand):
    before_length: float
    after_length: float

    def undo(self, canvas) -> None:
        _history_canvas_port("restore_bond_length_for_history")(canvas, self.before_length)

    def redo(self, canvas) -> None:
        _history_canvas_port("restore_bond_length_for_history")(canvas, self.after_length)


@dataclass
class SetSmilesInputCommand(HistoryCommand):
    before_value: str | None
    after_value: str | None

    def undo(self, canvas) -> None:
        _set_last_smiles_input(canvas, self.before_value)

    def redo(self, canvas) -> None:
        _set_last_smiles_input(canvas, self.after_value)


@dataclass
class AddAtomsCommand(HistoryCommand):
    atom_states: dict[int, dict]
    before_next_atom_id: int
    after_next_atom_id: int
    before_smiles_input: str | None = None
    after_smiles_input: str | None = None

    def undo(self, canvas) -> None:
        for atom_id in self.atom_states:
            _history_canvas_port("remove_atom_for_history")(canvas, atom_id)
        canvas.model.next_atom_id = self.before_next_atom_id
        _set_last_smiles_input(canvas, self.before_smiles_input)

    def redo(self, canvas) -> None:
        for atom_id, state in self.atom_states.items():
            _history_canvas_port("restore_atom_from_state_for_history")(canvas, atom_id, state)
        canvas.model.next_atom_id = self.after_next_atom_id
        _set_last_smiles_input(canvas, self.after_smiles_input)


@dataclass
class DeleteAtomsCommand(HistoryCommand):
    atom_states: dict[int, dict]
    mark_states: list[dict] = field(default_factory=list)
    before_next_atom_id: int = 0
    after_next_atom_id: int = 0
    before_smiles_input: str | None = None
    after_smiles_input: str | None = None
    remove_marks: bool = True

    def undo(self, canvas) -> None:
        for atom_id, state in self.atom_states.items():
            _history_canvas_port("restore_atom_from_state_for_history")(canvas, atom_id, state)
        if self.remove_marks:
            for mark_state in self.mark_states:
                _history_canvas_port("restore_mark_from_state_for_history")(canvas, mark_state)
        canvas.model.next_atom_id = self.before_next_atom_id
        _set_last_smiles_input(canvas, self.before_smiles_input)

    def redo(self, canvas) -> None:
        for atom_id in self.atom_states:
            _history_canvas_port("remove_atom_for_history")(canvas, atom_id, remove_marks=self.remove_marks)
        canvas.model.next_atom_id = self.after_next_atom_id
        _set_last_smiles_input(canvas, self.after_smiles_input)


@dataclass
class UpdateAtomColorCommand(HistoryCommand):
    atom_id: int
    before_color: str
    after_color: str

    def undo(self, canvas) -> None:
        _history_canvas_port("apply_atom_color_for_history")(canvas, self.atom_id, self.before_color)

    def redo(self, canvas) -> None:
        _history_canvas_port("apply_atom_color_for_history")(canvas, self.atom_id, self.after_color)


@dataclass
class AddBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    previous_bond_count: int
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        _history_canvas_port("remove_bond_for_history")(canvas, self.bond_id)
        _history_canvas_port("trim_bonds_for_history")(canvas, self.previous_bond_count)
        _set_last_smiles_input(canvas, self.before_smiles_input)

    def redo(self, canvas) -> None:
        _history_canvas_port("restore_bond_from_state_for_history")(canvas, self.bond_id, self.bond_state)
        _set_last_smiles_input(canvas, self.after_smiles_input)


@dataclass
class DeleteBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        _history_canvas_port("restore_bond_from_state_for_history")(canvas, self.bond_id, self.bond_state)
        _set_last_smiles_input(canvas, self.before_smiles_input)

    def redo(self, canvas) -> None:
        _history_canvas_port("remove_bond_for_history")(canvas, self.bond_id)
        _set_last_smiles_input(canvas, self.after_smiles_input)


@dataclass
class UpdateBondCommand(HistoryCommand):
    bond_id: int
    before_state: dict
    after_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        _history_canvas_port("restore_bond_from_state_for_history")(canvas, self.bond_id, self.before_state)
        _set_last_smiles_input(canvas, self.before_smiles_input)

    def redo(self, canvas) -> None:
        _history_canvas_port("restore_bond_from_state_for_history")(canvas, self.bond_id, self.after_state)
        _set_last_smiles_input(canvas, self.after_smiles_input)


def __getattr__(name: str):
    if name == "MoveItemsCommand":
        from ui.history_commands import MoveItemsCommand

        return MoveItemsCommand
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AddAtomsCommand",
    "AddBondCommand",
    "CompositeCommand",
    "DeleteAtomsCommand",
    "DeleteBondCommand",
    "HistoryCommand",
    "MoveAtomsCommand",
    "MoveItemsCommand",
    "SetAtomPositionsCommand",
    "SetRingPolygonsCommand",
    "SetSmilesInputCommand",
    "UpdateAtomColorCommand",
    "UpdateBondCommand",
    "UpdateBondLengthCommand",
]
