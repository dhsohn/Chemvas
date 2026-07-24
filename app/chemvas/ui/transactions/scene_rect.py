"""Scene-rect modes and the growth guard for canvas transactions.

Chemvas scenes run in one of two modes. "Explicit" is the production default:
a fixed sheet rect applied by sheet setup. "Automatic" is Qt\'s inherited
mode (a null ``setSceneRect``), where ``sceneRect()`` follows the items and
only ever grows. The growth guard exists for the automatic mode: a mutation
that fails and rolls back must not leave the scene permanently enlarged, so
a transaction pins a temporary explicit rect, records the geometry it added
as O(1) expansion hints, and re-enters automatic mode on release with the
recorded growth (or drops it on restore). Guards nest; each nesting level
journals its expansion writes so an aborted child can be rewound without
rescanning its siblings.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, cast

from PyQt6.QtCore import QObject, QRectF
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

_TRACKER_ATTRIBUTE = "_chemvas_scene_rect_tracker"
_AUTOMATIC_ATTRIBUTE = "_chemvas_scene_rect_automatic"
_VIEW_EXPLICIT_ATTRIBUTE = "_chemvas_view_scene_rect_explicit"

# An automatic empty scene cannot pin a null guard rect; use a tiny one.
_EMPTY_GUARD_RECT = QRectF(-0.5, -0.5, 1.0, 1.0)


def scene_rect_is_automatic(scene) -> bool:
    return bool(getattr(scene, _AUTOMATIC_ATTRIBUTE, True))


def view_scene_rect_is_explicit(view) -> bool:
    """Return whether Chemvas detached a view rect from its scene rect."""

    return bool(getattr(view, _VIEW_EXPLICIT_ATTRIBUTE, False))


def _resolve_rect_ports(
    target,
    scene_rect_getter: Callable[[], object] | None,
    set_scene_rect_setter: Callable[[QRectF], object] | None,
) -> tuple[Callable[[], object] | None, Callable[[QRectF], object] | None]:
    if scene_rect_getter is None:
        candidate = getattr(target, "sceneRect", None)
        scene_rect_getter = candidate if callable(candidate) else None
    if set_scene_rect_setter is None:
        candidate = getattr(target, "setSceneRect", None)
        set_scene_rect_setter = candidate if callable(candidate) else None
    return scene_rect_getter, set_scene_rect_setter


def set_explicit_scene_rect(
    scene,
    rect,
    *,
    scene_rect_getter: Callable[[], object] | None = None,
    set_scene_rect_setter: Callable[[QRectF], object] | None = None,
) -> None:
    """Set Chemvas' fixed sheet rect and keep an existing tracker coherent."""

    scene_rect_getter, set_scene_rect_setter = _resolve_rect_ports(
        scene,
        scene_rect_getter,
        set_scene_rect_setter,
    )
    if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
        raise AttributeError("Explicit scene rect requires sceneRect/setSceneRect")
    target = QRectF(rect)
    set_scene_rect_setter(QRectF(target))
    setattr(scene, _AUTOMATIC_ATTRIBUTE, False)
    tracker = getattr(scene, _TRACKER_ATTRIBUTE, None)
    if isinstance(tracker, _SceneRectTracker):
        tracker.known_rect = QRectF(target)
        tracker.baseline_rect = QRectF(target)
        tracker.pending_rect = QRectF(target)
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()


def set_explicit_view_scene_rect(
    view,
    rect,
    *,
    scene_rect_getter: Callable[[], object] | None = None,
    set_scene_rect_setter: Callable[[QRectF], object] | None = None,
) -> None:
    """Give a view its own rect and remember that it is no longer inherited."""

    scene_rect_getter, set_scene_rect_setter = _resolve_rect_ports(
        view,
        scene_rect_getter,
        set_scene_rect_setter,
    )
    if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
        raise AttributeError("Explicit view rect requires sceneRect/setSceneRect")
    set_scene_rect_setter(QRectF(rect))
    setattr(view, _VIEW_EXPLICIT_ATTRIBUTE, True)


