from __future__ import annotations

import inspect
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, cast

from core.history import (
    HistoryCommand,
    command_requires_exact_history_transaction,
    consume_authoritative_history_failure_restore,
    history_operation_scope,
    validate_history_transaction_restore_result,
)

from ui.canvas_history_state import CanvasHistoryState, history_state_for

_MISSING_HISTORY_PORT = object()
_ACTIVE_HISTORY_MUTATION_SERVICES: ContextVar[frozenset[int]] = ContextVar(
    "active_history_mutation_services",
    default=frozenset(),
)
_ACTIVE_HISTORY_PUBLICATION_SERVICES: ContextVar[frozenset[int]] = ContextVar(
    "active_history_publication_services",
    default=frozenset(),
)


def _add_history_notification_note(
    original_error: BaseException,
    notification_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "History notification also encountered "
                f"{type(notification_error).__name__}: {notification_error}"
            )
    except BaseException:
        return


def _add_history_authority_note(
    original_error: BaseException,
    authority_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                f"History {phase} also encountered "
                f"{type(authority_error).__name__}: {authority_error}"
            )
    except BaseException:
        return


@dataclass(frozen=True, slots=True)
class _HistoryConfigPort:
    """Capture-bound scalar policy port; observer callback is intentionally absent."""

    name: str
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]

    def _matches(self) -> bool:
        actual = self.getter()
        if actual is self.value:
            return True
        if type(actual) is not type(self.value):
            return False
        return bool(actual == self.value)

    def apply_once(self) -> None:
        if not self._matches():
            self.setter(self.value)

    def verify(self) -> None:
        if not self._matches():
            raise RuntimeError(f"history observer changed the {self.name} policy")


@dataclass(frozen=True, slots=True)
class _HistoryAuthorityRestoreResult:
    authoritative: bool
    errors: tuple[BaseException, ...] = ()


def _capture_history_config_port(
    state: object,
    name: str,
) -> _HistoryConfigPort:
    getattribute = inspect.getattr_static(
        type(state),
        "__getattribute__",
        _MISSING_HISTORY_PORT,
    )
    setattribute = inspect.getattr_static(
        type(state),
        "__setattr__",
        _MISSING_HISTORY_PORT,
    )
    if not callable(getattribute) or not callable(setattribute):
        raise RuntimeError(f"history {name} state has incomplete bound ports")

    def get_value(
        _getattribute=getattribute,
        _state=state,
        _name=name,
    ) -> object:
        return _getattribute(_state, _name)

    def set_value(
        value: object,
        _setattribute=setattribute,
        _state=state,
        _name=name,
    ) -> object:
        return _setattribute(_state, _name, value)

    return _HistoryConfigPort(
        name=name,
        value=get_value(),
        getter=get_value,
        setter=set_value,
    )


