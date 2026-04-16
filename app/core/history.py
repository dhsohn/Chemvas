from __future__ import annotations

from dataclasses import dataclass, field


class HistoryCommand:
    def undo(self, canvas) -> None:
        raise NotImplementedError

    def redo(self, canvas) -> None:
        raise NotImplementedError


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
        canvas.move_atoms(
            self.atom_ids,
            -self.dx,
            -self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )

    def redo(self, canvas) -> None:
        canvas.move_atoms(
            self.atom_ids,
            self.dx,
            self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )


@dataclass
class MoveItemsCommand(HistoryCommand):
    items: list
    dx: float
    dy: float

    def _apply(self, canvas, dx: float, dy: float) -> None:
        for item in self.items:
            if item is None:
                continue
            try:
                if item.scene() is not canvas.scene():
                    continue
            except RuntimeError:
                continue
            canvas.move_item(item, dx, dy, update_selection=False)
        canvas._update_selection_outline()

    def undo(self, canvas) -> None:
        self._apply(canvas, -self.dx, -self.dy)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.dx, self.dy)


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
            if hasattr(canvas, "_projection_center_3d"):
                canvas._projection_center_3d = projection_center_3d
            if hasattr(canvas, "_projection_anchor_2d"):
                canvas._projection_anchor_2d = projection_anchor_2d
        if coords_3d is None:
            canvas.set_atom_positions(positions, update_selection=self.update_selection)
            return
        try:
            canvas.set_atom_positions(
                positions,
                update_selection=self.update_selection,
                coords_3d=coords_3d,
            )
        except TypeError:
            canvas.set_atom_positions(positions, update_selection=self.update_selection)

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
        canvas.set_ring_polygons(self.ring_items, self.before_polygons)

    def redo(self, canvas) -> None:
        canvas.set_ring_polygons(self.ring_items, self.after_polygons)


@dataclass
class UpdateBondLengthCommand(HistoryCommand):
    before_length: float
    after_length: float

    def undo(self, canvas) -> None:
        canvas.renderer.set_bond_length(self.before_length)
        canvas._rebuild_graphics()
        canvas._mark_spatial_index_dirty()

    def redo(self, canvas) -> None:
        canvas.renderer.set_bond_length(self.after_length)
        canvas._rebuild_graphics()
        canvas._mark_spatial_index_dirty()


@dataclass
class SetSmilesInputCommand(HistoryCommand):
    before_value: str | None
    after_value: str | None

    def undo(self, canvas) -> None:
        canvas.last_smiles_input = self.before_value

    def redo(self, canvas) -> None:
        canvas.last_smiles_input = self.after_value


@dataclass
class AddAtomsCommand(HistoryCommand):
    atom_states: dict[int, dict]
    before_next_atom_id: int
    after_next_atom_id: int
    before_smiles_input: str | None = None
    after_smiles_input: str | None = None

    def undo(self, canvas) -> None:
        for atom_id in self.atom_states:
            canvas._remove_atom_only(atom_id)
        canvas.model.next_atom_id = self.before_next_atom_id
        canvas.last_smiles_input = self.before_smiles_input

    def redo(self, canvas) -> None:
        for atom_id, state in self.atom_states.items():
            canvas._restore_atom_from_state(atom_id, state)
        canvas.model.next_atom_id = self.after_next_atom_id
        canvas.last_smiles_input = self.after_smiles_input


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
            canvas._restore_atom_from_state(atom_id, state)
        if self.remove_marks:
            for mark_state in self.mark_states:
                canvas._restore_mark_from_state(mark_state)
        canvas.model.next_atom_id = self.before_next_atom_id
        canvas.last_smiles_input = self.before_smiles_input

    def redo(self, canvas) -> None:
        for atom_id in self.atom_states:
            canvas._remove_atom_only(atom_id, remove_marks=self.remove_marks)
        canvas.model.next_atom_id = self.after_next_atom_id
        canvas.last_smiles_input = self.after_smiles_input


@dataclass
class UpdateAtomColorCommand(HistoryCommand):
    atom_id: int
    before_color: str
    after_color: str

    def undo(self, canvas) -> None:
        canvas.apply_atom_color(self.atom_id, self.before_color)

    def redo(self, canvas) -> None:
        canvas.apply_atom_color(self.atom_id, self.after_color)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    item: object
    before_state: dict
    after_state: dict

    def undo(self, canvas) -> None:
        canvas.apply_scene_item_state(self.item, self.before_state)

    def redo(self, canvas) -> None:
        canvas.apply_scene_item_state(self.item, self.after_state)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        if not self.items:
            for state in self.item_states:
                self.items.append(canvas.create_scene_item_from_state(state))
            return
        for item in self.items:
            if item is None:
                continue
            canvas.restore_scene_item(item)

    def undo(self, canvas) -> None:
        for item in self.items:
            canvas.remove_scene_item(item)


@dataclass
class DeleteSceneItemsCommand(HistoryCommand):
    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        for item in self.items:
            canvas.remove_scene_item(item)

    def undo(self, canvas) -> None:
        if not self.items:
            for state in self.item_states:
                self.items.append(canvas.create_scene_item_from_state(state))
            return
        for item in self.items:
            if item is None:
                continue
            canvas.restore_scene_item(item)


@dataclass
class ChangeAtomLabelCommand(HistoryCommand):
    atom_id: int
    before_element: str
    after_element: str
    before_explicit_label: bool
    after_explicit_label: bool
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _apply(
        self,
        canvas,
        element: str,
        explicit_label: bool,
        smiles_input: str | None,
    ) -> None:
        canvas.add_or_update_atom_label(
            self.atom_id,
            element,
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=explicit_label,
        )
        canvas.last_smiles_input = smiles_input

    def undo(self, canvas) -> None:
        self._apply(
            canvas,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
        )

    def redo(self, canvas) -> None:
        self._apply(
            canvas,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
        )


@dataclass
class AddBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    previous_bond_count: int
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        canvas._remove_bond_by_id(self.bond_id)
        canvas._trim_bonds_to_length(self.previous_bond_count)
        canvas.last_smiles_input = self.before_smiles_input

    def redo(self, canvas) -> None:
        canvas._restore_bond_from_state(self.bond_id, self.bond_state)
        canvas.last_smiles_input = self.after_smiles_input


@dataclass
class DeleteBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        canvas._restore_bond_from_state(self.bond_id, self.bond_state)
        canvas.last_smiles_input = self.before_smiles_input

    def redo(self, canvas) -> None:
        canvas._remove_bond_by_id(self.bond_id)
        canvas.last_smiles_input = self.after_smiles_input


@dataclass
class UpdateBondCommand(HistoryCommand):
    bond_id: int
    before_state: dict
    after_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def undo(self, canvas) -> None:
        canvas._restore_bond_from_state(self.bond_id, self.before_state)
        canvas.last_smiles_input = self.before_smiles_input

    def redo(self, canvas) -> None:
        canvas._restore_bond_from_state(self.bond_id, self.after_state)
        canvas.last_smiles_input = self.after_smiles_input
