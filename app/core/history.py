from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol, cast


class HistoryCommand:
    def undo(self, canvas) -> None:
        raise NotImplementedError

    def redo(self, canvas) -> None:
        raise NotImplementedError


class HistoryCanvasPort(Protocol):
    """Canvas operations invoked by history commands.

    The core history layer depends on this interface it owns rather than on the
    concrete (PyQt-importing) ``ui.history_canvas_access`` module. The
    implementation is resolved lazily so importing this module never requires
    PyQt6, keeping the core package usable in headless contexts.
    """

    def move_atoms_for_history(
        self,
        canvas: Any,
        atom_ids: set[int],
        dx: float,
        dy: float,
        *,
        bond_ids: set[int] | None = ...,
        redraw_bond_ids: set[int] | None = ...,
        update_selection: bool = ...,
    ) -> None: ...

    def restore_projection_state_for_history(
        self,
        canvas: Any,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
    ) -> None: ...

    def set_atom_positions_for_history(
        self,
        canvas: Any,
        positions: dict[int, tuple[float, float]],
        *,
        update_selection: bool = ...,
        coords_3d: dict[int, tuple[float, float, float]] | None = ...,
    ) -> None: ...

    def set_ring_polygons_for_history(
        self,
        canvas: Any,
        ring_items: list,
        polygons: list[list[tuple[float, float]]],
    ) -> None: ...

    def set_last_smiles_input_for_history(self, canvas: Any, value: str | None) -> None: ...

    def restore_bond_length_for_history(self, canvas: Any, length_px: float) -> None: ...

    def remove_atom_for_history(self, canvas: Any, atom_id: int, *, remove_marks: bool = ...) -> None: ...

    def restore_atom_from_state_for_history(self, canvas: Any, atom_id: int, state: dict) -> None: ...

    def apply_atom_color_for_history(self, canvas: Any, atom_id: int, color: Any) -> None: ...

    def restore_mark_from_state_for_history(self, canvas: Any, mark_state: dict) -> Any: ...

    def restore_bond_from_state_for_history(self, canvas: Any, bond_id: int, bond_state: dict) -> None: ...

    def remove_bond_for_history(self, canvas: Any, bond_id: int) -> None: ...

    def trim_bonds_for_history(self, canvas: Any, length: int) -> None: ...

    def capture_history_transaction_for_history(
        self,
        canvas: Any,
        *,
        history_service: Any | None = ...,
    ) -> Any: ...

    def restore_history_transaction_for_history(
        self,
        canvas: Any,
        snapshot: Any,
    ) -> None: ...


def _history_canvas_port() -> HistoryCanvasPort:
    return cast(HistoryCanvasPort, import_module("ui.history_canvas_access"))


def _set_last_smiles_input(canvas, value: str | None) -> None:
    _history_canvas_port().set_last_smiles_input_for_history(canvas, value)


_NO_HISTORY_TRANSACTION = object()
_DEFER_TO_OUTER_HISTORY_TRANSACTION = object()
_ACTIVE_HISTORY_TRANSACTION_CANVASES: ContextVar[frozenset[int]] = ContextVar(
    "active_history_transaction_canvases",
    default=frozenset(),
)


def _capture_history_transaction(canvas) -> object:
    """Capture an exact UI transaction when the active port supports one.

    The core package remains usable without Qt: headless/fake ports can omit
    this optional capability and the commands retain their inverse-operation
    compensation below.
    """

    if id(canvas) in _ACTIVE_HISTORY_TRANSACTION_CANVASES.get():
        return _DEFER_TO_OUTER_HISTORY_TRANSACTION
    port = _history_canvas_port()
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
    # This is one optional capability, not two independent hooks.  Treat a
    # legacy/test port that only implements capture as unsupported so the
    # command keeps its inverse-operation fallback.
    if not callable(capture) or not callable(restore):
        return _NO_HISTORY_TRANSACTION
    return capture(canvas)


def _restore_history_transaction(
    canvas,
    snapshot: object,
    original_error: BaseException,
) -> bool:
    if snapshot is _NO_HISTORY_TRANSACTION:
        return False
    if snapshot is _DEFER_TO_OUTER_HISTORY_TRANSACTION:
        # The owning CompositeCommand restores its single absolute snapshot.
        return True
    restore = getattr(
        _history_canvas_port(),
        "restore_history_transaction_for_history",
        None,
    )
    if not callable(restore):
        return False
    try:
        restore(canvas, snapshot)
    except BaseException as rollback_error:
        _add_history_rollback_note(original_error, rollback_error)
    return True


