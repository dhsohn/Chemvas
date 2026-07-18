from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, NoReturn, cast

from PyQt6.QtCore import QObject, QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

_TRACKER_ATTRIBUTE = "_chemvas_scene_rect_tracker"
_AUTOMATIC_ATTRIBUTE = "_chemvas_scene_rect_automatic"
_VIEW_EXPLICIT_ATTRIBUTE = "_chemvas_view_scene_rect_explicit"
_MISSING_ATTRIBUTE = object()


class _RectTransitionVerificationError(RuntimeError):
    """A retryable setter no-op, distinct from setter-thrown RuntimeError."""


def _add_secondary_note(
    original_error: BaseException, secondary_error: BaseException
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Scene-rect recovery also encountered "
                f"{type(secondary_error).__name__}: {secondary_error}"
            )
    except BaseException:
        return


def _disconnect_callback_after_capture_failure(
    changed,
    callback,
    original_error: BaseException,
) -> None:
    try:
        disconnect = getattr(changed, "disconnect", None)
        if callable(disconnect):
            disconnect(callback)
    except BaseException as secondary_error:
        _add_secondary_note(original_error, secondary_error)


def _remove_partially_published_tracker(
    scene,
    tracker: _SceneRectTracker,
    original_error: BaseException,
) -> None:
    try:
        if getattr(scene, _TRACKER_ATTRIBUTE, None) is tracker:
            delattr(scene, _TRACKER_ATTRIBUTE)
    except BaseException as secondary_error:
        _add_secondary_note(original_error, secondary_error)


def scene_rect_is_automatic(scene) -> bool:
    return bool(getattr(scene, _AUTOMATIC_ATTRIBUTE, True))


def set_explicit_scene_rect(
    scene,
    rect,
    *,
    scene_rect_getter: Callable[[], object] | None = None,
    set_scene_rect_setter: Callable[[QRectF], object] | None = None,
) -> None:
    """Set Chemvas' fixed sheet rect and keep an existing tracker coherent."""
    if scene_rect_getter is None:
        _, candidate = _optional_attribute(scene, "sceneRect")
        scene_rect_getter = candidate if callable(candidate) else None
    if set_scene_rect_setter is None:
        _, candidate = _optional_attribute(scene, "setSceneRect")
        set_scene_rect_setter = candidate if callable(candidate) else None
    if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
        raise AttributeError("Explicit scene rect requires sceneRect/setSceneRect")
    target = QRectF(rect)
    previous_rect = QRectF(cast(Any, scene_rect_getter()))
    previous_present, previous_value = _optional_attribute(
        scene,
        _AUTOMATIC_ATTRIBUTE,
    )

    def apply_once() -> None:
        set_scene_rect_setter(QRectF(target))
        if not _rects_match(scene_rect_getter(), target):
            raise _RectTransitionVerificationError(
                "setSceneRect did not apply the explicit scene rect"
            )
        setattr(scene, _AUTOMATIC_ATTRIBUTE, False)
        if not _scene_mode_matches(scene, automatic=False):
            raise _RectTransitionVerificationError(
                "scene rect did not enter explicit mode"
            )

    try:
        _run_public_rect_transition(apply_once)
    except BaseException as original_error:
        _restore_helper_rect_after_failure(
            scene,
            scene_rect_getter,
            set_scene_rect_setter,
            previous_rect,
            automatic=(not previous_present or bool(previous_value)),
            attribute=_AUTOMATIC_ATTRIBUTE,
            attribute_present=previous_present,
            attribute_value=previous_value,
            original_error=original_error,
        )
        raise
    _, tracker = _optional_attribute(scene, _TRACKER_ATTRIBUTE)
    if isinstance(tracker, _SceneRectTracker):
        current = QRectF(target)
        tracker.known_rect = QRectF(current)
        tracker.baseline_rect = QRectF(current)
        tracker.pending_rect = QRectF(current)
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()


def view_scene_rect_is_explicit(view) -> bool:
    """Return whether Chemvas detached a view rect from its scene rect."""
    return bool(getattr(view, _VIEW_EXPLICIT_ATTRIBUTE, False))


def set_explicit_view_scene_rect(
    view,
    rect,
    *,
    scene_rect_getter: Callable[[], object] | None = None,
    set_scene_rect_setter: Callable[[QRectF], object] | None = None,
) -> None:
    """Give a view its own rect and remember that it is no longer inherited."""
    if scene_rect_getter is None:
        _, candidate = _optional_attribute(view, "sceneRect")
        scene_rect_getter = candidate if callable(candidate) else None
    if set_scene_rect_setter is None:
        _, candidate = _optional_attribute(view, "setSceneRect")
        set_scene_rect_setter = candidate if callable(candidate) else None
    if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
        raise AttributeError("Explicit view rect requires sceneRect/setSceneRect")
    target = QRectF(rect)
    previous_rect = QRectF(cast(Any, scene_rect_getter()))
    previous_present, previous_value = _optional_attribute(
        view,
        _VIEW_EXPLICIT_ATTRIBUTE,
    )

    def apply_once() -> None:
        set_scene_rect_setter(QRectF(target))
        if not _rects_match(scene_rect_getter(), target):
            raise _RectTransitionVerificationError(
                "setSceneRect did not apply the explicit view rect"
            )
        setattr(view, _VIEW_EXPLICIT_ATTRIBUTE, True)
        if not view_scene_rect_is_explicit(view):
            raise _RectTransitionVerificationError(
                "view rect did not enter explicit mode"
            )

    try:
        _run_public_rect_transition(apply_once)
    except BaseException as original_error:
        _restore_helper_rect_after_failure(
            view,
            scene_rect_getter,
            set_scene_rect_setter,
            previous_rect,
            automatic=(not previous_present or not bool(previous_value)),
            attribute=_VIEW_EXPLICIT_ATTRIBUTE,
            attribute_present=previous_present,
            attribute_value=previous_value,
            original_error=original_error,
        )
        raise


def set_inherited_view_scene_rect(view) -> None:
    """Return a view to Qt's default scene-rect inheritance mode."""
    present_getter, getter = _optional_attribute(view, "sceneRect")
    present_setter, setter = _optional_attribute(view, "setSceneRect")
    if (
        not present_getter
        or not callable(getter)
        or not present_setter
        or not callable(setter)
    ):
        raise AttributeError("Inherited view rect requires sceneRect/setSceneRect")
    previous_rect = QRectF(cast(Any, getter()))
    previous_present, previous_value = _optional_attribute(
        view,
        _VIEW_EXPLICIT_ATTRIBUTE,
    )

    def apply_once() -> None:
        inherited = _set_qt_inherited_rect_once(
            getter,
            setter,
            previous_rect,
        )
        if not _rects_match(getter(), inherited):
            raise _RectTransitionVerificationError(
                "view did not retain its inherited scene rect"
            )
        setattr(view, _VIEW_EXPLICIT_ATTRIBUTE, False)
        if view_scene_rect_is_explicit(view):
            raise _RectTransitionVerificationError(
                "view rect did not enter inherited mode"
            )

    try:
        _run_public_rect_transition(apply_once)
    except BaseException as original_error:
        _restore_helper_rect_after_failure(
            view,
            getter,
            setter,
            previous_rect,
            automatic=(not previous_present or not bool(previous_value)),
            attribute=_VIEW_EXPLICIT_ATTRIBUTE,
            attribute_present=previous_present,
            attribute_value=previous_value,
            original_error=original_error,
        )
        raise


@dataclass(slots=True)
class _SceneRectTracker:
    scene: Any
    known_rect: QRectF
    baseline_rect: QRectF
    pending_rect: QRectF
    pending_expansions: dict[int, QRectF]
    pending_journal: list[tuple[int, bool, QRectF | None]]
    depth: int = 0
    internal_change: bool = False
    accept_internal_rect: bool = False
    observed_internal_rect: bool = False
    changed_signal: object | None = None
    callback: Callable[[object], None] | None = None
    connect_port: Callable[[Callable[[object], None]], object] | None = None
    disconnect_port: Callable[[Callable[[object], None]], object] | None = None
    connection_probe: Callable[[], bool] | None = None
    signals_blocked_getter: Callable[[], object] | None = None
    connected: bool = False
    connection_uncertain: bool = False
    automatic_recovery_required: bool = False


def _optional_attribute(target, name: str) -> tuple[bool, object]:
    if inspect.getattr_static(target, name, _MISSING_ATTRIBUTE) is _MISSING_ATTRIBUTE:
        return False, _MISSING_ATTRIBUTE
    return True, getattr(target, name)


def _restore_optional_attribute(
    target,
    name: str,
    *,
    present: bool,
    value: object,
) -> None:
    if present:
        setattr(target, name, value)
        return
    if (
        inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
        is not _MISSING_ATTRIBUTE
    ):
        delattr(target, name)


def _rects_match(actual: object, expected: QRectF) -> bool:
    try:
        return QRectF(cast(Any, actual)) == expected
    except (TypeError, ValueError):
        return False


def _rect_verification_probe(target: QRectF) -> QRectF:
    width = max(1.0, abs(target.width()) + 1.0)
    height = max(1.0, abs(target.height()) + 1.0)
    return QRectF(
        target.x() + width + 137.0,
        target.y() + height + 149.0,
        width,
        height,
    )


def _set_qt_rect_mode_once(
    scene_rect: Callable[[], object],
    set_scene_rect: Callable[[QRectF], object],
    rect: QRectF,
    *,
    automatic: bool,
) -> None:
    probe = _rect_verification_probe(rect)
    set_scene_rect(QRectF(probe))
    if not _rects_match(scene_rect(), probe):
        raise _RectTransitionVerificationError(
            "setSceneRect did not apply the verification probe"
        )
    set_scene_rect(QRectF() if automatic else QRectF(rect))
    if not _rects_match(scene_rect(), rect):
        mode = "automatic" if automatic else "explicit"
        raise RuntimeError(f"setSceneRect did not restore the {mode} scene-rect value")


def _set_qt_inherited_rect_once(
    scene_rect: Callable[[], object],
    set_scene_rect: Callable[[QRectF], object],
    rect_hint: QRectF,
) -> QRectF:
    """Clear an explicit override and return Qt's authoritative live rect."""

    probe = _rect_verification_probe(rect_hint)
    set_scene_rect(QRectF(probe))
    if not _rects_match(scene_rect(), probe):
        raise _RectTransitionVerificationError(
            "setSceneRect did not apply the verification probe"
        )
    set_scene_rect(QRectF())
    live_rect = QRectF(cast(Any, scene_rect()))
    if live_rect == probe:
        raise _RectTransitionVerificationError(
            "setSceneRect did not clear the explicit scene rect"
        )
    return live_rect


