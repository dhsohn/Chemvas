from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from core.history import (
    CompositeCommand,
    HistoryCommand,
    UpdateAtomColorCommand,
)
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from ui.atom_label_access import implicit_carbon_dot_brush_for
from ui.bond_graphics_access import apply_color_to_bond_item_for
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    visible_atom_item_for,
)
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_history_recording_service import CallbackFreeHistoryBaseline
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id, bonds_for
from ui.graphics_items import AtomDotItem
from ui.history_command_snapshot import HistoryCommandSnapshot
from ui.history_commands import AddSceneItemsCommand, UpdateSceneItemCommand
from ui.history_push_failure_recovery import (
    RecordingHistoryPolicySnapshot,
    _restore_history_and_policy_silently,
    _verify_history_and_policy_authority,
)
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from ui.scene_item_access import item_is_in_canvas_scene
from ui.scene_item_state import (
    note_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class _CollectingHistory:
    """Drop-in for the history service that captures pushed commands instead of
    recording them, so a multi-element mutation can be bundled into one command."""

    def __init__(self, sink) -> None:
        self._sink = sink

    def push(self, command) -> None:
        self._sink(command)


def _set_graphics_brush_exact(item, brush: QBrush) -> None:
    if isinstance(item, QAbstractGraphicsShapeItem):
        QAbstractGraphicsShapeItem.setBrush(item, QBrush(brush))
        return
    item.setBrush(QBrush(brush))


def _set_graphics_pen_exact(item, pen: QPen) -> None:
    if isinstance(item, QAbstractGraphicsShapeItem):
        QAbstractGraphicsShapeItem.setPen(item, QPen(pen))
        return
    item.setPen(QPen(pen))


_DELETED_GRAPHICS_ITEM = object()
_MISSING_CAPTURE_ATTRIBUTE = object()
_UNKNOWN_HISTORY_ENABLED = object()


@dataclass(frozen=True, slots=True)
class _FrozenHistoryEnabledAuthority:
    value: object
    getter: Callable[[], object] | None
    setter: Callable[[bool], object] | None

    @classmethod
    def capture(cls, history: object) -> _FrozenHistoryEnabledAuthority:
        getter_value = _optional_live_capture_attribute(history, "is_enabled")
        setter_value = _optional_live_capture_attribute(history, "set_enabled")
        getter = getter_value if callable(getter_value) else None
        setter = setter_value if callable(setter_value) else None
        value = getter() if getter is not None else _UNKNOWN_HISTORY_ENABLED
        return cls(value=value, getter=getter, setter=setter)

    def restore(self, original_error: BaseException) -> bool:
        if self.getter is None or type(self.value) is not bool:
            return True
        try:
            if self.getter() is self.value:
                return True
            if self.setter is None:
                raise RuntimeError("color history enabled policy has no restore port")
            self.setter(self.value)
            if self.getter() is not self.value:
                raise RuntimeError("color history enabled policy was not restored")
        except BaseException as policy_error:
            _add_color_rollback_note(
                original_error,
                policy_error,
                phase="restoring the pre-push history policy",
            )
            return False
        return True


@dataclass(frozen=True, slots=True)
class _ColorHistoryAuthority:
    history: object | None
    stack_snapshot: HistoryStackSnapshot | None
    policy_snapshot: RecordingHistoryPolicySnapshot | None
    raw_baseline: CallbackFreeHistoryBaseline | None

    @classmethod
    def capture(
        cls,
        history: object | None,
        *,
        canvas: object | None = None,
        raw_baseline: CallbackFreeHistoryBaseline | None = None,
    ) -> _ColorHistoryAuthority:
        if history is None:
            return cls(None, None, None, None)
        raw_baseline = raw_baseline or CallbackFreeHistoryBaseline.capture(
            history,
            canvas=canvas,
        )
        stack_snapshot: HistoryStackSnapshot | None = None
        policy_snapshot: RecordingHistoryPolicySnapshot | None = None
        authority = cls(history, None, None, raw_baseline)
        try:
            stack_snapshot = HistoryStackSnapshot.capture(history)
            authority = cls(history, stack_snapshot, None, raw_baseline)
            if stack_snapshot is None:
                if raw_baseline is not None:
                    raise RuntimeError(
                        "callback-free color history backing was not exposed "
                        "through live stack ports"
                    )
                return authority
            if raw_baseline is None:
                raise RuntimeError(
                    "color history has mutable stacks but no callback-free "
                    "backing authority"
                )
            policy_snapshot = RecordingHistoryPolicySnapshot.capture(stack_snapshot)
            authority = cls(
                history,
                stack_snapshot,
                policy_snapshot,
                raw_baseline,
            )
            authority.verify_prepublication()
        except BaseException as original_error:
            authority.restore(
                original_error,
                phase="color history authority capture",
            )
            raise
        return authority

    def verify_prepublication(self) -> None:
        if self.stack_snapshot is None:
            return
        _verify_history_and_policy_authority(
            self.stack_snapshot,
            self.policy_snapshot,
        )
        if self.raw_baseline is None:
            raise RuntimeError(
                "color history has no callback-free prepublication authority"
            )
        self.raw_baseline.bind_snapshot(
            self.stack_snapshot,
            self.policy_snapshot,
        )

    def verify_published(
        self,
        command: HistoryCommand,
        *,
        accepted: bool,
    ) -> None:
        self.verify_published_commands(((command, accepted),))

    def verify_published_commands(
        self,
        publications: Iterable[tuple[HistoryCommand, bool]],
    ) -> None:
        publications = tuple(publications)
        self.verify_published_live_commands(publications)
        self.verify_published_raw_commands(publications)

    def verify_published_live_commands(
        self,
        publications: Iterable[tuple[HistoryCommand, bool]],
    ) -> None:
        snapshot = self.stack_snapshot
        if snapshot is None:
            return
        expected_history = list(snapshot.history_items)
        expected_redo = snapshot.redo_items
        limit = None
        if self.policy_snapshot is not None:
            limit = next(
                (
                    port.value
                    for port in self.policy_snapshot.ports
                    if port.name == "limit"
                ),
                None,
            )
        for command, accepted in publications:
            if not accepted:
                continue
            expected_history.append(command)
            expected_redo = ()
            if type(limit) is int and len(expected_history) > limit:
                expected_history.pop(0)

        def verify_stacks() -> None:
            snapshot.verify_exact_items(
                history_items=tuple(expected_history),
                redo_items=expected_redo,
            )

        verify_stacks()
        if self.policy_snapshot is None:
            return
        self.policy_snapshot.verify()
        verify_stacks()
        self.policy_snapshot.verify(reverse=True)
        verify_stacks()

    def verify_published_raw_commands(
        self,
        publications: Iterable[tuple[HistoryCommand, bool]],
    ) -> None:
        if self.stack_snapshot is None:
            return
        if self.raw_baseline is None:
            raise RuntimeError(
                "color history has no callback-free publication authority"
            )
        self.raw_baseline.verify_published_commands(tuple(publications))

    def restore(self, original_error: BaseException, *, phase: str) -> bool:
        live_restored = self.stack_snapshot is None
        if self.stack_snapshot is not None:
            for reverse in (False, True):
                if _restore_history_and_policy_silently(
                    self.stack_snapshot,
                    self.policy_snapshot,
                    original_error,
                    phase=phase,
                    reverse=reverse,
                ):
                    live_restored = True
                    break
        raw_restored = True
        if self.raw_baseline is not None:
            try:
                # Raw storage is deliberately the final writer after every live
                # restore callback.
                self.raw_baseline.restore()
            except BaseException as restore_error:
                raw_restored = False
                _add_color_rollback_note(
                    original_error,
                    restore_error,
                    phase=f"restoring callback-free history during {phase}",
                )
        return live_restored and raw_restored


def _graphics_item_is_deleted(item: object) -> bool:
    return isinstance(item, QGraphicsItem) and sip.isdeleted(item)


def _optional_live_capture_attribute(item: object, name: str) -> object | None:
    """Read a statically present optional graphics port exactly once.

    A descriptor may raise ``AttributeError`` from inside its getter.  Plain
    ``getattr(..., None)`` misclassifies that live capture failure as an absent
    optional method and permits mutation with a partial runtime savepoint.
    """

    if (
        inspect.getattr_static(item, name, _MISSING_CAPTURE_ATTRIBUTE)
        is _MISSING_CAPTURE_ATTRIBUTE
    ):
        return None
    return getattr(item, name)


def _graphics_item_data_for_capture(item: object, role: int) -> object:
    if _graphics_item_is_deleted(item):
        return _DELETED_GRAPHICS_ITEM
    try:
        data = _optional_live_capture_attribute(item, "data")
        return data(role) if callable(data) else None
    except BaseException:
        if _graphics_item_is_deleted(item):
            return _DELETED_GRAPHICS_ITEM
        raise


def _captured_graphics_brush(item: object) -> QBrush | None:
    if _graphics_item_is_deleted(item):
        return None
    try:
        brush = _optional_live_capture_attribute(item, "brush")
        if not callable(brush):
            return None
        value = brush()
        if isinstance(item, QAbstractGraphicsShapeItem):
            # Invoke the extension getter once as fallible preflight, then bind
            # the actual authority to Qt's base implementation.  Rollback and
            # verification never re-enter the extension getter.
            return QBrush(QAbstractGraphicsShapeItem.brush(item))
        if isinstance(value, QBrush):
            return QBrush(value)
        # Non-Qt extension/test doubles may expose a dynamic ``brush`` mock
        # without implementing Qt's QBrush contract. It is not a partial Qt
        # snapshot; leave that unsupported proxy to command-based rollback.
        return QBrush(value) if isinstance(item, QGraphicsItem) else None
    except BaseException:
        if _graphics_item_is_deleted(item):
            return None
        raise


def _captured_graphics_pen(item: object) -> QPen | None:
    if _graphics_item_is_deleted(item):
        return None
    try:
        pen = _optional_live_capture_attribute(item, "pen")
        if not callable(pen):
            return None
        value = pen()
        if isinstance(item, QAbstractGraphicsShapeItem):
            return QPen(QAbstractGraphicsShapeItem.pen(item))
        if isinstance(value, QPen):
            return QPen(value)
        return QPen(value) if isinstance(item, QGraphicsItem) else None
    except BaseException:
        if _graphics_item_is_deleted(item):
            return None
        raise


def _add_color_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    with contextlib.suppress(BaseException):
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(
            "Color rollback also failed during "
            f"{phase}: {type(rollback_error).__name__}: {rollback_error}"
        )


def _run_color_rollback_step(
    original_error: BaseException,
    phase: str,
    operation: Callable[[], None],
) -> None:
    try:
        operation()
    except BaseException as rollback_error:
        _add_color_rollback_note(
            original_error,
            rollback_error,
            phase=phase,
        )


def _restore_color_history_baseline(
    baseline: CallbackFreeHistoryBaseline | None,
    original_error: BaseException,
    *,
    phase: str,
) -> None:
    if baseline is None:
        return
    try:
        baseline.restore()
    except BaseException as restore_error:
        _add_color_rollback_note(
            original_error,
            restore_error,
            phase=phase,
        )


def _close_failed_color_prepublication(
    original_error: BaseException,
    *,
    runtime_rollback: Callable[[], None] | None,
    runtime_phase: str,
    history_authority: _ColorHistoryAuthority | None,
    raw_history_baseline: CallbackFreeHistoryBaseline | None = None,
    history_phase: str,
) -> None:
    """Restore runtime once, then make raw history storage the final writer."""

    if runtime_rollback is not None:
        _run_color_rollback_step(
            original_error,
            runtime_phase,
            runtime_rollback,
        )

    if history_authority is not None and not history_authority.restore(
        original_error,
        phase=history_phase,
    ):
        _add_color_rollback_note(
            original_error,
            RuntimeError("color history authority was not fully restored"),
            phase=history_phase,
        )

    # A runtime restore may cross NoteItem/extension setters. Reassert the raw
    # built-in stacks and policy values after every such callback, even though a
    # complete live authority restore also closes on this same baseline.
    final_raw_baseline = raw_history_baseline
    if final_raw_baseline is None and history_authority is not None:
        final_raw_baseline = history_authority.raw_baseline
    _restore_color_history_baseline(
        final_raw_baseline,
        original_error,
        phase=f"closing callback-free history after {history_phase}",
    )


def _run_restore_operations(
    label: str,
    operations: Iterable[Callable[[], None]],
) -> None:
    errors: list[BaseException] = []
    for operation in operations:
        try:
            operation()
        except BaseException as error:
            errors.append(error)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup(label, errors)


def _bond_graphics_style_restore(item) -> Callable[[], None]:
    if _graphics_item_is_deleted(item):
        return lambda: None
    brush = _captured_graphics_brush(item)
    pen = _captured_graphics_pen(item)

    def restore() -> None:
        operations: list[Callable[[], None]] = []
        if pen is not None:
            operations.append(lambda: _set_graphics_pen_exact(item, pen))
        if brush is not None:
            operations.append(lambda: _set_graphics_brush_exact(item, brush))
        _run_restore_operations("Bond graphics style rollback failed", operations)

    return restore


def _apply_bond_color_in_place(canvas, bond_id: int, color: QColor | str) -> None:
    bond = bond_for_id(canvas, bond_id)
    if bond is None:
        return
    color_value = QColor(color)
    if not color_value.isValid():
        return
    before_color = bond.color
    restores = [
        _bond_graphics_style_restore(item)
        for item in bond_items_for_id(canvas, bond_id)
    ]
    try:
        bond.color = color_value.name()
        for bond_item in bond_items_for_id(canvas, bond_id):
            apply_color_to_bond_item_for(canvas, bond_item, color_value)
    except BaseException as original_error:
        _run_color_rollback_step(
            original_error,
            "restoring the bond model color",
            lambda: setattr(bond, "color", before_color),
        )
        for restore in restores:
            _run_color_rollback_step(
                original_error,
                "restoring bond graphics",
                restore,
            )
        raise


@dataclass
class UpdateBondColorCommand(HistoryCommand):
    bond_id: int
    before_color: str
    after_color: str

    def undo(self, canvas) -> None:
        _apply_bond_color_in_place(canvas, self.bond_id, self.before_color)

    def redo(self, canvas) -> None:
        _apply_bond_color_in_place(canvas, self.bond_id, self.after_color)


@dataclass
class _NoteColorState:
    html: str
    cursor_anchor: int
    cursor_position: int
    interaction_flags: Qt.TextInteractionFlag
    default_text_color: QColor
    committed_text: str
    committed_html: str

    @classmethod
    def capture(cls, item: QGraphicsTextItem) -> _NoteColorState:
        cursor = item.textCursor()
        return cls(
            html=item.toHtml(),
            cursor_anchor=cursor.anchor(),
            cursor_position=cursor.position(),
            interaction_flags=item.textInteractionFlags(),
            default_text_color=QColor(item.defaultTextColor()),
            committed_text=committed_note_text_for(item),
            committed_html=committed_note_html_for(item),
        )

    def apply(self, item: QGraphicsTextItem) -> None:
        item.setHtml(self.html)
        QGraphicsTextItem.setDefaultTextColor(item, QColor(self.default_text_color))
        item.setTextInteractionFlags(self.interaction_flags)
        cursor = QTextCursor(item.document())
        cursor.setPosition(self.cursor_anchor)
        cursor.setPosition(self.cursor_position, QTextCursor.MoveMode.KeepAnchor)
        item.setTextCursor(cursor)
        set_committed_note_text_for(item, self.committed_text)
        set_committed_note_html_for(item, self.committed_html)


@dataclass(frozen=True, slots=True)
class _ColorRuntimeAuthority:
    restore_once: Callable[[], None]
    verify: Callable[[], None]

    def __call__(self) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                self.restore_once()
                self.verify()
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "Color runtime remained non-authoritative",
            errors,
        )