def set_inherited_view_scene_rect(view) -> None:
    """Return a view to Qt's default scene-rect inheritance mode."""

    getter, setter = _resolve_rect_ports(view, None, None)
    if not callable(getter) or not callable(setter):
        raise AttributeError("Inherited view rect requires sceneRect/setSceneRect")
    setter(QRectF())
    setattr(view, _VIEW_EXPLICIT_ATTRIBUTE, False)


@dataclass(slots=True)
class _SceneRectTracker:
    """Per-scene growth bookkeeping, stored on the scene itself."""

    scene: Any
    known_rect: QRectF
    baseline_rect: QRectF
    pending_rect: QRectF
    pending_expansions: dict[int, QRectF] = field(default_factory=dict)
    pending_journal: list[tuple[int, bool, QRectF | None]] = field(default_factory=list)
    depth: int = 0
    internal_change: bool = False


def _quiet_rect_read(scene, getter: Callable[[], object]) -> QRectF:
    if isinstance(scene, QObject):
        previous = QObject.blockSignals(scene, True)
        try:
            return QRectF(cast(Any, getter()))
        finally:
            QObject.blockSignals(scene, previous)
    return QRectF(cast(Any, getter()))


@contextmanager
def _internal_rect_write(scene, tracker: _SceneRectTracker):
    previous_flag = tracker.internal_change
    tracker.internal_change = True
    previous_signals = (
        QObject.blockSignals(scene, True) if isinstance(scene, QObject) else None
    )
    try:
        yield
    finally:
        if previous_signals is not None:
            QObject.blockSignals(scene, previous_signals)
        tracker.internal_change = previous_flag


def _tracker_for(scene, getter: Callable[[], object]) -> _SceneRectTracker:
    tracker = getattr(scene, _TRACKER_ATTRIBUTE, None)
    if isinstance(tracker, _SceneRectTracker):
        return tracker
    current = _quiet_rect_read(scene, getter)
    tracker = _SceneRectTracker(
        scene=scene,
        known_rect=QRectF(current),
        baseline_rect=QRectF(current),
        pending_rect=QRectF(current),
    )

    def remember_external_rect(rect, *, state: _SceneRectTracker = tracker) -> None:
        # Qt grows an automatic scene lazily; adopt external growth at depth
        # zero so the next capture starts from the true rect. Our own writes
        # and any change under an open guard are ignored.
        if state.internal_change or state.depth:
            return
        state.known_rect = QRectF(rect)

    changed_signal: Any
    if isinstance(scene, QGraphicsScene):
        changed_signal = QGraphicsScene.sceneRectChanged.__get__(scene, type(scene))
    else:
        changed_signal = getattr(scene, "sceneRectChanged", None)
    connect = getattr(changed_signal, "connect", None)
    if callable(connect):
        connect(remember_external_rect)
    setattr(scene, _TRACKER_ATTRIBUTE, tracker)
    return tracker


def _capture_view_scene_rect_updaters(scene) -> tuple[Callable[[QRectF], None], ...]:
    views_getter = getattr(scene, "views", None)
    if not callable(views_getter):
        return ()
    updaters: list[Callable[[QRectF], None]] = []
    for view in views_getter():
        if isinstance(view, QGraphicsView):

            def update_qt_view(rect: QRectF, *, _view=view) -> None:
                # Refresh the viewport without letting the view or its
                # scrollbars publish intermediate signals.
                blocked = [
                    (target, target.blockSignals(True))
                    for target in (
                        _view,
                        _view.horizontalScrollBar(),
                        _view.verticalScrollBar(),
                    )
                    if isinstance(target, QObject)
                ]
                try:
                    QGraphicsView.updateSceneRect(_view, QRectF(rect))
                finally:
                    for target, previous in reversed(blocked):
                        target.blockSignals(previous)

            updaters.append(update_qt_view)
            continue
        update_port = getattr(view, "updateSceneRect", None)
        if callable(update_port):
            updaters.append(update_port)
    return tuple(updaters)