def _restore_helper_rect_after_failure(
    target: object,
    scene_rect_getter: Callable[[], object],
    set_scene_rect_setter: Callable[[QRectF], object],
    rect: QRectF,
    *,
    automatic: bool,
    attribute: str,
    attribute_present: bool,
    attribute_value: object,
    original_error: BaseException,
) -> None:
    """Restore a public mode helper's exact pre-call state after failure."""

    authoritative_setter = set_scene_rect_setter
    if isinstance(target, QGraphicsScene):

        def set_authoritative_scene_rect(value: QRectF) -> object:
            return QGraphicsScene.setSceneRect(target, QRectF(value))

        authoritative_setter = set_authoritative_scene_rect
    elif isinstance(target, QGraphicsView):

        def set_authoritative_view_rect(value: QRectF) -> object:
            return QGraphicsView.setSceneRect(target, QRectF(value))

        authoritative_setter = set_authoritative_view_rect

    def restore_once() -> None:
        _set_qt_rect_mode_once(
            scene_rect_getter,
            authoritative_setter,
            rect,
            automatic=automatic,
        )
        _restore_optional_attribute(
            target,
            attribute,
            present=attribute_present,
            value=attribute_value,
        )
        if not _rects_match(scene_rect_getter(), rect):
            raise RuntimeError("rect helper recovery did not restore the prior rect")
        if not _optional_attribute_matches(
            target,
            attribute,
            present=attribute_present,
            value=attribute_value,
        ):
            raise RuntimeError("rect helper recovery did not restore the prior mode")

    try:
        _run_verified_rect_operation(restore_once)
    except BaseException as recovery_error:
        _add_secondary_note(original_error, recovery_error)


def _run_verified_rect_operation(
    operation: Callable[[], None],
) -> tuple[BaseException, ...]:
    errors: list[BaseException] = []
    for _attempt in range(2):
        try:
            operation()
        except BaseException as error:
            errors.append(error)
            continue
        return tuple(errors)
    first_error, second_error = errors
    _add_secondary_note(first_error, second_error)
    raise first_error


def _run_public_rect_transition(operation: Callable[[], None]) -> None:
    """Retry verified no-ops, while preserving setter control-flow errors."""

    errors: list[_RectTransitionVerificationError] = []
    for _attempt in range(2):
        try:
            operation()
        except _RectTransitionVerificationError as error:
            errors.append(error)
            continue
        return
    first_error, second_error = errors
    _add_secondary_note(first_error, second_error)
    raise first_error


def _optional_attribute_matches(
    target: object,
    name: str,
    *,
    present: bool,
    value: object,
) -> bool:
    actual_present, actual_value = _optional_attribute(target, name)
    if actual_present is not present:
        return False
    if not present:
        return True
    if actual_value is value:
        return True
    try:
        return bool(actual_value == value)
    except BaseException:
        return False


def _scene_mode_matches(scene: object, *, automatic: bool) -> bool:
    present, value = _optional_attribute(scene, _AUTOMATIC_ATTRIBUTE)
    return (not present and automatic) or (present and bool(value) is automatic)


def _callback_membership_probe(
    changed: object,
    callback: Callable[[object], None],
) -> Callable[[], bool] | None:
    """Capture a deterministic connection probe for lightweight test signals.

    PyQt bound signals do not expose their receiver list, so a successful
    ``disconnect`` call is authoritative there. Small signal adapters often do
    expose a mutable ``callbacks`` list; retaining that list identity lets us
    detect no-op disconnect implementations without re-reading a descriptor.
    """

    present, callbacks = _optional_attribute(changed, "callbacks")
    if not present or not isinstance(callbacks, list):
        return None
    return lambda: any(candidate is callback for candidate in callbacks)


def _tracker_connection_is_live(tracker: _SceneRectTracker) -> bool:
    probe = tracker.connection_probe
    if probe is None:
        return tracker.connected
    return bool(probe())


def _pyqt_disconnect_result_is_authoritative(signal: object | None) -> bool:
    signal_type = type(signal)
    return bool(
        signal_type.__name__ == "pyqtBoundSignal"
        and signal_type.__module__.startswith("PyQt6.")
    )


def _qgraphics_scene_rect_bound_signal(scene: object) -> object | None:
    """Bind Qt's real signal descriptor, bypassing Python-level proxies."""

    if not isinstance(scene, QGraphicsScene):
        return None
    return QGraphicsScene.sceneRectChanged.__get__(scene, type(scene))


def _rearm_qobject_tracker_once(tracker: _SceneRectTracker) -> None:
    """Rearm only the tracker callback on Qt's authoritative base signal."""

    callback = tracker.callback
    changed = _qgraphics_scene_rect_bound_signal(tracker.scene)
    if changed is None:
        raise RuntimeError("scene-rect tracker has no authoritative QObject signal")
    disconnect = getattr(changed, "disconnect", None)
    connect = getattr(changed, "connect", None)
    if callback is None or not callable(disconnect) or not callable(connect):
        raise RuntimeError("scene-rect tracker has incomplete QObject signal ports")
    try:
        disconnect(callback)
    except (TypeError, RuntimeError):
        # The specific tracker callback was already absent. Never infer which
        # receiver changed from a total receiver count: unrelated observers are
        # outside this transaction's authority.
        pass
    connect(callback)
    tracker.connected = True
    tracker.connection_uncertain = False


def _run_with_internal_scene_signals_blocked(
    tracker: _SceneRectTracker,
    operation: Callable[[], None],
) -> None:
    """Hide transaction-only rect probes from every external Qt observer."""

    scene = tracker.scene
    if not isinstance(scene, QObject):
        operation()
        return
    previous = QObject.blockSignals(scene, True)
    try:
        operation()
    finally:
        QObject.blockSignals(scene, previous)


def _read_live_rect_with_internal_signals_blocked(
    tracker: _SceneRectTracker,
    getter: Callable[[], object],
) -> QRectF:
    scene = tracker.scene
    if not isinstance(scene, QObject):
        return QRectF(cast(Any, getter()))
    previous = QObject.blockSignals(scene, True)
    try:
        return QRectF(cast(Any, getter()))
    finally:
        QObject.blockSignals(scene, previous)


def _rearm_pyqt_tracker_once(tracker: _SceneRectTracker) -> None:
    """Ensure exactly one captured PyQt receiver without emitting a probe rect."""

    if not _pyqt_disconnect_result_is_authoritative(tracker.changed_signal):
        _connect_tracker_once(tracker)
        return
    callback = tracker.callback
    disconnect = tracker.disconnect_port
    connect = tracker.connect_port
    if callback is None or not callable(disconnect) or not callable(connect):
        raise RuntimeError("scene-rect tracker has incomplete PyQt signal ports")
    try:
        disconnect(callback)
    except (TypeError, RuntimeError):
        # PyQt raises when the specific receiver was already removed. The one
        # connect below repairs that state without duplicating a live receiver.
        pass
    connect(callback)
    tracker.connected = True
    tracker.connection_uncertain = False


def _capture_view_scene_rect_updaters(
    scene: object,
) -> tuple[Callable[[QRectF], object], ...]:
    present, views_getter = _optional_attribute(scene, "views")
    if not present:
        return ()
    if not callable(views_getter):
        raise RuntimeError("scene views port is not callable")
    updaters: list[Callable[[QRectF], object]] = []
    for view in tuple(cast(Any, views_getter)()):
        if isinstance(view, QGraphicsView):
            horizontal_scrollbar = QGraphicsView.horizontalScrollBar(view)
            vertical_scrollbar = QGraphicsView.verticalScrollBar(view)
            if horizontal_scrollbar is None or vertical_scrollbar is None:
                raise RuntimeError("graphics view has no authoritative scrollbars")
            signal_targets: tuple[QObject, ...] = (
                view,
                horizontal_scrollbar,
                vertical_scrollbar,
            )

            def update_actual_view(
                rect: QRectF,
                _view: QGraphicsView = view,
                _signal_targets: tuple[QObject, ...] = signal_targets,
            ) -> object:
                result: object = None

                def apply_update() -> None:
                    nonlocal result
                    result = QGraphicsView.updateSceneRect(_view, QRectF(rect))

                _run_with_qobject_signals_blocked(
                    _signal_targets,
                    apply_update,
                )
                return result

            updaters.append(update_actual_view)
            continue
        present_update, candidate_update = _optional_attribute(
            view,
            "updateSceneRect",
        )
        if present_update and not callable(candidate_update):
            raise RuntimeError("scene view updateSceneRect port is not callable")
        if callable(candidate_update):
            updaters.append(candidate_update)
    return tuple(updaters)


def _refresh_captured_views_if_rect_changed(
    updaters: tuple[Callable[[QRectF], object], ...],
    released_rect: QRectF,
    baseline_rect: QRectF,
) -> None:
    if released_rect == baseline_rect:
        return
    for update_view_scene_rect in updaters:
        update_view_scene_rect(QRectF(released_rect))


def _run_with_qobject_signals_blocked(
    targets: tuple[QObject, ...],
    operation: Callable[[], None],
) -> None:
    """Run a Qt view refresh without publishing view/scrollbar callbacks."""

    previous_states: list[tuple[QObject, bool]] = []
    original_error: BaseException | None = None
    restore_errors: list[BaseException] = []
    try:
        seen: set[int] = set()
        for target in targets:
            identity = id(target)
            if identity in seen:
                continue
            seen.add(identity)
            previous = bool(QObject.signalsBlocked(target))
            previous_states.append((target, previous))
            QObject.blockSignals(target, True)
            if not QObject.signalsBlocked(target):
                raise RuntimeError("Qt view signal blocking did not take effect")
        operation()
    except BaseException as error:
        original_error = error
        raise
    finally:
        for target, previous in reversed(previous_states):
            try:
                QObject.blockSignals(target, previous)
                if bool(QObject.signalsBlocked(target)) is not previous:
                    raise RuntimeError(
                        "Qt view signal blocking did not restore its prior state"
                    )
            except BaseException as blocked_restore_error:
                restore_errors.append(blocked_restore_error)
        if original_error is not None:
            for secondary_error in restore_errors:
                _add_secondary_note(original_error, secondary_error)
        elif restore_errors:
            first_error = restore_errors[0]
            for secondary_error in restore_errors[1:]:
                _add_secondary_note(first_error, secondary_error)
            raise first_error


