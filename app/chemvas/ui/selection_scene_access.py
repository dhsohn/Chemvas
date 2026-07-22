from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from types import MemberDescriptorType
from typing import Any, Protocol, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from chemvas.ui.canvas_scene_items_state import selected_notes_for
from chemvas.ui.scene_signal_blocking import blocked_scene_signals

_MISSING_SCENE_ATTRIBUTE = object()

_RAW_SCENE_SELECTION_CONTAINER_FIELDS = frozenset(
    {
        "_selected_items",
        "selected_items",
    }
)
_RAW_SCENE_MEMBERSHIP_FIELDS = frozenset(
    {
        "items",
        "_items",
        "scene_items",
        "_scene_items",
        "members",
        "_members",
    }
)
_RAW_SCENE_DISTINCT_MEMBERSHIP_FIELDS = (
    _RAW_SCENE_MEMBERSHIP_FIELDS - _RAW_SCENE_SELECTION_CONTAINER_FIELDS
)
_QT_STACKING_FLAG_MASK = (
    QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent
    | QGraphicsItem.GraphicsItemFlag.ItemNegativeZStacksBehindParent
)


def _nested_builtin_container_members(value: object) -> tuple[object, ...] | None:
    """Flatten exact built-in containers without invoking overridable ports."""

    if type(value) not in {dict, list, tuple, set}:
        return None
    pending = [value]
    seen_containers: set[int] = set()
    seen_members: set[int] = set()
    members: list[object] = []
    while pending:
        candidate = pending.pop()
        if type(candidate) is dict:
            if id(candidate) in seen_containers:
                continue
            seen_containers.add(id(candidate))
            children: list[object] = []
            for key, child in tuple(dict.items(cast(dict, candidate))):
                children.extend((key, child))
            pending.extend(reversed(children))
            continue
        if type(candidate) in {list, tuple, set}:
            if id(candidate) in seen_containers:
                continue
            seen_containers.add(id(candidate))
            container_children = tuple(cast(Any, candidate))
            pending.extend(reversed(container_children))
            continue
        if id(candidate) in seen_members:
            continue
        seen_members.add(id(candidate))
        members.append(candidate)
    return tuple(members)


def _nested_mutable_builtin_container_ids(value: object) -> set[int]:
    """Collect every mutable built-in container in a captured container graph."""

    if type(value) not in {dict, list, tuple, set}:
        return set()
    pending = [value]
    seen_containers: set[int] = set()
    mutable_container_ids: set[int] = set()
    while pending:
        candidate = pending.pop()
        if type(candidate) not in {dict, list, tuple, set}:
            continue
        candidate_id = id(candidate)
        if candidate_id in seen_containers:
            continue
        seen_containers.add(candidate_id)
        if type(candidate) is dict:
            mutable_container_ids.add(candidate_id)
            for key, child in tuple(dict.items(cast(dict, candidate))):
                pending.extend((key, child))
            continue
        if type(candidate) in {list, set}:
            mutable_container_ids.add(candidate_id)
        pending.extend(tuple(cast(Any, candidate)))
    return mutable_container_ids


def _is_raw_signal_state_field(name: str) -> bool:
    normalized = name.strip("_").lower()
    return normalized == "blocked" or (
        "signal" in normalized and ("block" in normalized or "flag" in normalized)
    )


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

    def is_exact(self) -> bool:
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
        return exact

    def verify(self) -> None:
        if not self.is_exact():
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

    def raw_fields_are_exact(self, names: frozenset[str]) -> bool:
        """Compare selected raw fields without invoking live descriptors."""

        expected_namespace = {
            key: value for key, value in self.namespace_items if key in names
        }
        if self.namespace is None:
            if expected_namespace:
                return False
        else:
            actual_namespace = {
                key: value for key, value in self.namespace.items() if key in names
            }
            if actual_namespace.keys() != expected_namespace.keys() or any(
                actual_namespace[key] is not expected
                for key, expected in expected_namespace.items()
            ):
                return False

        expected_slots = {
            descriptor.__name__: (present, value)
            for descriptor, present, value in self.slots
            if descriptor.__name__ in names
        }
        for owner in type(self.target).__mro__:
            for name, descriptor in owner.__dict__.items():
                if name not in names or not isinstance(
                    descriptor, MemberDescriptorType
                ):
                    continue
                expected = expected_slots.get(name)
                if expected is None:
                    return False
                present, expected_value = expected
                try:
                    actual = descriptor.__get__(self.target, type(self.target))
                except AttributeError:
                    if present:
                        return False
                else:
                    if not present or actual is not expected_value:
                        return False
        return True

    def raw_container_ids_for(self, names: frozenset[str]) -> set[int]:
        container_ids: set[int] = set()
        for key, value in self.namespace_items:
            if key in names:
                container_ids.update(_nested_mutable_builtin_container_ids(value))
        for descriptor, present, value in self.slots:
            if present and descriptor.__name__ in names:
                container_ids.update(_nested_mutable_builtin_container_ids(value))
        return container_ids

    def has_raw_container_field(self, names: frozenset[str]) -> bool:
        return any(
            key in names and type(value) in {dict, list, set, tuple}
            for key, value in self.namespace_items
        ) or any(
            present
            and descriptor.__name__ in names
            and type(value) in {dict, list, set, tuple}
            for descriptor, present, value in self.slots
        )

    def raw_container_fields_are_empty(self, names: frozenset[str]) -> bool:
        """Check recognized live container fields without calling descriptors."""

        expected_namespace_names = {
            key
            for key, value in self.namespace_items
            if key in names and type(value) in {dict, list, set, tuple}
        }
        if self.namespace is None:
            if expected_namespace_names:
                return False
        else:
            actual_namespace_names = {key for key in self.namespace if key in names}
            if not expected_namespace_names.issubset(actual_namespace_names):
                return False
            for name in actual_namespace_names:
                value = dict.__getitem__(self.namespace, name)
                if (
                    type(value) not in {dict, list, set, tuple}
                    or len(cast(Any, value)) != 0
                ):
                    return False

        expected_slots = {
            descriptor.__name__: present
            for descriptor, present, value in self.slots
            if (
                descriptor.__name__ in names and type(value) in {dict, list, set, tuple}
            )
        }
        seen_slots: set[str] = set()
        for owner in type(self.target).__mro__:
            for name, descriptor in owner.__dict__.items():
                if (
                    name not in names
                    or name in seen_slots
                    or not isinstance(descriptor, MemberDescriptorType)
                ):
                    continue
                seen_slots.add(name)
                expected_present = expected_slots.get(name)
                try:
                    value = descriptor.__get__(self.target, type(self.target))
                except AttributeError:
                    if expected_present:
                        return False
                else:
                    if type(value) not in {dict, list, set, tuple} or len(value) != 0:
                        return False
        return True

    def callback_free_signal_state_reader(
        self,
        expected: bool,
    ) -> Callable[[], object] | None:
        """Return one unambiguous raw reader matching the live signal state."""

        readers: list[Callable[[], object]] = []
        if self.namespace is not None:
            for name, captured in self.namespace_items:
                if not _is_raw_signal_state_field(name) or type(captured) is not bool:
                    continue
                if captured is not expected:
                    continue

                def read_namespace_signal_state(
                    *,
                    namespace: dict[str, object] = self.namespace,
                    field: str = name,
                ) -> object:
                    return dict.__getitem__(namespace, field)

                readers.append(read_namespace_signal_state)

        for descriptor, present, captured in self.slots:
            if (
                not present
                or not _is_raw_signal_state_field(descriptor.__name__)
                or type(captured) is not bool
                or captured is not expected
            ):
                continue

            def read_slot_signal_state(
                *,
                target: object = self.target,
                member: MemberDescriptorType = descriptor,
            ) -> object:
                return member.__get__(target, type(target))

            readers.append(read_slot_signal_state)

        stable_readers: list[Callable[[], object]] = []
        for reader in readers:
            try:
                if reader() is expected:
                    stable_readers.append(reader)
            except BaseException:
                continue
        return stable_readers[0] if len(stable_readers) == 1 else None


