"""Undo/redo commands over the molecular model: atoms, bonds, positions, ring polygons, bond length, colors and the SMILES input."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import override

from chemvas.core.history import (
    HistoryAtomOperations,
    HistoryBondOperations,
    HistoryColorOperations,
    HistoryCommand,
    HistoryGeometryOperations,
    HistoryPositionOperations,
    HistorySmilesOperations,
    _capture_history_transaction,
    _release_history_transaction,
    _restore_atom_states,
    _restore_atom_states_best_effort,
    _restore_history_transaction,
    _set_last_smiles_input,
)
from chemvas.domain.transactions import (
    run_rollback_step,
)


@dataclass
class MoveAtomsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    atom_ids: set[int]
    dx: float
    dy: float
    bond_ids: set[int] | None = None
    redraw_bond_ids: set[int] | None = None

    @override
    def undo(self, operations: HistoryGeometryOperations) -> None:
        operations.move_atoms_for_history(
            self.atom_ids,
            -self.dx,
            -self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )

    @override
    def redo(self, operations: HistoryGeometryOperations) -> None:
        operations.move_atoms_for_history(
            self.atom_ids,
            self.dx,
            self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )


@dataclass(kw_only=True)
class SetAtomPositionsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
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
        operations: HistoryPositionOperations,
        positions: dict[int, tuple[float, float]],
        coords_3d: dict[int, tuple[float, float, float]] | None,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
    ) -> None:
        if self.restore_projection_state:
            operations.restore_projection_state_for_history(
                projection_center_3d,
                projection_anchor_2d,
            )
        if coords_3d is None:
            operations.set_atom_positions_for_history(
                positions,
                update_selection=self.update_selection,
            )
            return
        operations.set_atom_positions_for_history(
            positions,
            update_selection=self.update_selection,
            coords_3d=coords_3d,
        )

    def _compensate(
        self,
        operations: HistoryPositionOperations,
        positions: dict[int, tuple[float, float]],
        coords_3d: dict[int, tuple[float, float, float]] | None,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
        original_error: BaseException,
    ) -> None:
        port = operations
        if self.restore_projection_state:
            run_rollback_step(
                original_error,
                "restoring the projection state",
                lambda: port.restore_projection_state_for_history(
                    projection_center_3d,
                    projection_anchor_2d,
                ),
            )

        def restore_positions() -> None:
            if coords_3d is None:
                port.set_atom_positions_for_history(
                    positions,
                    update_selection=self.update_selection,
                )
            else:
                port.set_atom_positions_for_history(
                    positions,
                    update_selection=self.update_selection,
                    coords_3d=coords_3d,
                )

        run_rollback_step(
            original_error,
            "restoring atom positions",
            restore_positions,
        )

    @override
    def undo(self, operations: HistoryPositionOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            self._apply(
                operations,
                self.before_positions,
                self.before_coords_3d,
                self.before_projection_center_3d,
                self.before_projection_anchor_2d,
            )
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(
                    operations,
                    self.after_positions,
                    self.after_coords_3d,
                    self.after_projection_center_3d,
                    self.after_projection_anchor_2d,
                    exc,
                )
            raise

    @override
    def redo(self, operations: HistoryPositionOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            self._apply(
                operations,
                self.after_positions,
                self.after_coords_3d,
                self.after_projection_center_3d,
                self.after_projection_anchor_2d,
            )
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(
                    operations,
                    self.before_positions,
                    self.before_coords_3d,
                    self.before_projection_center_3d,
                    self.before_projection_anchor_2d,
                    exc,
                )
            raise


@dataclass
class SetRingPolygonsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    ring_ids: list[int]
    before_polygons: list[list[tuple[float, float]]]
    after_polygons: list[list[tuple[float, float]]]

    def _compensate(
        self,
        operations: HistoryGeometryOperations,
        polygons: list[list[tuple[float, float]]],
        original_error: BaseException,
    ) -> None:
        port = operations

        def restore_one_ring_polygon(
            ring_item, polygon: list[tuple[float, float]]
        ) -> None:
            port.set_ring_polygons_for_history([ring_item], [polygon])

        # Compensate one ring at a time so a persistently broken item cannot
        # prevent later rings from being restored.
        for ring_item, polygon in zip(self.ring_ids, polygons, strict=False):
            run_rollback_step(
                original_error,
                "restoring a ring polygon",
                partial(restore_one_ring_polygon, ring_item, polygon),
            )

    @override
    def undo(self, operations: HistoryGeometryOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.set_ring_polygons_for_history(
                self.ring_ids,
                self.before_polygons,
            )
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(operations, self.after_polygons, exc)
            raise

    @override
    def redo(self, operations: HistoryGeometryOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.set_ring_polygons_for_history(
                self.ring_ids,
                self.after_polygons,
            )
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(operations, self.before_polygons, exc)
            raise


@dataclass
class UpdateBondLengthCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    before_length: float
    after_length: float

    @staticmethod
    def _compensate(
        operations: HistoryGeometryOperations,
        length: float,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring the bond length",
            lambda: operations.restore_bond_length_for_history(
                length,
            ),
        )

    @override
    def undo(self, operations: HistoryGeometryOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_length_for_history(self.before_length)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(operations, self.after_length, exc)
            raise

    @override
    def redo(self, operations: HistoryGeometryOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_length_for_history(self.after_length)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._compensate(operations, self.before_length, exc)
            raise


@dataclass
class SetSmilesInputCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    before_value: str | None
    after_value: str | None

    @override
    def undo(self, operations: HistorySmilesOperations) -> None:
        _set_last_smiles_input(operations, self.before_value)

    @override
    def redo(self, operations: HistorySmilesOperations) -> None:
        _set_last_smiles_input(operations, self.after_value)


@dataclass(kw_only=True)
class AddAtomsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    atom_states: dict[int, dict]
    before_next_atom_id: int
    after_next_atom_id: int
    before_smiles_input: str | None = None
    after_smiles_input: str | None = None
    atom_coords_3d: dict[int, tuple[float, float, float]] | None = None

    def _remove_atoms_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        port = operations

        def remove_one_atom(atom_id: int) -> None:
            port.remove_atom_for_history(atom_id)

        for atom_id in reversed(self.atom_states):
            run_rollback_step(
                original_error,
                "removing an atom this command owns",
                partial(remove_one_atom, atom_id),
            )

    def _restore_atoms_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        # Normalize every atom owned by this command first. A failing port
        # call may have mutated the current atom before raising, so tracking
        # only calls that returned successfully is insufficient.
        self._remove_atoms_best_effort(operations, original_error)
        _restore_atom_states_best_effort(
            operations, original_error, self.atom_states, self.atom_coords_3d
        )
        run_rollback_step(
            original_error,
            "restoring the next atom id",
            lambda: operations.set_next_atom_id_for_history(self.after_next_atom_id),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.after_smiles_input),
        )

    def _restore_absent_state_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        self._remove_atoms_best_effort(operations, original_error)
        run_rollback_step(
            original_error,
            "restoring the next atom id",
            lambda: operations.set_next_atom_id_for_history(self.before_next_atom_id),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.before_smiles_input),
        )

    @override
    def undo(self, operations: HistoryAtomOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            for atom_id in self.atom_states:
                operations.remove_atom_for_history(atom_id)
            operations.set_next_atom_id_for_history(self.before_next_atom_id)
            _set_last_smiles_input(operations, self.before_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_atoms_best_effort(operations, exc)
            raise

    @override
    def redo(self, operations: HistoryAtomOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            _restore_atom_states(operations, self.atom_states, self.atom_coords_3d)
            operations.set_next_atom_id_for_history(self.after_next_atom_id)
            _set_last_smiles_input(operations, self.after_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_absent_state_best_effort(operations, exc)
            raise


@dataclass(kw_only=True)
class DeleteAtomsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    atom_states: dict[int, dict]
    mark_states: list[dict] = field(default_factory=list)
    before_next_atom_id: int = 0
    after_next_atom_id: int = 0
    before_smiles_input: str | None = None
    after_smiles_input: str | None = None
    remove_marks: bool = True
    atom_coords_3d: dict[int, tuple[float, float, float]] | None = None
    restore_projection_state: bool = False
    before_projection_center_3d: tuple[float, float, float] | None = None
    after_projection_center_3d: tuple[float, float, float] | None = None
    before_projection_anchor_2d: tuple[float, float] | None = None
    after_projection_anchor_2d: tuple[float, float] | None = None

    def _remove_atoms_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        port = operations

        def remove_one_atom(atom_id: int) -> None:
            port.remove_atom_for_history(
                atom_id,
                remove_marks=self.remove_marks,
            )

        for atom_id in reversed(self.atom_states):
            run_rollback_step(
                original_error,
                "removing an atom this command owns",
                partial(remove_one_atom, atom_id),
            )

    def _restore_deleted_state_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        self._remove_atoms_best_effort(operations, original_error)
        port = operations
        if self.restore_projection_state:
            run_rollback_step(
                original_error,
                "restoring the projection state",
                lambda: port.restore_projection_state_for_history(
                    self.before_projection_center_3d,
                    self.before_projection_anchor_2d,
                ),
            )
        _restore_atom_states_best_effort(
            operations, original_error, self.atom_states, self.atom_coords_3d
        )
        if self.remove_marks:

            def restore_one_mark_state(mark_state: dict) -> None:
                port.restore_mark_from_state_for_history(mark_state)

            for mark_state in self.mark_states:
                run_rollback_step(
                    original_error,
                    "restoring a mark state",
                    partial(restore_one_mark_state, mark_state),
                )
        run_rollback_step(
            original_error,
            "restoring the next atom id",
            lambda: operations.set_next_atom_id_for_history(self.before_next_atom_id),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.before_smiles_input),
        )

    def _restore_absent_state_best_effort(
        self,
        operations: HistoryAtomOperations,
        original_error: BaseException,
    ) -> None:
        self._remove_atoms_best_effort(operations, original_error)
        if self.restore_projection_state:
            run_rollback_step(
                original_error,
                "restoring the projection state",
                lambda: operations.restore_projection_state_for_history(
                    self.after_projection_center_3d,
                    self.after_projection_anchor_2d,
                ),
            )
        run_rollback_step(
            original_error,
            "restoring the next atom id",
            lambda: operations.set_next_atom_id_for_history(self.after_next_atom_id),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.after_smiles_input),
        )

    @override
    def undo(self, operations: HistoryAtomOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            if self.restore_projection_state:
                operations.restore_projection_state_for_history(
                    self.before_projection_center_3d,
                    self.before_projection_anchor_2d,
                )
            _restore_atom_states(operations, self.atom_states, self.atom_coords_3d)
            if self.remove_marks:
                for mark_state in self.mark_states:
                    operations.restore_mark_from_state_for_history(mark_state)
            operations.set_next_atom_id_for_history(self.before_next_atom_id)
            _set_last_smiles_input(operations, self.before_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_absent_state_best_effort(operations, exc)
            raise

    @override
    def redo(self, operations: HistoryAtomOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            for atom_id in self.atom_states:
                operations.remove_atom_for_history(
                    atom_id,
                    remove_marks=self.remove_marks,
                )
            if self.restore_projection_state:
                operations.restore_projection_state_for_history(
                    self.after_projection_center_3d,
                    self.after_projection_anchor_2d,
                )
            operations.set_next_atom_id_for_history(self.after_next_atom_id)
            _set_last_smiles_input(operations, self.after_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_deleted_state_best_effort(operations, exc)
            raise


@dataclass
class UpdateAtomColorCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    atom_id: int
    before_color: str
    after_color: str

    @staticmethod
    def _compensate(
        operations: HistoryColorOperations,
        atom_id: int,
        color: str,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring the prior atom color",
            lambda: operations.apply_atom_color_for_history(
                atom_id,
                color,
            ),
        )

    @override
    def undo(self, operations: HistoryColorOperations) -> None:
        try:
            operations.apply_atom_color_for_history(
                self.atom_id,
                self.before_color,
            )
        except Exception as exc:
            self._compensate(operations, self.atom_id, self.after_color, exc)
            raise

    @override
    def redo(self, operations: HistoryColorOperations) -> None:
        try:
            operations.apply_atom_color_for_history(
                self.atom_id,
                self.after_color,
            )
        except Exception as exc:
            self._compensate(operations, self.atom_id, self.before_color, exc)
            raise


@dataclass
class AddBondCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    bond_id: int
    bond_state: dict
    previous_bond_count: int
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _restore_added_state_best_effort(
        self,
        operations: HistoryBondOperations,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring the bond state",
            lambda: operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.bond_state,
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.after_smiles_input),
        )

    def _restore_absent_state_best_effort(
        self,
        operations: HistoryBondOperations,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "removing the bond",
            lambda: operations.remove_bond_for_history(
                self.bond_id,
            ),
        )
        run_rollback_step(
            original_error,
            "trimming the bond list",
            lambda: operations.trim_bonds_for_history(
                self.previous_bond_count,
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.before_smiles_input),
        )

    @override
    def undo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.remove_bond_for_history(self.bond_id)
            operations.trim_bonds_for_history(self.previous_bond_count)
            _set_last_smiles_input(operations, self.before_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_added_state_best_effort(operations, exc)
            raise

    @override
    def redo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.bond_state,
            )
            _set_last_smiles_input(operations, self.after_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_absent_state_best_effort(operations, exc)
            raise


@dataclass
class DeleteBondCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    bond_id: int
    bond_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _restore_present_state_best_effort(
        self,
        operations: HistoryBondOperations,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring the bond state",
            lambda: operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.bond_state,
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.before_smiles_input),
        )

    def _restore_absent_state_best_effort(
        self,
        operations: HistoryBondOperations,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "removing the bond",
            lambda: operations.remove_bond_for_history(
                self.bond_id,
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, self.after_smiles_input),
        )

    @override
    def undo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.bond_state,
            )
            _set_last_smiles_input(operations, self.before_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_absent_state_best_effort(operations, exc)
            raise

    @override
    def redo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.remove_bond_for_history(self.bond_id)
            _set_last_smiles_input(operations, self.after_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_present_state_best_effort(operations, exc)
            raise


@dataclass
class UpdateBondCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True
    bond_id: int
    before_state: dict
    after_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _restore_state_best_effort(
        self,
        operations: HistoryBondOperations,
        bond_state: dict,
        smiles_input: str | None,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring the bond state",
            lambda: operations.restore_bond_from_state_for_history(
                self.bond_id,
                bond_state,
            ),
        )
        run_rollback_step(
            original_error,
            "restoring the prior SMILES input",
            lambda: _set_last_smiles_input(operations, smiles_input),
        )

    @override
    def undo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.before_state,
            )
            _set_last_smiles_input(operations, self.before_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_state_best_effort(
                    operations,
                    self.after_state,
                    self.after_smiles_input,
                    exc,
                )
            raise

    @override
    def redo(self, operations: HistoryBondOperations) -> None:
        transaction = _capture_history_transaction(operations)
        try:
            operations.restore_bond_from_state_for_history(
                self.bond_id,
                self.after_state,
            )
            _set_last_smiles_input(operations, self.after_smiles_input)
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            if _restore_history_transaction(
                operations, transaction, exc
            ).fallback_to_inverse:
                self._restore_state_best_effort(
                    operations,
                    self.before_state,
                    self.before_smiles_input,
                    exc,
                )
            raise


__all__ = [
    "AddAtomsCommand",
    "AddBondCommand",
    "DeleteAtomsCommand",
    "DeleteBondCommand",
    "MoveAtomsCommand",
    "SetAtomPositionsCommand",
    "SetRingPolygonsCommand",
    "SetSmilesInputCommand",
    "UpdateAtomColorCommand",
    "UpdateBondCommand",
    "UpdateBondLengthCommand",
]