def _verify_opaque_tracker_disconnected(
    tracker: _SceneRectTracker,
    scene_rect_getter: Callable[[], object],
    set_scene_rect_setter: Callable[[QRectF], object],
    rect: QRectF,
    *,
    automatic: bool,
) -> None:
    """Prove an opaque custom signal stopped delivering the tracker callback."""

    if _tracker_signals_are_blocked(tracker):
        raise RuntimeError(
            "opaque scene-rect tracker disconnect cannot be verified while "
            "signals are blocked"
        )

    known_rect = QRectF(tracker.known_rect)
    baseline_rect = QRectF(tracker.baseline_rect)
    pending_rect = QRectF(tracker.pending_rect)
    previous_internal_change = tracker.internal_change
    previous_accept_internal_rect = tracker.accept_internal_rect
    previous_observed_internal_rect = tracker.observed_internal_rect
    callback_observed = False
    errors: list[BaseException] = []
    probe = _rect_verification_probe(rect)
    tracker.internal_change = True
    tracker.accept_internal_rect = True
    try:
        for target, expected in (
            (probe, probe),
            (QRectF() if automatic else QRectF(rect), rect),
        ):
            tracker.observed_internal_rect = False
            try:
                set_scene_rect_setter(QRectF(target))
            except BaseException as setter_error:
                errors.append(setter_error)
            try:
                if not _rects_match(scene_rect_getter(), expected):
                    errors.append(
                        RuntimeError(
                            "setSceneRect did not preserve the reversible "
                            "disconnect probe"
                        )
                    )
            except BaseException as getter_error:
                errors.append(getter_error)
            callback_observed = bool(
                callback_observed or tracker.observed_internal_rect
            )
    finally:
        # The controlled emissions are verification only. They may never become
        # tracker authority even when the captured callback was still live.
        tracker.known_rect = known_rect
        tracker.baseline_rect = baseline_rect
        tracker.pending_rect = pending_rect
        tracker.internal_change = previous_internal_change
        tracker.accept_internal_rect = previous_accept_internal_rect
        tracker.observed_internal_rect = previous_observed_internal_rect

    if callback_observed:
        errors.insert(
            0,
            RuntimeError("scene-rect tracker disconnect was a no-op"),
        )
    if errors:
        first_error = errors[0]
        for secondary_error in errors[1:]:
            _add_secondary_note(first_error, secondary_error)
        raise first_error


def _disconnect_tracker_once(
    tracker: _SceneRectTracker,
    *,
    scene_rect_getter: Callable[[], object] | None = None,
    set_scene_rect_setter: Callable[[QRectF], object] | None = None,
    rect: QRectF | None = None,
    automatic: bool = False,
) -> None:
    callback = tracker.callback
    if callback is None:
        tracker.connected = False
        return
    authoritative_qt_signal = _qgraphics_scene_rect_bound_signal(tracker.scene)
    if authoritative_qt_signal is None and not _tracker_connection_is_live(tracker):
        tracker.connected = False
        return
    disconnect = (
        getattr(authoritative_qt_signal, "disconnect", None)
        if authoritative_qt_signal is not None
        else tracker.disconnect_port
    )
    if not callable(disconnect):
        raise RuntimeError("scene-rect tracker has no captured disconnect port")
    disconnect_error: BaseException | None = None
    try:
        disconnect(callback)
    except BaseException as error:
        disconnect_error = error
    if tracker.connection_probe is not None and _tracker_connection_is_live(tracker):
        if disconnect_error is not None:
            _add_secondary_note(
                disconnect_error,
                RuntimeError("scene-rect tracker disconnect was a no-op"),
            )
            raise disconnect_error
        raise RuntimeError("scene-rect tracker disconnect was a no-op")
    if tracker.connection_probe is not None:
        tracker.connected = False
    if tracker.connection_probe is None:
        if authoritative_qt_signal is not None:
            if disconnect_error is not None and not isinstance(
                disconnect_error,
                (TypeError, RuntimeError),
            ):
                raise disconnect_error
            tracker.connected = False
        elif _pyqt_disconnect_result_is_authoritative(tracker.changed_signal):
            if disconnect_error is not None:
                if not isinstance(disconnect_error, (TypeError, RuntimeError)):
                    raise disconnect_error
            tracker.connected = False
        elif (
            callable(scene_rect_getter)
            and callable(set_scene_rect_setter)
            and rect is not None
        ):
            _verify_opaque_tracker_disconnected(
                tracker,
                scene_rect_getter,
                set_scene_rect_setter,
                rect,
                automatic=automatic,
            )
            tracker.connected = False
            if disconnect_error is not None:
                raise disconnect_error
        else:
            if disconnect_error is not None:
                raise disconnect_error
            raise RuntimeError(
                "opaque scene-rect tracker disconnect has no captured "
                "verification ports"
            )
    elif disconnect_error is not None:
        # A list-backed probe proves the callback was removed, but retain the
        # transient failure so the outer retry can record recovery evidence.
        raise disconnect_error
    tracker.connected = False


def _connect_tracker_once(tracker: _SceneRectTracker) -> None:
    callback = tracker.callback
    if callback is None:
        tracker.connected = False
        return
    if _tracker_connection_is_live(tracker):
        tracker.connected = True
        return
    connect = tracker.connect_port
    if not callable(connect):
        raise RuntimeError("scene-rect tracker has no captured connect port")
    connect(callback)
    if tracker.connection_probe is not None and not _tracker_connection_is_live(
        tracker
    ):
        raise RuntimeError("scene-rect tracker connect was a no-op")
    tracker.connected = True


def _run_connection_operation(operation: Callable[[], None]) -> None:
    errors: list[BaseException] = []
    for _attempt in range(2):
        try:
            operation()
        except BaseException as error:
            errors.append(error)
            continue
        return
    first_error, second_error = errors
    _add_secondary_note(first_error, second_error)
    raise first_error


def _raise_connection_errors(
    message: str,
    errors: list[BaseException],
) -> NoReturn:
    if not errors:
        raise RuntimeError(message)
    first_error = errors[0]
    for secondary_error in errors[1:]:
        _add_secondary_note(first_error, secondary_error)
    _add_secondary_note(first_error, RuntimeError(message))
    raise first_error


def _tracker_signals_are_blocked(tracker: _SceneRectTracker) -> bool:
    getter = tracker.signals_blocked_getter
    return bool(getter()) if callable(getter) else False


def _connect_tracker_after_missed_signal(
    tracker: _SceneRectTracker,
) -> tuple[BaseException, ...]:
    callback = tracker.callback
    connect = tracker.connect_port
    if callback is None or not callable(connect):
        raise RuntimeError("scene-rect tracker has no captured connect port")
    try:
        connect(callback)
    except BaseException as error:
        # A custom/PyQt wrapper may connect and then raise. Leave the connection
        # uncertain so the caller's next controlled setter emission, rather
        # than another blind connect, decides whether the mutation took effect.
        tracker.connection_uncertain = True
        return (error,)
    tracker.connected = True
    tracker.connection_uncertain = False
    return ()


def _set_rect_with_tracker_observation(
    tracker: _SceneRectTracker,
    scene_rect_getter: Callable[[], object],
    set_scene_rect_setter: Callable[[QRectF], object],
    rect: QRectF,
    *,
    expected_getter_rect: QRectF | None,
    callback_matches: Callable[[QRectF], bool],
) -> tuple[tuple[BaseException, ...], bool]:
    """Apply one rect and prove that the opaque callback received the signal.

    The first missed emission is allowed to re-arm the captured callback once.
    A connect that mutates and then raises is not repeated blindly: the second
    setter emission is the authority for whether it actually connected.
    """

    errors: list[BaseException] = []
    reconnected = False
    for attempt in range(2):
        tracker.observed_internal_rect = False
        setter_error: BaseException | None = None
        try:
            set_scene_rect_setter(QRectF(rect))
        except BaseException as error:
            setter_error = error
            errors.append(error)

        getter_matches = True
        if expected_getter_rect is not None:
            try:
                getter_matches = _rects_match(
                    scene_rect_getter(),
                    expected_getter_rect,
                )
            except BaseException as error:
                errors.append(error)
                getter_matches = False
            if not getter_matches and setter_error is None:
                errors.append(
                    RuntimeError(
                        "setSceneRect did not apply the verification probe or target rect"
                    )
                )

        callback_observed = bool(
            tracker.observed_internal_rect
            and callback_matches(QRectF(tracker.known_rect))
        )
        if setter_error is None and getter_matches and callback_observed:
            tracker.connected = True
            tracker.connection_uncertain = False
            return tuple(errors), reconnected

        if setter_error is not None or not getter_matches:
            tracker.connection_uncertain = True
            _raise_connection_errors(
                "scene-rect setter/getter verification failed",
                errors,
            )
        if _tracker_signals_are_blocked(tracker):
            errors.append(
                RuntimeError(
                    "scene-rect tracker callback cannot be verified while signals are blocked"
                )
            )
            break
        errors.append(RuntimeError("scene-rect tracker callback was not live"))
        if attempt == 0:
            reconnected = True
            errors.extend(_connect_tracker_after_missed_signal(tracker))

    tracker.connection_uncertain = True
    _raise_connection_errors(
        "scene-rect tracker callback could not be verified",
        errors,
    )


