"""Selection/direct-item drag transaction mixin for the select and move tools.

A drag mutates the document in place on every pointer frame. The mixin keeps
one gesture contract: nothing is captured for a plain click, a whole-document
savepoint opens lazily before the first effective mutation, a failed or
cancelled drag restores that savepoint, and exactly one history command is
pushed per moved gesture. After a successful push the stack top describes the
document, so later finalization failures never revert it (ADR 0002).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
    MoveAtomsCommand,
)
from chemvas.ui.canvas_model_access import bond_for_id
from chemvas.ui.canvas_scene_items_state import ring_items_for_atoms
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
)
from chemvas.ui.history_commands import MoveItemsCommand
from chemvas.ui.move_access import (
    move_atoms_for,
    move_item_for,
    shift_selection_outlines_for,
)
from chemvas.ui.selection_collection_access import independent_selection_items
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.selection_style_access import suspend_selection_outline_for

if TYPE_CHECKING:
    from chemvas.ui.tool_context import ToolContext

_DRAG_DELTA_EPSILON = 1e-6


def _add_drag_rollback_note(
    primary_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        primary_error.add_note(
            "Selection drag recovery also encountered an error while "
            f"{phase}: {type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        return


def atom_ids_with_bonds(canvas, atom_ids: set[int], bond_ids: set[int]) -> set[int]:
    expanded = set(atom_ids)
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is not None:
            expanded.add(bond.a)
            expanded.add(bond.b)
    return expanded


@dataclass(slots=True)
class _DragTransactionToken:
    """One active drag interaction and its lazily opened savepoint."""

    history_service: Any
    savepoint: Any | None = None
    pushed: bool = False


class SelectionDragMixin:
    # Provided by the host Tool subclass (SelectTool, MoveTool).
    context: ToolContext
    canvas: Any
    _drag_transaction: _DragTransactionToken | None

    def _reset_selection_drag_state(self) -> None:
        self._drag_selection = False
        self._selection_atom_ids: set[int] = set()
        self._selection_items: list = []
        self._drag_bond_ids: set[int] = set()
        self._drag_boundary_bond_ids: set[int] = set()
        self._drag_affected_ring_items: tuple[object, ...] | None = None
        self._suspended_outline = False
        self._selection_outline_was_suspended = False
        self._start_pos: QPointF | None = None
        self._moved: bool = False
        self._total_delta: QPointF = QPointF(0.0, 0.0)

    def _begin_drag_transaction(self) -> _DragTransactionToken:
        if self._drag_transaction is not None:
            raise RuntimeError("A selection drag transaction is already active")
        token = _DragTransactionToken(history_service=self.context.history_service)
        self._drag_transaction = token
        return token

    def _require_drag_token(self) -> _DragTransactionToken:
        token = self._drag_transaction
        if token is None:
            raise RuntimeError("No selection drag transaction is active")
        return token

    def _ensure_drag_owner(
        self,
        token: _DragTransactionToken,
        *,
        phase: str = "",
    ) -> None:
        if self._drag_transaction is not token:
            raise RuntimeError(
                f"Selection drag owner changed while {phase or 'interacting'}"
            )

    def _prepare_drag_mutation(self, token: _DragTransactionToken) -> None:
        """Open the whole-document savepoint before the first mutation."""

        if token.savepoint is None:
            token.savepoint = capture_history_transaction_for_history(
                self.canvas,
                history_service=token.history_service,
            )

    def _release_drag_transaction(self, token: _DragTransactionToken) -> None:
        savepoint = token.savepoint
        token.savepoint = None
        if self._drag_transaction is token:
            self._drag_transaction = None
        if savepoint is not None:
            savepoint.release()

    def _cancel_drag_transaction(
        self,
        token: _DragTransactionToken,
        original_error: BaseException | None = None,
    ) -> None:
        savepoint = token.savepoint
        token.savepoint = None
        if self._drag_transaction is token:
            self._drag_transaction = None
        if savepoint is None:
            return
        try:
            result = savepoint.restore_with_result()
        except BaseException as rollback_error:
            if original_error is None:
                raise
            _add_drag_rollback_note(
                original_error,
                rollback_error,
                phase="restoring the drag savepoint",
            )
            return
        rollback_errors = list(result.errors)
        if original_error is not None:
            for recovered_error in rollback_errors:
                _add_drag_rollback_note(
                    original_error,
                    recovered_error,
                    phase="restoring the drag savepoint",
                )
        elif rollback_errors and not result.authoritative:
            # A plain cancel only surfaces a rollback error when the restore
            # could not prove the pre-drag state; recovered secondary errors
            # must not corrupt a tool switch or deactivate.
            raise rollback_errors[0]

    def _commit_drag_transaction(self, commit) -> None:
        token = self._require_drag_token()
        try:
            commit(token)
        except BaseException as original_error:
            # Fail closed. Before the push commits, restore the savepoint;
            # after a successful push the stack top describes the document,
            # so the document must stay as pushed.
            if token.pushed:
                try:
                    self._release_drag_transaction(token)
                except BaseException as cleanup_error:
                    _add_drag_rollback_note(
                        original_error,
                        cleanup_error,
                        phase="releasing the drag savepoint",
                    )
            else:
                self._cancel_drag_transaction(token, original_error)
            raise
        self._release_drag_transaction(token)

    def _push_drag_history(
        self,
        owner: _DragTransactionToken,
        command: HistoryCommand,
    ) -> None:
        self._ensure_drag_owner(owner, phase="pushing its history command")
        if owner.history_service.push(command) is False:
            raise RuntimeError("Selection drag history push did not commit its command")
        owner.pushed = True

    def _cancel_selection_drag(
        self,
        original_error: BaseException | None = None,
        *,
        token: _DragTransactionToken | None = None,
    ) -> None:
        if token is None:
            if self._drag_transaction is None:
                self._reset_selection_drag_state()
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(token, original_error)
        finally:
            if self._drag_transaction is None:
                self._reset_selection_drag_state()

    def _begin_selection_drag(
        self, atom_ids: set[int], selection_items: list, start_pos
    ) -> bool:
        if not atom_ids and not selection_items:
            return False
        if self._drag_transaction is not None or self._drag_selection:
            self._cancel_selection_drag()

        selection_atom_ids = set(atom_ids)
        independent_items = independent_selection_items(
            selection_items,
            selection_atom_ids,
        )
        if selection_atom_ids:
            drag_bond_ids, drag_boundary_bond_ids = self.context.bond_sets_for_atoms(
                selection_atom_ids
            )
        else:
            drag_bond_ids = set()
            drag_boundary_bond_ids = set()
        outline_was_suspended = suspend_selection_outline_for(self.canvas)

        self._begin_drag_transaction()
        self._drag_selection = True
        self._selection_atom_ids = selection_atom_ids
        self._selection_items = independent_items
        self._drag_bond_ids = drag_bond_ids
        self._drag_boundary_bond_ids = drag_boundary_bond_ids
        # Discover affected rings once per gesture so frame cost scales with
        # the selection, not the document.
        self._drag_affected_ring_items = (
            tuple(ring_items_for_atoms(self.canvas, selection_atom_ids))
            if selection_atom_ids
            else None
        )
        self._selection_outline_was_suspended = outline_was_suspended
        self._start_pos = start_pos
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    @staticmethod
    def _drag_delta_is_effective(delta: QPointF) -> bool:
        return (
            abs(delta.x()) > _DRAG_DELTA_EPSILON or abs(delta.y()) > _DRAG_DELTA_EPSILON
        )

    def _drag_has_net_movement(self) -> bool:
        # The epsilon is only an input-frame filter, before any geometry is
        # changed. Once a frame was applied, every exact accumulated residual
        # must be represented by history; otherwise a sub-epsilon remainder
        # would survive without an undo command while redo stayed intact.
        return self._total_delta.x() != 0.0 or self._total_delta.y() != 0.0

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if not self._drag_selection:
            return
        # Qt can deliver a move event at the exact press coordinate. Treat it
        # as a true no-op: invoking move/outline callbacks would mark the drag
        # as moved, suppress a handle-toggle click, and later clear redo with a
        # zero-distance history command.
        if not self._drag_delta_is_effective(delta):
            return
        token = self._require_drag_token()
        try:
            self._prepare_drag_mutation(token)
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
                    affected_ring_items=self._drag_affected_ring_items,
                )
            for item in self._selection_items:
                move_item_for(
                    self.canvas,
                    item,
                    delta.x(),
                    delta.y(),
                    update_selection=False,
                )
            shift_selection_outlines_for(self.canvas, delta.x(), delta.y())
            self._total_delta += delta
            self._moved = True
        except BaseException as original_error:
            self._cancel_selection_drag(original_error, token=token)
            raise

    def _build_move_command(self) -> HistoryCommand | None:
        if not self._drag_has_net_movement():
            return None
        commands: list[HistoryCommand] = []
        if self._selection_atom_ids:
            commands.append(
                MoveAtomsCommand(
                    atom_ids=set(self._selection_atom_ids),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                    bond_ids=set(self._drag_bond_ids) if self._drag_bond_ids else None,
                    redraw_bond_ids=set(self._drag_boundary_bond_ids)
                    if self._drag_boundary_bond_ids
                    else None,
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
        self._require_drag_token()

        def commit(owner: _DragTransactionToken) -> None:
            if self._suspended_outline:
                self.context.suspend_selection_outline(
                    self._selection_outline_was_suspended
                )
                self._suspended_outline = False
            if self._moved and self._drag_has_net_movement():
                refresh_selection_outline_for(self.canvas)
                command = self._build_move_command()
                if command is not None:
                    self._push_drag_history(owner, command)

        try:
            self._commit_drag_transaction(commit)
        except BaseException:
            if self._drag_transaction is None:
                self._reset_selection_drag_state()
            raise
        self._reset_selection_drag_state()


__all__ = ["SelectionDragMixin", "atom_ids_with_bonds", "independent_selection_items"]