def _owns_history_transaction(snapshot: object) -> bool:
    return (
        snapshot is not _NO_HISTORY_TRANSACTION
        and snapshot is not _DEFER_TO_OUTER_HISTORY_TRANSACTION
    )


def _add_history_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    add_note = getattr(original_error, "add_note", None)
    if callable(add_note):
        add_note(
            "History rollback also encountered "
            f"{type(rollback_error).__name__}: {rollback_error}"
        )


def _run_history_rollback_step(
    original_error: BaseException,
    operation,
) -> None:
    try:
        operation()
    except BaseException as rollback_error:
        # Cancellation signals must remain the primary exception.  Continue
        # best-effort compensation and retain secondary failures as notes.
        _add_history_rollback_note(original_error, rollback_error)


@dataclass
class CompositeCommand(HistoryCommand):
    commands: list[HistoryCommand] = field(default_factory=list)

    def undo(self, canvas) -> None:
        # A composite must apply atomically: if one child fails part-way, roll
        # the already-undone children forward again so the canvas is not left
        # in a state no command on either stack describes.
        transaction = (
            _capture_history_transaction(canvas)
            if _command_requires_exact_history_transaction(self)
            else _NO_HISTORY_TRANSACTION
        )
        active_token = None
        if _owns_history_transaction(transaction):
            active = _ACTIVE_HISTORY_TRANSACTION_CANVASES.get()
            active_token = _ACTIVE_HISTORY_TRANSACTION_CANVASES.set(
                active | {id(canvas)}
            )
        completed: list[HistoryCommand] = []
        try:
            for command in reversed(self.commands):
                command.undo(canvas)
                completed.append(command)
        except BaseException as exc:
            restored = transaction is _DEFER_TO_OUTER_HISTORY_TRANSACTION
            if _owns_history_transaction(transaction):
                restored = _restore_history_transaction(canvas, transaction, exc)
            if transaction is _NO_HISTORY_TRANSACTION or not restored:
                if active_token is not None:
                    _ACTIVE_HISTORY_TRANSACTION_CANVASES.reset(active_token)
                    active_token = None
                for command in reversed(completed):
                    _run_history_rollback_step(
                        exc,
                        lambda command=command: command.redo(canvas),
                    )
            raise
        finally:
            if active_token is not None:
                _ACTIVE_HISTORY_TRANSACTION_CANVASES.reset(active_token)

    def redo(self, canvas) -> None:
        transaction = (
            _capture_history_transaction(canvas)
            if _command_requires_exact_history_transaction(self)
            else _NO_HISTORY_TRANSACTION
        )
        active_token = None
        if _owns_history_transaction(transaction):
            active = _ACTIVE_HISTORY_TRANSACTION_CANVASES.get()
            active_token = _ACTIVE_HISTORY_TRANSACTION_CANVASES.set(
                active | {id(canvas)}
            )
        completed: list[HistoryCommand] = []
        try:
            for command in self.commands:
                command.redo(canvas)
                completed.append(command)
        except BaseException as exc:
            restored = transaction is _DEFER_TO_OUTER_HISTORY_TRANSACTION
            if _owns_history_transaction(transaction):
                restored = _restore_history_transaction(canvas, transaction, exc)
            if transaction is _NO_HISTORY_TRANSACTION or not restored:
                if active_token is not None:
                    _ACTIVE_HISTORY_TRANSACTION_CANVASES.reset(active_token)
                    active_token = None
                for command in reversed(completed):
                    _run_history_rollback_step(
                        exc,
                        lambda command=command: command.undo(canvas),
                    )
            raise
        finally:
            if active_token is not None:
                _ACTIVE_HISTORY_TRANSACTION_CANVASES.reset(active_token)