def _verify_tracker_connection_roundtrip(
    tracker: _SceneRectTracker,
    scene_rect_getter: Callable[[], object],
    set_scene_rect_setter: Callable[[QRectF], object],
    rect: QRectF,
    *,
    automatic: bool,
) -> tuple[BaseException, ...]:
    """Prove one stable opaque callback connection with a reversible rect probe."""

    if tracker.callback is None:
        tracker.connected = False
        tracker.connection_uncertain = False
        return ()
    if _qgraphics_scene_rect_bound_signal(tracker.scene) is not None:
        _rearm_qobject_tracker_once(tracker)
        return ()
    if _tracker_signals_are_blocked(tracker):
        # A deterministic lightweight-signal probe is still authoritative while
        # delivery is blocked. Opaque Qt signals are verified after unblocking by
        # the next release/state verification; do not create duplicate receivers.
        if tracker.connection_probe is not None:
            _connect_tracker_once(tracker)
            tracker.connection_uncertain = False
        elif not tracker.connected:
            blocked_connect_errors = _connect_tracker_after_missed_signal(tracker)
            tracker.connection_uncertain = True
            return blocked_connect_errors
        return ()

    errors: list[BaseException] = []
    probe = _rect_verification_probe(rect)
    previous_internal_change = tracker.internal_change
    previous_accept_internal_rect = tracker.accept_internal_rect
    tracker.internal_change = True
    tracker.accept_internal_rect = True
    try:
        # A reconnect during the first cycle proves liveness at that instant but
        # not stability: a later callback in the same emission may immediately
        # disconnect us. Require a second roundtrip without another reconnect.
        for _cycle in range(2):
            probe_errors, probe_reconnected = _set_rect_with_tracker_observation(
                tracker,
                scene_rect_getter,
                set_scene_rect_setter,
                probe,
                expected_getter_rect=probe,
                callback_matches=lambda observed: observed == probe,
            )
            errors.extend(probe_errors)
            target = QRectF() if automatic else QRectF(rect)
            restore_errors, restore_reconnected = _set_rect_with_tracker_observation(
                tracker,
                scene_rect_getter,
                set_scene_rect_setter,
                target,
                expected_getter_rect=rect,
                callback_matches=lambda observed: observed != probe,
            )
            errors.extend(restore_errors)
            if not probe_reconnected and not restore_reconnected:
                tracker.connection_uncertain = False
                return tuple(errors)
        errors.append(
            RuntimeError(
                "scene-rect tracker callback did not remain connected for a full roundtrip"
            )
        )
        tracker.connection_uncertain = True
        _raise_connection_errors(
            "scene-rect tracker callback connection was unstable",
            errors,
        )
    finally:
        tracker.accept_internal_rect = previous_accept_internal_rect
        tracker.internal_change = previous_internal_change


@dataclass(slots=True)
class _SceneRectTrackerStateSnapshot:
    attribute_present: bool
    attribute_value: object
    tracker: _SceneRectTracker | None
    known_rect: QRectF | None
    baseline_rect: QRectF | None
    pending_rect: QRectF | None
    pending_expansions: dict[int, QRectF] | None
    pending_expansion_items: tuple[tuple[int, QRectF], ...]
    pending_journal: list[tuple[int, bool, QRectF | None]] | None
    pending_journal_items: tuple[tuple[int, bool, QRectF | None], ...]
    depth: int | None
    internal_change: bool | None
    accept_internal_rect: bool | None
    observed_internal_rect: bool | None
    changed_signal: object | None
    callback: Callable[[object], None] | None
    connect_port: Callable[[Callable[[object], None]], object] | None
    disconnect_port: Callable[[Callable[[object], None]], object] | None
    connection_probe: Callable[[], bool] | None
    signals_blocked_getter: Callable[[], object] | None
    connected: bool | None
    connection_uncertain: bool | None
    automatic_recovery_required: bool | None

    @classmethod
    def capture(cls, scene) -> _SceneRectTrackerStateSnapshot:
        present, value = _optional_attribute(scene, _TRACKER_ATTRIBUTE)
        tracker = value if isinstance(value, _SceneRectTracker) else None
        if tracker is None:
            return cls(
                attribute_present=present,
                attribute_value=value,
                tracker=None,
                known_rect=None,
                baseline_rect=None,
                pending_rect=None,
                pending_expansions=None,
                pending_expansion_items=(),
                pending_journal=None,
                pending_journal_items=(),
                depth=None,
                internal_change=None,
                accept_internal_rect=None,
                observed_internal_rect=None,
                changed_signal=None,
                callback=None,
                connect_port=None,
                disconnect_port=None,
                connection_probe=None,
                signals_blocked_getter=None,
                connected=None,
                connection_uncertain=None,
                automatic_recovery_required=None,
            )
        return cls(
            attribute_present=present,
            attribute_value=value,
            tracker=tracker,
            known_rect=QRectF(tracker.known_rect),
            baseline_rect=QRectF(tracker.baseline_rect),
            pending_rect=QRectF(tracker.pending_rect),
            pending_expansions=tracker.pending_expansions,
            pending_expansion_items=tuple(
                (key, QRectF(rect)) for key, rect in tracker.pending_expansions.items()
            ),
            pending_journal=tracker.pending_journal,
            pending_journal_items=tuple(
                (
                    key,
                    existed,
                    QRectF(previous) if previous is not None else None,
                )
                for key, existed, previous in tracker.pending_journal
            ),
            depth=tracker.depth,
            internal_change=tracker.internal_change,
            accept_internal_rect=tracker.accept_internal_rect,
            observed_internal_rect=tracker.observed_internal_rect,
            changed_signal=tracker.changed_signal,
            callback=tracker.callback,
            connect_port=tracker.connect_port,
            disconnect_port=tracker.disconnect_port,
            connection_probe=tracker.connection_probe,
            signals_blocked_getter=tracker.signals_blocked_getter,
            connected=_tracker_connection_is_live(tracker),
            connection_uncertain=tracker.connection_uncertain,
            automatic_recovery_required=tracker.automatic_recovery_required,
        )

    def restore(
        self,
        scene,
        *,
        scene_rect_getter: Callable[[], object] | None = None,
        set_scene_rect_setter: Callable[[QRectF], object] | None = None,
        rect: QRectF | None = None,
        automatic: bool = False,
    ) -> tuple[BaseException, ...]:
        recovery_errors: list[BaseException] = []
        current_present, current_value = _optional_attribute(
            scene,
            _TRACKER_ATTRIBUTE,
        )
        current_tracker_handles_changed = bool(
            current_value is self.tracker
            and self.tracker is not None
            and (
                self.tracker.changed_signal is not self.changed_signal
                or self.tracker.callback is not self.callback
                or self.tracker.connect_port is not self.connect_port
                or self.tracker.disconnect_port is not self.disconnect_port
                or self.tracker.connection_probe is not self.connection_probe
                or self.tracker.signals_blocked_getter
                is not self.signals_blocked_getter
            )
        )
        if (
            current_present
            and isinstance(current_value, _SceneRectTracker)
            and (
                current_value is not self.attribute_value
                or current_tracker_handles_changed
            )
        ):
            if (
                current_value.connection_probe is None
                and not _pyqt_disconnect_result_is_authoritative(
                    current_value.changed_signal
                )
                and current_value.callback is not None
                and callable(scene_rect_getter)
                and callable(set_scene_rect_setter)
                and rect is not None
                and not _tracker_signals_are_blocked(current_value)
            ):
                recovery_errors.extend(
                    _verify_tracker_connection_roundtrip(
                        current_value,
                        scene_rect_getter,
                        set_scene_rect_setter,
                        rect,
                        automatic=automatic,
                    )
                )
            _disconnect_tracker_once(
                current_value,
                scene_rect_getter=scene_rect_getter,
                set_scene_rect_setter=set_scene_rect_setter,
                rect=rect,
                automatic=automatic,
            )

        tracker = self.tracker
        if tracker is not None:
            assert self.known_rect is not None
            assert self.baseline_rect is not None
            assert self.pending_rect is not None
            assert self.pending_expansions is not None
            assert self.pending_journal is not None
            assert self.depth is not None
            assert self.internal_change is not None
            assert self.accept_internal_rect is not None
            assert self.observed_internal_rect is not None
            assert self.connected is not None
            assert self.connection_uncertain is not None
            assert self.automatic_recovery_required is not None
            tracker.changed_signal = self.changed_signal
            tracker.callback = self.callback
            tracker.connect_port = self.connect_port
            tracker.disconnect_port = self.disconnect_port
            tracker.connection_probe = self.connection_probe
            tracker.signals_blocked_getter = self.signals_blocked_getter
            self.pending_expansions.clear()
            self.pending_expansions.update(
                (key, QRectF(rect)) for key, rect in self.pending_expansion_items
            )
            self.pending_journal[:] = [
                (
                    key,
                    existed,
                    QRectF(previous) if previous is not None else None,
                )
                for key, existed, previous in self.pending_journal_items
            ]
            tracker.known_rect = QRectF(self.known_rect)
            tracker.baseline_rect = QRectF(self.baseline_rect)
            tracker.pending_rect = QRectF(self.pending_rect)
            tracker.pending_expansions = self.pending_expansions
            tracker.pending_journal = self.pending_journal
            tracker.depth = self.depth
            tracker.internal_change = self.internal_change
            tracker.accept_internal_rect = self.accept_internal_rect
            tracker.observed_internal_rect = self.observed_internal_rect
        _restore_optional_attribute(
            scene,
            _TRACKER_ATTRIBUTE,
            present=self.attribute_present,
            value=self.attribute_value,
        )
        if tracker is not None:
            if self.connected:
                if tracker.connection_probe is not None:
                    _connect_tracker_once(tracker)
                elif _qgraphics_scene_rect_bound_signal(tracker.scene) is not None:
                    _rearm_qobject_tracker_once(tracker)
                elif _pyqt_disconnect_result_is_authoritative(tracker.changed_signal):
                    _rearm_pyqt_tracker_once(tracker)
                elif (
                    callable(scene_rect_getter)
                    and callable(set_scene_rect_setter)
                    and rect is not None
                ):
                    recovery_errors.extend(
                        _verify_tracker_connection_roundtrip(
                            tracker,
                            scene_rect_getter,
                            set_scene_rect_setter,
                            rect,
                            automatic=automatic,
                        )
                    )
                else:
                    _connect_tracker_once(tracker)
            else:
                _disconnect_tracker_once(
                    tracker,
                    scene_rect_getter=scene_rect_getter,
                    set_scene_rect_setter=set_scene_rect_setter,
                    rect=rect,
                    automatic=automatic,
                )
            # Connection probing uses the same callback state fields as normal
            # release. Restore every captured scalar only after the probe is
            # complete so exact-state comparison remains authoritative.
            tracker.known_rect = QRectF(cast(QRectF, self.known_rect))
            tracker.baseline_rect = QRectF(cast(QRectF, self.baseline_rect))
            tracker.pending_rect = QRectF(cast(QRectF, self.pending_rect))
            tracker.depth = cast(int, self.depth)
            tracker.internal_change = cast(bool, self.internal_change)
            tracker.accept_internal_rect = cast(
                bool,
                self.accept_internal_rect,
            )
            tracker.observed_internal_rect = cast(
                bool,
                self.observed_internal_rect,
            )
            tracker.connected = cast(bool, self.connected)
            tracker.connection_uncertain = cast(
                bool,
                self.connection_uncertain,
            )
            tracker.automatic_recovery_required = cast(
                bool, self.automatic_recovery_required
            )
        return tuple(recovery_errors)

    def matches(self, scene) -> bool:
        if not _optional_attribute_matches(
            scene,
            _TRACKER_ATTRIBUTE,
            present=self.attribute_present,
            value=self.attribute_value,
        ):
            return False
        tracker = self.tracker
        if tracker is None:
            return True
        return bool(
            tracker.known_rect == self.known_rect
            and tracker.baseline_rect == self.baseline_rect
            and tracker.pending_rect == self.pending_rect
            and tracker.pending_expansions is self.pending_expansions
            and tuple(tracker.pending_expansions.items())
            == self.pending_expansion_items
            and tracker.pending_journal is self.pending_journal
            and tuple(tracker.pending_journal) == self.pending_journal_items
            and tracker.depth == self.depth
            and tracker.internal_change == self.internal_change
            and tracker.accept_internal_rect == self.accept_internal_rect
            and tracker.observed_internal_rect == self.observed_internal_rect
            and tracker.changed_signal is self.changed_signal
            and tracker.callback is self.callback
            and tracker.connect_port is self.connect_port
            and tracker.disconnect_port is self.disconnect_port
            and tracker.connection_probe is self.connection_probe
            and tracker.signals_blocked_getter is self.signals_blocked_getter
            and tracker.connected == self.connected
            and tracker.connection_uncertain == self.connection_uncertain
            and tracker.automatic_recovery_required == self.automatic_recovery_required
            and _tracker_connection_is_live(tracker) == self.connected
        )