@dataclass(frozen=True, slots=True)
class _HistoryPublicationAuthority:
    """Capture-bound stack/config authority around commands and observers."""

    stack_snapshot: Any
    config_ports: tuple[_HistoryConfigPort, ...]

    @classmethod
    def capture(cls, service: object) -> _HistoryPublicationAuthority:
        # Local import avoids making CanvasRuntimeState's import of this service
        # depend eagerly on the UI history-command graph.
        from ui.history_stack_snapshot import HistoryStackSnapshot

        stack_snapshot = HistoryStackSnapshot.capture(service)
        if stack_snapshot is None:
            raise RuntimeError("history operation requires exact mutable stacks")
        authority = cls(
            stack_snapshot=stack_snapshot,
            config_ports=tuple(
                _capture_history_config_port(stack_snapshot.state, name)
                for name in ("enabled", "limit")
            ),
        )
        if not authority.is_exact():
            raise RuntimeError("history authority changed while it was captured")
        return authority

    @property
    def history_items(self) -> tuple[object, ...]:
        return self.stack_snapshot.history_items

    @property
    def redo_items(self) -> tuple[object, ...]:
        return self.stack_snapshot.redo_items

    @staticmethod
    def _apply_stack(port: Any, items: tuple[object, ...]) -> None:
        port.setter(port.value)
        port.replace_items(slice(None), items)

    @staticmethod
    def _verify_stack(port: Any, items: tuple[object, ...]) -> None:
        if port.getter() is not port.value:
            raise RuntimeError("history stack setter did not restore list identity")
        actual_items = tuple(port.iterate())
        if len(actual_items) != len(items) or any(
            actual is not expected
            for actual, expected in zip(actual_items, items, strict=False)
        ):
            raise RuntimeError("history stack contents did not match the authority")

    def _verify(
        self,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
    ) -> None:
        snapshot = self.stack_snapshot
        # Policy and stack/root readers are independent callback boundaries.
        # A later policy getter may poison an earlier policy or a stack root;
        # a stack/root getter may poison a policy in return.  Close the combined
        # authority in both policy orders, with an exact raw-stack sweep after
        # each order.
        for ports in (self.config_ports, tuple(reversed(self.config_ports))):
            for port in ports:
                port.verify()
            snapshot.verify_exact_items(
                history_items=history_items,
                redo_items=redo_items,
            )

    def try_restore_exact(
        self,
        *,
        history_items: tuple[object, ...] | None = None,
        redo_items: tuple[object, ...] | None = None,
    ) -> _HistoryAuthorityRestoreResult:
        """Apply and globally verify one stack/config result in two orders."""

        expected_history = (
            self.history_items if history_items is None else history_items
        )
        expected_redo = self.redo_items if redo_items is None else redo_items
        errors: list[BaseException] = []
        snapshot = self.stack_snapshot
        for attempt in range(2):
            try:
                if attempt == 0:
                    snapshot.state_port.apply_once()
                    self._apply_stack(snapshot.history_port, expected_history)
                    self._apply_stack(snapshot.redo_port, expected_redo)
                    for port in self.config_ports:
                        port.apply_once()
                else:
                    for port in reversed(self.config_ports):
                        port.apply_once()
                    self._apply_stack(snapshot.redo_port, expected_redo)
                    self._apply_stack(snapshot.history_port, expected_history)
                    snapshot.state_port.apply_once()
                self._verify(expected_history, expected_redo)
            except BaseException as error:
                errors.append(error)
                continue
            return _HistoryAuthorityRestoreResult(True, tuple(errors))
        return _HistoryAuthorityRestoreResult(False, tuple(errors))

    def restore_exact(
        self,
        *,
        history_items: tuple[object, ...] | None = None,
        redo_items: tuple[object, ...] | None = None,
    ) -> tuple[BaseException, ...]:
        result = self.try_restore_exact(
            history_items=history_items,
            redo_items=redo_items,
        )
        if result.authoritative:
            return result.errors
        raise BaseExceptionGroup(
            "history observer corrupted the committed stack authority",
            list(result.errors),
        )

    def is_exact(
        self,
        *,
        history_items: tuple[object, ...] | None = None,
        redo_items: tuple[object, ...] | None = None,
    ) -> bool:
        try:
            self._verify(
                self.history_items if history_items is None else history_items,
                self.redo_items if redo_items is None else redo_items,
            )
        except BaseException:
            return False
        return True