@dataclass
class UpdateNoteColorCommand(HistoryCommand):
    item: QGraphicsTextItem
    before_state: _NoteColorState
    after_state: _NoteColorState

    def _apply(self, state: _NoteColorState, rollback_state: _NoteColorState) -> None:
        try:
            state.apply(self.item)
        except BaseException as original_error:
            _run_color_rollback_step(
                original_error,
                "restoring the prior note color state",
                lambda: rollback_state.apply(self.item),
            )
            raise

    def undo(self, canvas) -> None:
        del canvas
        self._apply(self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        del canvas
        self._apply(self.after_state, self.before_state)


@dataclass
class _CommitPendingNoteEditCommand(HistoryCommand):
    item: QGraphicsTextItem
    before_state: _NoteColorState
    after_state: _NoteColorState

    def _apply(self, state: _NoteColorState, rollback_state: _NoteColorState) -> None:
        try:
            state.apply(self.item)
        except BaseException as original_error:
            _run_color_rollback_step(
                original_error,
                "restoring the prior pending-note state",
                lambda: rollback_state.apply(self.item),
            )
            raise

    def undo(self, canvas) -> None:
        del canvas
        self._apply(self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        del canvas
        self._apply(self.after_state, self.before_state)


@dataclass(frozen=True, slots=True)
class _SceneColorItemState:
    item: QGraphicsItem
    runtime: _ColorRuntimeAuthority


@dataclass(frozen=True, slots=True)
class _SceneModelColorState:
    kind: str
    object_id: int
    target: object
    color: object
    graphics_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class _SceneColorPeerAuthority:
    service: CanvasColorMutationService
    item_states: tuple[_SceneColorItemState, ...]
    model_states: tuple[_SceneModelColorState, ...]

    def _verify_model_state(self, state: _SceneModelColorState) -> None:
        current = (
            atom_for_id(self.service.canvas, state.object_id)
            if state.kind == "atom"
            else bond_for_id(self.service.canvas, state.object_id)
        )
        if current is not state.target or getattr(current, "color", None) != state.color:
            raise RuntimeError(
                f"non-target scene {state.kind} color changed during publication"
            )

    def verify_peers(self, allowed_graphics_ids: frozenset[int]) -> None:
        for item_state in self.item_states:
            if id(item_state.item) not in allowed_graphics_ids:
                item_state.runtime.verify()
        for model_state in self.model_states:
            if not model_state.graphics_ids.intersection(allowed_graphics_ids):
                self._verify_model_state(model_state)

    def restore(self, original_error: BaseException) -> None:
        def restore_once() -> None:
            for model_state in self.model_states:
                current = (
                    atom_for_id(self.service.canvas, model_state.object_id)
                    if model_state.kind == "atom"
                    else bond_for_id(self.service.canvas, model_state.object_id)
                )
                if current is not model_state.target:
                    raise RuntimeError(
                        f"scene {model_state.kind} identity changed during color rollback"
                    )
                cast(Any, current).color = model_state.color
            for item_state in reversed(self.item_states):
                item_state.runtime.restore_once()

        def verify_all() -> None:
            for item_state in self.item_states:
                item_state.runtime.verify()
            for model_state in self.model_states:
                self._verify_model_state(model_state)

        try:
            _ColorRuntimeAuthority(restore_once, verify_all)()
        except BaseException as restore_error:
            _add_color_rollback_note(
                original_error,
                restore_error,
                phase="restoring scene-wide color peer authority",
            )


class CanvasColorMutationService:
    def __init__(
        self, canvas: CanvasView, *, graph_service, history_service=None
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.graph_service = graph_service
        self._scene_color_peer_transactions: list[
            tuple[_SceneColorPeerAuthority, frozenset[int]]
        ] = []

    @staticmethod
    def _live_graphics_ids(
        scene: QGraphicsScene,
        items: Iterable[object | None],
    ) -> frozenset[int]:
        return frozenset(
            id(item)
            for item in items
            if isinstance(item, QGraphicsItem)
            and not sip.isdeleted(item)
            and QGraphicsItem.scene(item) is scene
        )

    def _capture_scene_color_peer_authority(
        self,
    ) -> _SceneColorPeerAuthority | None:
        if not isinstance(self.canvas, QGraphicsView):
            return None
        scene = QGraphicsView.scene(self.canvas)
        if not isinstance(scene, QGraphicsScene):
            return None

        item_states: list[_SceneColorItemState] = []
        model_states: list[_SceneModelColorState] = []
        authority = _SceneColorPeerAuthority(self, (), ())
        try:
            for item in tuple(QGraphicsScene.items(scene)):
                if isinstance(item, QGraphicsTextItem):
                    runtime = self._note_runtime_rollback(item)
                elif isinstance(item, QAbstractGraphicsShapeItem):
                    brush = QBrush(QAbstractGraphicsShapeItem.brush(item))
                    pen = QPen(QAbstractGraphicsShapeItem.pen(item))

                    def restore_shape_color(
                        *,
                        target: QAbstractGraphicsShapeItem = item,
                        captured_brush: QBrush = brush,
                        captured_pen: QPen = pen,
                    ) -> None:
                        QAbstractGraphicsShapeItem.setPen(
                            target,
                            QPen(captured_pen),
                        )
                        QAbstractGraphicsShapeItem.setBrush(
                            target,
                            QBrush(captured_brush),
                        )

                    def verify_shape_color(
                        *,
                        target: QAbstractGraphicsShapeItem = item,
                        captured_brush: QBrush = brush,
                        captured_pen: QPen = pen,
                    ) -> None:
                        if (
                            QAbstractGraphicsShapeItem.brush(target)
                            != captured_brush
                            or QAbstractGraphicsShapeItem.pen(target) != captured_pen
                        ):
                            raise RuntimeError(
                                "non-target graphics color changed during publication"
                            )

                    runtime = _ColorRuntimeAuthority(
                        restore_shape_color,
                        verify_shape_color,
                    )
                else:
                    continue
                item_states.append(_SceneColorItemState(item, runtime))
                authority = _SceneColorPeerAuthority(
                    self,
                    tuple(item_states),
                    tuple(model_states),
                )

            atom_items = atom_items_for(self.canvas)
            atom_dots = atom_dots_for(self.canvas)
            for atom_id, atom in tuple(atoms_for(self.canvas).items()):
                model_states.append(
                    _SceneModelColorState(
                        "atom",
                        atom_id,
                        atom,
                        atom.color,
                        self._live_graphics_ids(
                            scene,
                            (atom_items.get(atom_id), atom_dots.get(atom_id)),
                        ),
                    )
                )
                authority = _SceneColorPeerAuthority(
                    self,
                    tuple(item_states),
                    tuple(model_states),
                )
            for bond_id, bond in enumerate(tuple(bonds_for(self.canvas))):
                if bond is None:
                    continue
                model_states.append(
                    _SceneModelColorState(
                        "bond",
                        bond_id,
                        bond,
                        bond.color,
                        self._live_graphics_ids(
                            scene,
                            bond_items_for_id(self.canvas, bond_id),
                        ),
                    )
                )
                authority = _SceneColorPeerAuthority(
                    self,
                    tuple(item_states),
                    tuple(model_states),
                )
            authority.verify_peers(frozenset())
        except BaseException as original_error:
            authority.restore(original_error)
            raise
        return authority

    def _intended_scene_color_graphics_ids(
        self,
        items: Iterable[object],
        *,
        expand_ring_structures: bool,
    ) -> frozenset[int]:
        allowed: set[int] = set()
        for item in items:
            allowed.add(id(item))
            if not isinstance(item, QGraphicsItem) or sip.isdeleted(item):
                continue
            kind = QGraphicsItem.data(item, 0)
            object_id = QGraphicsItem.data(item, 1)
            if kind == "atom" and isinstance(object_id, int):
                allowed.update(
                    id(candidate)
                    for candidate in (
                        atom_items_for(self.canvas).get(object_id),
                        atom_dots_for(self.canvas).get(object_id),
                    )
                    if candidate is not None
                )
            elif kind == "bond" and isinstance(object_id, int):
                allowed.update(
                    id(candidate)
                    for candidate in bond_items_for_id(self.canvas, object_id)
                )
            elif kind == "ring" and expand_ring_structures:
                allowed.update(
                    id(candidate)
                    for candidate in self._ring_structure_targets(item)
                )
        return frozenset(allowed)

    @contextlib.contextmanager
    def _scene_color_peer_transaction(
        self,
        items: Iterable[object],
        *,
        expand_ring_structures: bool,
    ):
        transactions = self._scene_color_peer_transactions
        if transactions:
            yield
            return
        raw_history_baseline = CallbackFreeHistoryBaseline.capture(
            self.history,
            canvas=self.canvas,
        )
        authority: _SceneColorPeerAuthority | None = None
        try:
            authority = self._capture_scene_color_peer_authority()
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
        except BaseException as original_error:
            if authority is not None:
                authority.restore(original_error)
            _restore_color_history_baseline(
                raw_history_baseline,
                original_error,
                phase="closing history after scene-color peer capture",
            )
            raise
        if authority is None:
            yield
            return
        try:
            allowed = self._intended_scene_color_graphics_ids(
                items,
                expand_ring_structures=expand_ring_structures,
            )
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
        except BaseException as original_error:
            authority.restore(original_error)
            _restore_color_history_baseline(
                raw_history_baseline,
                original_error,
                phase="closing history after scene-color target resolution",
            )
            raise
        transactions.append((authority, allowed))
        try:
            yield
            authority.verify_peers(allowed)
        except BaseException as original_error:
            authority.restore(original_error)
            _restore_color_history_baseline(
                raw_history_baseline,
                original_error,
                phase="closing history after scene-color peer rollback",
            )
            raise
        finally:
            transactions.pop()

    def _verify_active_scene_color_peers(self) -> None:
        if not self._scene_color_peer_transactions:
            return
        authority, allowed = self._scene_color_peer_transactions[-1]
        authority.verify_peers(allowed)

    def apply_color_to_item(self, item, color: QColor) -> None:
        with self._scene_color_peer_transaction(
            (item,),
            expand_ring_structures=True,
        ):
            self._apply_color_to_item_without_peer_guard(item, color)

    def _apply_color_to_item_without_peer_guard(self, item, color: QColor) -> None:
        if item is None or not color.isValid():
            return
        if not item_is_in_canvas_scene(self.canvas, item):
            return
        kind = _graphics_item_data_for_capture(item, 0)
        if kind == "bond":
            self._apply_bond_color(item, color)
            return
        if kind == "atom":
            self._apply_atom_color(item, color)
            return
        if kind == "ring":
            self._apply_ring_structure_color(item, color)
            return
        if kind == "note" and isinstance(item, QGraphicsTextItem):
            self._apply_note_color(item, color)
            return
        if kind == "shape":
            self._apply_shape_fill(item, color)

    def apply_color_to_items(self, items: Iterable[object], color: QColor) -> None:
        items = tuple(items)
        with self._scene_color_peer_transaction(
            items,
            expand_ring_structures=True,
        ):
            self._apply_color_to_items_without_peer_guard(items, color)

    def _apply_color_to_items_without_peer_guard(
        self,
        items: tuple[object, ...],
        color: QColor,
    ) -> None:
        raw_history_baseline = CallbackFreeHistoryBaseline.capture(
            self.history,
            canvas=self.canvas,
        )
        history_authority: _ColorHistoryAuthority | None = None
        rollback: Callable[[], None] | None = None
        try:
            rollback = self._batch_runtime_rollback(
                items,
                expand_ring_structures=True,
            )
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
            history_authority = _ColorHistoryAuthority.capture(
                self.history,
                canvas=self.canvas,
                raw_baseline=raw_history_baseline,
            )
            if isinstance(rollback, _ColorRuntimeAuthority):
                rollback.verify()
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
            history_authority.verify_prepublication()
        except BaseException as original_error:
            _close_failed_color_prepublication(
                original_error,
                runtime_rollback=rollback,
                runtime_phase="restoring runtime after color preflight",
                history_authority=history_authority,
                raw_history_baseline=raw_history_baseline,
                history_phase="color batch preflight",
            )
            raise
        assert history_authority is not None
        capture_published_runtime = self.history is not None
        published_runtime: _ColorRuntimeAuthority | None = None

        def apply_all() -> None:
            nonlocal published_runtime
            for item in items:
                self.apply_color_to_item(item, color)
            if capture_published_runtime:
                candidate = self._batch_runtime_rollback(
                    items,
                    expand_ring_structures=True,
                )
                if isinstance(candidate, _ColorRuntimeAuthority):
                    published_runtime = candidate

        self._run_history_transaction(
            apply_all,
            rollback=rollback,
            runtime_verify=(
                lambda: (
                    published_runtime.verify()
                    if published_runtime is not None
                    else None
                )
            ),
            history_authority=history_authority,
        )

    # Shape panels and ring fills stack behind the structure as ChemDraw-style
    # pastels: the picked colour is diluted toward the white sheet and applied
    # opaque, so it reads as tinted paper rather than translucent glass. A
    # translucent wash would blend with whatever sits underneath and look
    # layered instead.
    SHAPE_FILL_TINT = 0.12

    @staticmethod
    def _pastel_fill(color: QColor, tint: float) -> QColor:
        return QColor(
            round(255 - (255 - color.red()) * tint),
            round(255 - (255 - color.green()) * tint),
            round(255 - (255 - color.blue()) * tint),
        )

    def _record_scene_item_mutation(
        self,
        item,
        *,
        state_for: Callable[[object, object], dict],
        mutation: Callable[[], None],
        runtime_rollback: Callable[[], None] | None = None,
    ) -> None:
        rollback: UpdateSceneItemCommand | None = None
        try:
            before_state = state_for(self.canvas, item)
            rollback = UpdateSceneItemCommand(item, before_state, before_state)
            mutation()
            after_state = state_for(self.canvas, item)
            if before_state != after_state and self.history is not None:
                published_runtime = self._graphics_runtime_rollback(item)
                self._push_history_command(
                    UpdateSceneItemCommand(item, before_state, after_state),
                    rollback=(
                        runtime_rollback
                        if runtime_rollback is not None
                        else lambda: rollback.undo(self.canvas)
                    ),
                    runtime_verify=(
                        published_runtime.verify
                        if isinstance(published_runtime, _ColorRuntimeAuthority)
                        else None
                    ),
                )
        except BaseException as original_error:
            if self._color_rollback_is_complete(original_error):
                raise
            if runtime_rollback is not None:
                _run_color_rollback_step(
                    original_error,
                    "restoring scene-item graphics",
                    runtime_rollback,
                )
            elif rollback is not None:
                self._rollback_commands([rollback], original_error=original_error)
            raise

    def _apply_shape_fill(self, item, color: QColor) -> None:
        self._record_scene_item_mutation(
            item,
            state_for=shape_state_dict_for,
            mutation=lambda: item.setBrush(
                self._pastel_fill(color, self.SHAPE_FILL_TINT)
            ),
            runtime_rollback=self._graphics_runtime_rollback(item),
        )

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        with self._scene_color_peer_transaction(
            (item,),
            expand_ring_structures=False,
        ):
            self._apply_ring_fill_color_without_peer_guard(item, color, alpha)

    def _apply_ring_fill_color_without_peer_guard(
        self,
        item,
        color: QColor,
        alpha: float = 0.25,
    ) -> None:
        if item is None or _graphics_item_is_deleted(item) or not color.isValid():
            return
        if _graphics_item_data_for_capture(item, 0) != "ring":
            return
        # ``alpha`` is the pastel strength: 0 clears the fill, anything above
        # pre-dilutes the colour toward white and applies it opaque (the ring
        # sits behind the structure, so translucency is not needed).
        tint = max(0.0, min(1.0, float(alpha)))
        if tint <= 0.0:
            fill = QColor(color)
            fill.setAlphaF(0.0)
        else:
            fill = self._pastel_fill(color, tint)
        self._record_scene_item_mutation(
            item,
            state_for=ring_state_dict_for,
            mutation=lambda: item.setBrush(fill),
            runtime_rollback=self._graphics_runtime_rollback(item),
        )

    def apply_ring_fill_color_to_items(
        self,
        items: Iterable[object],
        color: QColor,
        alpha: float = 0.25,
    ) -> None:
        items = tuple(items)
        with self._scene_color_peer_transaction(
            items,
            expand_ring_structures=False,
        ):
            self._apply_ring_fill_color_to_items_without_peer_guard(
                items,
                color,
                alpha,
            )

    def _apply_ring_fill_color_to_items_without_peer_guard(
        self,
        items: tuple[object, ...],
        color: QColor,
        alpha: float,
    ) -> None:
        raw_history_baseline = CallbackFreeHistoryBaseline.capture(
            self.history,
            canvas=self.canvas,
        )
        history_authority: _ColorHistoryAuthority | None = None
        rollback: Callable[[], None] | None = None
        try:
            rollback = self._batch_runtime_rollback(
                items,
                expand_ring_structures=False,
            )
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
            history_authority = _ColorHistoryAuthority.capture(
                self.history,
                canvas=self.canvas,
                raw_baseline=raw_history_baseline,
            )
            if isinstance(rollback, _ColorRuntimeAuthority):
                rollback.verify()
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
            history_authority.verify_prepublication()
        except BaseException as original_error:
            _close_failed_color_prepublication(
                original_error,
                runtime_rollback=rollback,
                runtime_phase="restoring runtime after ring-fill preflight",
                history_authority=history_authority,
                raw_history_baseline=raw_history_baseline,
                history_phase="ring-fill batch preflight",
            )
            raise
        assert history_authority is not None
        capture_published_runtime = self.history is not None
        published_runtime: _ColorRuntimeAuthority | None = None

        def apply_all() -> None:
            nonlocal published_runtime
            for item in items:
                self.apply_ring_fill_color(item, color, alpha)
            if capture_published_runtime:
                candidate = self._batch_runtime_rollback(
                    items,
                    expand_ring_structures=False,
                )
                if isinstance(candidate, _ColorRuntimeAuthority):
                    published_runtime = candidate

        self._run_history_transaction(
            apply_all,
            rollback=rollback,
            runtime_verify=(
                lambda: (
                    published_runtime.verify()
                    if published_runtime is not None
                    else None
                )
            ),
            history_authority=history_authority,
        )

    def _run_history_transaction(
        self,
        mutation: Callable[[], None],
        *,
        rollback: Callable[[], None] | None = None,
        runtime_verify: Callable[[], None] | None = None,
        history_authority: _ColorHistoryAuthority | None = None,
    ) -> None:
        real_history = self.history
        history_authority = history_authority or _ColorHistoryAuthority.capture(
            real_history,
            canvas=self.canvas,
        )
        collected: list[HistoryCommand] = []
        self.history = _CollectingHistory(collected.append)
        try:
            mutation()
        except BaseException as error:
            runtime_rollback = rollback
            if runtime_rollback is None:
                def rollback_failed_mutation(
                    original_error: BaseException = error,
                ) -> None:
                    self._rollback_commands(
                        collected,
                        original_error=original_error,
                    )

                runtime_rollback = rollback_failed_mutation
            _close_failed_color_prepublication(
                error,
                runtime_rollback=runtime_rollback,
                runtime_phase="restoring the failed color batch runtime",
                history_authority=history_authority,
                history_phase="failed color batch mutation",
            )
            raise
        finally:
            self.history = real_history

        try:
            history_authority.verify_prepublication()
            if not collected or real_history is None:
                if real_history is not None:
                    # Even a no-op mutation crossed live history descriptors.
                    # Close on the exact post-mutation Qt/model runtime, then
                    # compare callback-free history storage last so neither
                    # authority can silently poison the other.
                    if runtime_verify is not None:
                        runtime_verify()
                    self._verify_active_scene_color_peers()
                    history_authority.verify_published_raw_commands(())
                return
        except BaseException as error:
            runtime_rollback = rollback
            if runtime_rollback is None:
                def rollback_prepublication(
                    original_error: BaseException = error,
                ) -> None:
                    self._rollback_commands(
                        collected,
                        original_error=original_error,
                    )

                runtime_rollback = rollback_prepublication
            _close_failed_color_prepublication(
                error,
                runtime_rollback=runtime_rollback,
                runtime_phase=(
                    "restoring runtime after color history preflight contamination"
                ),
                history_authority=history_authority,
                history_phase="color history prepublication",
            )
            raise
        command = (
            collected[0]
            if len(collected) == 1
            else CompositeCommand(commands=collected)
        )
        command_snapshot = HistoryCommandSnapshot.capture(command)
        history_snapshot: HistoryStackSnapshot | None = None
        try:
            history_snapshot = history_authority.stack_snapshot
            if history_snapshot is None:
                history_snapshot = HistoryStackSnapshot.capture(real_history)
            accepted = self._push_real_history_verified(real_history, command)
            command_snapshot.verify()
            history_authority.verify_published(command, accepted=accepted)
            history_authority.verify_published_live_commands(
                ((command, accepted),)
            )
            self._verify_published_color_result((command,), runtime_verify)
            command_snapshot.verify()
            history_authority.verify_published_raw_commands(
                ((command, accepted),)
            )
        except BaseException as error:
            command_snapshot.restore()
            history_authority.restore(
                error,
                phase="failed color history publication",
            )
            if history_snapshot is not None:
                assert history_authority is not None
                self._recover_failed_history_push(
                    error,
                    history_snapshot=history_snapshot,
                    history_authority=history_authority,
                    runtime_rollback=(
                        rollback
                        if rollback is not None
                        else lambda: command.undo(self.canvas)
                    ),
                    phase="color transaction",
                )
            elif rollback is not None:
                _run_color_rollback_step(
                    error,
                    "restoring the batch runtime snapshot",
                    rollback,
                )
            else:
                self._rollback_commands([command], original_error=error)
            raise

    @staticmethod
    def _push_real_history_verified(history, command: HistoryCommand) -> bool:
        enabled_authority = _FrozenHistoryEnabledAuthority.capture(history)
        try:
            result = history.push(command)
        except BaseException as original_error:
            enabled_authority.restore(original_error)
            raise
        if result is not False:
            return True
        if enabled_authority.value is False:
            # Disabled history is an explicit user/application policy: the
            # color mutation remains valid but intentionally unrecorded.
            disabled_result = RuntimeError(
                "color history push returned False while explicitly disabled"
            )
            if not enabled_authority.restore(disabled_result):
                raise disabled_result
            return False
        # A blocked/re-entrant or extension history service must not silently
        # turn a recorded color operation into an untracked mutation.
        rejection = RuntimeError(
            "color history push was rejected while history was enabled"
        )
        enabled_authority.restore(rejection)
        raise rejection

    def _recover_failed_history_push(
        self,
        original_error: BaseException,
        *,
        history_snapshot: HistoryStackSnapshot,
        history_authority: _ColorHistoryAuthority,
        runtime_rollback: Callable[[], None] | None,
        phase: str,
    ) -> None:
        runtime_authoritative = True
        if runtime_rollback is not None:
            try:
                runtime_rollback()
            except BaseException as rollback_error:
                runtime_authoritative = False
                _add_color_rollback_note(
                    original_error,
                    rollback_error,
                    phase=f"restoring runtime before {phase} publication",
                )
        if not runtime_authoritative:
            history_authority.restore(
                original_error,
                phase=f"{phase} runtime-failure history authority",
            )
            self._mark_color_rollback_complete(original_error)
            return

        history_authoritative = history_snapshot.restore(
            original_error,
            phase=phase,
        )
        if not history_authoritative:
            history_authority.restore(
                original_error,
                phase=f"{phase} notification-failure history authority",
            )
            self._mark_color_rollback_complete(original_error)
            return

        post_errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                # History setters/getters are callback ports and may re-poison
                # the just-restored Qt/model color runtime.  Always make the
                # runtime authority the final writer, then verify history roots,
                # re-check the callback-free Qt authority, and close on raw
                # built-in list storage.  No callback runs after that final raw
                # stack comparison.
                history_restored = history_authority.restore(
                    original_error,
                    phase=f"{phase} after notification",
                )
                if runtime_rollback is not None:
                    runtime_rollback()
                if not history_restored:
                    raise RuntimeError(
                        "color rollback history remained non-authoritative"
                    )
                self._verify_color_history_runtime_composite(
                    history_authority,
                    runtime_rollback,
                )
            except BaseException as post_error:
                post_errors.append(post_error)
                continue
            self._mark_color_rollback_complete(original_error)
            return
        for recorded_post_error in post_errors:
            _add_color_rollback_note(
                original_error,
                recorded_post_error,
                phase=f"reasserting runtime/history after {phase} publication",
            )
        self._mark_color_rollback_complete(original_error)

    @staticmethod
    def _verify_color_history_runtime_composite(
        history_authority: _ColorHistoryAuthority,
        runtime_rollback: Callable[[], None] | None,
    ) -> None:
        """Verify live stacks/policy before Qt runtime and raw storage last."""

        history_snapshot = history_authority.stack_snapshot
        if history_snapshot is None:
            raise RuntimeError("color rollback lost its exact history authority")
        _verify_history_and_policy_authority(
            history_snapshot,
            history_authority.policy_snapshot,
        )

        # Every production color rollback is an exact authority whose verifier
        # uses Qt base getters for text/brush/pen.  Keep compatibility with a
        # command-only extension rollback by relying on the completed restore
        # call above when no independent verifier is available.
        if isinstance(runtime_rollback, _ColorRuntimeAuthority):
            runtime_rollback.verify()
        if history_authority.raw_baseline is None:
            raise RuntimeError("color rollback lost its callback-free history authority")
        # No live descriptor or observer callback may run after this final raw
        # stack/policy comparison.
        history_authority.raw_baseline.verify()

    @staticmethod
    def _mark_color_rollback_complete(error: BaseException) -> None:
        with contextlib.suppress(BaseException):
            namespace = object.__getattribute__(error, "__dict__")
            if isinstance(namespace, dict):
                dict.__setitem__(
                    namespace,
                    "_chemvas_color_rollback_complete",
                    True,
                )

    @staticmethod
    def _color_rollback_is_complete(error: BaseException) -> bool:
        with contextlib.suppress(BaseException):
            namespace = object.__getattribute__(error, "__dict__")
            if isinstance(namespace, dict):
                return dict.get(namespace, "_chemvas_color_rollback_complete") is True
        return False

    def _rollback_commands(
        self,
        commands: Iterable[HistoryCommand],
        *,
        original_error: BaseException,
    ) -> None:
        for command in reversed(tuple(commands)):

            def undo_command(command_to_undo: HistoryCommand = command) -> None:
                command_to_undo.undo(self.canvas)

            _run_color_rollback_step(
                original_error,
                f"undoing {type(command).__name__}",
                undo_command,
            )

    def _push_history_command(
        self,
        command: HistoryCommand,
        *,
        rollback: Callable[[], None] | None = None,
        runtime_verify: Callable[[], None] | None = None,
    ) -> None:
        self._push_history_commands(
            [command],
            rollback=rollback,
            runtime_verify=runtime_verify,
        )

    def _push_history_commands(
        self,
        commands: Iterable[HistoryCommand],
        *,
        rollback: Callable[[], None] | None = None,
        runtime_verify: Callable[[], None] | None = None,
    ) -> None:
        if self.history is None:
            return
        commands = tuple(commands)
        if not commands:
            return
        command_snapshots = tuple(
            HistoryCommandSnapshot.capture(command) for command in commands
        )
        history_authority: _ColorHistoryAuthority | None = None
        history_snapshot: HistoryStackSnapshot | None = None
        publications: list[tuple[HistoryCommand, bool]] = []
        try:
            history_authority = _ColorHistoryAuthority.capture(
                self.history,
                canvas=self.canvas,
            )
            history_snapshot = history_authority.stack_snapshot
            if history_snapshot is None:
                history_snapshot = HistoryStackSnapshot.capture(self.history)
            for command in commands:
                accepted = self._push_real_history_verified(self.history, command)
                publications.append((command, accepted))
                for command_snapshot in command_snapshots:
                    command_snapshot.verify()
                history_authority.verify_published_commands(publications)
            history_authority.verify_published_live_commands(publications)
            self._verify_published_color_result(commands, runtime_verify)
            for command_snapshot in command_snapshots:
                command_snapshot.verify()
            history_authority.verify_published_raw_commands(publications)
        except BaseException as error:
            for command_snapshot in command_snapshots:
                command_snapshot.restore()
            if history_authority is not None:
                history_authority.restore(
                    error,
                    phase="failed single-item color history publication",
                )
            if history_snapshot is not None:
                assert history_authority is not None
                self._recover_failed_history_push(
                    error,
                    history_snapshot=history_snapshot,
                    history_authority=history_authority,
                    runtime_rollback=rollback,
                    phase="color command",
                )
            raise

    def _verify_published_color_result(
        self,
        commands: Iterable[HistoryCommand],
        runtime_verify: Callable[[], None] | None,
    ) -> None:
        """Close a successful publication on its command and runtime state."""

        self._verify_color_commands_after(commands)
        if runtime_verify is not None:
            # The exact runtime verifier is deliberately final. Production
            # authorities close on raw model fields and Qt base getters, so a
            # successful history observer cannot remain the last writer.
            runtime_verify()
        self._verify_active_scene_color_peers()

    def _verify_color_commands_after(
        self,
        commands: Iterable[HistoryCommand],
    ) -> None:
        flattened: list[HistoryCommand] = []

        def flatten(command: HistoryCommand) -> None:
            if isinstance(command, CompositeCommand):
                for child in command.commands:
                    flatten(child)
                return
            flattened.append(command)

        for command in commands:
            flatten(command)

        # Several linear commands may intentionally target the same runtime
        # (a pending note edit followed by its color command, for example).
        # Only the last command for that authority describes the published
        # state; earlier after-states are intermediate history checkpoints.
        verified_targets: set[tuple[str, object]] = set()
        for command in reversed(flattened):
            if isinstance(command, UpdateAtomColorCommand):
                key = ("atom", command.atom_id)
                if key in verified_targets:
                    continue
                verified_targets.add(key)
                atom = atom_for_id(self.canvas, command.atom_id)
                if atom is None or atom.color != command.after_color:
                    raise RuntimeError("atom color changed after history publication")
                continue
            if isinstance(command, UpdateBondColorCommand):
                key = ("bond", command.bond_id)
                if key in verified_targets:
                    continue
                verified_targets.add(key)
                bond = bond_for_id(self.canvas, command.bond_id)
                if bond is None or bond.color != command.after_color:
                    raise RuntimeError("bond color changed after history publication")
                continue
            if isinstance(
                command,
                (UpdateNoteColorCommand, _CommitPendingNoteEditCommand),
            ):
                key = ("note", id(command.item))
                if key in verified_targets:
                    continue
                verified_targets.add(key)
                if _NoteColorState.capture(command.item) != command.after_state:
                    raise RuntimeError("note color changed after history publication")
                continue
            if isinstance(command, UpdateSceneItemCommand):
                key = ("scene-item", id(command.item))
                if key in verified_targets:
                    continue
                verified_targets.add(key)
                kind = command.after_state.get("kind")
                state_for = {
                    "shape": shape_state_dict_for,
                    "ring": ring_state_dict_for,
                    "note": note_state_dict_for,
                }.get(kind if isinstance(kind, str) else "")
                if (
                    state_for is not None
                    and state_for(self.canvas, command.item) != command.after_state
                ):
                    raise RuntimeError(
                        "scene-item color changed after history publication"
                    )

    @staticmethod
    def _pending_note_edit_command(
        item: QGraphicsTextItem,
        current_state: dict,
        runtime: _NoteColorState,
    ) -> HistoryCommand | None:
        current_text = item.toPlainText().strip()
        if not current_text:
            return None
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        current_html = item.toHtml()
        html_changed = bool(committed_html) and current_html != committed_html
        if current_text == committed_text and not html_changed:
            return None
        if not committed_text:
            return AddSceneItemsCommand(
                item_states=[current_state],
                items=[item],
            )
        return _CommitPendingNoteEditCommand(
            item=item,
            before_state=_NoteColorState(
                html=committed_html,
                cursor_anchor=0,
                cursor_position=0,
                interaction_flags=Qt.TextInteractionFlag.NoTextInteraction,
                default_text_color=QColor(runtime.default_text_color),
                committed_text=committed_text,
                committed_html=committed_html,
            ),
            after_state=_NoteColorState(
                html=runtime.html,
                cursor_anchor=runtime.cursor_anchor,
                cursor_position=runtime.cursor_position,
                interaction_flags=runtime.interaction_flags,
                default_text_color=QColor(runtime.default_text_color),
                committed_text=current_text,
                committed_html=current_html,
            ),
        )

    def _apply_note_color(self, item, color: QColor) -> None:
        original_runtime = _NoteColorState.capture(item)
        current_state = note_state_dict_for(self.canvas, item)
        pending_command = self._pending_note_edit_command(
            item,
            current_state,
            original_runtime,
        )
        baseline_matches_runtime = (
            original_runtime.committed_html == original_runtime.html
        )
        commands: list[HistoryCommand] = []

        def mutate() -> None:
            document = item.document()
            if document is None:
                return
            char_format = QTextCharFormat()
            char_format.setForeground(color)
            cursor = item.textCursor()
            if cursor.hasSelection():
                # Recolour only the text the user has selected, so a single note can
                # hold several colours. The selection is kept so it stays visible.
                cursor.mergeCharFormat(char_format)
                item.setTextCursor(cursor)
                return
            whole = QTextCursor(document)
            whole.select(QTextCursor.SelectionType.Document)
            whole.mergeCharFormat(char_format)
            item.setDefaultTextColor(color)

        try:
            if pending_command is not None:
                commands.append(pending_command)
                set_committed_note_text_for(item, item.toPlainText().strip())
                set_committed_note_html_for(item, item.toHtml())
            before_color_runtime = _NoteColorState.capture(item)
            before_color_state = note_state_dict_for(self.canvas, item)
            mutate()
            # Formatting a fully committed note is itself the committed edit.
            # Keep the focus-out baseline in sync so the note controller does
            # not record the same colour change a second time later. Pending
            # typing is first represented by its own history command above, so
            # it is now safe to advance that baseline before recording color.
            if pending_command is not None or baseline_matches_runtime:
                set_committed_note_html_for(item, item.toHtml())
            after_state = note_state_dict_for(self.canvas, item)
            if before_color_state != after_state:
                commands.append(
                    UpdateNoteColorCommand(
                        item=item,
                        before_state=before_color_runtime,
                        after_state=_NoteColorState.capture(item),
                    )
                )
            published_runtime = (
                self._note_runtime_rollback(item)
                if commands and self.history is not None
                else None
            )
            self._push_history_commands(
                commands,
                rollback=lambda: original_runtime.apply(item),
                runtime_verify=(
                    published_runtime.verify
                    if isinstance(published_runtime, _ColorRuntimeAuthority)
                    else None
                ),
            )
        except BaseException as original_error:
            if self._color_rollback_is_complete(original_error):
                raise
            _run_color_rollback_step(
                original_error,
                "restoring the original note runtime",
                lambda: original_runtime.apply(item),
            )
            raise

    def _apply_bond_color(self, item, color: QColor) -> None:
        bond_id = _graphics_item_data_for_capture(item, 1)
        if not isinstance(bond_id, int):
            return
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        before_color = bond.color
        rollback = self._bond_runtime_rollback(item)
        try:
            _apply_bond_color_in_place(self.canvas, bond_id, color)
            after_color = bond.color
            if before_color != after_color and self.history is not None:
                published_runtime = self._bond_runtime_rollback(item)
                self._push_history_command(
                    UpdateBondColorCommand(
                        bond_id=bond_id,
                        before_color=before_color,
                        after_color=after_color,
                    ),
                    rollback=rollback,
                    runtime_verify=(
                        published_runtime.verify
                        if isinstance(published_runtime, _ColorRuntimeAuthority)
                        else None
                    ),
                )
        except BaseException as error:
            if self._color_rollback_is_complete(error):
                raise
            try:
                rollback()
            except BaseException as rollback_error:
                _add_color_rollback_note(
                    error,
                    rollback_error,
                    phase="restoring the bond color",
                )
            raise

    def _apply_atom_item_graphic(self, item, color: QColor) -> None:
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(color)
        elif isinstance(item, AtomDotItem):
            item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(color)

    def _apply_atom_color(self, item, color: QColor) -> None:
        atom_id = _graphics_item_data_for_capture(item, 1)
        atom = atom_for_id(
            self.canvas,
            atom_id if isinstance(atom_id, int) else None,
        )
        if atom is None:
            rollback = self._graphics_runtime_rollback(item)
            try:
                self._apply_atom_item_graphic(item, color)
            except BaseException as original_error:
                _run_color_rollback_step(
                    original_error,
                    "restoring orphan atom graphics",
                    rollback,
                )
                raise
            return
        assert isinstance(atom_id, int)
        before_color = atom.color
        rollback = self._atom_runtime_rollback(item)
        try:
            self._apply_atom_item_graphic(item, color)
            atom.color = color.name()
            label_item = atom_items_for(self.canvas).get(atom_id)
            if label_item is not None and label_item is not item:
                label_item.setDefaultTextColor(color)
            dot_item = atom_dots_for(self.canvas).get(atom_id)
            if dot_item is not None and dot_item is not item:
                dot_item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
            after_color = atom.color
            if before_color != after_color and self.history is not None:
                published_runtime = self._atom_runtime_rollback(item)
                self._push_history_command(
                    UpdateAtomColorCommand(
                        atom_id=atom_id,
                        before_color=before_color,
                        after_color=after_color,
                    ),
                    rollback=rollback,
                    runtime_verify=(
                        published_runtime.verify
                        if isinstance(published_runtime, _ColorRuntimeAuthority)
                        else None
                    ),
                )
        except BaseException as error:
            if self._color_rollback_is_complete(error):
                raise
            try:
                rollback()
            except BaseException as rollback_error:
                _add_color_rollback_note(
                    error,
                    rollback_error,
                    phase="restoring the atom color",
                )
            raise

    def _apply_ring_structure_color(self, item, color: QColor) -> None:
        targets = self._ring_structure_targets(item)
        if not targets:
            return
        # A ring is itself one color transaction. This remains atomic when it is
        # nested inside a multi-selection transaction because the outer collector
        # captures this transaction's single command.
        self.apply_color_to_items(targets, color)

    def _ring_structure_targets(self, item) -> list[object]:
        ring_atom_ids = _graphics_item_data_for_capture(item, 2)
        if ring_atom_ids is _DELETED_GRAPHICS_ITEM:
            return []
        if not isinstance(ring_atom_ids, list):
            return []
        atom_ids = {
            atom_id
            for atom_id in ring_atom_ids
            if isinstance(atom_id, int)
            and atom_for_id(self.canvas, atom_id) is not None
        }
        if not atom_ids:
            return []
        bond_ids, _ = self.graph_service.bond_sets_for_atoms(atom_ids)
        targets: list[object] = []
        for atom_id in sorted(atom_ids):
            atom_item = visible_atom_item_for(self.canvas, atom_id)
            if atom_item is not None:
                targets.append(atom_item)
        for bond_id in sorted(bond_ids):
            bond_items = bond_items_for_id(self.canvas, bond_id)
            if bond_items:
                targets.append(bond_items[0])
        return targets

    def _graphics_runtime_rollback(self, item) -> Callable[[], None]:
        if _graphics_item_is_deleted(item):
            return lambda: None
        text_color = (
            QColor(QGraphicsTextItem.defaultTextColor(item))
            if isinstance(item, QGraphicsTextItem)
            else None
        )
        brush = _captured_graphics_brush(item)
        pen = _captured_graphics_pen(item)

        if text_color is None and brush is None and pen is None:
            raise RuntimeError("color runtime has no exact Qt text/brush/pen authority")

        def restore() -> None:
            operations: list[Callable[[], None]] = []
            if text_color is not None and isinstance(item, QGraphicsTextItem):
                operations.append(
                    lambda: QGraphicsTextItem.setDefaultTextColor(
                        item,
                        QColor(text_color),
                    )
                )
            if pen is not None:
                operations.append(lambda: _set_graphics_pen_exact(item, pen))
            if brush is not None:
                operations.append(lambda: _set_graphics_brush_exact(item, brush))
            _run_restore_operations("Graphics color rollback failed", operations)

        def verify() -> None:
            if _graphics_item_is_deleted(item):
                raise RuntimeError("color rollback graphics item was deleted")
            if (
                text_color is not None
                and isinstance(item, QGraphicsTextItem)
                and QGraphicsTextItem.defaultTextColor(item) != text_color
            ):
                raise RuntimeError("text color did not match its savepoint")
            if pen is not None:
                actual_pen = (
                    QPen(QAbstractGraphicsShapeItem.pen(item))
                    if isinstance(item, QAbstractGraphicsShapeItem)
                    else _captured_graphics_pen(item)
                )
                if actual_pen != pen:
                    raise RuntimeError("graphics pen did not match its savepoint")
            if brush is not None:
                actual_brush = (
                    QBrush(QAbstractGraphicsShapeItem.brush(item))
                    if isinstance(item, QAbstractGraphicsShapeItem)
                    else _captured_graphics_brush(item)
                )
                if actual_brush != brush:
                    raise RuntimeError("graphics brush did not match its savepoint")

        return _ColorRuntimeAuthority(restore, verify)

    def _note_runtime_rollback(
        self,
        item: QGraphicsTextItem,
    ) -> _ColorRuntimeAuthority:
        state = _NoteColorState.capture(item)

        def verify() -> None:
            if _NoteColorState.capture(item) != state:
                raise RuntimeError("note color runtime did not match its savepoint")

        return _ColorRuntimeAuthority(lambda: state.apply(item), verify)

    def _atom_runtime_rollback(self, item) -> Callable[[], None]:
        atom_id = _graphics_item_data_for_capture(item, 1)
        if atom_id is _DELETED_GRAPHICS_ITEM:
            return lambda: None
        if not isinstance(atom_id, int):
            return self._graphics_runtime_rollback(item)
        atom = atom_for_id(self.canvas, atom_id)
        before_color = atom.color if atom is not None else None
        graphics_items = [
            item,
            atom_items_for(self.canvas).get(atom_id),
            atom_dots_for(self.canvas).get(atom_id),
        ]
        restores = self._unique_graphics_restores(graphics_items)

        def restore() -> None:
            operations: list[Callable[[], None]] = []
            if before_color is not None:

                def restore_model_color() -> None:
                    current_atom = atom_for_id(self.canvas, atom_id)
                    if current_atom is not None:
                        current_atom.color = before_color

                operations.append(restore_model_color)
            for restore_graphics in restores:
                operations.append(restore_graphics)
            _run_restore_operations("Atom color rollback failed", operations)

        def verify() -> None:
            if atom is not None:
                current_atom = atom_for_id(self.canvas, atom_id)
                if current_atom is not atom or current_atom.color != before_color:
                    raise RuntimeError(
                        "atom color authority did not match its savepoint"
                    )
            self._verify_runtime_restores(restores)

        return _ColorRuntimeAuthority(restore, verify)

    def _bond_runtime_rollback(self, item) -> Callable[[], None]:
        bond_id = _graphics_item_data_for_capture(item, 1)
        if bond_id is _DELETED_GRAPHICS_ITEM:
            return lambda: None
        if not isinstance(bond_id, int):
            return self._graphics_runtime_rollback(item)
        bond = bond_for_id(self.canvas, bond_id)
        before_color = bond.color if bond is not None else None
        restores = self._unique_graphics_restores(
            bond_items_for_id(self.canvas, bond_id)
        )

        def restore() -> None:
            operations: list[Callable[[], None]] = []
            if before_color is not None:

                def restore_model_color() -> None:
                    current_bond = bond_for_id(self.canvas, bond_id)
                    if current_bond is not None:
                        current_bond.color = before_color

                operations.append(restore_model_color)
            for restore_graphics in restores:
                operations.append(restore_graphics)
            _run_restore_operations("Bond color rollback failed", operations)

        def verify() -> None:
            if bond is not None:
                current_bond = bond_for_id(self.canvas, bond_id)
                if current_bond is not bond or current_bond.color != before_color:
                    raise RuntimeError(
                        "bond color authority did not match its savepoint"
                    )
            self._verify_runtime_restores(restores)

        return _ColorRuntimeAuthority(restore, verify)

    @staticmethod
    def _verify_runtime_restores(restores: Iterable[Callable[[], None]]) -> None:
        for restore in restores:
            if isinstance(restore, _ColorRuntimeAuthority):
                restore.verify()

    def _unique_graphics_restores(
        self, items: Iterable[object | None]
    ) -> list[Callable[[], None]]:
        restores: list[Callable[[], None]] = []
        seen_ids: set[int] = set()
        for item in items:
            if item is None or id(item) in seen_ids or _graphics_item_is_deleted(item):
                continue
            seen_ids.add(id(item))
            try:
                restores.append(self._graphics_runtime_rollback(item))
            except RuntimeError:
                if not isinstance(item, QGraphicsItem):
                    # Lightweight model-companion test doubles are not direct
                    # color transaction targets. Production companions are Qt
                    # items and must always expose an exact authority.
                    continue
                raise
        return restores

    def _batch_runtime_rollback(
        self,
        items: Iterable[object],
        *,
        expand_ring_structures: bool,
    ) -> Callable[[], None] | None:
        restores: list[Callable[[], None]] = []
        seen_ids: set[int] = set()

        def capture_target(item: object, kind: object) -> bool:
            if item is None or id(item) in seen_ids or _graphics_item_is_deleted(item):
                return True
            seen_ids.add(id(item))
            if kind is _DELETED_GRAPHICS_ITEM:
                return True
            if kind not in {"atom", "bond", "note", "shape", "ring"}:
                # Keep the generic command-based transaction behavior for test
                # doubles and extension items whose runtime state this service
                # does not know how to snapshot exactly.
                return False
            if kind == "atom":
                restores.append(self._atom_runtime_rollback(item))
            elif kind == "bond":
                restores.append(self._bond_runtime_rollback(item))
            elif kind == "note" and isinstance(item, QGraphicsTextItem):
                restores.append(self._note_runtime_rollback(item))
            else:
                restores.append(self._graphics_runtime_rollback(item))
            return True

        def unwind_unsupported_capture() -> None:
            # Returning ``None`` hands this batch back to command-based
            # rollback.  Before doing so, close every authority already
            # captured: the unsupported item's live data getter may have
            # contaminated an earlier target without raising.
            _run_restore_operations(
                "Unsupported color batch capture unwind failed",
                reversed(restores),
            )

        try:
            # Capture each target immediately after resolving it.  A later live
            # data/brush/pen getter can mutate an earlier target before raising;
            # retaining the earlier authority lets capture abort unwind that
            # contamination even though no color mutation has started yet.
            for item in items:
                kind = _graphics_item_data_for_capture(item, 0)
                if kind is _DELETED_GRAPHICS_ITEM:
                    continue
                if expand_ring_structures and kind == "ring":
                    for target in self._ring_structure_targets(item):
                        target_kind = _graphics_item_data_for_capture(target, 0)
                        if not capture_target(target, target_kind):
                            unwind_unsupported_capture()
                            return None
                    continue
                if not capture_target(item, kind):
                    unwind_unsupported_capture()
                    return None
        except BaseException as original_error:
            for restore in reversed(restores):
                _run_color_rollback_step(
                    original_error,
                    "unwinding a partially captured batch runtime",
                    restore,
                )
            raise

        def restore_all() -> None:
            _run_restore_operations(
                "Color batch runtime rollback failed",
                reversed(restores),
            )

        return _ColorRuntimeAuthority(
            restore_all,
            lambda: self._verify_runtime_restores(restores),
        )


__all__ = [
    "CanvasColorMutationService",
    "UpdateBondColorCommand",
    "UpdateNoteColorCommand",
]
