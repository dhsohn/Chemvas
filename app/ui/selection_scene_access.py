from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import MemberDescriptorType
from typing import Any, Protocol, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from ui.canvas_scene_items_state import selected_notes_for
from ui.scene_signal_blocking import blocked_scene_signals

_MISSING_SCENE_ATTRIBUTE = object()


class _SelectedNotesState(Protocol):
    selected_notes: list


def _optional_live_attribute(
    target: object | None,
    name: str,
    *,
    default: object = None,
) -> object:
    if target is None:
        return default
    if (
        inspect.getattr_static(target, name, _MISSING_SCENE_ATTRIBUTE)
        is _MISSING_SCENE_ATTRIBUTE
    ):
        return default
    return getattr(target, name)


def _required_live_method(target: object, name: str) -> Callable:
    method = _optional_live_attribute(
        target,
        name,
        default=_MISSING_SCENE_ATTRIBUTE,
    )
    if method is _MISSING_SCENE_ATTRIBUTE:
        raise AttributeError(f"Selection item requires {name}")
    if not callable(method):
        raise TypeError(f"Selection port {name!r} is not callable")
    return method


def _add_selection_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                f"Selection recovery also failed while {phase}: "
                f"{type(secondary_error).__name__}: {secondary_error}"
            )
    except BaseException:
        return


@dataclass(slots=True)
class _RawSelectionContainer:
    target: object
    kind: str
    contents: tuple[object, ...]

    def restore(self) -> None:
        if self.kind == "dict":
            dictionary = cast(dict, self.target)
            dict.clear(dictionary)
            dict.update(dictionary, cast(tuple, self.contents))
        elif self.kind == "list":
            values = cast(list, self.target)
            list.clear(values)
            list.extend(values, self.contents)
        else:
            members = cast(set, self.target)
            set.clear(members)
            set.update(members, self.contents)

    def verify(self) -> None:
        if self.kind == "dict":
            actual = tuple(cast(dict, self.target).items())
            expected = cast(tuple[tuple[object, object], ...], self.contents)
            exact = len(actual) == len(expected) and all(
                actual_key is expected_key and actual_value is expected_value
                for (actual_key, actual_value), (
                    expected_key,
                    expected_value,
                ) in zip(actual, expected, strict=True)
            )
        elif self.kind == "list":
            actual = tuple(cast(list, self.target))
            exact = len(actual) == len(self.contents) and all(
                value is expected
                for value, expected in zip(actual, self.contents, strict=True)
            )
        else:
            exact = {id(value) for value in cast(set, self.target)} == {
                id(value) for value in self.contents
            }
        if not exact:
            raise RuntimeError("selection capture changed a raw container")


@dataclass(slots=True)
class _RawSelectionObject:
    target: object
    namespace: dict[str, object] | None
    namespace_items: tuple[tuple[str, object], ...]
    slots: tuple[tuple[MemberDescriptorType, bool, object], ...]

    @classmethod
    def capture(
        cls,
        target: object,
        capture_container: Callable[[object], None],
    ) -> _RawSelectionObject:
        try:
            namespace_value = object.__getattribute__(target, "__dict__")
        except (AttributeError, TypeError):
            namespace = None
            namespace_items: tuple[tuple[str, object], ...] = ()
        else:
            namespace = namespace_value if isinstance(namespace_value, dict) else None
            namespace_items = (
                tuple(
                    (key, dict.__getitem__(namespace, key))
                    for key in tuple(dict.__iter__(namespace))
                )
                if namespace is not None
                else ()
            )
            for _key, value in namespace_items:
                capture_container(value)
        slots: list[tuple[MemberDescriptorType, bool, object]] = []
        seen: set[int] = set()
        if not isinstance(target, QObject):
            for owner in type(target).__mro__:
                for descriptor in owner.__dict__.values():
                    if (
                        not isinstance(descriptor, MemberDescriptorType)
                        or id(descriptor) in seen
                    ):
                        continue
                    seen.add(id(descriptor))
                    try:
                        value = descriptor.__get__(target, type(target))
                    except AttributeError:
                        slots.append((descriptor, False, _MISSING_SCENE_ATTRIBUTE))
                        continue
                    slots.append((descriptor, True, value))
                    capture_container(value)
        return cls(target, namespace, namespace_items, tuple(slots))

    def restore(self) -> None:
        if self.namespace is not None:
            dict.clear(self.namespace)
            dict.update(self.namespace, self.namespace_items)
        for descriptor, present, value in self.slots:
            if present:
                descriptor.__set__(self.target, value)
            else:
                try:
                    descriptor.__delete__(self.target)
                except AttributeError:
                    pass

    def verify(self) -> None:
        if self.namespace is not None:
            actual = tuple(self.namespace.items())
            if len(actual) != len(self.namespace_items) or any(
                actual_key != expected_key or actual_value is not expected_value
                for (actual_key, actual_value), (
                    expected_key,
                    expected_value,
                ) in zip(actual, self.namespace_items, strict=True)
            ):
                raise RuntimeError("selection capture changed a raw object namespace")
        for descriptor, present, expected in self.slots:
            try:
                actual = descriptor.__get__(self.target, type(self.target))
            except AttributeError:
                if present:
                    raise RuntimeError(
                        "selection capture removed a raw object slot"
                    ) from None
                continue
            if not present or actual is not expected:
                raise RuntimeError("selection capture changed a raw object slot")