@dataclass(slots=True)
class SceneRectSnapshot:
    """Nestable growth guard with O(1) successful child accumulation."""

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
        scene_rect_getter, set_scene_rect_setter = _resolve_rect_ports(
            scene,
            scene_rect_getter,
            set_scene_rect_setter,
        )
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            return None
        if automatic is None:
            automatic = scene_rect_is_automatic(scene)
        view_scene_rect_updaters = _capture_view_scene_rect_updaters(scene)
        tracker = _tracker_for(scene, scene_rect_getter)
        if tracker.depth == 0 and (not automatic or not incremental_tracking):
            # Re-sync from the live rect. Automatic incremental captures skip
            # this O(n) read and trust the rolling union instead, which keeps
            # sequential attaches linear.
            current = _quiet_rect_read(scene, scene_rect_getter)
            tracker.known_rect = QRectF(current)
            tracker.baseline_rect = QRectF(current)
            tracker.pending_rect = QRectF(current)

        if not automatic or not guard_growth:
            tracker.baseline_rect = QRectF(tracker.known_rect)
            return cls(
                tracker=tracker,
                automatic=automatic,
                baseline_rect=QRectF(tracker.known_rect),
                scene_rect_getter=scene_rect_getter,
                set_scene_rect_setter=set_scene_rect_setter,
                scene_items_bounding_rect_getter=scene_items_bounding_rect_getter,
                view_scene_rect_updaters=view_scene_rect_updaters,
                incremental_tracking=incremental_tracking,
                journal_index=len(tracker.pending_journal),
                guarded=False,
            )

        if tracker.depth == 0:
            tracker.baseline_rect = QRectF(tracker.known_rect)
            tracker.pending_rect = QRectF(tracker.known_rect)
            tracker.pending_expansions.clear()
            tracker.pending_journal.clear()
            guard_rect = QRectF(tracker.baseline_rect)
            if guard_rect.isNull():
                guard_rect = QRectF(_EMPTY_GUARD_RECT)
            with _internal_rect_write(scene, tracker):
                set_scene_rect_setter(QRectF(guard_rect))
        tracker.depth += 1
        return cls(
            tracker=tracker,
            automatic=True,
            baseline_rect=QRectF(tracker.baseline_rect),
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
            scene_items_bounding_rect_getter=scene_items_bounding_rect_getter,
            view_scene_rect_updaters=view_scene_rect_updaters,
            incremental_tracking=incremental_tracking,
            journal_index=len(tracker.pending_journal),
        )

    def live_rect(self) -> QRectF:
        """Read the current scene rect without publishing signals."""

        return _quiet_rect_read(self.tracker.scene, self.scene_rect_getter)

    def _record_expansion(
        self,
        expanded_rect,
        expansion_key: object | None,
        expansion_owner_scene_getter: Callable[[], object] | None,
    ) -> None:
        tracker = self.tracker
        key = id(expansion_key) if expansion_key is not None else id(self)
        if expansion_key is not None:
            owner_scene_getter = expansion_owner_scene_getter
            if owner_scene_getter is None:
                owner_scene_getter = getattr(expansion_key, "scene", None)
            if callable(owner_scene_getter):
                if owner_scene_getter() is not tracker.scene:
                    # The item detached mid-transaction; its earlier hint must
                    # not keep the rect grown.
                    if key in tracker.pending_expansions:
                        tracker.pending_journal.append(
                            (key, True, QRectF(tracker.pending_expansions[key]))
                        )
                        tracker.pending_expansions.pop(key)
                    return
        if expanded_rect is None:
            return
        candidate = QRectF(expanded_rect)
        if candidate.isNull():
            return
        previous = tracker.pending_expansions.get(key)
        if previous is not None and previous == candidate:
            return
        tracker.pending_journal.append(
            (key, previous is not None, QRectF(previous) if previous else None)
        )
        tracker.pending_expansions[key] = QRectF(candidate)
        tracker.pending_rect = tracker.pending_rect.united(candidate)

    def release(
        self,
        expanded_rect=None,
        *,
        expansion_key: object | None = None,
        expansion_owner_scene_getter: Callable[[], object] | None = None,
        authoritative_scene_bounds_getter: Callable[[], object] | None = None,
    ) -> None:
        if not self.active:
            return
        if not self.automatic or not self.guarded:
            self.active = False
            return
        tracker = self.tracker
        self._record_expansion(
            expanded_rect,
            expansion_key,
            expansion_owner_scene_getter,
        )
        if tracker.depth > 1:
            tracker.depth -= 1
            self.active = False
            return

        final_rect = QRectF(tracker.baseline_rect)
        for expansion in tracker.pending_expansions.values():
            final_rect = final_rect.united(expansion)
        if callable(authoritative_scene_bounds_getter):
            bounds = authoritative_scene_bounds_getter()
            if bounds is not None:
                final_rect = final_rect.united(QRectF(cast(Any, bounds)))
        tracker.pending_rect = QRectF(final_rect)

        view_refresh_rect = QRectF(final_rect)
        if (
            self.view_scene_rect_updaters
            and view_refresh_rect == tracker.baseline_rect
            and not self.incremental_tracking
        ):
            # No growth was recorded; union in the live item bounds so views
            # still observe real growth Qt tracked lazily.
            scene = tracker.scene
            if isinstance(scene, QGraphicsScene):
                view_refresh_rect = view_refresh_rect.united(
                    QGraphicsScene.itemsBoundingRect(scene)
                )
            elif callable(self.scene_items_bounding_rect_getter):
                view_refresh_rect = view_refresh_rect.united(
                    QRectF(cast(Any, self.scene_items_bounding_rect_getter()))
                )
        if view_refresh_rect != tracker.baseline_rect:
            with _internal_rect_write(tracker.scene, tracker):
                for updater in self.view_scene_rect_updaters:
                    updater(QRectF(view_refresh_rect))

        with _internal_rect_write(tracker.scene, tracker):
            self.set_scene_rect_setter(QRectF())
            if self.incremental_tracking:
                released_rect = QRectF(tracker.pending_rect)
            else:
                released_rect = QRectF(cast(Any, self.scene_rect_getter()))
        setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, True)
        tracker.known_rect = QRectF(released_rect)
        tracker.pending_rect = QRectF(released_rect)
        tracker.depth = 0
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        self.active = False

    def _rewind_pending_expansions(self) -> None:
        tracker = self.tracker
        if len(tracker.pending_journal) <= self.journal_index:
            # Nothing was journaled at this nesting level; skip the union
            # recomputation so empty child aborts stay O(1).
            return
        for key, existed, previous in reversed(
            tracker.pending_journal[self.journal_index :]
        ):
            if existed and previous is not None:
                tracker.pending_expansions[key] = QRectF(previous)
            else:
                tracker.pending_expansions.pop(key, None)
        del tracker.pending_journal[self.journal_index :]
        rewound = QRectF(tracker.baseline_rect)
        for expansion in tracker.pending_expansions.values():
            rewound = rewound.united(expansion)
        tracker.pending_rect = rewound

    def _restore_explicit_scene_rect(self) -> None:
        tracker = self.tracker
        with _internal_rect_write(tracker.scene, tracker):
            self.set_scene_rect_setter(QRectF(self.baseline_rect))
        setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, False)
        tracker.known_rect = QRectF(self.baseline_rect)
        tracker.baseline_rect = QRectF(self.baseline_rect)
        tracker.pending_rect = QRectF(self.baseline_rect)

    def _restore_automatic_scene_rect(self) -> None:
        tracker = self.tracker
        with _internal_rect_write(tracker.scene, tracker):
            self.set_scene_rect_setter(QRectF())
            restored_rect = QRectF(cast(Any, self.scene_rect_getter()))
        setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, True)
        # Qt may have lazily grown past the captured baseline; the live rect
        # after clearing the override is the new authority.
        self.baseline_rect = QRectF(restored_rect)
        tracker.known_rect = QRectF(restored_rect)
        tracker.baseline_rect = QRectF(restored_rect)
        tracker.pending_rect = QRectF(restored_rect)

    def restore(self) -> None:
        """Abort a mutation, dropping this nesting level's recorded growth."""

        if not self.active:
            return
        tracker = self.tracker
        if not self.automatic:
            self._restore_explicit_scene_rect()
            self.active = False
            return
        if not self.guarded:
            self._restore_automatic_scene_rect()
            self.active = False
            return
        if tracker.depth > 1:
            self._rewind_pending_expansions()
            tracker.depth -= 1
            self.active = False
            return
        self._restore_automatic_scene_rect()
        tracker.depth = 0
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        self.active = False

    def reassert(self) -> None:
        """Idempotently re-apply the captured rect and mode.

        Restores normally while active; after consumption it re-applies only
        at depth zero (never under another transaction's open guard) and only
        when the live rect or mode drifted.
        """

        if self.active:
            self.restore()
            return
        tracker = self.tracker
        if tracker.depth:
            return
        current_rect = self.live_rect()
        current_automatic = scene_rect_is_automatic(tracker.scene)
        if current_rect == self.baseline_rect and (current_automatic is self.automatic):
            return
        if self.automatic:
            self._restore_automatic_scene_rect()
        else:
            self._restore_explicit_scene_rect()

    def commit_replacement(self, expanded_rect=None) -> None:
        """Finalize a document replacement that may have switched the mode."""

        if not self.active:
            return
        tracker = self.tracker
        if scene_rect_is_automatic(tracker.scene):
            if self.automatic and self.guarded:
                self.release(expanded_rect)
                return
            current = self.live_rect()
            tracker.known_rect = QRectF(current)
            tracker.baseline_rect = QRectF(current)
            tracker.pending_rect = QRectF(current)
            tracker.pending_expansions.clear()
            tracker.pending_journal.clear()
            setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, True)
            self.active = False
            return
        current = self.live_rect()
        if self.automatic and self.guarded:
            # The replacement installed an explicit sheet rect under this
            # guard; consume the nesting level without touching the rect.
            tracker.depth = max(0, tracker.depth - 1)
        tracker.known_rect = QRectF(current)
        tracker.baseline_rect = QRectF(current)
        tracker.pending_rect = QRectF(current)
        tracker.pending_expansions.clear()
        tracker.pending_journal.clear()
        setattr(tracker.scene, _AUTOMATIC_ATTRIBUTE, False)
        self.active = False