@dataclass
class MoveAtomsCommand(HistoryCommand):
    atom_ids: set[int]
    dx: float
    dy: float
    bond_ids: set[int] | None = None
    redraw_bond_ids: set[int] | None = None

    def undo(self, canvas) -> None:
        _history_canvas_port().move_atoms_for_history(
            canvas,
            self.atom_ids,
            -self.dx,
            -self.dy,
            bond_ids=self.bond_ids,
            redraw_bond_ids=self.redraw_bond_ids,
            update_selection=True,
        )

    def redo(self, canvas) -> None:
        _history_canvas_port().move_atoms_for_history(
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
            _history_canvas_port().restore_projection_state_for_history(
                canvas,
                projection_center_3d,
                projection_anchor_2d,
            )
        if coords_3d is None:
            _history_canvas_port().set_atom_positions_for_history(
                canvas,
                positions,
                update_selection=self.update_selection,
            )
            return
        _history_canvas_port().set_atom_positions_for_history(
            canvas,
            positions,
            update_selection=self.update_selection,
            coords_3d=coords_3d,
        )

    def _compensate(
        self,
        canvas,
        positions: dict[int, tuple[float, float]],
        coords_3d: dict[int, tuple[float, float, float]] | None,
        projection_center_3d: tuple[float, float, float] | None,
        projection_anchor_2d: tuple[float, float] | None,
        original_error: BaseException,
    ) -> None:
        port = _history_canvas_port()
        if self.restore_projection_state:
            _run_history_rollback_step(
                original_error,
                lambda: port.restore_projection_state_for_history(
                    canvas,
                    projection_center_3d,
                    projection_anchor_2d,
                ),
            )

        def restore_positions() -> None:
            if coords_3d is None:
                port.set_atom_positions_for_history(
                    canvas,
                    positions,
                    update_selection=self.update_selection,
                )
            else:
                port.set_atom_positions_for_history(
                    canvas,
                    positions,
                    update_selection=self.update_selection,
                    coords_3d=coords_3d,
                )

        _run_history_rollback_step(original_error, restore_positions)

    def undo(self, canvas) -> None:
        try:
            self._apply(
                canvas,
                self.before_positions,
                self.before_coords_3d,
                self.before_projection_center_3d,
                self.before_projection_anchor_2d,
            )
        except BaseException as exc:
            self._compensate(
                canvas,
                self.after_positions,
                self.after_coords_3d,
                self.after_projection_center_3d,
                self.after_projection_anchor_2d,
                exc,
            )
            raise

    def redo(self, canvas) -> None:
        try:
            self._apply(
                canvas,
                self.after_positions,
                self.after_coords_3d,
                self.after_projection_center_3d,
                self.after_projection_anchor_2d,
            )
        except BaseException as exc:
            self._compensate(
                canvas,
                self.before_positions,
                self.before_coords_3d,
                self.before_projection_center_3d,
                self.before_projection_anchor_2d,
                exc,
            )
            raise


@dataclass
class SetRingPolygonsCommand(HistoryCommand):
    ring_items: list
    before_polygons: list[list[tuple[float, float]]]
    after_polygons: list[list[tuple[float, float]]]

    def _compensate(
        self,
        canvas,
        polygons: list[list[tuple[float, float]]],
        original_error: BaseException,
    ) -> None:
        port = _history_canvas_port()
        # Compensate one ring at a time so a persistently broken item cannot
        # prevent later rings from being restored.
        for ring_item, polygon in zip(self.ring_items, polygons, strict=False):
            _run_history_rollback_step(
                original_error,
                lambda ring_item=ring_item, polygon=polygon: (
                    port.set_ring_polygons_for_history(
                        canvas,
                        [ring_item],
                        [polygon],
                    )
                ),
            )

    def undo(self, canvas) -> None:
        try:
            _history_canvas_port().set_ring_polygons_for_history(
                canvas,
                self.ring_items,
                self.before_polygons,
            )
        except BaseException as exc:
            self._compensate(canvas, self.after_polygons, exc)
            raise

    def redo(self, canvas) -> None:
        try:
            _history_canvas_port().set_ring_polygons_for_history(
                canvas,
                self.ring_items,
                self.after_polygons,
            )
        except BaseException as exc:
            self._compensate(canvas, self.before_polygons, exc)
            raise


@dataclass
class UpdateBondLengthCommand(HistoryCommand):
    before_length: float
    after_length: float

    @staticmethod
    def _compensate(
        canvas,
        length: float,
        original_error: BaseException,
    ) -> None:
        _run_history_rollback_step(
            original_error,
            lambda: _history_canvas_port().restore_bond_length_for_history(
                canvas,
                length,
            ),
        )

    def undo(self, canvas) -> None:
        try:
            _history_canvas_port().restore_bond_length_for_history(canvas, self.before_length)
        except BaseException as exc:
            self._compensate(canvas, self.after_length, exc)
            raise

    def redo(self, canvas) -> None:
        try:
            _history_canvas_port().restore_bond_length_for_history(canvas, self.after_length)
        except BaseException as exc:
            self._compensate(canvas, self.before_length, exc)
            raise


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
    atom_coords_3d: dict[int, tuple[float, float, float]] | None = None

    def _remove_atoms_best_effort(self, canvas) -> None:
        port = _history_canvas_port()
        for atom_id in reversed(self.atom_states):
            with contextlib.suppress(BaseException):
                port.remove_atom_for_history(canvas, atom_id)

    def _restore_atoms_best_effort(self, canvas) -> None:
        port = _history_canvas_port()
        # Normalize every atom owned by this command first. A failing port
        # call may have mutated the current atom before raising, so tracking
        # only calls that returned successfully is insufficient.
        self._remove_atoms_best_effort(canvas)
        for atom_id, state in self.atom_states.items():
            with contextlib.suppress(BaseException):
                port.restore_atom_from_state_for_history(canvas, atom_id, state)
        if self.atom_coords_3d:
            with contextlib.suppress(BaseException):
                port.set_atom_positions_for_history(
                    canvas,
                    {},
                    update_selection=False,
                    coords_3d=self.atom_coords_3d,
                )
        with contextlib.suppress(BaseException):
            canvas.model.next_atom_id = self.after_next_atom_id
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.after_smiles_input)

    def _restore_absent_state_best_effort(self, canvas) -> None:
        self._remove_atoms_best_effort(canvas)
        with contextlib.suppress(BaseException):
            canvas.model.next_atom_id = self.before_next_atom_id
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.before_smiles_input)

    def undo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            for atom_id in self.atom_states:
                _history_canvas_port().remove_atom_for_history(canvas, atom_id)
            canvas.model.next_atom_id = self.before_next_atom_id
            _set_last_smiles_input(canvas, self.before_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_atoms_best_effort(canvas)
            raise

    def redo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            for atom_id, state in self.atom_states.items():
                _history_canvas_port().restore_atom_from_state_for_history(canvas, atom_id, state)
            if self.atom_coords_3d:
                _history_canvas_port().set_atom_positions_for_history(
                    canvas,
                    {},
                    update_selection=False,
                    coords_3d=self.atom_coords_3d,
                )
            canvas.model.next_atom_id = self.after_next_atom_id
            _set_last_smiles_input(canvas, self.after_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_absent_state_best_effort(canvas)
            raise


@dataclass
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

    def _remove_atoms_best_effort(self, canvas) -> None:
        port = _history_canvas_port()
        for atom_id in reversed(self.atom_states):
            with contextlib.suppress(BaseException):
                port.remove_atom_for_history(
                    canvas,
                    atom_id,
                    remove_marks=self.remove_marks,
                )

    def _restore_deleted_state_best_effort(self, canvas) -> None:
        self._remove_atoms_best_effort(canvas)
        port = _history_canvas_port()
        if self.restore_projection_state:
            with contextlib.suppress(BaseException):
                port.restore_projection_state_for_history(
                    canvas,
                    self.before_projection_center_3d,
                    self.before_projection_anchor_2d,
                )
        for atom_id, state in self.atom_states.items():
            with contextlib.suppress(BaseException):
                port.restore_atom_from_state_for_history(canvas, atom_id, state)
        if self.atom_coords_3d:
            with contextlib.suppress(BaseException):
                port.set_atom_positions_for_history(
                    canvas,
                    {},
                    update_selection=False,
                    coords_3d=self.atom_coords_3d,
                )
        if self.remove_marks:
            for mark_state in self.mark_states:
                with contextlib.suppress(BaseException):
                    port.restore_mark_from_state_for_history(canvas, mark_state)
        with contextlib.suppress(BaseException):
            canvas.model.next_atom_id = self.before_next_atom_id
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.before_smiles_input)

    def _restore_absent_state_best_effort(self, canvas) -> None:
        self._remove_atoms_best_effort(canvas)
        if self.restore_projection_state:
            with contextlib.suppress(BaseException):
                _history_canvas_port().restore_projection_state_for_history(
                    canvas,
                    self.after_projection_center_3d,
                    self.after_projection_anchor_2d,
                )
        with contextlib.suppress(BaseException):
            canvas.model.next_atom_id = self.after_next_atom_id
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.after_smiles_input)

    def undo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            if self.restore_projection_state:
                _history_canvas_port().restore_projection_state_for_history(
                    canvas,
                    self.before_projection_center_3d,
                    self.before_projection_anchor_2d,
                )
            for atom_id, state in self.atom_states.items():
                _history_canvas_port().restore_atom_from_state_for_history(canvas, atom_id, state)
            if self.atom_coords_3d:
                _history_canvas_port().set_atom_positions_for_history(
                    canvas,
                    {},
                    update_selection=False,
                    coords_3d=self.atom_coords_3d,
                )
            if self.remove_marks:
                for mark_state in self.mark_states:
                    _history_canvas_port().restore_mark_from_state_for_history(canvas, mark_state)
            canvas.model.next_atom_id = self.before_next_atom_id
            _set_last_smiles_input(canvas, self.before_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_absent_state_best_effort(canvas)
            raise

    def redo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            for atom_id in self.atom_states:
                _history_canvas_port().remove_atom_for_history(
                    canvas,
                    atom_id,
                    remove_marks=self.remove_marks,
                )
            if self.restore_projection_state:
                _history_canvas_port().restore_projection_state_for_history(
                    canvas,
                    self.after_projection_center_3d,
                    self.after_projection_anchor_2d,
                )
            canvas.model.next_atom_id = self.after_next_atom_id
            _set_last_smiles_input(canvas, self.after_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_deleted_state_best_effort(canvas)
            raise


@dataclass
class UpdateAtomColorCommand(HistoryCommand):
    atom_id: int
    before_color: str
    after_color: str

    @staticmethod
    def _compensate(canvas, atom_id: int, color: str) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().apply_atom_color_for_history(canvas, atom_id, color)

    def undo(self, canvas) -> None:
        try:
            _history_canvas_port().apply_atom_color_for_history(
                canvas,
                self.atom_id,
                self.before_color,
            )
        except BaseException:
            self._compensate(canvas, self.atom_id, self.after_color)
            raise

    def redo(self, canvas) -> None:
        try:
            _history_canvas_port().apply_atom_color_for_history(
                canvas,
                self.atom_id,
                self.after_color,
            )
        except BaseException:
            self._compensate(canvas, self.atom_id, self.before_color)
            raise


@dataclass
class AddBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    previous_bond_count: int
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _restore_added_state_best_effort(self, canvas) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.bond_state,
            )
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.after_smiles_input)

    def _restore_absent_state_best_effort(self, canvas) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().remove_bond_for_history(canvas, self.bond_id)
        with contextlib.suppress(BaseException):
            _history_canvas_port().trim_bonds_for_history(canvas, self.previous_bond_count)
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.before_smiles_input)

    def undo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().remove_bond_for_history(canvas, self.bond_id)
            _history_canvas_port().trim_bonds_for_history(canvas, self.previous_bond_count)
            _set_last_smiles_input(canvas, self.before_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_added_state_best_effort(canvas)
            raise

    def redo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.bond_state,
            )
            _set_last_smiles_input(canvas, self.after_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_absent_state_best_effort(canvas)
            raise


@dataclass
class DeleteBondCommand(HistoryCommand):
    bond_id: int
    bond_state: dict
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _restore_present_state_best_effort(self, canvas) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.bond_state,
            )
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.before_smiles_input)

    def _restore_absent_state_best_effort(self, canvas) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().remove_bond_for_history(canvas, self.bond_id)
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, self.after_smiles_input)

    def undo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.bond_state,
            )
            _set_last_smiles_input(canvas, self.before_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_absent_state_best_effort(canvas)
            raise

    def redo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().remove_bond_for_history(canvas, self.bond_id)
            _set_last_smiles_input(canvas, self.after_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_present_state_best_effort(canvas)
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
        canvas,
        bond_state: dict,
        smiles_input: str | None,
    ) -> None:
        with contextlib.suppress(BaseException):
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                bond_state,
            )
        with contextlib.suppress(BaseException):
            _set_last_smiles_input(canvas, smiles_input)

    def undo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.before_state,
            )
            _set_last_smiles_input(canvas, self.before_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_state_best_effort(
                    canvas,
                    self.after_state,
                    self.after_smiles_input,
                )
            raise

    def redo(self, canvas) -> None:
        transaction = _capture_history_transaction(canvas)
        try:
            _history_canvas_port().restore_bond_from_state_for_history(
                canvas,
                self.bond_id,
                self.after_state,
            )
            _set_last_smiles_input(canvas, self.after_smiles_input)
        except BaseException as exc:
            if not _restore_history_transaction(canvas, transaction, exc):
                self._restore_state_best_effort(
                    canvas,
                    self.before_state,
                    self.before_smiles_input,
                )
            raise


def _command_requires_exact_history_transaction(command: HistoryCommand) -> bool:
    if isinstance(
        command,
        (
            AddAtomsCommand,
            DeleteAtomsCommand,
            AddBondCommand,
            DeleteBondCommand,
            UpdateBondCommand,
        ),
    ):
        return True
    if isinstance(command, CompositeCommand):
        return any(
            _command_requires_exact_history_transaction(child)
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
]
