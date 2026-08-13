from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from chemvas.core.history import (
    HistoryCommand,
    command_is_fully_covered_by_history_transaction,
    command_requires_exact_history_transaction,
    history_transaction_scope,
)
from chemvas.domain.transactions import RestoreOutcome, validate_restore_outcome
from chemvas.ui import history_canvas_access
from chemvas.ui.canvas_history_state import CanvasHistoryState, history_state_for


@dataclass(frozen=True, slots=True)
class HistoryStackSnapshot:
    """The single immutable value used for history stack-policy recovery."""

    state: CanvasHistoryState
    history: tuple[HistoryCommand, ...]
    redo_stack: tuple[HistoryCommand, ...]
    enabled: bool
    limit: int


def _add_history_recovery_note(
    original_error: BaseException,
    recovery_error: BaseException,
    *,
    phase: str,
) -> None:
    original_error.add_note(
        f"History {phase} also encountered "
        f"{type(recovery_error).__name__}: {recovery_error}"
    )


class CanvasHistoryService:
    """Own the undo/redo stacks and every policy decision applied to them."""

    def __init__(
        self,
        canvas,
        state: CanvasHistoryState | None = None,
    ) -> None:
        self.canvas = canvas
        self.state = state if state is not None else history_state_for(canvas)
        self._history_mutation_active = False
        self._history_publication_active = False

    def capture_stack_snapshot(self) -> HistoryStackSnapshot:
        state = self.state
        return HistoryStackSnapshot(
            state=state,
            history=tuple(state.history),
            redo_stack=tuple(state.redo_stack),
            enabled=state.enabled,
            limit=state.limit,
        )

    def verify_stack_snapshot(
        self,
        snapshot: HistoryStackSnapshot,
        *,
        history: tuple[HistoryCommand, ...] | None = None,
        redo_stack: tuple[HistoryCommand, ...] | None = None,
    ) -> None:
        expected_history = snapshot.history if history is None else history
        expected_redo = snapshot.redo_stack if redo_stack is None else redo_stack
        if self.state is not snapshot.state:
            raise RuntimeError("history state identity changed")
        actual_history = tuple(self.state.history)
        if len(actual_history) != len(expected_history) or any(
            actual is not expected
            for actual, expected in zip(actual_history, expected_history, strict=True)
        ):
            raise RuntimeError("undo stack did not match the expected history state")
        actual_redo = tuple(self.state.redo_stack)
        if len(actual_redo) != len(expected_redo) or any(
            actual is not expected
            for actual, expected in zip(actual_redo, expected_redo, strict=True)
        ):
            raise RuntimeError("redo stack did not match the expected history state")
        if self.state.enabled is not snapshot.enabled:
            raise RuntimeError("history enabled policy changed")
        if self.state.limit != snapshot.limit:
            raise RuntimeError("history limit policy changed")

    def restore_stack_snapshot(
        self,
        snapshot: HistoryStackSnapshot,
        original_error: BaseException,
        *,
        history: tuple[HistoryCommand, ...] | None = None,
        redo_stack: tuple[HistoryCommand, ...] | None = None,
        phase: str,
    ) -> bool:
        """Restore once, verify once, and clear both stacks on uncertainty."""

        expected_history = snapshot.history if history is None else history
        expected_redo = snapshot.redo_stack if redo_stack is None else redo_stack
        try:
            self.state = snapshot.state
            self.state.history[:] = expected_history
            self.state.redo_stack[:] = expected_redo
            self.state.enabled = snapshot.enabled
            self.state.limit = snapshot.limit
            self.verify_stack_snapshot(
                snapshot,
                history=expected_history,
                redo_stack=expected_redo,
            )
        except Exception as recovery_error:
            _add_history_recovery_note(
                original_error,
                recovery_error,
                phase=phase,
            )
            try:
                snapshot.state.history.clear()
                snapshot.state.redo_stack.clear()
            except Exception as clear_error:
                _add_history_recovery_note(
                    original_error,
                    clear_error,
                    phase=f"{phase} conservative stack clear",
                )
            if self.state is not snapshot.state:
                try:
                    self.state.history.clear()
                    self.state.redo_stack.clear()
                except Exception as clear_error:
                    _add_history_recovery_note(
                        original_error,
                        clear_error,
                        phase=f"{phase} current stack clear",
                    )
            return False
        return True

    def _begin_mutation(self) -> None:
        if self._history_mutation_active or self._history_publication_active:
            raise RuntimeError("re-entrant history mutation is not allowed")
        self._history_mutation_active = True

    def _finish_mutation(self) -> None:
        self._history_mutation_active = False

    def _commit_stack_delta(
        self,
        snapshot: HistoryStackSnapshot,
        *,
        history: tuple[HistoryCommand, ...],
        redo_stack: tuple[HistoryCommand, ...],
        operation: str,
    ) -> None:
        try:
            self.state.history[:] = history
            self.state.redo_stack[:] = redo_stack
            self.verify_stack_snapshot(
                snapshot,
                history=history,
                redo_stack=redo_stack,
            )
        except Exception as commit_error:
            self.restore_stack_snapshot(
                snapshot,
                commit_error,
                phase=f"rolling back failed {operation}",
            )
            raise
        self.notify_change()

    def _notify_failed_operation(self, original_error: BaseException) -> None:
        try:
            self.notify_change()
        except Exception as notification_error:
            _add_history_recovery_note(
                original_error,
                notification_error,
                phase="failure notification",
            )

    @staticmethod
    def _failure_stack_delta(
        snapshot: HistoryStackSnapshot,
        command: HistoryCommand,
        *,
        direction: str,
    ) -> tuple[tuple[HistoryCommand, ...], tuple[HistoryCommand, ...]]:
        if direction == "undo":
            history = snapshot.history
            if history and history[-1] is command:
                history = history[:-1]
            return history, ()
        return snapshot.history, ()

    def _capture_document_savepoint(self):
        return history_canvas_access.capture_history_transaction_for_history(
            self.canvas,
            history_service=None,
            guard_scene_rect=True,
        )

    def _restore_document_savepoint(
        self,
        snapshot,
        original_error: BaseException,
    ) -> RestoreOutcome:
        try:
            result = validate_restore_outcome(
                history_canvas_access.restore_history_transaction_for_history(
                    self.canvas,
                    snapshot,
                )
            )
            for recovery_error in result.errors:
                _add_history_recovery_note(
                    original_error,
                    recovery_error,
                    phase="document savepoint restore",
                )
            return result
        except Exception as recovery_error:
            _add_history_recovery_note(
                original_error,
                recovery_error,
                phase="document savepoint restore",
            )
            return RestoreOutcome(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(recovery_error,),
            )

    def _apply_exact_command(
        self,
        stack_snapshot: HistoryStackSnapshot,
        command: HistoryCommand,
        *,
        direction: str,
    ) -> None:
        try:
            document_snapshot = self._capture_document_savepoint()
        except Exception as capture_error:
            conservative_history, conservative_redo = self._failure_stack_delta(
                stack_snapshot,
                command,
                direction=direction,
            )
            self.restore_stack_snapshot(
                stack_snapshot,
                capture_error,
                history=conservative_history,
                redo_stack=conservative_redo,
                phase=f"cleaning failed exact {direction} capture",
            )
            self._notify_failed_operation(capture_error)
            raise

        try:
            with history_transaction_scope(self.canvas):
                getattr(command, direction)(self.canvas)
            history_canvas_access.release_history_transaction_for_history(
                self.canvas,
                document_snapshot,
            )
        except Exception as original_error:
            restore_result = self._restore_document_savepoint(
                document_snapshot,
                original_error,
            )
            if (
                restore_result.authoritative
                and command_is_fully_covered_by_history_transaction(command)
            ):
                self.restore_stack_snapshot(
                    stack_snapshot,
                    original_error,
                    phase=f"restoring failed exact {direction} stacks",
                )
            else:
                conservative_history, conservative_redo = self._failure_stack_delta(
                    stack_snapshot,
                    command,
                    direction=direction,
                )
                self.restore_stack_snapshot(
                    stack_snapshot,
                    original_error,
                    history=conservative_history,
                    redo_stack=conservative_redo,
                    phase=f"cleaning failed exact {direction} stacks",
                )
            self._notify_failed_operation(original_error)
            raise

    def push(self, command: HistoryCommand) -> bool:
        return self.push_many((command,))

    def push_many(self, commands: Iterable[HistoryCommand]) -> bool:
        commands = tuple(commands)
        if not commands:
            return False
        self._begin_mutation()
        try:
            snapshot = self.capture_stack_snapshot()
            if not snapshot.enabled:
                return False
            history = [*snapshot.history, *commands]
            if len(history) > snapshot.limit:
                del history[: len(history) - snapshot.limit]
            self._commit_stack_delta(
                snapshot,
                history=tuple(history),
                redo_stack=(),
                operation="history push",
            )
            return True
        finally:
            self._finish_mutation()

    def undo(self) -> None:
        self._begin_mutation()
        try:
            snapshot = self.capture_stack_snapshot()
            if not snapshot.history:
                return
            command = cast(HistoryCommand, snapshot.history[-1])
            if command_requires_exact_history_transaction(command):
                self._apply_exact_command(snapshot, command, direction="undo")
                self._commit_stack_delta(
                    snapshot,
                    history=snapshot.history[:-1],
                    redo_stack=(*snapshot.redo_stack, command),
                    operation="exact history undo",
                )
                return

            inflight_history = snapshot.history[:-1]
            self.state.history[:] = inflight_history
            try:
                command.undo(self.canvas)
            except Exception as original_error:
                self.state.redo_stack.clear()
                self._notify_failed_operation(original_error)
                raise
            self._commit_stack_delta(
                snapshot,
                history=inflight_history,
                redo_stack=(*snapshot.redo_stack, command),
                operation="relative history undo",
            )
        finally:
            self._finish_mutation()

    def redo(self) -> None:
        self._begin_mutation()
        try:
            snapshot = self.capture_stack_snapshot()
            if not snapshot.redo_stack:
                return
            command = cast(HistoryCommand, snapshot.redo_stack[-1])
            if command_requires_exact_history_transaction(command):
                self._apply_exact_command(snapshot, command, direction="redo")
                self._commit_stack_delta(
                    snapshot,
                    history=(*snapshot.history, command),
                    redo_stack=snapshot.redo_stack[:-1],
                    operation="exact history redo",
                )
                return

            inflight_redo = snapshot.redo_stack[:-1]
            self.state.redo_stack[:] = inflight_redo
            try:
                command.redo(self.canvas)
            except Exception as original_error:
                self.state.redo_stack.clear()
                self._notify_failed_operation(original_error)
                raise
            self._commit_stack_delta(
                snapshot,
                history=(*snapshot.history, command),
                redo_stack=inflight_redo,
                operation="relative history redo",
            )
        finally:
            self._finish_mutation()

    def set_change_callback(self, callback) -> None:
        self.state.change_callback = callback

    def set_enabled(self, enabled: bool) -> None:
        if self._history_mutation_active or self._history_publication_active:
            raise RuntimeError("history policy cannot change during a mutation")
        self.state.enabled = bool(enabled)

    def clear(self) -> None:
        self._begin_mutation()
        try:
            snapshot = self.capture_stack_snapshot()
            self._commit_stack_delta(
                snapshot,
                history=(),
                redo_stack=(),
                operation="history clear",
            )
        finally:
            self._finish_mutation()

    def notify_change(self) -> None:
        if self._history_publication_active:
            raise RuntimeError("re-entrant history publication is not allowed")
        self._history_publication_active = True
        try:
            callback = self.state.change_callback
            if callback is None:
                return
            try:
                callback()
            except Exception:
                # Toolbar and dirty-marker refresh failures do not invalidate
                # the already-committed document/history transition.
                return
        finally:
            self._history_publication_active = False

    def is_enabled(self) -> bool:
        return bool(self.state.enabled)

    def can_undo(self) -> bool:
        return bool(self.state.history)

    def can_redo(self) -> bool:
        return bool(self.state.redo_stack)


__all__ = ["CanvasHistoryService", "HistoryStackSnapshot"]