class CanvasHistoryService:
    def __init__(
        self,
        canvas,
        state: CanvasHistoryState | None = None,
    ) -> None:
        self.canvas = canvas
        self.state = state if state is not None else history_state_for(canvas)
        self._history_mutation_active = False
        self._history_publication_active = False

    def _mutation_is_blocked(self) -> bool:
        service_id = id(self)
        return (
            service_id in _ACTIVE_HISTORY_MUTATION_SERVICES.get()
            or service_id in _ACTIVE_HISTORY_PUBLICATION_SERVICES.get()
        )

    def _begin_history_mutation(self) -> Token[frozenset[int]]:
        if self._mutation_is_blocked():
            raise RuntimeError("re-entrant history mutation is not allowed")
        active = _ACTIVE_HISTORY_MUTATION_SERVICES.get()
        context_token = _ACTIVE_HISTORY_MUTATION_SERVICES.set(active | {id(self)})
        try:
            self._history_mutation_active = True
        except BaseException:
            _ACTIVE_HISTORY_MUTATION_SERVICES.reset(context_token)
            raise
        return context_token

    def _finish_history_mutation(
        self,
        context_token: Token[frozenset[int]],
    ) -> None:
        try:
            self._history_mutation_active = False
        finally:
            _ACTIVE_HISTORY_MUTATION_SERVICES.reset(context_token)

    def _begin_history_publication(self) -> Token[frozenset[int]]:
        active = _ACTIVE_HISTORY_PUBLICATION_SERVICES.get()
        if id(self) in active:
            raise RuntimeError("re-entrant history publication is not allowed")
        context_token = _ACTIVE_HISTORY_PUBLICATION_SERVICES.set(active | {id(self)})
        try:
            self._history_publication_active = True
        except BaseException:
            _ACTIVE_HISTORY_PUBLICATION_SERVICES.reset(context_token)
            raise
        return context_token

    def _finish_history_publication(
        self,
        context_token: Token[frozenset[int]],
    ) -> None:
        try:
            self._history_publication_active = False
        finally:
            _ACTIVE_HISTORY_PUBLICATION_SERVICES.reset(context_token)

    @staticmethod
    def _record_authority_errors(
        original_error: BaseException,
        result: _HistoryAuthorityRestoreResult,
        *,
        phase: str,
    ) -> None:
        for authority_error in result.errors:
            _add_history_authority_note(
                original_error,
                authority_error,
                phase=phase,
            )

    def _best_effort_conservative_stacks(
        self,
        authority: _HistoryPublicationAuthority,
        *,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
    ) -> None:
        """Leave every reachable stack non-retryable if bound setters stay broken."""

        snapshot = authority.stack_snapshot
        try:
            list.__setitem__(snapshot.history, slice(None), history_items)
        except BaseException:
            pass
        try:
            list.__setitem__(snapshot.redo_stack, slice(None), redo_items)
        except BaseException:
            pass

        # A failed bound setter can leave replacement roots reachable from the
        # captured state even when ``self.state`` was replaced independently.
        # Clear every list root we can still reach, not only the two roots that
        # happened to win the last service-state assignment.
        reachable_stacks: list[list] = []
        for getter in (
            snapshot.history_port.getter,
            snapshot.redo_port.getter,
        ):
            try:
                candidate = getter()
            except BaseException:
                continue
            if isinstance(candidate, list):
                reachable_stacks.append(candidate)
        try:
            current_state = self.state
            current_history = getattr(current_state, "history", None)
            current_redo = getattr(current_state, "redo_stack", None)
            if isinstance(current_history, list):
                reachable_stacks.append(current_history)
            if isinstance(current_redo, list):
                reachable_stacks.append(current_redo)
        except BaseException:
            pass
        seen: set[int] = {id(snapshot.history), id(snapshot.redo_stack)}
        for stack in reachable_stacks:
            if id(stack) in seen:
                continue
            seen.add(id(stack))
            try:
                list.__setitem__(stack, slice(None), ())
            except BaseException:
                continue

    def _restore_history_authority(
        self,
        authority: _HistoryPublicationAuthority,
        original_error: BaseException,
        *,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
        phase: str,
        clear_on_failure: bool = False,
    ) -> bool:
        result = authority.try_restore_exact(
            history_items=history_items,
            redo_items=redo_items,
        )
        self._record_authority_errors(
            original_error,
            result,
            phase=phase,
        )
        if not result.authoritative:
            self._best_effort_conservative_stacks(
                authority,
                history_items=() if clear_on_failure else history_items,
                redo_items=() if clear_on_failure else redo_items,
            )
        return result.authoritative

    @staticmethod
    def _exact_post_items(
        authority: _HistoryPublicationAuthority,
        command: HistoryCommand,
        *,
        direction: str,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        history_items = authority.history_items
        redo_items = authority.redo_items
        if direction == "undo":
            if not history_items or history_items[-1] is not command:
                raise RuntimeError("exact undo lost its captured top command")
            return history_items[:-1], (*redo_items, command)
        if not redo_items or redo_items[-1] is not command:
            raise RuntimeError("exact redo lost its captured top command")
        return (*history_items, command), redo_items[:-1]

    @staticmethod
    def _exact_failure_items(
        authority: _HistoryPublicationAuthority,
        command: HistoryCommand,
        *,
        direction: str,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        if direction == "undo":
            history_items = authority.history_items
            if history_items and history_items[-1] is command:
                history_items = history_items[:-1]
            return history_items, ()
        return authority.history_items, ()

    def _commit_history_success(
        self,
        authority: _HistoryPublicationAuthority,
        *,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
        operation: str,
        rollback_to_pre_on_failure: bool = False,
    ) -> None:
        result = authority.try_restore_exact(
            history_items=history_items,
            redo_items=redo_items,
        )
        if not result.authoritative:
            commit_error = BaseExceptionGroup(
                f"{operation} could not commit its stack delta",
                list(result.errors),
            )
            if rollback_to_pre_on_failure:
                restored_pre = self._restore_history_authority(
                    authority,
                    commit_error,
                    history_items=authority.history_items,
                    redo_items=authority.redo_items,
                    phase=f"rolling back failed {operation}",
                )
                if not restored_pre:
                    self._best_effort_conservative_stacks(
                        authority,
                        history_items=(),
                        redo_items=(),
                    )
            else:
                self._restore_history_authority(
                    authority,
                    commit_error,
                    history_items=(),
                    redo_items=(),
                    phase=f"{operation} success conservative cleanup",
                    clear_on_failure=True,
                )
            raise commit_error

        try:
            self.notify_change()
        except BaseException as publication_error:
            if not authority.is_exact(
                history_items=history_items,
                redo_items=redo_items,
            ):
                self._restore_history_authority(
                    authority,
                    publication_error,
                    history_items=(),
                    redo_items=(),
                    phase=f"{operation} publication conservative cleanup",
                    clear_on_failure=True,
                )
            raise

        if authority.is_exact(
            history_items=history_items,
            redo_items=redo_items,
        ):
            return
        post_publication_error = RuntimeError(
            f"{operation} stack changed after publication"
        )
        self._restore_history_authority(
            authority,
            post_publication_error,
            history_items=(),
            redo_items=(),
            phase=f"{operation} final conservative cleanup",
            clear_on_failure=True,
        )
        raise post_publication_error

    def _stage_history_delta(
        self,
        authority: _HistoryPublicationAuthority,
        *,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
        operation: str,
    ) -> None:
        result = authority.try_restore_exact(
            history_items=history_items,
            redo_items=redo_items,
        )
        if result.authoritative:
            return
        staging_error = BaseExceptionGroup(
            f"{operation} could not stage its pop-first stack delta",
            list(result.errors),
        )
        restored_pre = self._restore_history_authority(
            authority,
            staging_error,
            history_items=authority.history_items,
            redo_items=authority.redo_items,
            phase=f"rolling back failed {operation} staging",
        )
        if not restored_pre:
            self._best_effort_conservative_stacks(
                authority,
                history_items=(),
                redo_items=(),
            )
        raise staging_error

    def _commit_exact_success(
        self,
        authority: _HistoryPublicationAuthority,
        command: HistoryCommand,
        *,
        direction: str,
    ) -> None:
        post_history, post_redo = self._exact_post_items(
            authority,
            command,
            direction=direction,
        )
        self._commit_history_success(
            authority,
            history_items=post_history,
            redo_items=post_redo,
            operation=f"exact history {direction}",
        )

    def _handle_exact_failure(
        self,
        authority: _HistoryPublicationAuthority,
        command: HistoryCommand,
        original_error: BaseException,
        *,
        operation_token: object,
        direction: str,
    ) -> None:
        restore_was_authoritative = consume_authoritative_history_failure_restore(
            original_error,
            operation_token=operation_token,
        )
        stack_was_authoritative = self._restore_history_authority(
            authority,
            original_error,
            history_items=authority.history_items,
            redo_items=authority.redo_items,
            phase=f"restoring failed exact {direction} stacks",
        )
        retryable = restore_was_authoritative and stack_was_authoritative
        conservative_history, conservative_redo = self._exact_failure_items(
            authority,
            command,
            direction=direction,
        )
        if not retryable:
            self._restore_history_authority(
                authority,
                original_error,
                history_items=conservative_history,
                redo_items=conservative_redo,
                phase=f"cleaning failed exact {direction} stacks",
                clear_on_failure=True,
            )
        notification_was_authoritative = self._notify_failed_operation(original_error)
        if retryable and not notification_was_authoritative:
            self._restore_history_authority(
                authority,
                original_error,
                history_items=conservative_history,
                redo_items=conservative_redo,
                phase=f"cleaning exact {direction} notification failure",
                clear_on_failure=True,
            )

    def push(self, command: HistoryCommand) -> bool:
        mutation_token = self._begin_history_mutation()
        try:
            authority = _HistoryPublicationAuthority.capture(self)
            policies = {port.name: port.value for port in authority.config_ports}
            if not bool(policies["enabled"]):
                return False
            history_items = [*authority.history_items, command]
            history_limit: Any = policies["limit"]
            if len(history_items) > history_limit:
                history_items.pop(0)
            self._commit_history_success(
                authority,
                history_items=tuple(history_items),
                redo_items=(),
                operation="history push",
                rollback_to_pre_on_failure=True,
            )
            return True
        finally:
            self._finish_history_mutation(mutation_token)

    def undo(self) -> None:
        mutation_token = self._begin_history_mutation()
        try:
            self._undo_once()
        finally:
            self._finish_history_mutation(mutation_token)

    def _undo_once(self) -> None:
        authority = _HistoryPublicationAuthority.capture(self)
        history_items = authority.history_items
        if not history_items:
            return
        command = cast(HistoryCommand, history_items[-1])
        if command_requires_exact_history_transaction(command):
            self._exact_post_items(authority, command, direction="undo")
            with history_operation_scope() as operation_token:
                try:
                    command.undo(self.canvas)
                except BaseException as original_error:
                    self._handle_exact_failure(
                        authority,
                        command,
                        original_error,
                        operation_token=operation_token,
                        direction="undo",
                    )
                    raise
            self._commit_exact_success(authority, command, direction="undo")
            return
        # Pop before applying: a command whose undo fails part-way must not
        # stay on the stack, or retrying would re-apply the parts that did
        # succeed on top of an already half-undone canvas.
        inflight_history = history_items[:-1]
        self._stage_history_delta(
            authority,
            history_items=inflight_history,
            redo_items=authority.redo_items,
            operation="legacy history undo",
        )
        try:
            command.undo(self.canvas)
        except BaseException as original_error:
            # The canvas no longer matches what the redo stack expects.
            self._restore_history_authority(
                authority,
                original_error,
                history_items=inflight_history,
                redo_items=(),
                phase="cleaning failed legacy undo stacks",
                clear_on_failure=True,
            )
            notification_was_authoritative = self._notify_failed_operation(
                original_error
            )
            if not notification_was_authoritative:
                self._restore_history_authority(
                    authority,
                    original_error,
                    history_items=inflight_history,
                    redo_items=(),
                    phase="closing failed legacy undo publication stacks",
                    clear_on_failure=True,
                )
            raise
        self._commit_history_success(
            authority,
            history_items=inflight_history,
            redo_items=(*authority.redo_items, command),
            operation="legacy history undo",
        )

    def redo(self) -> None:
        mutation_token = self._begin_history_mutation()
        try:
            self._redo_once()
        finally:
            self._finish_history_mutation(mutation_token)

    def _redo_once(self) -> None:
        authority = _HistoryPublicationAuthority.capture(self)
        redo_items = authority.redo_items
        if not redo_items:
            return
        command = cast(HistoryCommand, redo_items[-1])
        if command_requires_exact_history_transaction(command):
            self._exact_post_items(authority, command, direction="redo")
            with history_operation_scope() as operation_token:
                try:
                    command.redo(self.canvas)
                except BaseException as original_error:
                    self._handle_exact_failure(
                        authority,
                        command,
                        original_error,
                        operation_token=operation_token,
                        direction="redo",
                    )
                    raise
            self._commit_exact_success(authority, command, direction="redo")
            return
        inflight_redo = redo_items[:-1]
        self._stage_history_delta(
            authority,
            history_items=authority.history_items,
            redo_items=inflight_redo,
            operation="legacy history redo",
        )
        try:
            command.redo(self.canvas)
        except BaseException as original_error:
            # Deeper redo entries assumed this command was applied.
            self._restore_history_authority(
                authority,
                original_error,
                history_items=authority.history_items,
                redo_items=(),
                phase="cleaning failed legacy redo stacks",
                clear_on_failure=True,
            )
            notification_was_authoritative = self._notify_failed_operation(
                original_error
            )
            if not notification_was_authoritative:
                self._restore_history_authority(
                    authority,
                    original_error,
                    history_items=authority.history_items,
                    redo_items=(),
                    phase="closing failed legacy redo publication stacks",
                    clear_on_failure=True,
                )
            raise
        self._commit_history_success(
            authority,
            history_items=(*authority.history_items, command),
            redo_items=inflight_redo,
            operation="legacy history redo",
        )

    def set_change_callback(self, callback) -> None:
        # A callback may deliberately unsubscribe itself while it is running.
        self.state.change_callback = callback

    def set_enabled(self, enabled: bool) -> None:
        if self._mutation_is_blocked():
            raise RuntimeError("history policy cannot change during a mutation")
        self.state.enabled = bool(enabled)

    def clear(self) -> None:
        mutation_token = self._begin_history_mutation()
        try:
            authority = _HistoryPublicationAuthority.capture(self)
            self._commit_history_success(
                authority,
                history_items=(),
                redo_items=(),
                operation="history clear",
                rollback_to_pre_on_failure=True,
            )
        finally:
            self._finish_history_mutation(mutation_token)

    def notify_change(self) -> None:
        publication_token = self._begin_history_publication()
        authority: _HistoryPublicationAuthority | None = None
        try:
            try:
                authority = _HistoryPublicationAuthority.capture(self)
                callback = authority.stack_snapshot.state.change_callback
            except BaseException as lookup_error:
                if authority is not None:
                    try:
                        authority.restore_exact()
                    except BaseException as authority_error:
                        _add_history_notification_note(
                            lookup_error,
                            authority_error,
                        )
                raise
            if callback is None:
                if not authority.is_exact():
                    authority.restore_exact()
                return
            callback_error: BaseException | None = None
            try:
                callback()
            except Exception:
                # Preserve the established observer contract: ordinary UI callback
                # failures are non-fatal, but their partial mutations are not.
                pass
            except BaseException as error:
                callback_error = error
            try:
                authority.restore_exact()
            except BaseException as authority_error:
                if callback_error is not None:
                    _add_history_notification_note(callback_error, authority_error)
                    raise callback_error from authority_error
                raise
            if callback_error is not None:
                raise callback_error
        finally:
            # The guard owns both observer execution and the exact reassertion.
            # A captured setter invoked by restoration must not publish a nested
            # command that this outer savepoint will subsequently erase.
            self._finish_history_publication(publication_token)

    def _notify_failed_operation(self, original_error: BaseException) -> bool:
        try:
            publication_authority = _HistoryPublicationAuthority.capture(self)
            callback = publication_authority.stack_snapshot.state.change_callback
            if not publication_authority.is_exact():
                publication_authority.restore_exact()
        except BaseException as preflight_error:
            _add_history_notification_note(original_error, preflight_error)
            return False
        if callback is None:
            return True
        # Capture the already-restored/cleaned failure result immediately before
        # publication. This fresh unguarded exact snapshot lets a one-shot UI
        # observer run while ensuring it cannot become the final canvas writer.
        try:
            from ui.history_canvas_access import (
                capture_history_transaction_for_history,
                restore_history_transaction_for_history,
            )

            runtime_snapshot = capture_history_transaction_for_history(
                self.canvas,
                history_service=None,
                guard_scene_rect=False,
            )
            runtime_verify = getattr(runtime_snapshot, "verify_exact", None)
            if not callable(runtime_verify):
                raise RuntimeError(
                    "failed history publication runtime has no exact verifier"
                )
        except BaseException as capture_error:
            _add_history_notification_note(original_error, capture_error)
            # Skipping an observer is safer than invoking it without a recovery
            # authority, but a mutate-then-fail capture is not evidence that
            # the already-restored runtime remained exact.
            return False

        try:
            self.notify_change()
        except BaseException as notification_error:
            # A cancellation/termination raised by the command is the primary
            # control-flow signal.  Stack cleanup still happens, and a broken
            # observer cannot replace that signal while reporting the change.
            _add_history_notification_note(original_error, notification_error)

        accumulated_errors: list[BaseException] = []
        for attempt in range(2):
            pass_errors: list[BaseException] = []
            runtime_authoritative = False
            history_authoritative = False

            def restore_runtime(
                _pass_errors: list[BaseException] = pass_errors,
            ) -> None:
                nonlocal runtime_authoritative
                try:
                    result = validate_history_transaction_restore_result(
                        restore_history_transaction_for_history(
                            self.canvas,
                            runtime_snapshot,
                        )
                    )
                except BaseException as restore_error:
                    _pass_errors.append(restore_error)
                    return
                runtime_authoritative = result.authoritative
                _pass_errors.extend(result.errors)
                if not result.authoritative and not result.errors:
                    _pass_errors.append(
                        RuntimeError(
                            "failed history publication runtime restore "
                            "was not authoritative"
                        )
                    )

            def restore_history(
                _pass_errors: list[BaseException] = pass_errors,
            ) -> None:
                nonlocal history_authoritative
                result = publication_authority.try_restore_exact()
                history_authoritative = result.authoritative
                _pass_errors.extend(result.errors)
                if not result.authoritative and not result.errors:
                    _pass_errors.append(
                        RuntimeError(
                            "failed history publication stack restore "
                            "was not authoritative"
                        )
                    )

            if attempt == 0:
                # Runtime callbacks may poison history; history is final in the
                # first global ordering.
                restore_runtime()
                restore_history()
            else:
                # Reverse the independent writers without notifying again.
                restore_history()
                restore_runtime()

            verification_errors: list[BaseException] = []
            # Two complete sweeps catch either verifier poisoning the other
            # authority after it was checked in the preceding sweep.
            for _sweep in range(2):
                if not publication_authority.is_exact():
                    verification_errors.append(
                        RuntimeError(
                            "failed history publication runtime re-corrupted "
                            "the history authority"
                        )
                    )
                try:
                    verification_errors.extend(runtime_verify())
                except BaseException as verify_error:
                    verification_errors.append(verify_error)
                # Runtime verification is itself a callback boundary. It may
                # report an exact canvas while replacing the history state,
                # policies, or stack roots as a side effect. Re-close the
                # composite on the capture-bound policy/root ports and raw
                # built-in list contents after every runtime verifier call.
                if not publication_authority.is_exact():
                    verification_errors.append(
                        RuntimeError(
                            "failed history publication runtime verifier "
                            "re-corrupted the history authority"
                        )
                    )

            if (
                runtime_authoritative
                and history_authoritative
                and not verification_errors
            ):
                for recovered_error in (*accumulated_errors, *pass_errors):
                    _add_history_notification_note(
                        original_error,
                        recovered_error,
                    )
                return True
            accumulated_errors.extend(pass_errors)
            accumulated_errors.extend(verification_errors)

        for restore_error in accumulated_errors:
            _add_history_notification_note(original_error, restore_error)
        return False

    def is_enabled(self) -> bool:
        return bool(self.state.enabled)

    def can_undo(self) -> bool:
        return bool(self.state.history)

    def can_redo(self) -> bool:
        return bool(self.state.redo_stack)


__all__ = ["CanvasHistoryService"]