@dataclass(slots=True)
class SceneRectStateSnapshot:
    """Exact scene rect/mode/tracker savepoint without opening a growth guard."""

    scene: Any
    rect: QRectF
    automatic: bool
    qt_inherited: bool
    automatic_attribute_present: bool
    automatic_attribute_value: object
    tracker_state: _SceneRectTrackerStateSnapshot
    scene_rect_getter: Callable[[], object]
    set_scene_rect_setter: Callable[[QRectF], object]
    active: bool = True
    recovery_errors: list[BaseException] = field(default_factory=list)

    @classmethod
    def capture(
        cls,
        scene,
        *,
        scene_rect_getter: Callable[[], object] | None = None,
        set_scene_rect_setter: Callable[[QRectF], object] | None = None,
    ) -> SceneRectStateSnapshot:
        if scene_rect_getter is None:
            _, scene_rect = _optional_attribute(scene, "sceneRect")
            scene_rect_getter = scene_rect if callable(scene_rect) else None
        if set_scene_rect_setter is None:
            _, set_scene_rect = _optional_attribute(scene, "setSceneRect")
            set_scene_rect_setter = set_scene_rect if callable(set_scene_rect) else None
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            raise AttributeError("Scene rect savepoint requires sceneRect/setSceneRect")
        automatic_present, automatic_value = _optional_attribute(
            scene,
            _AUTOMATIC_ATTRIBUTE,
        )
        tracker_state = _SceneRectTrackerStateSnapshot.capture(scene)
        automatic = bool(automatic_value) if automatic_present else True
        temporary_guard = bool(
            tracker_state.tracker is not None
            and tracker_state.depth is not None
            and tracker_state.depth > 0
        )
        if isinstance(scene, QObject):
            previous_scene_signals = QObject.blockSignals(scene, True)
            try:
                captured_rect = QRectF(cast(Any, scene_rect_getter()))
            finally:
                QObject.blockSignals(scene, previous_scene_signals)
        else:
            captured_rect = QRectF(cast(Any, scene_rect_getter()))
        return cls(
            scene=scene,
            rect=captured_rect,
            automatic=automatic,
            qt_inherited=automatic and not temporary_guard,
            automatic_attribute_present=automatic_present,
            automatic_attribute_value=automatic_value,
            tracker_state=tracker_state,
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
        )

    def restore(self) -> None:
        if not self.active:
            return
        connection_recovery_errors: list[BaseException] = []

        def restore_once() -> None:
            tracker = self.tracker_state.tracker
            previous_internal_change = (
                tracker.internal_change
                if isinstance(tracker, _SceneRectTracker)
                else None
            )
            if isinstance(tracker, _SceneRectTracker):
                tracker.internal_change = True
            previous_scene_signals = (
                QObject.blockSignals(self.scene, True)
                if isinstance(self.scene, QObject)
                else None
            )
            try:
                _set_qt_rect_mode_once(
                    self.scene_rect_getter,
                    self.set_scene_rect_setter,
                    self.rect,
                    automatic=self.qt_inherited,
                )
            finally:
                if previous_scene_signals is not None:
                    QObject.blockSignals(
                        self.scene,
                        previous_scene_signals,
                    )
                if (
                    isinstance(tracker, _SceneRectTracker)
                    and previous_internal_change is not None
                ):
                    tracker.internal_change = previous_internal_change
            _restore_optional_attribute(
                self.scene,
                _AUTOMATIC_ATTRIBUTE,
                present=self.automatic_attribute_present,
                value=self.automatic_attribute_value,
            )
            restored_connection_errors = self.tracker_state.restore(
                self.scene,
                scene_rect_getter=self.scene_rect_getter,
                set_scene_rect_setter=self.set_scene_rect_setter,
                rect=self.rect,
                automatic=self.qt_inherited,
            )
            connection_recovery_errors[:] = restored_connection_errors
            if isinstance(self.scene, QObject):
                previous_scene_signals = QObject.blockSignals(self.scene, True)
                try:
                    restored_rect = self.scene_rect_getter()
                finally:
                    QObject.blockSignals(self.scene, previous_scene_signals)
            else:
                restored_rect = self.scene_rect_getter()
            if not _rects_match(restored_rect, self.rect):
                raise RuntimeError("scene rect did not match its captured value")
            if not _optional_attribute_matches(
                self.scene,
                _AUTOMATIC_ATTRIBUTE,
                present=self.automatic_attribute_present,
                value=self.automatic_attribute_value,
            ):
                raise RuntimeError("scene rect mode did not match its captured value")
            if not self.tracker_state.matches(self.scene):
                raise RuntimeError(
                    "scene rect tracker did not match its captured state"
                )

        self.recovery_errors.extend(_run_verified_rect_operation(restore_once))
        self.recovery_errors.extend(connection_recovery_errors)
        self.active = False

    def release(self) -> None:
        self.active = False


@dataclass(slots=True)
class ViewSceneRectStateSnapshot:
    """Exact view-owned rect mode savepoint."""

    view: Any
    rect: QRectF
    explicit: bool
    explicit_attribute_present: bool
    explicit_attribute_value: object
    scene_rect_getter: Callable[[], object]
    set_scene_rect_setter: Callable[[QRectF], object]
    active: bool = True
    recovery_errors: list[BaseException] = field(default_factory=list)

    @classmethod
    def capture(
        cls,
        view,
        *,
        scene_rect_getter: Callable[[], object] | None = None,
        set_scene_rect_setter: Callable[[QRectF], object] | None = None,
    ) -> ViewSceneRectStateSnapshot:
        if scene_rect_getter is None:
            _, scene_rect = _optional_attribute(view, "sceneRect")
            scene_rect_getter = scene_rect if callable(scene_rect) else None
        if set_scene_rect_setter is None:
            _, set_scene_rect = _optional_attribute(view, "setSceneRect")
            set_scene_rect_setter = set_scene_rect if callable(set_scene_rect) else None
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            raise AttributeError("View rect savepoint requires sceneRect/setSceneRect")
        explicit_present, explicit_value = _optional_attribute(
            view,
            _VIEW_EXPLICIT_ATTRIBUTE,
        )
        return cls(
            view=view,
            rect=QRectF(cast(Any, scene_rect_getter())),
            explicit=(bool(explicit_value) if explicit_present else False),
            explicit_attribute_present=explicit_present,
            explicit_attribute_value=explicit_value,
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
        )

    def restore(self) -> None:
        if not self.active:
            return

        def restore_once() -> None:
            _set_qt_rect_mode_once(
                self.scene_rect_getter,
                self.set_scene_rect_setter,
                self.rect,
                automatic=not self.explicit,
            )
            _restore_optional_attribute(
                self.view,
                _VIEW_EXPLICIT_ATTRIBUTE,
                present=self.explicit_attribute_present,
                value=self.explicit_attribute_value,
            )
            if not _rects_match(self.scene_rect_getter(), self.rect):
                raise RuntimeError("view rect did not match its captured value")
            if not _optional_attribute_matches(
                self.view,
                _VIEW_EXPLICIT_ATTRIBUTE,
                present=self.explicit_attribute_present,
                value=self.explicit_attribute_value,
            ):
                raise RuntimeError("view rect mode did not match its captured value")

        self.recovery_errors.extend(_run_verified_rect_operation(restore_once))
        self.active = False

    def release(self) -> None:
        self.active = False


def _repair_interrupted_capture_if_needed(
    tracker: _SceneRectTracker,
    scene: object,
    scene_rect_getter: Callable[[], object],
    set_scene_rect_setter: Callable[[QRectF], object],
) -> tuple[BaseException, ...]:
    if not tracker.automatic_recovery_required:
        return ()

    def repair_interrupted_capture() -> None:
        previous_internal_change = tracker.internal_change
        tracker.internal_change = True
        try:
            _run_with_internal_scene_signals_blocked(
                tracker,
                lambda: _set_qt_rect_mode_once(
                    scene_rect_getter,
                    set_scene_rect_setter,
                    tracker.baseline_rect,
                    automatic=True,
                ),
            )
            setattr(scene, _AUTOMATIC_ATTRIBUTE, True)
        finally:
            tracker.internal_change = previous_internal_change

    recovery_errors = _run_verified_rect_operation(repair_interrupted_capture)
    tracker.known_rect = QRectF(tracker.baseline_rect)
    tracker.pending_rect = QRectF(tracker.baseline_rect)
    tracker.automatic_recovery_required = False
    return recovery_errors


