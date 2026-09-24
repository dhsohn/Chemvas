from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, override

from chemvas.domain.transactions import (
    RestoreOutcome,
    add_recovery_error_note,
    run_rollback_step,
    validate_restore_outcome,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class HistoryCommand:
    # This command opens/restores its own exact transaction when invoked
    # standalone. History services use this independent protocol to decide
    # whether a failed command can safely retain its stack entry. It is not the
    # same as snapshot coverage: a command can be fully covered by an outer
    # transaction without owning one itself.
    history_transaction_owns_exact_state = False

    # Opt-in coverage protocol for commands whose entire mutable state is part
    # of the UI history transaction snapshot. Unknown commands remain false so
    # an exact sibling cannot make an arbitrary partial failure retryable.
    history_transaction_snapshot_covers_state = False

    def undo(self, operations) -> None:
        raise NotImplementedError

    def redo(self, operations) -> None:
        raise NotImplementedError


class HistorySmilesOperations(Protocol):
    def set_last_smiles_input_for_history(self, value: str | None) -> None: ...


class HistoryPositionOperations(Protocol):
    def restore_projection_state_for_history(
        self,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
    ) -> None: ...

    def set_atom_positions_for_history(
        self,
        positions: dict[int, tuple[float, float]],
        *,
        update_selection: bool = ...,
        coords_3d: dict[int, tuple[float, float, float]] | None = ...,
    ) -> None: ...


class HistoryGeometryOperations(HistoryPositionOperations, Protocol):
    def move_atoms_for_history(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        *,
        bond_ids: set[int] | None = ...,
        redraw_bond_ids: set[int] | None = ...,
        update_selection: bool = ...,
    ) -> None: ...

    def set_ring_polygons_for_history(
        self,
        ring_ids: list[int],
        polygons: list[list[tuple[float, float]]],
    ) -> None: ...

    def restore_bond_length_for_history(self, length_px: float) -> None: ...


class HistoryAtomOperations(
    HistoryPositionOperations, HistorySmilesOperations, Protocol
):
    def set_next_atom_id_for_history(self, atom_id: int) -> None: ...

    def remove_atom_for_history(
        self, atom_id: int, *, remove_marks: bool = ...
    ) -> None: ...

    def restore_atom_from_state_for_history(
        self, atom_id: int, state: dict
    ) -> None: ...

    def restore_mark_from_state_for_history(self, mark_state: dict) -> Any: ...


class HistoryBondOperations(HistorySmilesOperations, Protocol):
    def restore_bond_from_state_for_history(
        self, bond_id: int, bond_state: dict
    ) -> None: ...

    def remove_bond_for_history(self, bond_id: int) -> None: ...

    def trim_bonds_for_history(self, length: int) -> None: ...


class HistoryColorOperations(Protocol):
    def apply_atom_color_for_history(self, atom_id: int, color: Any) -> None: ...


def _set_last_smiles_input(
    operations: HistorySmilesOperations, value: str | None
) -> None:
    operations.set_last_smiles_input_for_history(value)


_NO_HISTORY_TRANSACTION = object()
_DEFER_TO_OUTER_HISTORY_TRANSACTION = object()
_ACTIVE_HISTORY_TRANSACTION_OPERATIONS: ContextVar[frozenset[int]] = ContextVar(
    "active_history_transaction_operations",
    default=frozenset(),
)


@contextmanager
def history_transaction_scope(operations) -> Iterator[None]:
    """Make nested commands defer to one already-captured document savepoint."""

    active = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.get()
    reset_token = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.set(active | {id(operations)})
    try:
        yield
    finally:
        _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.reset(reset_token)


def _capture_history_transaction(operations) -> object:
    """Capture an exact UI transaction when the active port supports one.

    The core package remains usable without Qt: headless/fake ports can omit
    this optional capability and the commands retain their inverse-operation
    compensation below.
    """

    if id(operations) in _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.get():
        return _DEFER_TO_OUTER_HISTORY_TRANSACTION
    port = operations
    capture = getattr(
        port,
        "capture_history_transaction_for_history",
        None,
    )
    restore = getattr(
        port,
        "restore_history_transaction_for_history",
        None,
    )
    # This is one optional capability, not two independent hooks. Treat a
    # headless/test port that only implements capture as unsupported so the
    # command keeps its inverse-operation fallback.
    if not callable(capture) or not callable(restore):
        return _NO_HISTORY_TRANSACTION
    return capture()


def capture_history_transaction_for_command(operations) -> object:
    """Capture or defer a command-local exact transaction.

    UI commands with a standalone exact rollback use this port so a lifecycle
    composite that already owns a full snapshot does not capture the scene a
    second time.
    """

    return _capture_history_transaction(operations)


def _restore_history_transaction(
    operations,
    snapshot: object,
    original_error: BaseException,
) -> RestoreOutcome:
    if snapshot is _NO_HISTORY_TRANSACTION:
        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=True,
        )
    if snapshot is _DEFER_TO_OUTER_HISTORY_TRANSACTION:
        # The owning CompositeCommand restores its single absolute snapshot.
        return RestoreOutcome(authoritative=True)
    restore = getattr(
        operations,
        "restore_history_transaction_for_history",
        None,
    )
    if not callable(restore):
        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=True,
        )
    try:
        result = validate_restore_outcome(restore(snapshot))
    except Exception as caught_restore_error:
        # An unstructured exception does not prove that the absolute restore
        # failed before touching state.  It may have restored only part of the
        # snapshot, in which case a relative inverse can corrupt that mixed
        # state further.  Ports that can prove no mutation occurred must opt
        # into the inverse fallback explicitly through a structured result.
        result = RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=(caught_restore_error,),
        )
    for rollback_error in result.errors:
        add_recovery_error_note(
            original_error,
            rollback_error,
            phase="restoring the exact history transaction",
        )

    return result