@dataclass(slots=True)
class _SelectionCaptureAuthority:
    scene: object | None
    raw_objects: tuple[_RawSelectionObject, ...]
    raw_containers: tuple[_RawSelectionContainer, ...]
    qt_selection: tuple[tuple[QGraphicsItem, bool], ...]
    qt_signals_blocked: bool | None

    @classmethod
    def capture(
        cls,
        scene: object | None,
        targets: tuple[object, ...],
    ) -> _SelectionCaptureAuthority:
        containers: list[_RawSelectionContainer] = []
        container_ids: set[int] = set()

        def capture_container(value: object) -> None:
            if type(value) is dict:
                if id(value) in container_ids:
                    return
                container_ids.add(id(value))
                contents = tuple(cast(dict, value).items())
                containers.append(_RawSelectionContainer(value, "dict", contents))
                for key, child in contents:
                    capture_container(key)
                    capture_container(child)
            elif type(value) in {list, set}:
                if id(value) in container_ids:
                    return
                container_ids.add(id(value))
                member_contents: tuple[object, ...] = tuple(cast(Any, value))
                containers.append(
                    _RawSelectionContainer(
                        value,
                        "list" if type(value) is list else "set",
                        member_contents,
                    )
                )
                for child in member_contents:
                    capture_container(child)
            elif type(value) is tuple:
                for child in cast(tuple, value):
                    capture_container(child)

        raw_targets: list[object] = [*targets]
        if scene is not None:
            raw_targets.insert(0, scene)
            try:
                namespace = object.__getattribute__(scene, "__dict__")
            except (AttributeError, TypeError):
                namespace = None
            if isinstance(namespace, dict):
                for value in tuple(namespace.values()):
                    if type(value) not in {list, tuple, set, dict}:
                        continue
                    pending = list(value.values()) if type(value) is dict else list(value)
                    for candidate in pending:
                        if not isinstance(candidate, (str, bytes, int, float, bool)):
                            raw_targets.append(candidate)
        raw_objects: list[_RawSelectionObject] = []
        seen_objects: set[int] = set()
        for target in raw_targets:
            if id(target) in seen_objects or inspect.isroutine(target):
                continue
            seen_objects.add(id(target))
            raw_objects.append(
                _RawSelectionObject.capture(target, capture_container)
            )

        qt_items: list[QGraphicsItem] = []
        if isinstance(scene, QGraphicsScene):
            qt_items.extend(QGraphicsScene.items(scene))
        qt_items.extend(
            target for target in targets if isinstance(target, QGraphicsItem)
        )
        qt_selection: list[tuple[QGraphicsItem, bool]] = []
        seen_qt: set[int] = set()
        for item in qt_items:
            if id(item) in seen_qt:
                continue
            seen_qt.add(id(item))
            qt_selection.append((item, bool(QGraphicsItem.isSelected(item))))
        return cls(
            scene=scene,
            raw_objects=tuple(raw_objects),
            raw_containers=tuple(containers),
            qt_selection=tuple(qt_selection),
            qt_signals_blocked=(
                bool(QObject.signalsBlocked(scene))
                if isinstance(scene, QObject)
                else None
            ),
        )

    def restore(self, original_error: BaseException) -> None:
        recorded: list[BaseException] = []
        for _attempt in range(2):
            errors: list[BaseException] = []
            try:
                if isinstance(self.scene, QObject):
                    QObject.blockSignals(self.scene, True)
                for raw_object in self.raw_objects:
                    raw_object.restore()
                for raw_container in self.raw_containers:
                    raw_container.restore()
                for selected in (True, False):
                    for item, expected in self.qt_selection:
                        if expected is selected:
                            QGraphicsItem.setSelected(item, expected)
                for raw_object in self.raw_objects:
                    raw_object.restore()
                for raw_container in self.raw_containers:
                    raw_container.restore()
            except BaseException as error:
                errors.append(error)
            finally:
                if (
                    isinstance(self.scene, QObject)
                    and self.qt_signals_blocked is not None
                ):
                    try:
                        QObject.blockSignals(
                            self.scene,
                            self.qt_signals_blocked,
                        )
                    except BaseException as error:
                        errors.append(error)
            for raw_object in self.raw_objects:
                try:
                    raw_object.verify()
                except BaseException as error:
                    errors.append(error)
            for raw_container in self.raw_containers:
                try:
                    raw_container.verify()
                except BaseException as error:
                    errors.append(error)
            for item, expected in self.qt_selection:
                try:
                    if bool(QGraphicsItem.isSelected(item)) is not expected:
                        raise RuntimeError(
                            "selection capture did not restore Qt selection"
                        )
                except BaseException as error:
                    errors.append(error)
            if (
                isinstance(self.scene, QObject)
                and self.qt_signals_blocked is not None
                and bool(QObject.signalsBlocked(self.scene))
                is not self.qt_signals_blocked
            ):
                errors.append(
                    RuntimeError("selection capture changed Qt signal state")
                )
            if not errors:
                return
            recorded.extend(errors)
        for recorded_error in recorded:
            _add_selection_recovery_note(
                original_error,
                recorded_error,
                phase="unwinding failed selection capture",
            )