@dataclass(slots=True)
class SceneRectSnapshot:
    """Nestable guard with O(1) successful child accumulation."""

    tracker: _SceneRectTracker
    automatic: bool
    baseline_rect: QRectF
    scene_rect_getter: Callable[[], object]
    set_scene_rect_setter: Callable[[QRectF], object]
    scene_items_bounding_rect_getter: Callable[[], object] | None = None
    view_scene_rect_updaters: tuple[Callable[[QRectF], object], ...] = ()
    incremental_tracking: bool = False
    journal_index: int = 0
    guarded: bool = True
    active: bool = True
    recovery_errors: list[BaseException] = field(default_factory=list)

    @classmethod
    def capture(
        cls,
        scene,
        *,
        automatic: bool | None = None,
        guard_growth: bool = True,
        scene_rect_getter: Callable[[], object] | None = None,
        set_scene_rect_setter: Callable[[QRectF], object] | None = None,
        scene_items_bounding_rect_getter: Callable[[], object] | None = None,
        incremental_tracking: bool = False,
    ) -> SceneRectSnapshot | None:
        if scene_rect_getter is None:
            _, scene_rect = _optional_attribute(scene, "sceneRect")
            scene_rect_getter = scene_rect if callable(scene_rect) else None
        if set_scene_rect_setter is None:
            _, set_scene_rect = _optional_attribute(scene, "setSceneRect")
            set_scene_rect_setter = set_scene_rect if callable(set_scene_rect) else None
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            return None
        automatic_present, automatic_value = _optional_attribute(
            scene,
            _AUTOMATIC_ATTRIBUTE,
        )
        if automatic is None:
            automatic = bool(automatic_value) if automatic_present else True
        view_scene_rect_updaters = _capture_view_scene_rect_updaters(scene)

        _, tracker = _optional_attribute(scene, _TRACKER_ATTRIBUTE)
        recovered_capture_errors: list[BaseException] = []
        if not isinstance(tracker, _SceneRectTracker):
            if isinstance(scene, QObject):
                previous_scene_signals = QObject.blockSignals(scene, True)
                try:
                    current = QRectF(cast(Any, scene_rect_getter()))
                finally:
                    QObject.blockSignals(scene, previous_scene_signals)
            else:
                current = QRectF(cast(Any, scene_rect_getter()))
            _, signals_blocked = _optional_attribute(scene, "signalsBlocked")
            tracker = _SceneRectTracker(
                scene=scene,
                known_rect=QRectF(current),
                baseline_rect=QRectF(current),
                pending_rect=QRectF(current),
                pending_expansions={},
                pending_journal=[],
                signals_blocked_getter=(
                    signals_blocked if callable(signals_blocked) else None
                ),
            )
            authoritative_changed = _qgraphics_scene_rect_bound_signal(scene)
            if authoritative_changed is not None:
                changed_present, changed = True, authoritative_changed
            else:
                changed_present, changed = _optional_attribute(
                    scene,
                    "sceneRectChanged",
                )
            connect_present, connect = _optional_attribute(changed, "connect")
            disconnect_present, disconnect = _optional_attribute(
                changed,
                "disconnect",
            )
            remember_external_rect: Callable[[object], None] | None = None
            if changed_present or connect_present or disconnect_present:
                if not callable(connect) or not callable(disconnect):
                    raise RuntimeError(
                        "sceneRectChanged must expose connect/disconnect together"
                    )

                def remember_external_rect(rect: object, *, state=tracker) -> None:
                    if state.accept_internal_rect:
                        state.known_rect = QRectF(cast(Any, rect))
                        state.observed_internal_rect = True
                        return
                    if state.internal_change or state.depth:
                        return
                    state.known_rect = QRectF(cast(Any, rect))

                tracker.changed_signal = changed
                tracker.callback = remember_external_rect
                tracker.connect_port = connect
                tracker.disconnect_port = disconnect
                tracker.connection_probe = _callback_membership_probe(
                    changed,
                    remember_external_rect,
                )
                try:
                    connect(remember_external_rect)
                except BaseException as original_error:
                    tracker.connection_uncertain = True
                    tracker.connected = (
                        _tracker_connection_is_live(tracker)
                        if tracker.connection_probe is not None
                        else True
                    )
                    try:
                        _run_connection_operation(
                            lambda: _disconnect_tracker_once(
                                tracker,
                                scene_rect_getter=scene_rect_getter,
                                set_scene_rect_setter=set_scene_rect_setter,
                                rect=current,
                                automatic=automatic,
                            )
                        )
                    except BaseException as disconnect_error:
                        _add_secondary_note(original_error, disconnect_error)
                        # Retain explicit ownership if a mutating connect raised
                        # and its captured disconnect port cannot remove the
                        # callback. A later state restore can retry cleanup.
                        try:
                            setattr(scene, _TRACKER_ATTRIBUTE, tracker)
                        except BaseException as publish_error:
                            _add_secondary_note(original_error, publish_error)
                    raise
                tracker.connected = True
                tracker.connection_uncertain = False
                if (
                    tracker.connection_probe is not None
                    and not _tracker_connection_is_live(tracker)
                ):
                    connect_error = RuntimeError(
                        "scene-rect tracker connect was a no-op"
                    )
                    try:
                        _run_connection_operation(
                            lambda: _disconnect_tracker_once(
                                tracker,
                                scene_rect_getter=scene_rect_getter,
                                set_scene_rect_setter=set_scene_rect_setter,
                                rect=current,
                                automatic=automatic,
                            )
                        )
                    except BaseException as disconnect_error:
                        _add_secondary_note(connect_error, disconnect_error)
                    raise connect_error
            try:
                setattr(scene, _TRACKER_ATTRIBUTE, tracker)
            except BaseException as original_error:
                _remove_partially_published_tracker(
                    scene,
                    tracker,
                    original_error,
                )
                if remember_external_rect is not None:
                    try:
                        _run_connection_operation(
                            lambda: _disconnect_tracker_once(
                                tracker,
                                scene_rect_getter=scene_rect_getter,
                                set_scene_rect_setter=set_scene_rect_setter,
                                rect=current,
                                automatic=automatic,
                            )
                        )
                    except BaseException as disconnect_error:
                        _add_secondary_note(original_error, disconnect_error)
                raise

        elif (
            tracker.depth == 0
            and (not automatic or not incremental_tracking)
            and not tracker.automatic_recovery_required
        ):
            # A prior raw setter may have run while scene signals were blocked,
            # leaving the persistent tracker stale in either rect mode.
            # Automatic hint-complete attach paths retain their O(1) rolling
            # authority; every explicit outer capture synchronizes the live
            # bound getter because that exact value is its rollback authority.
            current = _read_live_rect_with_internal_signals_blocked(
                tracker,
                scene_rect_getter,
            )
            tracker.known_rect = QRectF(current)
            tracker.baseline_rect = QRectF(current)
            tracker.pending_rect = QRectF(current)

        recovered_capture_errors.extend(
            _repair_interrupted_capture_if_needed(
                tracker,
                scene,
                scene_rect_getter,
                set_scene_rect_setter,
            )
        )

        if not automatic:
            tracker.baseline_rect = QRectF(tracker.known_rect)
            return cls(
                tracker=tracker,
                automatic=False,
                baseline_rect=QRectF(tracker.known_rect),
                scene_rect_getter=scene_rect_getter,
                set_scene_rect_setter=set_scene_rect_setter,
                scene_items_bounding_rect_getter=(scene_items_bounding_rect_getter),
                view_scene_rect_updaters=view_scene_rect_updaters,
                incremental_tracking=incremental_tracking,
                journal_index=len(tracker.pending_journal),
                guarded=False,
                recovery_errors=list(recovered_capture_errors),
            )

        if not guard_growth:
            tracker.baseline_rect = QRectF(tracker.known_rect)
            return cls(
                tracker=tracker,
                automatic=True,
                baseline_rect=QRectF(tracker.known_rect),
                scene_rect_getter=scene_rect_getter,
                set_scene_rect_setter=set_scene_rect_setter,
                scene_items_bounding_rect_getter=(scene_items_bounding_rect_getter),
                view_scene_rect_updaters=view_scene_rect_updaters,
                incremental_tracking=incremental_tracking,
                journal_index=len(tracker.pending_journal),
                guarded=False,
                recovery_errors=list(recovered_capture_errors),
            )

        if tracker.depth == 0:
            tracker.baseline_rect = QRectF(tracker.known_rect)
            tracker.pending_rect = QRectF(tracker.known_rect)
            tracker.pending_expansions.clear()
            tracker.pending_journal.clear()
            # A null QRectF means automatic mode and cannot guard growth. Use a
            # tiny non-null temporary rect for an empty scene; it is removed on
            # release/restore before control returns to the caller.
            guard_rect = QRectF(tracker.baseline_rect)
            if guard_rect.isNull():
                guard_rect = QRectF(-0.5, -0.5, 1.0, 1.0)
            tracker.internal_change = True
            try:
                _run_with_internal_scene_signals_blocked(
                    tracker,
                    lambda: _set_qt_rect_mode_once(
                        scene_rect_getter,
                        set_scene_rect_setter,
                        guard_rect,
                        automatic=False,
                    ),
                )
            except BaseException as original_error:
                # The setter can mutate before raising. Replay the complete
                # verified automatic-mode transition twice, preserving the
                # original cancellation/termination signal as the authority.
                tracker.automatic_recovery_required = True
                try:
                    cleanup_errors = _run_verified_rect_operation(
                        lambda: _run_with_internal_scene_signals_blocked(
                            tracker,
                            lambda: _set_qt_rect_mode_once(
                                scene_rect_getter,
                                set_scene_rect_setter,
                                tracker.baseline_rect,
                                automatic=True,
                            ),
                        )
                    )
                except BaseException as cleanup_error:
                    _add_secondary_note(original_error, cleanup_error)
                else:
                    for recovered_cleanup_error in cleanup_errors:
                        _add_secondary_note(
                            original_error,
                            recovered_cleanup_error,
                        )
                    _restore_optional_attribute(
                        scene,
                        _AUTOMATIC_ATTRIBUTE,
                        present=automatic_present,
                        value=automatic_value,
                    )
                    tracker.automatic_recovery_required = False
                tracker.depth = 0
                tracker.known_rect = QRectF(tracker.baseline_rect)
                tracker.pending_rect = QRectF(tracker.baseline_rect)
                tracker.pending_expansions.clear()
                tracker.pending_journal.clear()
                raise
            finally:
                tracker.internal_change = False
        tracker.depth += 1
        return cls(
            tracker=tracker,
            automatic=True,
            baseline_rect=QRectF(tracker.baseline_rect),
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
            scene_items_bounding_rect_getter=(scene_items_bounding_rect_getter),
            view_scene_rect_updaters=view_scene_rect_updaters,
            incremental_tracking=incremental_tracking,
            journal_index=len(tracker.pending_journal),
            recovery_errors=list(recovered_capture_errors),
        )

    def _rewind_pending_expansions(self) -> None:
        tracker = self.tracker
        checkpoint = min(self.journal_index, len(tracker.pending_journal))
        if checkpoint == len(tracker.pending_journal):
            return
        for key, existed, previous in reversed(tracker.pending_journal[checkpoint:]):
            if existed and previous is not None:
                tracker.pending_expansions[key] = QRectF(previous)
            else:
                tracker.pending_expansions.pop(key, None)
        del tracker.pending_journal[checkpoint:]
        tracker.pending_rect = QRectF(tracker.baseline_rect)
        for candidate in tracker.pending_expansions.values():
            tracker.pending_rect = tracker.pending_rect.united(candidate)

    def release(  # noqa: C901
        self,
        expanded_rect: QRectF | None = None,
        *,
        expansion_key: object | None = None,
        expansion_owner_scene_getter: Callable[[], object] | None = None,
        authoritative_scene_bounds_getter: Callable[[], object] | None = None,
    ) -> None:
        """Commit a successful mutation and return the scene to auto mode."""
        if not self.active:
            return
        tracker = self.tracker
        if not self.automatic:
            self.active = False
            return
        if not self.guarded:
            self.active = False
            return
        expansion_owner_is_live = True
        if expansion_key is not None:
            if expansion_owner_scene_getter is not None:
                if expansion_owner_scene_getter() is not tracker.scene:
                    expansion_owner_is_live = False
            else:
                scene_port_present, scene_port = _optional_attribute(
                    expansion_key,
                    "scene",
                )
                if scene_port_present:
                    if not callable(scene_port):
                        raise RuntimeError(
                            "scene rect expansion owner has no callable scene port"
                        )
                    if scene_port() is not tracker.scene:
                        expansion_owner_is_live = False
            if not expansion_owner_is_live:
                expanded_rect = None
                key = id(expansion_key)
                previous = tracker.pending_expansions.get(key)
                if previous is not None:
                    tracker.pending_journal.append((key, True, QRectF(previous)))
                    tracker.pending_expansions.pop(key, None)
        if expanded_rect is not None and not expanded_rect.isNull():
            key = id(expansion_key) if expansion_key is not None else id(self)
            candidate = QRectF(expanded_rect)
            existed = key in tracker.pending_expansions
            previous = tracker.pending_expansions.get(key)
            if not existed or previous != candidate:
                tracker.pending_journal.append(
                    (
                        key,
                        existed,
                        QRectF(previous) if previous is not None else None,
                    )
                )
                tracker.pending_expansions[key] = candidate
                # Keep nested releases O(1), including the common mark
                # lifecycle that records an item before and after centering.
                tracker.pending_rect = tracker.pending_rect.united(candidate)
        if tracker.depth > 1:
            tracker.depth -= 1
            self.active = False
            return
        authoritative_bounds = None
        if callable(authoritative_scene_bounds_getter):
            authoritative_bounds = QRectF(
                cast(Any, authoritative_scene_bounds_getter())
            )
        pending_rect = QRectF(tracker.baseline_rect)
        for pending_candidate in tracker.pending_expansions.values():
            pending_rect = pending_rect.united(pending_candidate)
        if authoritative_bounds is not None and not authoritative_bounds.isNull():
            pending_rect = pending_rect.united(authoritative_bounds)
        released_rect = QRectF(tracker.known_rect)
        connection_recovery_errors: list[BaseException] = []
        scene_authority = tracker.scene
        tracker_authority = tracker
        active_authority = self.active
        automatic_authority = self.automatic
        baseline_rect_authority = QRectF(self.baseline_rect)
        scene_rect_getter_authority = self.scene_rect_getter
        set_scene_rect_setter_authority = self.set_scene_rect_setter
        scene_items_bounding_rect_getter_authority = (
            self.scene_items_bounding_rect_getter
        )
        view_scene_rect_updaters_authority = self.view_scene_rect_updaters
        incremental_tracking_authority = self.incremental_tracking
        journal_index_authority = self.journal_index
        guarded_authority = self.guarded

        def release_once() -> None:  # noqa: C901
            nonlocal released_rect
            tracker_present, tracker_value = _optional_attribute(
                scene_authority,
                _TRACKER_ATTRIBUTE,
            )
            if not tracker_present or tracker_value is not tracker:
                raise RuntimeError("scene rect release lost tracker ownership")
            if tracker.depth != 1:
                raise RuntimeError("scene rect release lost its outer guard depth")
            previous_internal_change = tracker.internal_change
            previous_accept_internal_rect = tracker.accept_internal_rect
            tracker.internal_change = True
            tracker.accept_internal_rect = True
            try:
                guard_rect = QRectF(baseline_rect_authority)
                if guard_rect.isNull():
                    guard_rect = QRectF(-0.5, -0.5, 1.0, 1.0)
                view_refresh_rect = QRectF(pending_rect)
                if (
                    view_scene_rect_updaters_authority
                    and view_refresh_rect == baseline_rect_authority
                    and not incremental_tracking_authority
                ):
                    current_scene_bounds = None
                    if isinstance(scene_authority, QGraphicsScene):
                        current_scene_bounds = QGraphicsScene.itemsBoundingRect(
                            scene_authority
                        )
                    elif callable(scene_items_bounding_rect_getter_authority):
                        current_scene_bounds = QRectF(
                            cast(Any, scene_items_bounding_rect_getter_authority())
                        )
                    if (
                        current_scene_bounds is not None
                        and not current_scene_bounds.isNull()
                    ):
                        view_refresh_rect = view_refresh_rect.united(
                            current_scene_bounds
                        )

                # All fallible/untrusted view callbacks run while Qt still owns
                # the temporary explicit guard. If they fail or poison the
                # scene, the automatic grow-only cache has not been published
                # and this active savepoint remains exactly rollbackable.
                if (
                    view_scene_rect_updaters_authority
                    and view_refresh_rect != baseline_rect_authority
                ):
                    _run_with_internal_scene_signals_blocked(
                        tracker,
                        lambda: _set_qt_rect_mode_once(
                            scene_rect_getter_authority,
                            set_scene_rect_setter_authority,
                            guard_rect,
                            automatic=False,
                        ),
                    )
                    tracker_state_authority = _SceneRectTrackerStateSnapshot.capture(
                        scene_authority
                    )
                    automatic_present, automatic_value = _optional_attribute(
                        scene_authority,
                        _AUTOMATIC_ATTRIBUTE,
                    )
                    try:
                        _run_with_internal_scene_signals_blocked(
                            tracker,
                            lambda: _refresh_captured_views_if_rect_changed(
                                view_scene_rect_updaters_authority,
                                view_refresh_rect,
                                baseline_rect_authority,
                            ),
                        )
                        tracker_present, tracker_value = _optional_attribute(
                            scene_authority,
                            _TRACKER_ATTRIBUTE,
                        )
                        if not tracker_present or tracker_value is not tracker:
                            raise RuntimeError(
                                "view scene-rect refresh replaced tracker ownership"
                            )
                        if tracker.depth != 1:
                            raise RuntimeError(
                                "view scene-rect refresh changed the guard depth"
                            )
                        if self.tracker is not tracker_authority:
                            raise RuntimeError(
                                "view scene-rect refresh changed the snapshot tracker"
                            )
                        if self.active is not active_authority:
                            raise RuntimeError(
                                "view scene-rect refresh changed the active savepoint"
                            )
                        if tracker.scene is not scene_authority:
                            raise RuntimeError(
                                "view scene-rect refresh changed the tracker scene"
                            )
                        if not _scene_mode_matches(
                            scene_authority,
                            automatic=True,
                        ):
                            raise RuntimeError(
                                "view scene-rect refresh changed the scene rect mode"
                            )
                        guarded_live_rect = (
                            _read_live_rect_with_internal_signals_blocked(
                                tracker,
                                scene_rect_getter_authority,
                            )
                        )
                        if guarded_live_rect != guard_rect:
                            raise RuntimeError(
                                "view scene-rect refresh changed the guarded scene rect"
                            )
                        if not tracker_state_authority.matches(scene_authority):
                            raise RuntimeError(
                                "view scene-rect refresh changed tracker state"
                            )
                    except BaseException as original_error:
                        restored_connection_errors: list[BaseException] = []

                        def restore_view_refresh_authority() -> None:
                            tracker.scene = scene_authority
                            self.tracker = tracker_authority
                            self.active = active_authority
                            self.automatic = automatic_authority
                            self.baseline_rect = QRectF(baseline_rect_authority)
                            self.scene_rect_getter = scene_rect_getter_authority
                            self.set_scene_rect_setter = set_scene_rect_setter_authority
                            self.scene_items_bounding_rect_getter = (
                                scene_items_bounding_rect_getter_authority
                            )
                            self.view_scene_rect_updaters = (
                                view_scene_rect_updaters_authority
                            )
                            self.incremental_tracking = incremental_tracking_authority
                            self.journal_index = journal_index_authority
                            self.guarded = guarded_authority
                            restored_connection_errors[:] = (
                                tracker_state_authority.restore(
                                    scene_authority,
                                    scene_rect_getter=(scene_rect_getter_authority),
                                    set_scene_rect_setter=(
                                        set_scene_rect_setter_authority
                                    ),
                                    rect=guard_rect,
                                    automatic=False,
                                )
                            )
                            _run_with_internal_scene_signals_blocked(
                                tracker,
                                lambda: _set_qt_rect_mode_once(
                                    scene_rect_getter_authority,
                                    set_scene_rect_setter_authority,
                                    guard_rect,
                                    automatic=False,
                                ),
                            )
                            _restore_optional_attribute(
                                scene_authority,
                                _AUTOMATIC_ATTRIBUTE,
                                present=automatic_present,
                                value=automatic_value,
                            )
                            tracker.scene = scene_authority
                            self.tracker = tracker_authority
                            self.active = active_authority
                            if not _rects_match(
                                _read_live_rect_with_internal_signals_blocked(
                                    tracker,
                                    scene_rect_getter_authority,
                                ),
                                guard_rect,
                            ):
                                raise RuntimeError(
                                    "view refresh unwind lost the guarded scene rect"
                                )
                            if not _optional_attribute_matches(
                                scene_authority,
                                _AUTOMATIC_ATTRIBUTE,
                                present=automatic_present,
                                value=automatic_value,
                            ):
                                raise RuntimeError(
                                    "view refresh unwind lost the scene rect mode"
                                )
                            if not tracker_state_authority.matches(scene_authority):
                                raise RuntimeError(
                                    "view refresh unwind lost tracker authority"
                                )

                        try:
                            recovered_errors = _run_verified_rect_operation(
                                restore_view_refresh_authority
                            )
                        except BaseException as recovery_error:
                            _add_secondary_note(original_error, recovery_error)
                        else:
                            for recovered_error_note in (
                                *recovered_errors,
                                *restored_connection_errors,
                            ):
                                _add_secondary_note(
                                    original_error,
                                    recovered_error_note,
                                )
                        raise

                if _qgraphics_scene_rect_bound_signal(tracker.scene) is not None:
                    _rearm_qobject_tracker_once(tracker)
                elif _pyqt_disconnect_result_is_authoritative(tracker.changed_signal):
                    _rearm_pyqt_tracker_once(tracker)

                if _qgraphics_scene_rect_bound_signal(
                    tracker.scene
                ) is not None or _pyqt_disconnect_result_is_authoritative(
                    tracker.changed_signal
                ):

                    def restore_inherited_mode() -> None:
                        nonlocal released_rect
                        if incremental_tracking_authority:
                            # The builtin hint-complete attach path already
                            # owns the exact grow-only union. Verify the setter
                            # on an explicit probe, then clear it without an
                            # O(n) inherited sceneRect read.
                            probe = _rect_verification_probe(pending_rect)
                            set_scene_rect_setter_authority(QRectF(probe))
                            if not _rects_match(
                                scene_rect_getter_authority(),
                                probe,
                            ):
                                raise RuntimeError(
                                    "setSceneRect did not apply the release probe"
                                )
                            set_scene_rect_setter_authority(QRectF())
                            released_rect = QRectF(pending_rect)
                            return
                        released_rect = _set_qt_inherited_rect_once(
                            scene_rect_getter_authority,
                            set_scene_rect_setter_authority,
                            pending_rect,
                        )

                    _run_with_internal_scene_signals_blocked(
                        tracker,
                        restore_inherited_mode,
                    )
                elif tracker.callback is not None:
                    probe = _rect_verification_probe(pending_rect)
                    recovered: list[BaseException] = []
                    stable = False
                    for _cycle in range(2):
                        probe_errors, probe_reconnected = (
                            _set_rect_with_tracker_observation(
                                tracker,
                                scene_rect_getter_authority,
                                set_scene_rect_setter_authority,
                                probe,
                                expected_getter_rect=probe,
                                callback_matches=lambda observed: observed == probe,
                            )
                        )
                        recovered.extend(probe_errors)
                        inherited_errors, inherited_reconnected = (
                            _set_rect_with_tracker_observation(
                                tracker,
                                scene_rect_getter_authority,
                                set_scene_rect_setter_authority,
                                QRectF(),
                                expected_getter_rect=None,
                                callback_matches=lambda observed: observed != probe,
                            )
                        )
                        recovered.extend(inherited_errors)
                        if not probe_reconnected and not inherited_reconnected:
                            stable = True
                            break
                    if not stable:
                        recovered.append(
                            RuntimeError(
                                "scene-rect tracker callback did not remain connected during release"
                            )
                        )
                        _raise_connection_errors(
                            "scene-rect tracker callback was unstable during release",
                            recovered,
                        )
                    connection_recovery_errors[:] = recovered
                    # Qt computes the items-derived live rect lazily. The
                    # pending union is the O(1) authoritative lower bound; an
                    # eager sceneRect() read here would make sequential inserts
                    # quadratic.
                    released_rect = QRectF(pending_rect)
                else:
                    released_rect = _set_qt_inherited_rect_once(
                        scene_rect_getter_authority,
                        set_scene_rect_setter_authority,
                        pending_rect,
                    )
                    if not released_rect.contains(pending_rect):
                        raise RuntimeError(
                            "automatic scene rect omitted its committed expansion"
                        )
                setattr(scene_authority, _AUTOMATIC_ATTRIBUTE, True)
                if not _scene_mode_matches(scene_authority, automatic=True):
                    raise RuntimeError(
                        "scene rect release did not restore automatic mode"
                    )
                tracker_present, tracker_value = _optional_attribute(
                    scene_authority,
                    _TRACKER_ATTRIBUTE,
                )
                if not tracker_present or tracker_value is not tracker:
                    raise RuntimeError("scene rect release lost tracker ownership")
                if tracker.depth != 1:
                    raise RuntimeError("scene rect release lost its outer guard depth")
            finally:
                tracker.accept_internal_rect = previous_accept_internal_rect
                tracker.internal_change = previous_internal_change

        self.recovery_errors.extend(_run_verified_rect_operation(release_once))
        self.recovery_errors.extend(connection_recovery_errors)
        tracker.pending_rect = QRectF(released_rect)
        tracker.known_rect = QRectF(released_rect)
        tracker.observed_internal_rect = False
        tracker.depth = 0
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        self.active = False

    def commit_replacement(self, expanded_rect: QRectF | None = None) -> None:
        """Close this savepoint while preserving a replacement's rect mode.

        A document replacement can legitimately switch an automatic old scene
        to Chemvas' explicit sheet rect. A normal ``release`` would instead
        put that replacement back into automatic mode, so replacement owners
        use this mode-aware finalizer.
        """
        if not self.active:
            return
        tracker = self.tracker
        scene = tracker.scene
        if scene_rect_is_automatic(scene):
            if self.automatic and self.guarded:
                self.release(expanded_rect)
                return
            current = _read_live_rect_with_internal_signals_blocked(
                tracker,
                self.scene_rect_getter,
            )
            if not _scene_mode_matches(scene, automatic=True):
                raise RuntimeError(
                    "replacement scene rect did not retain automatic mode"
                )
            tracker.known_rect = QRectF(current)
            tracker.baseline_rect = QRectF(current)
            tracker.pending_rect = QRectF(current)
            tracker.pending_expansions.clear()
            tracker.pending_journal.clear()
            setattr(scene, _AUTOMATIC_ATTRIBUTE, True)
            self.active = False
            return

        current = _read_live_rect_with_internal_signals_blocked(
            tracker,
            self.scene_rect_getter,
        )
        if not _scene_mode_matches(scene, automatic=False):
            raise RuntimeError("replacement scene rect did not retain explicit mode")
        if self.automatic and self.guarded:
            if tracker.depth < 1:
                raise RuntimeError("scene rect guard depth underflow during commit")
            tracker.depth -= 1
        tracker.known_rect = QRectF(current)
        tracker.baseline_rect = QRectF(current)
        tracker.pending_rect = QRectF(current)
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        setattr(scene, _AUTOMATIC_ATTRIBUTE, False)
        self.active = False

    def _restore_automatic_scene_rect(self) -> None:
        """Restore Qt's inherited rect mode without consuming a failed savepoint."""

        tracker = self.tracker
        restored_rect = QRectF(self.baseline_rect)

        def restore_once() -> None:
            nonlocal restored_rect
            previous_internal_change = tracker.internal_change
            previous_accept_internal_rect = tracker.accept_internal_rect
            tracker.internal_change = True
            tracker.accept_internal_rect = False
            try:

                def restore_inherited() -> None:
                    nonlocal restored_rect
                    restored_rect = _set_qt_inherited_rect_once(
                        self.scene_rect_getter,
                        self.set_scene_rect_setter,
                        self.baseline_rect,
                    )

                _run_with_internal_scene_signals_blocked(
                    tracker,
                    restore_inherited,
                )

                # Publish the logical mode only after both Qt operations
                # succeed. If publication fails, the active savepoint can
                # replay the complete operation on its second attempt.
                setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, True)
                if not _rects_match(
                    _read_live_rect_with_internal_signals_blocked(
                        tracker,
                        self.scene_rect_getter,
                    ),
                    restored_rect,
                ):
                    raise RuntimeError(
                        "scene rect restore did not preserve its baseline"
                    )
                if not _scene_mode_matches(tracker.scene, automatic=True):
                    raise RuntimeError(
                        "scene rect restore did not restore automatic mode"
                    )
            finally:
                tracker.accept_internal_rect = previous_accept_internal_rect
                tracker.internal_change = previous_internal_change

        self.recovery_errors.extend(_run_verified_rect_operation(restore_once))
        self.baseline_rect = QRectF(restored_rect)

    def _restore_explicit_scene_rect(self) -> None:
        tracker = self.tracker

        def restore_once() -> None:
            previous_internal_change = tracker.internal_change
            tracker.internal_change = True
            try:
                _run_with_internal_scene_signals_blocked(
                    tracker,
                    lambda: _set_qt_rect_mode_once(
                        self.scene_rect_getter,
                        self.set_scene_rect_setter,
                        self.baseline_rect,
                        automatic=False,
                    ),
                )
                setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, False)
                if not _rects_match(
                    _read_live_rect_with_internal_signals_blocked(
                        tracker,
                        self.scene_rect_getter,
                    ),
                    self.baseline_rect,
                ):
                    raise RuntimeError(
                        "explicit scene rect restore did not preserve its baseline"
                    )
                if not _scene_mode_matches(tracker.scene, automatic=False):
                    raise RuntimeError(
                        "scene rect restore did not restore explicit mode"
                    )
            finally:
                tracker.internal_change = previous_internal_change

        self.recovery_errors.extend(_run_verified_rect_operation(restore_once))

    def restore(self) -> None:
        """Abort a mutation after its item was detached, preserving auto mode."""
        if not self.active:
            return
        tracker = self.tracker
        if not self.automatic:
            baseline_rect = self.baseline_rect
            self._restore_explicit_scene_rect()
            tracker.known_rect = QRectF(baseline_rect)
            tracker.baseline_rect = QRectF(baseline_rect)
            tracker.pending_rect = QRectF(baseline_rect)
            self.active = False
            return
        if not self.guarded:
            self._restore_automatic_scene_rect()
            baseline_rect = self.baseline_rect
            tracker.known_rect = QRectF(baseline_rect)
            tracker.baseline_rect = QRectF(baseline_rect)
            tracker.pending_rect = QRectF(baseline_rect)
            self.active = False
            return
        if tracker.depth > 1:
            self._rewind_pending_expansions()
            tracker.depth -= 1
            self.active = False
            return
        self._restore_automatic_scene_rect()
        baseline_rect = self.baseline_rect
        tracker.depth = 0
        tracker.baseline_rect = QRectF(baseline_rect)
        tracker.pending_rect = QRectF(baseline_rect)
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        tracker.known_rect = QRectF(baseline_rect)
        self.active = False


__all__ = [
    "SceneRectSnapshot",
    "SceneRectStateSnapshot",
    "ViewSceneRectStateSnapshot",
    "scene_rect_is_automatic",
    "set_explicit_scene_rect",
    "set_explicit_view_scene_rect",
    "set_inherited_view_scene_rect",
    "view_scene_rect_is_explicit",
]