def restore_history_transaction_for_command(
    operations,
    snapshot: object,
    original_error: BaseException,
) -> RestoreOutcome:
    """Restore a command-local transaction or defer to its outer owner."""

    return _restore_history_transaction(operations, snapshot, original_error)


def _release_history_transaction(operations, snapshot: object) -> None:
    if (
        snapshot is _NO_HISTORY_TRANSACTION
        or snapshot is _DEFER_TO_OUTER_HISTORY_TRANSACTION
    ):
        return
    operations.release_history_transaction_for_history(snapshot)


def release_history_transaction_for_command(operations, snapshot: object) -> None:
    """Commit a command-local savepoint after its mutation succeeds."""

    _release_history_transaction(operations, snapshot)


def _owns_history_transaction(snapshot: object) -> bool:
    return (
        snapshot is not _NO_HISTORY_TRANSACTION
        and snapshot is not _DEFER_TO_OUTER_HISTORY_TRANSACTION
    )


def _restore_atom_states(
    operations: HistoryAtomOperations,
    atom_states: dict[int, dict],
    atom_coords_3d: dict[int, tuple[float, float, float]] | None,
) -> None:
    for atom_id, state in atom_states.items():
        operations.restore_atom_from_state_for_history(atom_id, state)
    if atom_coords_3d:
        operations.set_atom_positions_for_history(
            {},
            update_selection=False,
            coords_3d=atom_coords_3d,
        )


# Only the atom-state and 3-D coordinate steps are shared between the add and
# delete atom commands. The projection restore that precedes them in the delete
# command and the mark restore that follows stay at their own call sites, so
# each compensation order still reads top to bottom where it is written.
def _restore_atom_states_best_effort(
    operations: HistoryAtomOperations,
    original_error: BaseException,
    atom_states: dict[int, dict],
    atom_coords_3d: dict[int, tuple[float, float, float]] | None,
) -> None:
    port = operations

    # The port attribute is looked up inside this body, not in the ``partial``
    # below, so a missing port method is caught by the rollback step and noted
    # instead of escaping and masking the original error — headless and
    # model-only canvases really do reach these paths. It is a named function
    # rather than a per-iteration lambda because the loop variables then bind
    # through ``partial`` instead of default arguments, which the rollback
    # runner's zero-argument callable type cannot describe.
    def restore_one_atom_state(atom_id: int, state: dict) -> None:
        port.restore_atom_from_state_for_history(atom_id, state)

    for atom_id, state in atom_states.items():
        run_rollback_step(
            original_error,
            "restoring an atom state",
            partial(restore_one_atom_state, atom_id, state),
        )
    if atom_coords_3d:
        run_rollback_step(
            original_error,
            "restoring the 3-D atom coordinates",
            lambda: port.set_atom_positions_for_history(
                {},
                update_selection=False,
                coords_3d=atom_coords_3d,
            ),
        )