@dataclass(slots=True)
class SceneRectStateSnapshot:
    """Exact scene rect/mode savepoint without opening a growth guard."""

    scene: Any
    rect: QRectF
    automatic: bool
    qt_inherited: bool
    automatic_attribute_present: bool
    automatic_attribute_value: object
    scene_rect_getter: Callable[[], object]
    set_scene_rect_setter: Callable[[QRectF], object]
    tracker_state: tuple | None = None
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
        scene_rect_getter, set_scene_rect_setter = _resolve_rect_ports(
            scene,
            scene_rect_getter,
            set_scene_rect_setter,
        )
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            raise AttributeError("Scene rect savepoint requires sceneRect/setSceneRect")
        automatic_present = hasattr(scene, _AUTOMATIC_ATTRIBUTE)
        automatic_value = (
            getattr(scene, _AUTOMATIC_ATTRIBUTE) if automatic_present else None
        )
        automatic = bool(automatic_value) if automatic_present else True
        tracker = getattr(scene, _TRACKER_ATTRIBUTE, None)
        tracker_state = None
        guarded = False
        if isinstance(tracker, _SceneRectTracker):
            guarded = tracker.depth > 0
            # An open guard's rewind bookkeeping must survive a savepoint
            # rollback that runs beneath it (sheet setup, document restore).
            tracker_state = (
                QRectF(tracker.known_rect),
                QRectF(tracker.baseline_rect),
                QRectF(tracker.pending_rect),
                tuple(
                    (key, QRectF(rect))
                    for key, rect in tracker.pending_expansions.items()
                ),
                tuple(
                    (key, existed, QRectF(prev) if prev is not None else None)
                    for key, existed, prev in tracker.pending_journal
                ),
                tracker.depth,
            )
        captured_rect = _quiet_rect_read(scene, scene_rect_getter)
        return cls(
            scene=scene,
            rect=captured_rect,
            automatic=automatic,
            qt_inherited=automatic and not guarded,
            automatic_attribute_present=automatic_present,
            automatic_attribute_value=automatic_value,
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
            tracker_state=tracker_state,
        )

    def restore(self) -> None:
        if not self.active:
            return
        scene = self.scene
        tracker = getattr(scene, _TRACKER_ATTRIBUTE, None)
        previous_flag = None
        if isinstance(tracker, _SceneRectTracker):
            previous_flag = tracker.internal_change
            tracker.internal_change = True
        previous_signals = (
            QObject.blockSignals(scene, True) if isinstance(scene, QObject) else None
        )
        try:
            self.set_scene_rect_setter(
                QRectF() if self.qt_inherited else QRectF(self.rect)
            )
        finally:
            if previous_signals is not None:
                QObject.blockSignals(scene, previous_signals)
            if isinstance(tracker, _SceneRectTracker) and previous_flag is not None:
                tracker.internal_change = previous_flag
        if self.automatic_attribute_present:
            setattr(scene, _AUTOMATIC_ATTRIBUTE, self.automatic_attribute_value)
        elif hasattr(scene, _AUTOMATIC_ATTRIBUTE):
            delattr(scene, _AUTOMATIC_ATTRIBUTE)
        if isinstance(tracker, _SceneRectTracker):
            if self.tracker_state is not None:
                known, baseline, pending, expansions, journal, depth = (
                    self.tracker_state
                )
                tracker.known_rect = QRectF(known)
                tracker.baseline_rect = QRectF(baseline)
                tracker.pending_rect = QRectF(pending)
                tracker.pending_expansions.clear()
                tracker.pending_expansions.update(
                    (key, QRectF(rect)) for key, rect in expansions
                )
                tracker.pending_journal[:] = [
                    (key, existed, QRectF(prev) if prev is not None else None)
                    for key, existed, prev in journal
                ]
                tracker.depth = depth
            else:
                tracker.known_rect = QRectF(self.rect)
                tracker.baseline_rect = QRectF(self.rect)
                tracker.pending_rect = QRectF(self.rect)
        self.active = False

    def release(self) -> None:
        self.active = False