@dataclass(slots=True)
class _ItemSelectionSnapshot:
    item: object
    selected: bool
    is_selected: Callable[[], object]
    set_selected: Callable[[bool], object]

    @classmethod
    def capture(cls, item: object) -> _ItemSelectionSnapshot:
        is_selected = _required_live_method(item, "isSelected")
        set_selected = _required_live_method(item, "setSelected")
        return cls(
            item=item,
            selected=bool(is_selected()),
            is_selected=is_selected,
            set_selected=set_selected,
        )

    def restore(self, original_error: BaseException) -> None:
        for attempt in range(2):
            try:
                self.set_selected(self.selected)
            except BaseException as restore_error:
                _add_selection_recovery_note(
                    original_error,
                    restore_error,
                    phase=(
                        "restoring an item's selection"
                        if attempt == 0
                        else "retrying an item's selection restore"
                    ),
                )
            try:
                if bool(self.is_selected()) == self.selected:
                    return
            except BaseException as verify_error:
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying an item's restored selection",
                )
        _add_selection_recovery_note(
            original_error,
            RuntimeError("item selection did not return to its captured state"),
            phase="verifying selection recovery after retry",
        )


def _optional_canvas_state_object(
    canvas: object,
    runtime_state: object | None,
    name: str,
) -> object | None:
    if runtime_state is not None:
        state = _optional_live_attribute(runtime_state, name)
        if state is not None:
            return state
    return _optional_live_attribute(canvas, name)