def _compensate_completed_nonexact_commands(
    original_error: BaseException,
    completed: list[HistoryCommand],
    operations,
    *,
    operation_name: str,
) -> set[int]:
    """Inverse completed state not guaranteed to be in the UI savepoint.

    These inverses run before the absolute restore. Therefore commands that
    mutate both arbitrary state and snapshotted canvas state are safe: the
    final absolute pass normalizes the latter after the inverse.
    """

    attempted: set[int] = set()

    # Named, and defined once outside the loop, so ``partial`` binds an
    # already-resolved local while the port lookup itself stays inside the
    # rollback step's own try. A missing operation must become a note, not
    # escape and mask the primary error.
    def invert_one_completed_command(child: HistoryCommand) -> None:
        getattr(child, operation_name)(operations)

    for command in reversed(completed):
        if command_is_fully_covered_by_history_transaction(command):
            continue
        attempted.add(id(command))
        run_rollback_step(
            original_error,
            f"inverting a completed child command with {operation_name}",
            partial(invert_one_completed_command, command),
        )
    return attempted


@dataclass
class CompositeCommand(HistoryCommand):
    commands: list[HistoryCommand] = field(default_factory=list)

    @override
    def undo(self, operations) -> None:
        # A composite must apply atomically: if one child fails part-way, roll
        # the already-undone children forward again so the canvas is not left
        # in a state no command on either stack describes.
        transaction = (
            _capture_history_transaction(operations)
            if command_requires_exact_history_transaction(self)
            else _NO_HISTORY_TRANSACTION
        )
        active_token = None
        if _owns_history_transaction(transaction):
            active = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.get()
            active_token = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.set(
                active | {id(operations)}
            )
        completed: list[HistoryCommand] = []
        failed_command: HistoryCommand | None = None
        try:
            for command in reversed(self.commands):
                failed_command = command
                command.undo(operations)
                completed.append(command)
                failed_command = None
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            precompensated: set[int] = set()
            if transaction is not _NO_HISTORY_TRANSACTION:
                precompensated = _compensate_completed_nonexact_commands(
                    exc,
                    completed,
                    operations,
                    operation_name="redo",
                )
            restore_result = _restore_history_transaction(operations, transaction, exc)
            if restore_result.fallback_to_inverse:
                if active_token is not None:
                    _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.reset(active_token)
                    active_token = None
                # Lifecycle commands suppress their own inverse while an outer
                # exact transaction is active. If that outer restore later
                # proves it never ran and explicitly requests inverse fallback,
                # repair the partially executed current child before replaying
                # children whose undo completed. Commands outside this exact
                # lifecycle family already run their own local compensation.
                if (
                    _owns_history_transaction(transaction)
                    and failed_command is not None
                    and command_requires_exact_history_transaction(failed_command)
                ):
                    run_rollback_step(
                        exc,
                        "redoing the child command whose undo failed",
                        lambda: failed_command.redo(operations),
                    )

                def redo_one_completed_command(child: HistoryCommand) -> None:
                    child.redo(operations)

                for command in reversed(completed):
                    if id(command) in precompensated:
                        continue
                    run_rollback_step(
                        exc,
                        "redoing a completed child command",
                        partial(redo_one_completed_command, command),
                    )
            raise
        finally:
            if active_token is not None:
                _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.reset(active_token)

    @override
    def redo(self, operations) -> None:
        transaction = (
            _capture_history_transaction(operations)
            if command_requires_exact_history_transaction(self)
            else _NO_HISTORY_TRANSACTION
        )
        active_token = None
        if _owns_history_transaction(transaction):
            active = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.get()
            active_token = _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.set(
                active | {id(operations)}
            )
        completed: list[HistoryCommand] = []
        failed_command: HistoryCommand | None = None
        try:
            for command in self.commands:
                failed_command = command
                command.redo(operations)
                completed.append(command)
                failed_command = None
            _release_history_transaction(operations, transaction)
        except Exception as exc:
            precompensated: set[int] = set()
            if transaction is not _NO_HISTORY_TRANSACTION:
                precompensated = _compensate_completed_nonexact_commands(
                    exc,
                    completed,
                    operations,
                    operation_name="undo",
                )
            restore_result = _restore_history_transaction(operations, transaction, exc)
            if restore_result.fallback_to_inverse:
                if active_token is not None:
                    _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.reset(active_token)
                    active_token = None
                if (
                    _owns_history_transaction(transaction)
                    and failed_command is not None
                    and command_requires_exact_history_transaction(failed_command)
                ):
                    run_rollback_step(
                        exc,
                        "undoing the child command whose redo failed",
                        lambda: failed_command.undo(operations),
                    )

                def undo_one_completed_command(child: HistoryCommand) -> None:
                    child.undo(operations)

                for command in reversed(completed):
                    if id(command) in precompensated:
                        continue
                    run_rollback_step(
                        exc,
                        "undoing a completed child command",
                        partial(undo_one_completed_command, command),
                    )
            raise
        finally:
            if active_token is not None:
                _ACTIVE_HISTORY_TRANSACTION_OPERATIONS.reset(active_token)


