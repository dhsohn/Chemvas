from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

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

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
    UpdateAtomColorCommand,
)
from chemvas.ui.atom_label_access import implicit_carbon_dot_brush_for
from chemvas.ui.bond_graphics_access import apply_color_to_bond_item_for
from chemvas.ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    set_atom_dots_for,
    set_atom_items_for,
    visible_atom_item_for,
)
from chemvas.ui.canvas_bond_graphics_state import (
    bond_items_for,
    bond_items_for_id,
    set_bond_items_for,
)
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_for_id,
    bonds_for,
)
from chemvas.ui.graphics_items import AtomDotItem
from chemvas.ui.history_commands import AddSceneItemsCommand, UpdateSceneItemCommand
from chemvas.ui.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from chemvas.ui.scene_item_access import item_is_in_canvas_scene
from chemvas.ui.scene_item_state import (
    note_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


class _CollectingHistory:
    """Drop-in for the history service that captures pushed commands instead of
    recording them, so a multi-element mutation can be bundled into one command."""

    def __init__(self, sink) -> None:
        self._sink = sink

    def push(self, command) -> bool:
        self._sink(command)
        return True

    def push_many(self, commands: Iterable[HistoryCommand]) -> bool:
        for command in commands:
            self._sink(command)
        return True

    @staticmethod
    def is_enabled() -> bool:
        return True


def _set_graphics_brush_exact(item, brush: QBrush) -> None:
    item.setBrush(QBrush(brush))


def _set_graphics_pen_exact(item, pen: QPen) -> None:
    item.setPen(QPen(pen))


_DELETED_GRAPHICS_ITEM = object()
_MISSING_CAPTURE_ATTRIBUTE = object()


def _graphics_item_is_deleted(item: object) -> bool:
    return isinstance(item, QGraphicsItem) and sip.isdeleted(item)


def _optional_live_capture_attribute(item: object, name: str) -> object | None:
    return getattr(item, name, None)


def _graphics_item_data_for_capture(item: object, role: int) -> object:
    if _graphics_item_is_deleted(item):
        return _DELETED_GRAPHICS_ITEM
    try:
        data = _optional_live_capture_attribute(item, "data")
        return data(role) if callable(data) else None
    except Exception:
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
        if isinstance(value, QBrush):
            return QBrush(value)
        # Non-Qt extension/test doubles may expose a dynamic ``brush`` mock
        # without implementing Qt's QBrush contract. It is not a partial Qt
        # snapshot; leave that unsupported proxy to command-based rollback.
        return QBrush(value) if isinstance(item, QGraphicsItem) else None
    except Exception:
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
        if isinstance(value, QPen):
            return QPen(value)
        return QPen(value) if isinstance(item, QGraphicsItem) else None
    except Exception:
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
    except Exception as rollback_error:
        _add_color_rollback_note(
            original_error,
            rollback_error,
            phase=phase,
        )


def _close_failed_color_prepublication(
    original_error: BaseException,
    *,
    runtime_rollback: Callable[[], None] | None,
    runtime_phase: str,
) -> None:
    if runtime_rollback is not None:
        _run_color_rollback_step(
            original_error,
            runtime_phase,
            runtime_rollback,
        )


def _run_restore_operations(
    label: str,
    operations: Iterable[Callable[[], None]],
) -> None:
    errors: list[BaseException] = []
    for operation in operations:
        try:
            operation()
        except Exception as error:
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
    except Exception as original_error:
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
        item.setDefaultTextColor(QColor(self.default_text_color))
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
        self.restore_once()
        self.verify()


@dataclass
class UpdateNoteColorCommand(HistoryCommand):
    item: QGraphicsTextItem
    before_state: _NoteColorState
    after_state: _NoteColorState

    def _apply(self, state: _NoteColorState, rollback_state: _NoteColorState) -> None:
        try:
            state.apply(self.item)
        except Exception as original_error:
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
        except Exception as original_error:
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
class _SceneGraphicsRegistryAuthority:
    canvas: object
    atom_items: dict[int, object]
    atom_item_entries: tuple[tuple[int, object], ...]
    atom_dots: dict[int, object]
    atom_dot_entries: tuple[tuple[int, object], ...]
    bond_items: dict[int, list[object]]
    bond_item_entries: tuple[tuple[int, list[object]], ...]
    bond_list_contents: tuple[tuple[list[object], tuple[object, ...]], ...]
    item_scenes: tuple[tuple[QGraphicsItem, QGraphicsScene | None], ...]

    @classmethod
    def capture(
        cls,
        canvas: object,
        scene: QGraphicsScene,
    ) -> _SceneGraphicsRegistryAuthority:
        atom_items = cast(dict[int, object], atom_items_for(canvas))
        atom_dots = cast(dict[int, object], atom_dots_for(canvas))
        bond_items = cast(dict[int, list[object]], bond_items_for(canvas))
        atom_item_entries = tuple(dict.items(atom_items))
        atom_dot_entries = tuple(dict.items(atom_dots))
        bond_item_entries = tuple(dict.items(bond_items))
        bond_list_contents = tuple(
            (items, tuple(items)) for _bond_id, items in bond_item_entries
        )
        scene_states: list[tuple[QGraphicsItem, QGraphicsScene | None]] = []
        seen: set[int] = set()
        for candidate in (
            *(value for _key, value in atom_item_entries),
            *(value for _key, value in atom_dot_entries),
            *(value for _items, contents in bond_list_contents for value in contents),
        ):
            if not isinstance(candidate, QGraphicsItem) or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            scene_states.append((candidate, candidate.scene()))
        return cls(
            canvas=canvas,
            atom_items=atom_items,
            atom_item_entries=atom_item_entries,
            atom_dots=atom_dots,
            atom_dot_entries=atom_dot_entries,
            bond_items=bond_items,
            bond_item_entries=bond_item_entries,
            bond_list_contents=bond_list_contents,
            item_scenes=tuple(scene_states),
        )

    @staticmethod
    def _mapping_is_exact(
        mapping: dict[int, object],
        entries: tuple[tuple[int, object], ...],
    ) -> bool:
        actual = tuple(mapping.items())
        return len(actual) == len(entries) and all(
            actual_key == expected_key and actual_value is expected_value
            for (actual_key, actual_value), (
                expected_key,
                expected_value,
            ) in zip(actual, entries, strict=True)
        )

    def verify(self) -> None:
        if atom_items_for(
            self.canvas
        ) is not self.atom_items or not self._mapping_is_exact(
            self.atom_items,
            self.atom_item_entries,
        ):
            raise RuntimeError(
                "atom graphics registry changed during color transaction"
            )
        if atom_dots_for(
            self.canvas
        ) is not self.atom_dots or not self._mapping_is_exact(
            self.atom_dots,
            self.atom_dot_entries,
        ):
            raise RuntimeError("atom-dot registry changed during color transaction")
        if bond_items_for(
            self.canvas
        ) is not self.bond_items or not self._mapping_is_exact(
            cast(dict[int, object], self.bond_items),
            cast(tuple[tuple[int, object], ...], self.bond_item_entries),
        ):
            raise RuntimeError(
                "bond graphics registry changed during color transaction"
            )
        for items, contents in self.bond_list_contents:
            actual = tuple(items)
            if len(actual) != len(contents) or any(
                value is not expected
                for value, expected in zip(actual, contents, strict=True)
            ):
                raise RuntimeError(
                    "bond graphics list changed during color transaction"
                )
        for item, expected_scene in self.item_scenes:
            if sip.isdeleted(item) or item.scene() is not expected_scene:
                raise RuntimeError(
                    "mapped graphics scene identity changed during color transaction"
                )

    def verify_frozen_targets(self, targets: Iterable[object]) -> None:
        self.verify()
        captured_scenes = {
            id(item): expected_scene for item, expected_scene in self.item_scenes
        }
        for target in targets:
            if not isinstance(target, QGraphicsItem):
                continue
            expected_scene = captured_scenes.get(
                id(target),
                _MISSING_CAPTURE_ATTRIBUTE,
            )
            if expected_scene is _MISSING_CAPTURE_ATTRIBUTE:
                raise RuntimeError(
                    "frozen ring target had no captured registry scene identity"
                )
            if sip.isdeleted(target) or target.scene() is not expected_scene:
                raise RuntimeError(
                    "frozen ring target scene identity changed before mutation"
                )

    def restore(self) -> None:
        set_atom_items_for(self.canvas, self.atom_items)
        set_atom_dots_for(self.canvas, self.atom_dots)
        set_bond_items_for(self.canvas, self.bond_items)
        for items, contents in self.bond_list_contents:
            items[:] = contents
        self.atom_items.clear()
        self.atom_items.update(self.atom_item_entries)
        self.atom_dots.clear()
        self.atom_dots.update(self.atom_dot_entries)
        self.bond_items.clear()
        self.bond_items.update(self.bond_item_entries)
        for item, expected_scene in self.item_scenes:
            if sip.isdeleted(item):
                raise RuntimeError(
                    "mapped graphics item was deleted during color transaction"
                )
            current_scene = item.scene()
            if current_scene is expected_scene:
                continue
            if current_scene is not None:
                current_scene.removeItem(item)
            if expected_scene is not None:
                expected_scene.addItem(item)
        self.verify()


@dataclass(frozen=True, slots=True)
class _SceneColorPeerAuthority:
    service: CanvasColorMutationService
    item_states: tuple[_SceneColorItemState, ...]
    model_states: tuple[_SceneModelColorState, ...]
    registry: _SceneGraphicsRegistryAuthority | None = None

    def _verify_model_state(self, state: _SceneModelColorState) -> None:
        current = (
            atom_for_id(self.service.canvas, state.object_id)
            if state.kind == "atom"
            else bond_for_id(self.service.canvas, state.object_id)
        )
        if (
            current is not state.target
            or getattr(current, "color", None) != state.color
        ):
            raise RuntimeError(
                f"non-target scene {state.kind} color changed during publication"
            )

    def verify_peers(self, allowed_graphics_ids: frozenset[int]) -> None:
        if self.registry is not None:
            self.registry.verify()
        for item_state in self.item_states:
            if id(item_state.item) not in allowed_graphics_ids:
                item_state.runtime.verify()
        for model_state in self.model_states:
            if not model_state.graphics_ids.intersection(allowed_graphics_ids):
                self._verify_model_state(model_state)

    def restore(self, original_error: BaseException) -> None:
        def restore_once() -> None:
            if self.registry is not None:
                self.registry.restore()
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
            if self.registry is not None:
                self.registry.restore()

        def verify_all() -> None:
            if self.registry is not None:
                self.registry.verify()
            for item_state in self.item_states:
                item_state.runtime.verify()
            for model_state in self.model_states:
                self._verify_model_state(model_state)

        try:
            _ColorRuntimeAuthority(restore_once, verify_all)()
        except Exception as restore_error:
            _add_color_rollback_note(
                original_error,
                restore_error,
                phase="restoring scene-wide color peer authority",
            )


@dataclass(frozen=True, slots=True)
class _SceneColorPeerTransaction:
    authority: _SceneColorPeerAuthority
    allowed_graphics_ids: frozenset[int]
    ring_targets: tuple[tuple[object, tuple[object, ...]], ...]

    def targets_for_ring(self, item: object) -> tuple[object, ...] | None:
        targets = next(
            (
                targets
                for captured_item, targets in self.ring_targets
                if captured_item is item
            ),
            None,
        )
        if targets is None:
            return None
        registry = self.authority.registry
        if registry is not None:
            registry.verify_frozen_targets(targets)
        return targets


class CanvasColorMutationService:
    def __init__(
        self, canvas: CanvasView, *, graph_service, history_service=None
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.graph_service = graph_service
        self._scene_color_peer_transactions: list[_SceneColorPeerTransaction] = []

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
            and item.scene() is scene
        )

    def _capture_scene_color_peer_authority(
        self,
    ) -> _SceneColorPeerAuthority | None:
        if not isinstance(self.canvas, QGraphicsView):
            return None
        scene = self.canvas.scene()
        if not isinstance(scene, QGraphicsScene):
            return None

        item_states: list[_SceneColorItemState] = []
        model_states: list[_SceneModelColorState] = []
        registry = _SceneGraphicsRegistryAuthority.capture(self.canvas, scene)
        authority = _SceneColorPeerAuthority(self, (), (), registry)
        try:
            for item in tuple(scene.items()):
                if isinstance(item, QGraphicsTextItem):
                    runtime = self._note_runtime_rollback(item)
                elif isinstance(item, QAbstractGraphicsShapeItem):
                    brush = QBrush(item.brush())
                    pen = QPen(item.pen())

                    def restore_shape_color(
                        *,
                        target: QAbstractGraphicsShapeItem = item,
                        captured_brush: QBrush = brush,
                        captured_pen: QPen = pen,
                    ) -> None:
                        target.setPen(QPen(captured_pen))
                        target.setBrush(QBrush(captured_brush))

                    def verify_shape_color(
                        *,
                        target: QAbstractGraphicsShapeItem = item,
                        captured_brush: QBrush = brush,
                        captured_pen: QPen = pen,
                    ) -> None:
                        if (
                            target.brush() != captured_brush
                            or target.pen() != captured_pen
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
                    registry,
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
                    registry,
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
                    registry,
                )
            authority.verify_peers(frozenset())
        except Exception as original_error:
            authority.restore(original_error)
            raise
        return authority

    def _resolve_intended_scene_color_targets(
        self,
        items: Iterable[object],
        *,
        expand_ring_structures: bool,
    ) -> tuple[
        frozenset[int],
        tuple[tuple[object, tuple[object, ...]], ...],
    ]:
        allowed: set[int] = set()
        ring_targets: list[tuple[object, tuple[object, ...]]] = []
        for item in items:
            allowed.add(id(item))
            if not isinstance(item, QGraphicsItem) or sip.isdeleted(item):
                continue
            kind = item.data(0)
            object_id = item.data(1)
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
                targets = next(
                    (
                        captured_targets
                        for captured_item, captured_targets in ring_targets
                        if captured_item is item
                    ),
                    None,
                )
                if targets is None:
                    targets = self._resolve_ring_structure_targets(item)
                    ring_targets.append((item, targets))
                allowed.update(id(candidate) for candidate in targets)
        return frozenset(allowed), tuple(ring_targets)

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
        authority: _SceneColorPeerAuthority | None = None
        try:
            authority = self._capture_scene_color_peer_authority()
        except Exception as original_error:
            if authority is not None:
                authority.restore(original_error)
            raise
        if authority is None:
            yield
            return
        try:
            allowed, ring_targets = self._resolve_intended_scene_color_targets(
                items,
                expand_ring_structures=expand_ring_structures,
            )
            # Target discovery is still pre-mutation. Ring graph ports are
            # live extension boundaries and must not redefine the before-state
            # of an atom/bond that will subsequently become an allowed target.
            authority.verify_peers(frozenset())
        except Exception as original_error:
            authority.restore(original_error)
            raise
        transactions.append(
            _SceneColorPeerTransaction(
                authority=authority,
                allowed_graphics_ids=allowed,
                ring_targets=ring_targets,
            )
        )
        try:
            yield
            authority.verify_peers(allowed)
        except Exception as original_error:
            authority.restore(original_error)
            raise
        finally:
            transactions.pop()

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
        rollback = self._batch_runtime_rollback(
            items,
            expand_ring_structures=True,
        )

        def apply_all() -> None:
            for item in items:
                self.apply_color_to_item(item, color)

        self._run_history_transaction(
            apply_all,
            rollback=rollback,
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
                self._push_history_command(
                    UpdateSceneItemCommand(item, before_state, after_state),
                    rollback=(
                        runtime_rollback
                        if runtime_rollback is not None
                        else lambda: rollback.undo(self.canvas)
                    ),
                )
        except Exception as original_error:
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
        rollback = self._batch_runtime_rollback(
            items,
            expand_ring_structures=False,
        )

        def apply_all() -> None:
            for item in items:
                self.apply_ring_fill_color(item, color, alpha)

        self._run_history_transaction(
            apply_all,
            rollback=rollback,
        )

    def _run_history_transaction(
        self,
        mutation: Callable[[], None],
        *,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        real_history = self.history
        collected: list[HistoryCommand] = []
        self.history = _CollectingHistory(collected.append)
        try:
            mutation()
        except Exception as error:
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
            )
            raise
        finally:
            self.history = real_history

        if not collected or real_history is None:
            return
        command = (
            collected[0]
            if len(collected) == 1
            else CompositeCommand(commands=collected)
        )
        try:
            real_history.push(command)
        except Exception as error:
            runtime_rollback = (
                rollback if rollback is not None else lambda: command.undo(self.canvas)
            )
            _run_color_rollback_step(
                error,
                "restoring runtime after color history publication",
                runtime_rollback,
            )
            self._mark_color_rollback_complete(error)
            raise

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
    ) -> None:
        self._push_history_commands(
            [command],
            rollback=rollback,
        )

    def _push_history_commands(
        self,
        commands: Iterable[HistoryCommand],
        *,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        if self.history is None:
            return
        commands = tuple(commands)
        if not commands:
            return
        command = (
            commands[0]
            if len(commands) == 1
            else CompositeCommand(commands=list(commands))
        )
        try:
            if len(commands) == 1:
                self.history.push(command)
            else:
                self.history.push_many(commands)
        except Exception as error:
            if rollback is not None:
                _run_color_rollback_step(
                    error,
                    "restoring runtime after color command publication",
                    rollback,
                )
            self._mark_color_rollback_complete(error)
            raise

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
            self._push_history_commands(
                commands,
                rollback=lambda: original_runtime.apply(item),
            )
        except Exception as original_error:
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
                self._push_history_command(
                    UpdateBondColorCommand(
                        bond_id=bond_id,
                        before_color=before_color,
                        after_color=after_color,
                    ),
                    rollback=rollback,
                )
        except Exception as error:
            if self._color_rollback_is_complete(error):
                raise
            try:
                rollback()
            except Exception as rollback_error:
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
            except Exception as original_error:
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
                self._push_history_command(
                    UpdateAtomColorCommand(
                        atom_id=atom_id,
                        before_color=before_color,
                        after_color=after_color,
                    ),
                    rollback=rollback,
                )
        except Exception as error:
            if self._color_rollback_is_complete(error):
                raise
            try:
                rollback()
            except Exception as rollback_error:
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

    def _ring_structure_targets(self, item) -> tuple[object, ...]:
        if self._scene_color_peer_transactions:
            transaction = self._scene_color_peer_transactions[-1]
            targets = transaction.targets_for_ring(item)
            if targets is None:
                raise RuntimeError("ring color targets were not frozen before mutation")
            return targets
        return self._resolve_ring_structure_targets(item)

    def _resolve_ring_structure_targets(self, item) -> tuple[object, ...]:
        ring_atom_ids = _graphics_item_data_for_capture(item, 2)
        if ring_atom_ids is _DELETED_GRAPHICS_ITEM:
            return ()
        if not isinstance(ring_atom_ids, list):
            return ()
        atom_ids = {
            atom_id
            for atom_id in ring_atom_ids
            if isinstance(atom_id, int)
            and atom_for_id(self.canvas, atom_id) is not None
        }
        if not atom_ids:
            return ()
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
        return tuple(targets)

    def _graphics_runtime_rollback(self, item) -> Callable[[], None]:
        if _graphics_item_is_deleted(item):
            return lambda: None
        text_color = (
            QColor(item.defaultTextColor())
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
                operations.append(lambda: item.setDefaultTextColor(QColor(text_color)))
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
                and item.defaultTextColor() != text_color
            ):
                raise RuntimeError("text color did not match its savepoint")
            if pen is not None:
                actual_pen = _captured_graphics_pen(item)
                if actual_pen != pen:
                    raise RuntimeError("graphics pen did not match its savepoint")
            if brush is not None:
                actual_brush = _captured_graphics_brush(item)
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
        except Exception as original_error:
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
