from __future__ import annotations

import inspect
from contextlib import contextmanager

_USE_LIVE_SCENE_PORT = object()
_MISSING_SCENE_PORT = object()


def _add_signal_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                f"Scene signal recovery also failed while {phase}: "
                f"{type(secondary_error).__name__}: {secondary_error}"
            )
    except BaseException:
        return


def _optional_scene_port(scene, name: str):
    try:
        return getattr(scene, name)
    except AttributeError:
        if inspect.getattr_static(
            scene,
            name,
            _MISSING_SCENE_PORT,
        ) is not _MISSING_SCENE_PORT:
            raise
        return None


def _set_verified_signal_state(
    block_signals,
    signals_blocked,
    blocked: bool,
) -> tuple[bool, list[BaseException]]:
    failures: list[BaseException] = []
    for _attempt in range(2):
        try:
            block_signals(blocked)
            if bool(signals_blocked()) != blocked:
                raise RuntimeError(
                    "scene signal-blocking setter did not apply the requested state"
                )
        except BaseException as error:
            failures.append(error)
            continue
        return True, failures
    return False, failures


def _add_signal_failure_notes(
    primary_error: BaseException,
    failures: list[BaseException],
    *,
    phase: str,
) -> None:
    for failure in failures:
        _add_signal_recovery_note(
            primary_error,
            failure,
            phase=phase,
        )


@contextmanager
def blocked_scene_signals(
    scene,
    *,
    block_signals=_USE_LIVE_SCENE_PORT,
    signals_blocked=_USE_LIVE_SCENE_PORT,
):
    """Temporarily block a scene while preserving its exact prior state.

    Callers that already captured a live scene port may inject it to avoid a
    second descriptor read between validation and mutation.  Omitting the
    keyword arguments preserves the original live-lookup behaviour.
    """
    if block_signals is _USE_LIVE_SCENE_PORT:
        block_signals = _optional_scene_port(scene, "blockSignals")
    if not callable(block_signals):
        raise RuntimeError("scene does not expose a signal-blocking setter")
    if signals_blocked is _USE_LIVE_SCENE_PORT:
        signals_blocked = _optional_scene_port(scene, "signalsBlocked")

    if not callable(signals_blocked):
        legacy_original_error: BaseException | None = None
        previous_blocked = bool(block_signals(True))
        try:
            yield
        except BaseException as error:
            legacy_original_error = error
            raise
        finally:
            try:
                block_signals(previous_blocked)
            except BaseException as secondary_error:
                primary_error = legacy_original_error or secondary_error
                if legacy_original_error is not None:
                    _add_signal_recovery_note(
                        legacy_original_error,
                        secondary_error,
                        phase="restoring the prior signal-block state",
                    )
                try:
                    block_signals(previous_blocked)
                except BaseException as retry_error:
                    _add_signal_recovery_note(
                        primary_error,
                        retry_error,
                        phase="retrying the prior signal-block restore",
                    )
                if legacy_original_error is None:
                    raise
        return

    previous_blocked = (
        bool(signals_blocked())
    )
    entered, enter_failures = _set_verified_signal_state(
        block_signals,
        signals_blocked,
        True,
    )
    if not entered:
        primary_error = enter_failures[0]
        _add_signal_failure_notes(
            primary_error,
            enter_failures[1:],
            phase="retrying scene signal blocking before the operation",
        )
        _restored, restore_failures = _set_verified_signal_state(
            block_signals,
            signals_blocked,
            previous_blocked,
        )
        _add_signal_failure_notes(
            primary_error,
            restore_failures,
            phase="restoring the prior state after signal-block entry failed",
        )
        raise primary_error

    original_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        original_error = error
        raise
    finally:
        restored, restore_failures = _set_verified_signal_state(
            block_signals,
            signals_blocked,
            previous_blocked,
        )
        if restored:
            if original_error is not None:
                _add_signal_failure_notes(
                    original_error,
                    restore_failures,
                    phase="restoring the prior signal-block state",
                )
        elif original_error is not None:
            _add_signal_failure_notes(
                original_error,
                restore_failures,
                phase="restoring the prior signal-block state",
            )
        else:
            primary_error = restore_failures[0]
            _add_signal_failure_notes(
                primary_error,
                restore_failures[1:],
                phase="retrying the prior signal-block restore",
            )
            raise primary_error


__all__ = ["blocked_scene_signals"]