@dataclass(slots=True)
class _SelectionInfoRecoverySnapshot:
    state: object | None
    values: dict[str, object]
    callback: Callable[[str, str], object] | None
    update_outline: Callable[[], object] | None
    scene_items_state: _SelectedNotesState | None
    selected_notes: list | None
    selected_note_contents: tuple[object, ...]
    note_items: tuple[object, ...]
    update_note_selection_box: Callable[[object], object] | None
    published: bool = False

    @classmethod
    def capture(cls, canvas: object) -> _SelectionInfoRecoverySnapshot:
        services = _optional_live_attribute(canvas, "services")
        controller = _optional_live_attribute(services, "selection_controller")
        runtime_state = _optional_live_attribute(canvas, "runtime_state")
        update_outline_value = _optional_live_attribute(
            controller,
            "update_selection_outline",
        )
        update_outline = (
            update_outline_value if callable(update_outline_value) else None
        )
        update_note_box_value = _optional_live_attribute(
            controller,
            "update_note_selection_box",
        )
        update_note_selection_box = (
            update_note_box_value if callable(update_note_box_value) else None
        )

        scene_items_state_value = _optional_canvas_state_object(
            canvas,
            runtime_state,
            "scene_items_state",
        )
        selected_notes_value = _optional_live_attribute(
            scene_items_state_value,
            "selected_notes",
        )
        selected_notes = (
            selected_notes_value if isinstance(selected_notes_value, list) else None
        )
        scene_items_state = (
            cast(_SelectedNotesState, scene_items_state_value)
            if selected_notes is not None
            else None
        )
        note_items_value = _optional_live_attribute(
            scene_items_state_value,
            "note_items",
        )
        note_items = (
            tuple(note_items_value) if isinstance(note_items_value, list) else ()
        )

        state = _optional_canvas_state_object(
            canvas,
            runtime_state,
            "selection_info_state",
        )
        values: dict[str, object] = {}
        callback: Callable[[str, str], object] | None = None
        if state is not None:
            for name in (
                "signature",
                "pending_signature",
                "cache",
                "rdkit_warmup_pending",
                "last_interaction_time",
            ):
                value = _optional_live_attribute(
                    state,
                    name,
                    default=_MISSING_SCENE_ATTRIBUTE,
                )
                if value is not _MISSING_SCENE_ATTRIBUTE:
                    values[name] = value
            callback_value = _optional_live_attribute(
                state,
                "callback",
                default=_MISSING_SCENE_ATTRIBUTE,
            )
            if callback_value is not _MISSING_SCENE_ATTRIBUTE:
                values["callback"] = callback_value
                if callable(callback_value):
                    callback = callback_value
        return cls(
            state=state,
            values=values,
            callback=callback,
            update_outline=update_outline,
            scene_items_state=scene_items_state,
            selected_notes=selected_notes,
            selected_note_contents=tuple(selected_notes or ()),
            note_items=note_items,
            update_note_selection_box=update_note_selection_box,
        )

    def _restore_note_runtime(
        self,
        original_error: BaseException,
        *,
        refresh_boxes: bool,
    ) -> None:
        selected_notes = self.selected_notes
        if selected_notes is not None:
            try:
                selected_notes[:] = self.selected_note_contents
            except BaseException as restore_error:
                _add_selection_recovery_note(
                    original_error,
                    restore_error,
                    phase="restoring selected-note contents",
                )
            if self.scene_items_state is not None:
                try:
                    self.scene_items_state.selected_notes = selected_notes
                except BaseException as restore_error:
                    _add_selection_recovery_note(
                        original_error,
                        restore_error,
                        phase="restoring selected-note list identity",
                    )
        if not refresh_boxes or self.update_note_selection_box is None:
            return
        for note in self.note_items:
            try:
                self.update_note_selection_box(note)
            except BaseException as refresh_error:
                _add_selection_recovery_note(
                    original_error,
                    refresh_error,
                    phase="refreshing restored note-selection UI",
                )

    def _restore_info_state(self, original_error: BaseException) -> None:
        if self.state is None:
            return
        for name, value in self.values.items():
            try:
                setattr(self.state, name, value)
            except BaseException as restore_error:
                _add_selection_recovery_note(
                    original_error,
                    restore_error,
                    phase=f"restoring selection-info field {name}",
                )

    @staticmethod
    def _values_match(actual: object, expected: object, *, identity: bool) -> bool:
        if actual is expected:
            return True
        if identity:
            return False
        try:
            return bool(actual == expected)
        except BaseException:
            return False

    def logical_state_is_exact(self, original_error: BaseException) -> bool:
        exact = True
        selected_notes = self.selected_notes
        if selected_notes is not None:
            if self.scene_items_state is not None:
                try:
                    actual_list = self.scene_items_state.selected_notes
                    if actual_list is not selected_notes:
                        raise RuntimeError(
                            "selected-note list identity did not match its savepoint"
                        )
                except BaseException as verify_error:
                    exact = False
                    _add_selection_recovery_note(
                        original_error,
                        verify_error,
                        phase="verifying selected-note list identity",
                    )
            try:
                if len(selected_notes) != len(self.selected_note_contents) or any(
                    actual is not expected
                    for actual, expected in zip(
                        selected_notes,
                        self.selected_note_contents,
                        strict=False,
                    )
                ):
                    raise RuntimeError(
                        "selected-note contents did not match their savepoint"
                    )
            except BaseException as verify_error:
                exact = False
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying selected-note contents",
                )

        if self.state is not None:
            for name, expected in self.values.items():
                try:
                    actual = getattr(self.state, name)
                    if not self._values_match(
                        actual,
                        expected,
                        identity=name == "callback",
                    ):
                        raise RuntimeError(
                            f"selection-info field {name!r} did not match its savepoint"
                        )
                except BaseException as verify_error:
                    exact = False
                    _add_selection_recovery_note(
                        original_error,
                        verify_error,
                        phase=f"verifying selection-info field {name}",
                    )
        return exact

    def republish_after_partial_signal_failure(
        self,
        original_error: BaseException,
    ) -> None:
        self._restore_note_runtime(original_error, refresh_boxes=False)
        if self.update_outline is not None:
            for attempt in range(2):
                try:
                    self.update_outline()
                except BaseException as refresh_error:
                    _add_selection_recovery_note(
                        original_error,
                        refresh_error,
                        phase=(
                            "refreshing derived selection UI"
                            if attempt == 0
                            else "retrying the derived selection UI refresh"
                        ),
                    )
                    continue
                break

        # A custom outline refresh can itself touch note-selection runtime.
        # Replay the exact list identity/contents after it, then update each
        # registered note box once from that authoritative logical state.
        self._restore_note_runtime(original_error, refresh_boxes=True)

        # Outline refresh computes from the restored item selection, but it can
        # also rewrite cache/pending/warmup/timestamp fields while publishing.
        # Put those runtime authorities back exactly, then publish the captured
        # cache so status/preview consumers observe the same pre-operation view.
        self._restore_info_state(original_error)
        cache = self.values.get("cache")
        if self.published:
            return
        self.published = True
        if self.callback is None or not (
            isinstance(cache, tuple) and len(cache) == 2
        ):
            return
        try:
            self.callback(str(cache[0]), str(cache[1]))
        except BaseException as callback_error:
            _add_selection_recovery_note(
                original_error,
                callback_error,
                phase="republishing the restored selection status",
            )