def _callback_free_signal_state_getter_for(
    scene: object | None,
    raw_objects: Iterable[_RawSelectionObject],
    captured: bool | None,
) -> Callable[[], object] | None:
    if captured is None:
        return None
    if isinstance(scene, QObject):
        return partial(QObject.signalsBlocked, scene)
    scene_raw = next(
        (raw_object for raw_object in raw_objects if raw_object.target is scene),
        None,
    )
    if scene_raw is None:
        return None
    return scene_raw.callback_free_signal_state_reader(captured)


@dataclass(frozen=True, slots=True)
class _QtSceneItemTopology:
    item: QGraphicsItem
    parent: QGraphicsItem | None
    z_value: float
    stacking_flags: QGraphicsItem.GraphicsItemFlag


@dataclass(slots=True)
class _QtSceneMembershipSnapshot:
    scene: QGraphicsScene
    ordered_items: tuple[QGraphicsItem, ...]
    topology: tuple[_QtSceneItemTopology, ...]

    @classmethod
    def capture(cls, scene: QGraphicsScene) -> _QtSceneMembershipSnapshot:
        ordered_items = tuple(QGraphicsScene.items(scene))
        topology = tuple(
            _QtSceneItemTopology(
                item=item,
                parent=QGraphicsItem.parentItem(item),
                z_value=float(QGraphicsItem.zValue(item)),
                stacking_flags=(QGraphicsItem.flags(item) & _QT_STACKING_FLAG_MASK),
            )
            for item in ordered_items
        )
        return cls(scene, ordered_items, topology)

    def is_exact(self) -> bool:
        try:
            current = tuple(QGraphicsScene.items(self.scene))
            if len(current) != len(self.ordered_items) or any(
                actual is not expected
                for actual, expected in zip(
                    current,
                    self.ordered_items,
                    strict=True,
                )
            ):
                return False
            for state in self.topology:
                if (
                    sip.isdeleted(state.item)
                    or QGraphicsItem.scene(state.item) is not self.scene
                    or QGraphicsItem.parentItem(state.item) is not state.parent
                    or float(QGraphicsItem.zValue(state.item)) != state.z_value
                    or (QGraphicsItem.flags(state.item) & _QT_STACKING_FLAG_MASK)
                    != state.stacking_flags
                ):
                    return False
        except BaseException:
            return False
        return True

    def _restore_membership(self) -> None:
        expected_ids = {id(item) for item in self.ordered_items}
        current = tuple(QGraphicsScene.items(self.scene))
        unexpected = tuple(item for item in current if id(item) not in expected_ids)
        unexpected_ids = {id(item) for item in unexpected}
        for item in unexpected:
            parent = QGraphicsItem.parentItem(item)
            if parent is not None and id(parent) in unexpected_ids:
                continue
            QGraphicsScene.removeItem(self.scene, item)

        topology_by_id = {id(state.item): state for state in self.topology}
        for item in reversed(self.ordered_items):
            state = topology_by_id[id(item)]
            if state.parent is not None:
                continue
            if QGraphicsItem.scene(item) is not self.scene:
                QGraphicsScene.addItem(self.scene, item)

        pending = list(reversed(self.ordered_items))
        for _sweep in range(len(pending) + 1):
            if not pending:
                break
            next_pending: list[QGraphicsItem] = []
            for item in pending:
                state = topology_by_id[id(item)]
                parent = state.parent
                if parent is not None and QGraphicsItem.scene(parent) is not self.scene:
                    next_pending.append(item)
                    continue
                if QGraphicsItem.parentItem(item) is not parent:
                    QGraphicsItem.setParentItem(item, parent)
                if QGraphicsItem.scene(item) is not self.scene:
                    QGraphicsScene.addItem(self.scene, item)
            if len(next_pending) == len(pending):
                break
            pending = next_pending
        if pending:
            raise RuntimeError(
                "selection recovery could not reattach scene descendants"
            )

    def _restore_topology_and_order(self) -> None:
        for state in self.topology:
            item = state.item
            current_flags = QGraphicsItem.flags(item)
            restored_flags = (
                current_flags & ~_QT_STACKING_FLAG_MASK
            ) | state.stacking_flags
            if restored_flags != current_flags:
                QGraphicsItem.setFlags(item, restored_flags)
            if float(QGraphicsItem.zValue(item)) != state.z_value:
                QGraphicsItem.setZValue(item, state.z_value)

        sibling_groups: dict[
            tuple[int, float],
            list[_QtSceneItemTopology],
        ] = {}
        for state in self.topology:
            sibling_groups.setdefault(
                (id(state.parent), state.z_value),
                [],
            ).append(state)
        for siblings in sibling_groups.values():
            for higher, lower in zip(siblings, siblings[1:], strict=False):
                QGraphicsItem.stackBefore(lower.item, higher.item)

    def restore(self) -> None:
        for _attempt in range(2):
            self._restore_membership()
            self._restore_topology_and_order()
            if self.is_exact():
                return
        raise RuntimeError(
            "selection recovery did not restore exact Qt scene membership/order"
        )