@dataclass(slots=True)
class ViewSceneRectStateSnapshot:
    """Exact view rect/mode savepoint."""

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
        scene_rect_getter, set_scene_rect_setter = _resolve_rect_ports(
            view,
            scene_rect_getter,
            set_scene_rect_setter,
        )
        if not callable(scene_rect_getter) or not callable(set_scene_rect_setter):
            raise AttributeError("View rect savepoint requires sceneRect/setSceneRect")
        explicit_present = hasattr(view, _VIEW_EXPLICIT_ATTRIBUTE)
        explicit_value = (
            getattr(view, _VIEW_EXPLICIT_ATTRIBUTE) if explicit_present else None
        )
        return cls(
            view=view,
            rect=QRectF(cast(Any, scene_rect_getter())),
            explicit=bool(explicit_value) if explicit_present else False,
            explicit_attribute_present=explicit_present,
            explicit_attribute_value=explicit_value,
            scene_rect_getter=scene_rect_getter,
            set_scene_rect_setter=set_scene_rect_setter,
        )

    def restore(self) -> None:
        if not self.active:
            return
        self.set_scene_rect_setter(QRectF(self.rect) if self.explicit else QRectF())
        if self.explicit_attribute_present:
            setattr(
                self.view,
                _VIEW_EXPLICIT_ATTRIBUTE,
                self.explicit_attribute_value,
            )
        elif hasattr(self.view, _VIEW_EXPLICIT_ATTRIBUTE):
            delattr(self.view, _VIEW_EXPLICIT_ATTRIBUTE)
        self.active = False

    def release(self) -> None:
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