def _scene_for(canvas, *, strict: bool = False):
    try:
        scene = canvas.scene
    except AttributeError:
        if strict and inspect.getattr_static(
            canvas,
            "scene",
            _MISSING_SCENE_ATTRIBUTE,
        ) is not _MISSING_SCENE_ATTRIBUTE:
            raise
        return None
    if not callable(scene):
        return None
    try:
        scene_obj = scene()
    except RuntimeError:
        if isinstance(canvas, QObject) and sip.isdeleted(canvas):
            return None
        if strict:
            raise
        return None
    if isinstance(scene_obj, QObject) and sip.isdeleted(scene_obj):
        return None
    return scene_obj


@dataclass(slots=True)
class _SelectionMutationSnapshot:
    scene: object | None
    targets: tuple[object, ...]
    item_snapshots: dict[int, _ItemSelectionSnapshot]
    original_scene_selected_ids: frozenset[int] | None
    selected_items: Callable[[], object] | None
    clear_selection: Callable[[], object] | None
    block_signals: Callable[[bool], object] | None
    signals_blocked: Callable[[], object] | None
    previous_signals_blocked: bool | None
    derived_recovery: _SelectionInfoRecoverySnapshot | None

    @classmethod
    def capture(
        cls,
        canvas: object,
        scene: object | None,
        items: Iterable[object],
        *,
        block_signals: bool,
    ) -> _SelectionMutationSnapshot:
        targets = tuple(items)
        item_snapshots: dict[int, _ItemSelectionSnapshot] = {}
        for item in targets:
            if id(item) not in item_snapshots:
                item_snapshots[id(item)] = _ItemSelectionSnapshot.capture(item)

        bound_block_signals: Callable[[bool], object] | None = None
        bound_signals_blocked: Callable[[], object] | None = None
        previous_signals_blocked: bool | None = None
        bound_selected_items: Callable[[], object] | None = None
        bound_clear_selection: Callable[[], object] | None = None
        original_scene_selected_ids: frozenset[int] | None = None
        derived_recovery: _SelectionInfoRecoverySnapshot | None = None

        if scene is not None:
            block_method = _required_live_method(scene, "blockSignals")
            bound_block_signals = block_method
            signals_method = _optional_live_attribute(scene, "signalsBlocked")
            if callable(signals_method):
                bound_signals_blocked = signals_method
                previous_signals_blocked = bool(bound_signals_blocked())

            # With live signals, a selectionChanged callback can expand groups
            # beyond ``targets``. Capture the whole selected frontier so a
            # downstream setter failure can remove callback-added selections.
            if not block_signals:
                selected_method = _required_live_method(scene, "selectedItems")
                clear_method = _required_live_method(scene, "clearSelection")
                original_selected = tuple(selected_method())
                for item in original_selected:
                    if id(item) not in item_snapshots:
                        item_snapshots[id(item)] = _ItemSelectionSnapshot.capture(
                            item
                        )
                original_scene_selected_ids = frozenset(
                    id(item) for item in original_selected
                )
                bound_selected_items = selected_method
                bound_clear_selection = clear_method
                derived_recovery = _SelectionInfoRecoverySnapshot.capture(canvas)

        return cls(
            scene=scene,
            targets=targets,
            item_snapshots=item_snapshots,
            original_scene_selected_ids=original_scene_selected_ids,
            selected_items=bound_selected_items,
            clear_selection=bound_clear_selection,
            block_signals=bound_block_signals,
            signals_blocked=bound_signals_blocked,
            previous_signals_blocked=previous_signals_blocked,
            derived_recovery=derived_recovery,
        )

    def _signals_blocked_capture(self) -> Callable[[], object] | None:
        if self.previous_signals_blocked is None:
            return None
        return self.signals_blocked

    def mutate(self, selected: bool, *, block_signals: bool) -> None:
        def apply() -> None:
            for item in self.targets:
                self.item_snapshots[id(item)].set_selected(selected)

        if self.scene is None or not block_signals:
            apply()
            return
        assert self.block_signals is not None
        with blocked_scene_signals(
            self.scene,
            block_signals=self.block_signals,
            signals_blocked=self._signals_blocked_capture(),
        ):
            apply()

    def _target_selection_is_exact(
        self,
        original_error: BaseException,
    ) -> bool:
        exact = True
        for snapshot in self.item_snapshots.values():
            try:
                exact = exact and (
                    bool(snapshot.is_selected()) == snapshot.selected
                )
            except BaseException as verify_error:
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying restored target selections",
                )
                exact = False
        return exact

    def _scene_selection_is_exact(
        self,
        original_error: BaseException,
    ) -> bool:
        expected_ids = self.original_scene_selected_ids
        if expected_ids is None or self.selected_items is None:
            return self._target_selection_is_exact(original_error)
        try:
            actual_items = cast(Iterable[object], self.selected_items())
            actual_ids = frozenset(id(item) for item in actual_items)
        except BaseException as verify_error:
            _add_selection_recovery_note(
                original_error,
                verify_error,
                phase="verifying the restored scene selection",
            )
            return False
        return actual_ids == expected_ids

    def _restore_once(self, original_error: BaseException) -> None:
        if self.original_scene_selected_ids is not None:
            assert self.clear_selection is not None
            try:
                self.clear_selection()
            except BaseException as clear_error:
                _add_selection_recovery_note(
                    original_error,
                    clear_error,
                    phase="clearing partial scene selection",
                )
        # Re-establish captured-true items first and captured-false peers last.
        # A custom true setter can synchronously select another item; making
        # false the final writer prevents that callback from repolluting peers.
        for selected_state in (True, False):
            for snapshot in self.item_snapshots.values():
                if snapshot.selected is selected_state:
                    snapshot.restore(original_error)

    def _restore_selection_under_blocked_signals(
        self,
        original_error: BaseException,
    ) -> None:
        if self.scene is not None and self.block_signals is not None:
            with blocked_scene_signals(
                self.scene,
                block_signals=self.block_signals,
                signals_blocked=self._signals_blocked_capture(),
            ):
                self._restore_once(original_error)
            return
        self._restore_once(original_error)

    def _restore_signal_state(self, original_error: BaseException) -> None:
        if (
            self.previous_signals_blocked is None
            or self.signals_blocked is None
            or self.block_signals is None
        ):
            return
        for attempt in range(2):
            try:
                if (
                    bool(self.signals_blocked())
                    == self.previous_signals_blocked
                ):
                    return
            except BaseException as verify_error:
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying restored scene signal state",
                )
            try:
                self.block_signals(self.previous_signals_blocked)
            except BaseException as restore_error:
                _add_selection_recovery_note(
                    original_error,
                    restore_error,
                    phase=(
                        "restoring the scene signal state"
                        if attempt == 0
                        else "retrying the scene signal-state restore"
                    ),
                )
        try:
            restored = (
                bool(self.signals_blocked())
                == self.previous_signals_blocked
            )
        except BaseException as verify_error:
            _add_selection_recovery_note(
                original_error,
                verify_error,
                phase="verifying retried scene signal-state recovery",
            )
            restored = False
        if not restored:
            _add_selection_recovery_note(
                original_error,
                RuntimeError(
                    "scene signal state did not return to its captured value"
                ),
                phase="finishing selection recovery",
            )

    def _signal_state_is_exact(self, original_error: BaseException) -> bool:
        if self.previous_signals_blocked is None or self.signals_blocked is None:
            return True
        try:
            return bool(self.signals_blocked()) == self.previous_signals_blocked
        except BaseException as verify_error:
            _add_selection_recovery_note(
                original_error,
                verify_error,
                phase="verifying final scene signal state",
            )
            return False

    def _reassert_after_status_publication(
        self,
        original_error: BaseException,
    ) -> None:
        derived = self.derived_recovery
        if derived is None:
            return

        for attempt in range(2):
            try:
                if attempt == 0:
                    self._restore_selection_under_blocked_signals(original_error)
                    derived._restore_note_runtime(
                        original_error,
                        refresh_boxes=False,
                    )
                    derived._restore_info_state(original_error)
                else:
                    # Reverse the independent authorities on retry so a
                    # cross-mutating setter cannot always run last.
                    derived._restore_info_state(original_error)
                    derived._restore_note_runtime(
                        original_error,
                        refresh_boxes=False,
                    )
                    self._restore_selection_under_blocked_signals(original_error)
            except BaseException as restore_error:
                _add_selection_recovery_note(
                    original_error,
                    restore_error,
                    phase=(
                        "silently reasserting selection after status publication"
                        if attempt == 0
                        else "retrying silent selection reassertion"
                    ),
                )
            self._restore_signal_state(original_error)
            selection_exact = self._scene_selection_is_exact(original_error)
            logical_exact = derived.logical_state_is_exact(original_error)
            signals_exact = self._signal_state_is_exact(original_error)
            if selection_exact and logical_exact and signals_exact:
                return

        _add_selection_recovery_note(
            original_error,
            RuntimeError(
                "selection/status state remained non-authoritative after publication"
            ),
            phase="finishing selection status recovery",
        )

    def _restore_derived_state_silently(
        self,
        original_error: BaseException,
    ) -> None:
        """Restore captured logical selection state without publishing again."""

        derived = self.derived_recovery
        if derived is None:
            return
        for attempt in range(2):
            if attempt == 0:
                derived._restore_note_runtime(
                    original_error,
                    refresh_boxes=False,
                )
                derived._restore_info_state(original_error)
            else:
                # Reverse independent writers on retry so a cross-mutating
                # descriptor cannot always be the final authority.
                derived._restore_info_state(original_error)
                derived._restore_note_runtime(
                    original_error,
                    refresh_boxes=False,
                )
            if derived.logical_state_is_exact(original_error):
                return
        _add_selection_recovery_note(
            original_error,
            RuntimeError(
                "derived selection state remained non-authoritative after retry"
            ),
            phase="finishing silent derived selection recovery",
        )

    def restore(self, original_error: BaseException) -> None:
        # A fail-before setter may leave both selection and signal state exact.
        # Avoid redundant item/signal traffic, but still restore and verify the
        # independently captured note/status authorities: a custom setter can
        # poison those before raising without changing item selection at all.
        if self._scene_selection_is_exact(original_error):
            self._restore_signal_state(original_error)
            self._restore_derived_state_silently(original_error)
            return
        for attempt in range(2):
            try:
                self._restore_selection_under_blocked_signals(original_error)
            except BaseException as rollback_error:
                _add_selection_recovery_note(
                    original_error,
                    rollback_error,
                    phase=(
                        "restoring selection under blocked signals"
                        if attempt == 0
                        else "retrying selection under blocked signals"
                    ),
                )
            if self._scene_selection_is_exact(original_error):
                break
        else:
            _add_selection_recovery_note(
                original_error,
                RuntimeError("scene selection remained partial after retry"),
                phase="finishing exact selection recovery",
            )

        self._restore_signal_state(original_error)
        if self.derived_recovery is not None:
            self.derived_recovery.republish_after_partial_signal_failure(
                original_error
            )
            self._reassert_after_status_publication(original_error)