@dataclass
class MoveAtomsCommand(HistoryCommand):
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


def command_requires_exact_history_transaction(command: HistoryCommand) -> bool:
    """Return whether *command* owns an authoritative canvas savepoint.

    History-stack adapters use this predicate to distinguish commands whose
    failed application is proven to restore the exact pre-operation state
    from relative commands that must retain the conservative pop-first
    failure policy.
    """
    if isinstance(
        command,
        (
            AddAtomsCommand,
            DeleteAtomsCommand,
            AddBondCommand,
            DeleteBondCommand,
            SetAtomPositionsCommand,
            SetRingPolygonsCommand,
            UpdateBondCommand,
            UpdateBondLengthCommand,
        ),
    ):
        return True
    # The flag carries the same answer for commands this layer cannot name:
    # chemvas.ui.history_commands sits above core and opts in by class attribute.
    if command.history_transaction_owns_exact_state:
        return True
    if isinstance(command, CompositeCommand):
        return any(
            command_requires_exact_history_transaction(child)
            for child in command.commands
        )
    return False


def command_is_fully_covered_by_history_transaction(
    command: HistoryCommand,
) -> bool:
    """Return whether the UI absolute snapshot fully owns command state.

    Unknown commands can mutate state outside the canvas transaction port and
    therefore still require their ordinary inverse even when a lifecycle
    sibling makes the surrounding composite exact.
    """

    if isinstance(
        command,
        (
            AddAtomsCommand,
            DeleteAtomsCommand,
            AddBondCommand,
            DeleteBondCommand,
            MoveAtomsCommand,
            SetAtomPositionsCommand,
            SetRingPolygonsCommand,
            SetSmilesInputCommand,
            UpdateAtomColorCommand,
            UpdateBondCommand,
            UpdateBondLengthCommand,
        ),
    ):
        return True
    if command.history_transaction_snapshot_covers_state:
        return True
    if isinstance(command, CompositeCommand):
        return bool(command.commands) and all(
            command_is_fully_covered_by_history_transaction(child)
            for child in command.commands
        )
    return False


__all__ = [
    "AddAtomsCommand",
    "AddBondCommand",
    "CompositeCommand",
    "DeleteAtomsCommand",
    "DeleteBondCommand",
    "HistoryCommand",
    "MoveAtomsCommand",
    "SetAtomPositionsCommand",
    "SetRingPolygonsCommand",
    "SetSmilesInputCommand",
    "UpdateAtomColorCommand",
    "UpdateBondCommand",
    "UpdateBondLengthCommand",
    "capture_history_transaction_for_command",
    "command_is_fully_covered_by_history_transaction",
    "command_requires_exact_history_transaction",
    "history_transaction_scope",
    "release_history_transaction_for_command",
    "restore_history_transaction_for_command",
]