@dataclass(slots=True)
class _SelectionCaptureAuthority:
    scene: object | None
    raw_objects: tuple[_RawSelectionObject, ...]
    raw_containers: tuple[_RawSelectionContainer, ...]
    qt_selection: tuple[tuple[QGraphicsItem, bool], ...]
    qt_membership: _QtSceneMembershipSnapshot | None
    signal_state_getter: Callable[[], object] | None
    signal_state_setter: Callable[[bool], object] | None
    callback_free_signal_state_getter: Callable[[], object] | None
    captured_signal_state: bool | None

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
                    nested_members = _nested_builtin_container_members(value)
                    if nested_members is None:
                        continue
                    for candidate in nested_members:
                        if not isinstance(candidate, (str, bytes, int, float, bool)):
                            raw_targets.append(candidate)
        raw_objects: list[_RawSelectionObject] = []
        seen_objects: set[int] = set()
        for target in raw_targets:
            if id(target) in seen_objects or inspect.isroutine(target):
                continue
            seen_objects.add(id(target))
            raw_objects.append(_RawSelectionObject.capture(target, capture_container))

        qt_membership = (
            _QtSceneMembershipSnapshot.capture(scene)
            if isinstance(scene, QGraphicsScene)
            else None
        )
        qt_items: list[QGraphicsItem] = []
        if qt_membership is not None:
            qt_items.extend(qt_membership.ordered_items)
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
        authority = cls(
            scene=scene,
            raw_objects=tuple(raw_objects),
            raw_containers=tuple(containers),
            qt_selection=tuple(qt_selection),
            qt_membership=qt_membership,
            signal_state_getter=None,
            signal_state_setter=None,
            callback_free_signal_state_getter=None,
            captured_signal_state=None,
        )
        try:
            if isinstance(scene, QObject):
                authority.signal_state_getter = partial(QObject.signalsBlocked, scene)
                authority.signal_state_setter = partial(QObject.blockSignals, scene)
            elif scene is not None:
                signal_state_candidate = _optional_live_attribute(
                    scene,
                    "signalsBlocked",
                    default=_MISSING_SCENE_ATTRIBUTE,
                )
                if callable(signal_state_candidate):
                    authority.signal_state_getter = signal_state_candidate
                signal_setter_candidate = _optional_live_attribute(
                    scene,
                    "blockSignals",
                    default=_MISSING_SCENE_ATTRIBUTE,
                )
                if callable(signal_setter_candidate):
                    authority.signal_state_setter = signal_setter_candidate
            captured_signal_state = (
                bool(authority.signal_state_getter())
                if authority.signal_state_getter is not None
                else None
            )
        except BaseException as capture_error:
            authority.restore(capture_error)
            raise
        if not authority.raw_state_is_exact():
            raw_capture_error = RuntimeError(
                "selection signal-state capture changed raw authority"
            )
            authority.restore(raw_capture_error)
            raise raw_capture_error
        authority.callback_free_signal_state_getter = (
            _callback_free_signal_state_getter_for(
                scene,
                authority.raw_objects,
                captured_signal_state,
            )
        )
        authority.captured_signal_state = captured_signal_state
        return authority

    def raw_state_is_exact(self) -> bool:
        try:
            for raw_object in self.raw_objects:
                raw_object.verify()
            for raw_container in self.raw_containers:
                raw_container.verify()
        except BaseException:
            return False
        return True

    def _raw_containers_are_exact_for(
        self,
        names: frozenset[str],
        *,
        scene_only: bool,
    ) -> bool:
        container_ids: set[int] = set()
        for raw_object in self.raw_objects:
            if scene_only and raw_object.target is not self.scene:
                continue
            container_ids.update(raw_object.raw_container_ids_for(names))
        return all(
            raw_container.is_exact()
            for raw_container in self.raw_containers
            if id(raw_container.target) in container_ids
        )

    def selection_state_is_exact(
        self,
        item_snapshots: Iterable[_ItemSelectionSnapshot] = (),
    ) -> bool:
        """Compare selection authorities without calling overridable ports."""

        try:
            if any(
                bool(QGraphicsItem.isSelected(item)) is not expected
                for item, expected in self.qt_selection
            ):
                return False
        except BaseException:
            return False
        try:
            for snapshot in item_snapshots:
                if not snapshot.capture_was_stable:
                    return False
                actual = snapshot.current_selected(callback_free=True)
                if actual is not None and actual is not snapshot.selected:
                    return False
        except BaseException:
            return False
        return self._raw_containers_are_exact_for(
            _RAW_SCENE_SELECTION_CONTAINER_FIELDS,
            scene_only=True,
        )

    def raw_selection_containers_are_empty(self) -> bool:
        scene_raw = next(
            (
                raw_object
                for raw_object in self.raw_objects
                if raw_object.target is self.scene
            ),
            None,
        )
        if scene_raw is None:
            return True
        # A selected-items-only list is a documented sparse compatibility
        # frontier and may intentionally remain stale.  Once the scene also
        # exposes a distinct raw membership container, the selection container
        # is an exact authority and must be empty after a successful clear.
        if not scene_raw.has_raw_container_field(_RAW_SCENE_DISTINCT_MEMBERSHIP_FIELDS):
            return True
        return scene_raw.raw_container_fields_are_empty(
            _RAW_SCENE_SELECTION_CONTAINER_FIELDS
        )

    def membership_state_is_exact(self) -> bool:
        if self.qt_membership is not None and not self.qt_membership.is_exact():
            return False
        scene_raw = next(
            (
                raw_object
                for raw_object in self.raw_objects
                if raw_object.target is self.scene
            ),
            None,
        )
        if scene_raw is not None and not scene_raw.raw_fields_are_exact(
            _RAW_SCENE_MEMBERSHIP_FIELDS
        ):
            return False
        return self._raw_containers_are_exact_for(
            _RAW_SCENE_MEMBERSHIP_FIELDS,
            scene_only=True,
        )

    def signal_state_is_exact(self) -> bool:
        """Compare state only through a callback-free captured authority."""

        getter = self.callback_free_signal_state_getter
        expected = self.captured_signal_state
        if expected is None:
            return True
        if getter is None:
            return False
        try:
            return bool(getter()) is expected
        except BaseException:
            return False

    def authoritative_state_is_exact(
        self,
        item_snapshots: Iterable[_ItemSelectionSnapshot] = (),
    ) -> bool:
        return (
            self.selection_state_is_exact(item_snapshots)
            and self.membership_state_is_exact()
            and self.signal_state_is_exact()
        )

    def require_unchanged_capture(
        self,
        item_snapshots: Iterable[_ItemSelectionSnapshot] = (),
    ) -> None:
        if self.authoritative_state_is_exact(item_snapshots):
            return
        capture_error = RuntimeError(
            "selection capture changed authoritative selection or signal state"
        )
        self.restore(capture_error)
        raise capture_error

    def restore_if_authority_changed(
        self,
        original_error: BaseException,
        item_snapshots: Iterable[_ItemSelectionSnapshot] = (),
    ) -> None:
        if not self.authoritative_state_is_exact(item_snapshots):
            self.restore(original_error)

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
                if self.qt_membership is not None:
                    self.qt_membership.restore()
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
                    self.signal_state_setter is not None
                    and self.captured_signal_state is not None
                ):
                    try:
                        self.signal_state_setter(self.captured_signal_state)
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
            if self.qt_membership is not None and not self.qt_membership.is_exact():
                errors.append(
                    RuntimeError("selection capture changed Qt scene membership/order")
                )
            if not self.signal_state_is_exact():
                errors.append(
                    RuntimeError("selection capture changed scene signal state")
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


@dataclass(frozen=True, slots=True)
class _SelectionReaderCandidate:
    reader: Callable[[], bool]
    captured: bool


def _qt_item_has_python_item_change_override(item: QGraphicsItem) -> bool:
    """Reject selection writes that can re-enter a Python virtual hook.

    Calling ``QGraphicsItem.setSelected`` bypasses a Python ``setSelected``
    override, but Qt still dispatches ``itemChange`` virtually.  A Python
    override can irreversibly delete another C++ scene item before rollback.
    Direct aliases of Qt's base implementation remain safe.
    """

    base_item_change = QGraphicsItem.__dict__["itemChange"]
    qt_method_descriptor_type = type(base_item_change)
    for owner in type(item).__mro__:
        if owner is QGraphicsItem:
            return False
        candidate = owner.__dict__.get(
            "itemChange",
            _MISSING_SCENE_ATTRIBUTE,
        )
        if candidate is _MISSING_SCENE_ATTRIBUTE:
            continue
        if (
            candidate is base_item_change
            or type(candidate) is qt_method_descriptor_type
        ):
            # Standard Qt subclasses such as QGraphicsWidget expose their own
            # C++ implementation through the same immutable sip descriptor.
            continue
        return True
    return False


def _callback_free_item_selection_candidates(
    item: object,
) -> tuple[_SelectionReaderCandidate, ...]:
    if isinstance(item, QGraphicsItem):

        def read_qt_selection() -> bool:
            return bool(QGraphicsItem.isSelected(item))

        return (
            _SelectionReaderCandidate(
                read_qt_selection,
                read_qt_selection(),
            ),
        )

    readers: list[Callable[[], bool]] = []
    try:
        namespace = object.__getattribute__(item, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict):
        for name in ("_selected", "selected"):
            if dict.__contains__(namespace, name):

                def read_namespace_selection(
                    *,
                    target: object = item,
                    field: str = name,
                ) -> bool:
                    current_namespace = object.__getattribute__(target, "__dict__")
                    if not isinstance(current_namespace, dict):
                        raise RuntimeError("selection authority namespace disappeared")
                    return bool(dict.__getitem__(current_namespace, field))

                readers.append(read_namespace_selection)

    if not isinstance(item, QObject):
        seen_descriptors: set[int] = set()
        for owner in type(item).__mro__:
            for name in ("_selected", "selected"):
                descriptor = owner.__dict__.get(name)
                if (
                    not isinstance(descriptor, MemberDescriptorType)
                    or id(descriptor) in seen_descriptors
                ):
                    continue
                seen_descriptors.add(id(descriptor))

                def read_slot_selection(
                    *,
                    target: object = item,
                    member: MemberDescriptorType = descriptor,
                ) -> bool:
                    return bool(member.__get__(target, type(target)))

                readers.append(read_slot_selection)
    return tuple(_SelectionReaderCandidate(reader, reader()) for reader in readers)


@dataclass(slots=True)
class _ItemSelectionSnapshot:
    item: object
    selected: bool
    is_selected: Callable[[], object]
    set_selected: Callable[[bool], object]
    authoritative_is_selected: Callable[[], bool] | None
    capture_was_stable: bool

    @classmethod
    def capture(cls, item: object) -> _ItemSelectionSnapshot:
        is_selected: Callable[[], object]
        set_selected: Callable[[bool], object]
        if isinstance(item, QGraphicsItem):
            # Qt's C++ selection state is the exact authority.  Calling a
            # Python subclass override here would let an item delete or detach
            # unrelated scene peers before topology recovery can protect their
            # wrappers.  Match the Qt clear path and bind the base ports for
            # capture, mutation, verification, and rollback.
            is_selected = partial(QGraphicsItem.isSelected, item)
            set_selected = partial(QGraphicsItem.setSelected, item)
        else:
            is_selected = _required_live_method(item, "isSelected")
            set_selected = _required_live_method(item, "setSelected")
        candidates = _callback_free_item_selection_candidates(item)
        live_selected = bool(is_selected())
        stable_candidates: list[_SelectionReaderCandidate] = []
        capture_was_stable = True
        for candidate in candidates:
            current = candidate.reader()
            if current is not candidate.captured:
                capture_was_stable = False
                continue
            if candidate.captured is live_selected:
                stable_candidates.append(candidate)
        authoritative_candidate: _SelectionReaderCandidate | None
        if isinstance(item, QGraphicsItem):
            authoritative_candidate = candidates[0]
        else:
            authoritative_candidate = (
                stable_candidates[0] if len(stable_candidates) == 1 else None
            )
        authoritative_is_selected = (
            authoritative_candidate.reader
            if authoritative_candidate is not None
            else None
        )
        return cls(
            item=item,
            selected=(
                authoritative_candidate.captured
                if authoritative_candidate is not None
                else live_selected
            ),
            is_selected=is_selected,
            set_selected=set_selected,
            authoritative_is_selected=authoritative_is_selected,
            capture_was_stable=capture_was_stable,
        )

    def current_selected(self, *, callback_free: bool) -> bool | None:
        authoritative = (
            self.authoritative_is_selected()
            if self.authoritative_is_selected is not None
            else None
        )
        if callback_free:
            return authoritative
        live = bool(self.is_selected())
        if authoritative is not None and live is not authoritative:
            raise RuntimeError("selection public getter disagrees with raw authority")
        return live

    def require_reversible_mutation_port(self) -> None:
        if isinstance(self.item, QGraphicsItem) and (
            _qt_item_has_python_item_change_override(self.item)
        ):
            raise RuntimeError(
                "Qt selection item has a Python itemChange override without "
                "an exact reversible mutation port"
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
                public_selected = self.current_selected(callback_free=False)
                final_authority = self.current_selected(callback_free=True)
                if public_selected == self.selected and (
                    final_authority is None or final_authority is self.selected
                ):
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


def _full_scene_selection_candidates(scene: object) -> tuple[object, ...]:
    """Return callback-visible selection peers without trusting Qt overrides."""

    if isinstance(scene, QGraphicsScene):
        return tuple(QGraphicsScene.items(scene))

    def candidates_from_container(value: object) -> tuple[object, ...] | None:
        return _nested_builtin_container_members(value)

    items_port = _optional_live_attribute(
        scene,
        "items",
        default=_MISSING_SCENE_ATTRIBUTE,
    )
    if callable(items_port):
        try:
            signature = inspect.signature(items_port)
            signature.bind()
        except (TypeError, ValueError):
            # Custom scenes can expose unrelated ``items(key)`` APIs. They are
            # not a zero-argument membership authority and must not be invoked.
            pass
        else:
            live_items = items_port()
            candidates = candidates_from_container(live_items)
            if candidates is not None:
                return candidates
            return tuple(cast(Iterable[object], live_items))
    else:
        candidates = candidates_from_container(items_port)
        if candidates is not None:
            return candidates

    # Sparse legacy fakes commonly retain the selection frontier in a stale
    # list. It is useful for rollback capture, but unlike ``items`` it is not a
    # post-operation selectedItems authority.
    try:
        namespace = object.__getattribute__(scene, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict):
        for name in (
            "_items",
            "scene_items",
            "_scene_items",
            "selected_items",
            "_selected_items",
        ):
            if not dict.__contains__(namespace, name):
                continue
            candidates = candidates_from_container(dict.__getitem__(namespace, name))
            if candidates is not None:
                return candidates
    return ()


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
        selection_services = _optional_live_attribute(services, "selection")
        controller = _optional_live_attribute(
            selection_services,
            "selection_controller",
        )
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
        if self.callback is None or not (isinstance(cache, tuple) and len(cache) == 2):
            return
        try:
            self.callback(str(cache[0]), str(cache[1]))
        except BaseException as callback_error:
            _add_selection_recovery_note(
                original_error,
                callback_error,
                phase="republishing the restored selection status",
            )


def _scene_for(
    canvas,
    *,
    strict: bool = False,
    callback_free_qt: bool = False,
):
    if callback_free_qt and isinstance(canvas, QGraphicsView):
        try:
            scene_obj = QGraphicsView.scene(canvas)
        except RuntimeError:
            if sip.isdeleted(canvas):
                return None
            if strict:
                raise
            return None
    else:
        try:
            scene = canvas.scene
        except AttributeError:
            if (
                strict
                and inspect.getattr_static(
                    canvas,
                    "scene",
                    _MISSING_SCENE_ATTRIBUTE,
                )
                is not _MISSING_SCENE_ATTRIBUTE
            ):
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
        capture_full_scene: bool = False,
    ) -> _SelectionMutationSnapshot:
        targets = tuple(items)
        item_snapshots: dict[int, _ItemSelectionSnapshot] = {}
        for item in targets:
            if id(item) not in item_snapshots:
                item_snapshots[id(item)] = _ItemSelectionSnapshot.capture(item)

        if scene is not None and (block_signals or capture_full_scene):
            for item in _full_scene_selection_candidates(scene):
                if id(item) in item_snapshots:
                    continue
                if (
                    inspect.getattr_static(
                        item,
                        "isSelected",
                        _MISSING_SCENE_ATTRIBUTE,
                    )
                    is _MISSING_SCENE_ATTRIBUTE
                    or inspect.getattr_static(
                        item,
                        "setSelected",
                        _MISSING_SCENE_ATTRIBUTE,
                    )
                    is _MISSING_SCENE_ATTRIBUTE
                ):
                    continue
                item_snapshots[id(item)] = _ItemSelectionSnapshot.capture(item)

        bound_block_signals: Callable[[bool], object] | None = None
        bound_signals_blocked: Callable[[], object] | None = None
        previous_signals_blocked: bool | None = None
        bound_selected_items: Callable[[], object] | None = None
        bound_clear_selection: Callable[[], object] | None = None
        original_scene_selected_ids: frozenset[int] | None = None
        derived_recovery: _SelectionInfoRecoverySnapshot | None = None

        if scene is not None:
            if isinstance(scene, QObject):
                bound_block_signals = partial(QObject.blockSignals, scene)
            else:
                block_method = _optional_live_attribute(
                    scene,
                    "blockSignals",
                    default=_MISSING_SCENE_ATTRIBUTE,
                )
                if block_method is not _MISSING_SCENE_ATTRIBUTE:
                    if not callable(block_method):
                        raise TypeError("Selection port 'blockSignals' is not callable")
                    bound_block_signals = block_method
                elif block_signals:
                    raise AttributeError("Selection item requires blockSignals")
            signals_method = (
                partial(QObject.signalsBlocked, scene)
                if isinstance(scene, QObject)
                else _optional_live_attribute(scene, "signalsBlocked")
            )
            if callable(signals_method):
                bound_signals_blocked = signals_method
                previous_signals_blocked = bool(bound_signals_blocked())

            # With live signals, a selectionChanged callback can expand groups
            # beyond ``targets``. Capture the whole selected frontier so a
            # downstream setter failure can remove callback-added selections.
            if not block_signals:
                selected_method = (
                    partial(QGraphicsScene.selectedItems, scene)
                    if isinstance(scene, QGraphicsScene)
                    else _required_live_method(scene, "selectedItems")
                )
                clear_method = (
                    partial(QGraphicsScene.clearSelection, scene)
                    if isinstance(scene, QGraphicsScene)
                    else _required_live_method(scene, "clearSelection")
                )
                original_selected = tuple(selected_method())
                for item in original_selected:
                    if id(item) not in item_snapshots:
                        item_snapshots[id(item)] = _ItemSelectionSnapshot.capture(item)
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

    def require_reversible_mutation_ports(
        self,
        selected: bool,
        *,
        recovery_peer_items: Iterable[object] = (),
    ) -> None:
        """Reject only Qt virtual ports that a real transition may enter."""

        changing_targets: list[_ItemSelectionSnapshot] = []
        for item in self.targets:
            snapshot = self.item_snapshots[id(item)]
            if snapshot.selected is selected:
                continue
            changing_targets.append(snapshot)
            snapshot.require_reversible_mutation_port()
        if not changing_targets:
            return

        # With live scene signals, a callback can select/deselect a peer and a
        # later rollback may need to enter that peer's itemChange hook.  Blocked
        # operations cannot publish that callback, so their unchanged peers do
        # not needlessly lose safe no-op support.
        changing_ids = {id(snapshot.item) for snapshot in changing_targets}
        for item in recovery_peer_items:
            if id(item) in changing_ids or not isinstance(item, QGraphicsItem):
                continue
            if _qt_item_has_python_item_change_override(item):
                raise RuntimeError(
                    "Qt selection peer has a Python itemChange override without "
                    "an exact reversible rollback port"
                )

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
                    snapshot.current_selected(callback_free=False) == snapshot.selected
                )
            except BaseException as verify_error:
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying restored target selections",
                )
                exact = False
        for snapshot in self.item_snapshots.values():
            try:
                final_authority = snapshot.current_selected(callback_free=True)
                exact = exact and (
                    final_authority is None or final_authority is snapshot.selected
                )
            except BaseException as verify_error:
                _add_selection_recovery_note(
                    original_error,
                    verify_error,
                    phase="verifying callback-free restored target selections",
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
        scene_exact = actual_ids == expected_ids
        item_exact = self._target_selection_is_exact(original_error)
        return scene_exact and item_exact

    def verify_empty_selection(self) -> None:
        """Cross-check the captured frontier through raw and public authorities."""

        snapshots = tuple(self.item_snapshots.values())

        def verify_items(values: Iterable[_ItemSelectionSnapshot]) -> None:
            for snapshot in values:
                selected = snapshot.current_selected(callback_free=False)
                if selected is None:
                    raise RuntimeError(
                        "scene selection clear has no item selection authority"
                    )
                if selected:
                    raise RuntimeError(
                        "scene selection clear left a frontier item selected"
                    )

        verify_items(snapshots)
        verify_items(reversed(snapshots))
        for snapshot in snapshots:
            selected = snapshot.current_selected(callback_free=True)
            if selected is None:
                raise RuntimeError(
                    "scene selection clear has no callback-free item authority"
                )
            if selected:
                raise RuntimeError(
                    "scene selection clear left a callback-free item selected"
                )
        if isinstance(self.scene, QGraphicsScene):
            actual = tuple(QGraphicsScene.selectedItems(self.scene))
            if actual:
                raise RuntimeError("scene selection clear left selected scene items")

    def verify_compatible_empty_selection(self) -> None:
        """Verify public-only frontiers without requiring a raw authority."""

        snapshots = tuple(self.item_snapshots.values())
        for values in (snapshots, tuple(reversed(snapshots))):
            for snapshot in values:
                if snapshot.current_selected(callback_free=False):
                    raise RuntimeError(
                        "compatible scene selection clear left an item selected"
                    )
        for snapshot in snapshots:
            selected = snapshot.current_selected(callback_free=True)
            if selected:
                raise RuntimeError(
                    "compatible scene selection clear left a callback-free "
                    "item selected"
                )

    def has_callback_free_selection_authority(self) -> bool:
        return all(
            snapshot.authoritative_is_selected is not None
            for snapshot in self.item_snapshots.values()
        )

    def verify_selection_postcondition(
        self,
        expected: bool,
        *,
        preserve_peers: bool,
    ) -> None:
        target_ids = {id(item) for item in self.targets}
        snapshots = (
            tuple(self.item_snapshots.values())
            if preserve_peers
            else tuple(self.item_snapshots[id(item)] for item in self.targets)
        )

        def expected_for(snapshot: _ItemSelectionSnapshot) -> bool:
            return expected if id(snapshot.item) in target_ids else snapshot.selected

        def verify(values: Iterable[_ItemSelectionSnapshot]) -> None:
            for snapshot in values:
                actual = snapshot.current_selected(callback_free=False)
                snapshot_expected = expected_for(snapshot)
                if actual is not snapshot_expected:
                    if id(snapshot.item) not in target_ids:
                        raise RuntimeError(
                            "scene item selection setter changed a non-target peer"
                        )
                    raise RuntimeError(
                        "scene item selection setter did not apply the requested state"
                    )

        verify(snapshots)
        verify(reversed(snapshots))
        for snapshot in snapshots:
            actual = snapshot.current_selected(callback_free=True)
            snapshot_expected = expected_for(snapshot)
            if actual is not None and actual is not snapshot_expected:
                if id(snapshot.item) not in target_ids:
                    raise RuntimeError(
                        "scene item selection setter did not preserve a "
                        "callback-free non-target peer"
                    )
                raise RuntimeError(
                    "scene item selection setter did not preserve its "
                    "callback-free postcondition"
                )

    def _restore_once(
        self,
        original_error: BaseException,
        *,
        reverse_order: bool,
    ) -> None:
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
        # The forward pass makes captured-false peers final so a custom true
        # setter cannot select one. The retry reverses both state groups and
        # peer order so a synchronous writer cannot keep the same last word.
        selection_states = (False, True) if reverse_order else (True, False)
        snapshots = tuple(self.item_snapshots.values())
        ordered_snapshots = tuple(reversed(snapshots)) if reverse_order else snapshots
        for selected_state in selection_states:
            for snapshot in ordered_snapshots:
                if snapshot.selected is selected_state:
                    snapshot.restore(original_error)

    def _restore_selection_under_blocked_signals(
        self,
        original_error: BaseException,
        *,
        reverse_order: bool = False,
    ) -> None:
        if self.scene is not None and self.block_signals is not None:
            with blocked_scene_signals(
                self.scene,
                block_signals=self.block_signals,
                signals_blocked=self._signals_blocked_capture(),
            ):
                self._restore_once(
                    original_error,
                    reverse_order=reverse_order,
                )
            return
        self._restore_once(
            original_error,
            reverse_order=reverse_order,
        )

    def _restore_signal_state(self, original_error: BaseException) -> None:
        if (
            self.previous_signals_blocked is None
            or self.signals_blocked is None
            or self.block_signals is None
        ):
            return
        for attempt in range(2):
            try:
                if bool(self.signals_blocked()) == self.previous_signals_blocked:
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
            restored = bool(self.signals_blocked()) == self.previous_signals_blocked
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
                RuntimeError("scene signal state did not return to its captured value"),
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
                    self._restore_selection_under_blocked_signals(
                        original_error,
                        reverse_order=False,
                    )
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
                    self._restore_selection_under_blocked_signals(
                        original_error,
                        reverse_order=True,
                    )
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
                self._restore_selection_under_blocked_signals(
                    original_error,
                    reverse_order=bool(attempt),
                )
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
            self.derived_recovery.republish_after_partial_signal_failure(original_error)
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


def _clear_scene_selection_compatibly(
    scene_obj: object,
    clear_selection: Callable[[], object],
    *,
    block_signals: bool,
) -> bool:
    """Retain the sparse-scene contract when no exact snapshot is possible."""

    if block_signals:
        with blocked_scene_signals(scene_obj):
            clear_selection()
    else:
        clear_selection()
    return True


def clear_scene_selection_for(canvas, *, block_signals: bool = False) -> bool:
    scene_obj = _scene_for(canvas, strict=True, callback_free_qt=True)
    if scene_obj is None:
        return False
    clear_selection = (
        partial(QGraphicsScene.clearSelection, scene_obj)
        if isinstance(scene_obj, QGraphicsScene)
        else _required_live_method(scene_obj, "clearSelection")
    )
    # Selection restoration needs all three scene ports. Lightweight renderer
    # and structure-service fakes intentionally expose only ``clearSelection``;
    # preserve that historical best-effort API instead of invoking item ports
    # they do not claim to implement.
    if inspect.getattr_static(
        scene_obj,
        "selectedItems",
        _MISSING_SCENE_ATTRIBUTE,
    ) is _MISSING_SCENE_ATTRIBUTE or (
        block_signals
        and (
            inspect.getattr_static(
                scene_obj,
                "blockSignals",
                _MISSING_SCENE_ATTRIBUTE,
            )
            is _MISSING_SCENE_ATTRIBUTE
            or inspect.getattr_static(
                scene_obj,
                "signalsBlocked",
                _MISSING_SCENE_ATTRIBUTE,
            )
            is _MISSING_SCENE_ATTRIBUTE
        )
    ):
        return _clear_scene_selection_compatibly(
            scene_obj,
            clear_selection,
            block_signals=block_signals,
        )
    capture_authority = _SelectionCaptureAuthority.capture(scene_obj, ())
    compatibility_required = False
    snapshot: _SelectionMutationSnapshot | None = None
    try:
        selected_items = (
            partial(QGraphicsScene.selectedItems, scene_obj)
            if isinstance(scene_obj, QGraphicsScene)
            else _required_live_method(scene_obj, "selectedItems")
        )
        targets = tuple(selected_items())
        if any(
            inspect.getattr_static(
                item,
                "isSelected",
                _MISSING_SCENE_ATTRIBUTE,
            )
            is _MISSING_SCENE_ATTRIBUTE
            or inspect.getattr_static(
                item,
                "setSelected",
                _MISSING_SCENE_ATTRIBUTE,
            )
            is _MISSING_SCENE_ATTRIBUTE
            for item in targets
        ):
            compatibility_required = True
        else:
            snapshot = _SelectionMutationSnapshot.capture(
                canvas,
                scene_obj,
                targets,
                block_signals=block_signals,
                capture_full_scene=True,
            )
            if not snapshot.has_callback_free_selection_authority():
                compatibility_required = True
    except BaseException as original_error:
        capture_authority.restore(original_error)
        raise
    captured_item_states = (
        tuple(snapshot.item_snapshots.values()) if snapshot is not None else ()
    )
    capture_authority.require_unchanged_capture(captured_item_states)
    if compatibility_required:
        try:
            result = _clear_scene_selection_compatibly(
                scene_obj,
                clear_selection,
                block_signals=block_signals,
            )
            if snapshot is not None:
                snapshot.verify_compatible_empty_selection()
            if not capture_authority.membership_state_is_exact():
                raise RuntimeError(
                    "compatible scene selection clear changed "
                    "authoritative membership/order"
                )
            if not capture_authority.signal_state_is_exact():
                raise RuntimeError(
                    "compatible scene selection clear changed "
                    "authoritative signal state"
                )
            return result
        except BaseException as original_error:
            if snapshot is not None:
                snapshot.restore(original_error)
            capture_authority.restore_if_authority_changed(
                original_error,
                captured_item_states,
            )
            raise
    assert snapshot is not None
    try:
        snapshot.require_reversible_mutation_ports(
            False,
            recovery_peer_items=(
                (item for item, _selected in capture_authority.qt_selection)
                if not block_signals
                else ()
            ),
        )
        if block_signals:
            assert snapshot.block_signals is not None
            with blocked_scene_signals(
                scene_obj,
                block_signals=snapshot.block_signals,
                signals_blocked=snapshot._signals_blocked_capture(),
            ):
                clear_selection()
        else:
            clear_selection()
        snapshot.verify_empty_selection()
        if not capture_authority.raw_selection_containers_are_empty():
            raise RuntimeError(
                "scene selection clear left a raw selection container populated"
            )
        if block_signals and not capture_authority.membership_state_is_exact():
            raise RuntimeError(
                "scene selection clear changed authoritative membership/order"
            )
        if not capture_authority.signal_state_is_exact():
            raise RuntimeError(
                "scene selection clear changed authoritative signal state"
            )
    except BaseException as original_error:
        snapshot.restore(original_error)
        capture_authority.restore_if_authority_changed(
            original_error,
            captured_item_states,
        )
        raise
    return True


def set_scene_items_selected_for(
    canvas,
    items,
    selected: bool,
    *,
    block_signals: bool = True,
) -> None:
    scene_obj = _scene_for(canvas, strict=True, callback_free_qt=True)
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
    captured_item_states = tuple(snapshot.item_snapshots.values())
    capture_authority.require_unchanged_capture(captured_item_states)
    try:
        snapshot.require_reversible_mutation_ports(
            selected,
            recovery_peer_items=(
                (item for item, _selected in capture_authority.qt_selection)
                if not block_signals
                else ()
            ),
        )
        snapshot.mutate(selected, block_signals=block_signals)
        snapshot.verify_selection_postcondition(
            selected,
            preserve_peers=block_signals,
        )
        if block_signals and not capture_authority.membership_state_is_exact():
            raise RuntimeError(
                "scene item selection changed authoritative membership/order"
            )
        if not capture_authority.signal_state_is_exact():
            raise RuntimeError(
                "scene item selection changed authoritative signal state"
            )
    except BaseException as original_error:
        snapshot.restore(original_error)
        capture_authority.restore_if_authority_changed(
            original_error,
            captured_item_states,
        )
        raise


__all__ = [
    "clear_scene_selection_for",
    "scene_selected_items_for",
    "selected_scene_notes_for",
    "set_scene_items_selected_for",
]