def scene_selected_items_for(canvas) -> list:
    scene_obj = _scene_for(canvas)
    if scene_obj is None:
        return []
    return list(scene_obj.selectedItems())


def selected_scene_notes_for(canvas):
    scene_obj = _scene_for(canvas)
    if scene_obj is None:
        return []
    notes = []
    for note in selected_notes_for(canvas):
        try:
            attached_scene = note.scene()
        except RuntimeError:
            continue
        if attached_scene is scene_obj:
            notes.append(note)
    return notes


def clear_scene_selection_for(canvas, *, block_signals: bool = False) -> bool:
    scene_obj = _scene_for(canvas, strict=True)
    if scene_obj is None:
        return False
    if block_signals:
        with blocked_scene_signals(scene_obj):
            scene_obj.clearSelection()
        return True
    scene_obj.clearSelection()
    return True


def set_scene_items_selected_for(
    canvas,
    items,
    selected: bool,
    *,
    block_signals: bool = True,
) -> None:
    scene_obj = _scene_for(canvas, strict=True)
    targets = tuple(items)
    capture_authority = _SelectionCaptureAuthority.capture(scene_obj, targets)
    try:
        snapshot = _SelectionMutationSnapshot.capture(
            canvas,
            scene_obj,
            targets,
            block_signals=block_signals,
        )
    except BaseException as original_error:
        capture_authority.restore(original_error)
        raise
    try:
        snapshot.mutate(selected, block_signals=block_signals)
    except BaseException as original_error:
        snapshot.restore(original_error)
        raise


__all__ = [
    "clear_scene_selection_for",
    "scene_selected_items_for",
    "selected_scene_notes_for",
    "set_scene_items_selected_for",
]
