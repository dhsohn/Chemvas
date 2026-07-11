from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass, replace
from functools import partial
from types import MemberDescriptorType
from typing import Any, cast

from core.model import MoleculeModel
from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from ui.atom_coords_access import clear_atom_coords_3d_for
from ui.benzene_preview_access import clear_benzene_preview_for
from ui.canvas_atom_graphics_state import clear_atom_graphics_for
from ui.canvas_bond_graphics_state import clear_bond_graphics_for
from ui.canvas_document_state import snapshot_canvas_document_state
from ui.canvas_graph_state import graph_state_for
from ui.canvas_group_state import clear_groups_for
from ui.canvas_hover_state import (
    set_hover_atom_id_for,
    set_hover_bond_id_for,
    set_hover_items_for,
)
from ui.canvas_insert_state import insert_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import set_model_for
from ui.canvas_rotation_preview_state import rotation_preview_state_for
from ui.canvas_rotation_state import rotation_state_for
from ui.canvas_scene_items_state import clear_scene_item_collections_for
from ui.handle_state import set_active_handles_for, set_handle_target_for
from ui.history_push_failure_recovery import RecordingHistoryPolicySnapshot
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.insert_mode_logic import clear_insert_session
from ui.insert_session_access import (
    apply_insert_session_state_for,
    clear_smiles_preview_for,
    clear_template_preview_for,
)
from ui.scene_signal_blocking import blocked_scene_signals
from ui.selection_info_state import SelectionInfoState, selection_info_state_for
from ui.selection_outline_state import clear_selection_outlines_for
from ui.selection_style_state import SelectionStyleState, selection_style_state_for
from ui.spatial_index_state import mark_spatial_index_dirty_for

_MISSING_ATTRIBUTE = object()


_RESET_OWNED_RUNTIME_FIELDS: dict[str, tuple[str, ...] | None] = {
    # The runtime aliases are independent live authorities from the service
    # bundle aliases below. Their contents and policy are closed by the bound
    # HistoryStackSnapshot/RecordingHistoryPolicySnapshot pair.
    "history_state": (),
    "history_service": (),
    "graph_state": None,
    "group_state": None,
    "insert_state": None,
    "atom_coords_3d_state": None,
    "atom_graphics_state": None,
    "bond_graphics_state": None,
    "mark_registry": ("by_atom",),
    "spatial_index_state": ("dirty",),
    "rotation_preview_state": None,
    "rotation_state": None,
    "handle_state": None,
    "selection_style_state": ("selected_items", "suspend_outline"),
    "selection_info_state": (
        "signature",
        "pending_signature",
        "cache",
        "rdkit_warmup_pending",
    ),
    "selection_outline_state": None,
    "hover_preview_state": ("items", "atom_id", "bond_id"),
    "scene_items_state": None,
}


def _add_reset_recovery_note(
    original_error: BaseException,
    recovery_error: BaseException,
) -> None:
    try:
        original_error.add_note(
            "Scene reset recovery also failed with "
            f"{type(recovery_error).__name__}: {recovery_error}"
        )
    except BaseException:
        return


def _capture_optional_attribute(target: object, name: str) -> object:
    """Read an optional port without hiding a live descriptor failure."""
    try:
        return getattr(target, name)
    except AttributeError:
        static_value = inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
        if static_value is not _MISSING_ATTRIBUTE:
            raise
        return _MISSING_ATTRIBUTE


def _capture_optional_callable(
    target: object,
    name: str,
) -> Callable[..., Any] | None:
    value = _capture_optional_attribute(target, name)
    if value is _MISSING_ATTRIBUTE:
        return None
    if not callable(value):
        raise TypeError(f"{type(target).__name__}.{name} is not callable")
    return value


def _capture_statically_bound_callable(
    target: object,
    name: str,
) -> Callable[..., Any] | None:
    """Bind an ordinary Python method without entering a live descriptor.

    This intentionally supports only callback-free instance callables and
    ordinary function/method descriptors. Properties and arbitrary custom
    descriptors remain live ports and are resolved later, after reversible
    non-Qt membership has already been frozen.
    """

    try:
        namespace = object.__getattribute__(target, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict) and name in namespace:
        value = dict.__getitem__(namespace, name)
        return value if callable(value) else None

    descriptor = inspect.getattr_static(type(target), name, _MISSING_ATTRIBUTE)
    if descriptor is _MISSING_ATTRIBUTE or isinstance(descriptor, property):
        return None
    if isinstance(descriptor, staticmethod):
        value = descriptor.__func__
        return value if callable(value) else None
    if isinstance(descriptor, classmethod):
        value = descriptor.__func__
        return partial(value, type(target)) if callable(value) else None
    if inspect.isfunction(descriptor) or inspect.ismethoddescriptor(descriptor):
        return partial(descriptor, target)
    return None


def _raw_attribute(target: object, name: str) -> object:
    """Read a captured root without re-entering an overridden __getattribute__."""

    try:
        namespace = object.__getattribute__(target, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict) and name in namespace:
        return dict.__getitem__(namespace, name)
    return object.__getattribute__(target, name)


def _raw_optional_attribute(target: object, name: str) -> tuple[bool, object]:
    try:
        return True, _raw_attribute(target, name)
    except AttributeError:
        return False, _MISSING_ATTRIBUTE


def _set_raw_attribute(target: object, name: str, value: object) -> None:
    object.__setattr__(target, name, value)


def _delete_raw_attribute(target: object, name: str) -> None:
    try:
        object.__delattr__(target, name)
    except AttributeError:
        return


def _authority_leaf_matches(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    if type(actual) is not type(expected):
        return False
    if isinstance(
        expected,
        (type(None), bool, int, float, complex, str, bytes, tuple, frozenset),
    ):
        try:
            return bool(actual == expected)
        except BaseException:
            return False
    return False


@dataclass(frozen=True, slots=True)
class _AuthorityContainerState:
    target: object
    kind: str
    contents: tuple


@dataclass(frozen=True, slots=True)
class _AuthorityObjectState:
    target: object
    fields: tuple[tuple[str, bool, object], ...]


class _ResetOwnedObjectGraph:
    """Callback-free exact state for reset-owned Python roots and containers."""

    def __init__(self) -> None:
        self._containers: dict[int, _AuthorityContainerState] = {}
        self._objects: dict[int, _AuthorityObjectState] = {}
        self._immutable_seen: set[int] = set()

    def capture_value(self, value: object) -> None:
        if isinstance(value, dict):
            if id(value) in self._containers:
                return
            contents = tuple(dict.items(value))
            self._containers[id(value)] = _AuthorityContainerState(
                value,
                "dict",
                contents,
            )
            for key, item in contents:
                self.capture_value(key)
                self.capture_value(item)
            return
        if isinstance(value, list):
            if id(value) in self._containers:
                return
            contents = tuple(list.__iter__(value))
            self._containers[id(value)] = _AuthorityContainerState(
                value,
                "list",
                contents,
            )
            for item in contents:
                self.capture_value(item)
            return
        if isinstance(value, set):
            if id(value) in self._containers:
                return
            contents = tuple(set.__iter__(value))
            self._containers[id(value)] = _AuthorityContainerState(
                value,
                "set",
                contents,
            )
            for item in contents:
                self.capture_value(item)
            return
        if isinstance(value, (tuple, frozenset)):
            if id(value) in self._immutable_seen:
                return
            self._immutable_seen.add(id(value))
            for item in value:
                self.capture_value(item)
            return
        if is_dataclass(value) and not isinstance(value, type):
            self.capture_object(value)

    def capture_object(
        self,
        target: object,
        names: tuple[str, ...] | None = None,
    ) -> None:
        if id(target) in self._objects:
            return
        if names is None:
            if not is_dataclass(target) or isinstance(target, type):
                raise TypeError(
                    f"reset authority needs explicit fields for {type(target).__name__}"
                )
            names = tuple(field.name for field in fields(target))
        captured: list[tuple[str, bool, object]] = []
        # Publish the record before descending so aliases and accidental cycles
        # cannot recurse indefinitely.
        self._objects[id(target)] = _AuthorityObjectState(target, ())
        for name in names:
            present, value = _raw_optional_attribute(target, name)
            captured.append((name, present, value))
            if present:
                self.capture_value(value)
        self._objects[id(target)] = _AuthorityObjectState(
            target,
            tuple(captured),
        )

    def restore(self) -> None:
        for object_state in self._objects.values():
            for name, present, value in object_state.fields:
                if present:
                    _set_raw_attribute(object_state.target, name, value)
                else:
                    _delete_raw_attribute(object_state.target, name)
        for container_state in self._containers.values():
            if container_state.kind == "dict":
                dictionary = cast(dict, container_state.target)
                dict.clear(dictionary)
                dict.update(
                    dictionary,
                    cast(
                        tuple[tuple[object, object], ...],
                        container_state.contents,
                    ),
                )
            elif container_state.kind == "list":
                values = cast(list, container_state.target)
                list.__setitem__(values, slice(None), container_state.contents)
            else:
                members = cast(set, container_state.target)
                set.clear(members)
                set.update(members, container_state.contents)

    def verify(self) -> None:
        for object_state in self._objects.values():
            for name, present, expected in object_state.fields:
                actual_present, actual = _raw_optional_attribute(
                    object_state.target,
                    name,
                )
                if actual_present is not present or (
                    present and not _authority_leaf_matches(actual, expected)
                ):
                    raise RuntimeError(
                        "scene reset changed reset-owned field "
                        f"{type(object_state.target).__name__}.{name}"
                    )
        for container_state in self._containers.values():
            if container_state.kind == "dict":
                actual = tuple(dict.items(cast(dict, container_state.target)))
                expected = cast(
                    tuple[tuple[object, object], ...],
                    container_state.contents,
                )
                exact = len(actual) == len(expected) and all(
                    actual_key is expected_key and actual_value is expected_value
                    for (actual_key, actual_value), (
                        expected_key,
                        expected_value,
                    ) in zip(actual, expected, strict=True)
                )
            elif container_state.kind == "list":
                actual = tuple(list.__iter__(cast(list, container_state.target)))
                exact = len(actual) == len(container_state.contents) and all(
                    value is expected
                    for value, expected in zip(
                        actual,
                        container_state.contents,
                        strict=True,
                    )
                )
            else:
                actual_ids = {
                    id(value)
                    for value in set.__iter__(cast(set, container_state.target))
                }
                exact = actual_ids == {id(value) for value in container_state.contents}
            if not exact:
                raise RuntimeError("scene reset changed a reset-owned container")


@dataclass(frozen=True, slots=True)
class _ResetOwnedAuthoritySnapshot:
    runtime_present: bool
    runtime_state: object
    owner: object
    model_present: bool
    model: object
    state_roots: tuple[tuple[str, bool, object], ...]
    graph: _ResetOwnedObjectGraph

    @classmethod
    def capture(cls, canvas: object) -> _ResetOwnedAuthoritySnapshot:
        runtime_present, runtime_state = _raw_optional_attribute(
            canvas,
            "runtime_state",
        )
        owner = runtime_state if runtime_present else canvas
        model_present, model = _raw_optional_attribute(canvas, "model")
        graph = _ResetOwnedObjectGraph()
        if model_present and is_dataclass(model) and not isinstance(model, type):
            graph.capture_object(model)
        state_roots: list[tuple[str, bool, object]] = []
        for name, owned_fields in _RESET_OWNED_RUNTIME_FIELDS.items():
            present, state = _raw_optional_attribute(owner, name)
            state_roots.append((name, present, state))
            if not present:
                continue
            graph.capture_object(state, owned_fields)
        return cls(
            runtime_present=runtime_present,
            runtime_state=runtime_state,
            owner=owner,
            model_present=model_present,
            model=model,
            state_roots=tuple(state_roots),
            graph=graph,
        )

    def restore_roots(self, canvas: object) -> None:
        if self.runtime_present:
            _set_raw_attribute(canvas, "runtime_state", self.runtime_state)
        else:
            _delete_raw_attribute(canvas, "runtime_state")
        if self.model_present:
            _set_raw_attribute(canvas, "model", self.model)
        else:
            _delete_raw_attribute(canvas, "model")
        for name, present, state in self.state_roots:
            if present:
                _set_raw_attribute(self.owner, name, state)
            else:
                _delete_raw_attribute(self.owner, name)

    def restore(self, canvas: object) -> None:
        self.restore_roots(canvas)
        self.graph.restore()
        self.restore_roots(canvas)

    def verify(self, canvas: object) -> None:
        runtime_present, runtime_state = _raw_optional_attribute(
            canvas,
            "runtime_state",
        )
        if runtime_present is not self.runtime_present or (
            runtime_present and runtime_state is not self.runtime_state
        ):
            raise RuntimeError("scene reset changed the runtime-state root")
        model_present, model = _raw_optional_attribute(canvas, "model")
        if model_present is not self.model_present or (
            model_present and model is not self.model
        ):
            raise RuntimeError("scene reset changed the model root")
        for name, present, expected in self.state_roots:
            actual_present, actual = _raw_optional_attribute(self.owner, name)
            if actual_present is not present or (present and actual is not expected):
                raise RuntimeError(f"scene reset changed reset-owned root {name!r}")
        self.graph.verify()


@dataclass(frozen=True, slots=True)
class _RawCanvasScenePort:
    canvas: object
    name: str
    namespace: dict | None
    descriptor: MemberDescriptorType | None
    present: bool
    value: object

    def current(self) -> object:
        if self.namespace is not None:
            return dict.get(
                self.namespace,
                self.name,
                _MISSING_ATTRIBUTE,
            )
        descriptor = self.descriptor
        if descriptor is None:
            return _MISSING_ATTRIBUTE
        try:
            return descriptor.__get__(self.canvas, type(self.canvas))
        except AttributeError:
            return _MISSING_ATTRIBUTE

    def restore(self) -> None:
        if self.namespace is not None:
            if self.present:
                dict.__setitem__(self.namespace, self.name, self.value)
            else:
                self.namespace.pop(self.name, None)
            return
        descriptor = self.descriptor
        if descriptor is None:
            raise RuntimeError("canvas scene root has no callback-free restore port")
        if self.present:
            descriptor.__set__(self.canvas, self.value)
            return
        try:
            descriptor.__delete__(self.canvas)
        except AttributeError:
            return

    def is_exact(self) -> bool:
        current = self.current()
        if not self.present:
            return current is _MISSING_ATTRIBUTE
        return current is self.value


@dataclass(frozen=True, slots=True)
class _RawCanvasSceneRoot:
    """Exact conventional non-Qt scene aliases captured without callbacks."""

    scene: object
    ports: tuple[_RawCanvasScenePort, ...]

    @classmethod
    def capture(cls, canvas: object) -> _RawCanvasSceneRoot | None:
        try:
            namespace_value = object.__getattribute__(canvas, "__dict__")
        except (AttributeError, TypeError):
            namespace = None
        else:
            namespace = namespace_value if isinstance(namespace_value, dict) else None

        ports: list[_RawCanvasScenePort] = []
        if namespace is not None:
            for name in ("_scene", "scene_obj"):
                present = name in namespace
                value = (
                    dict.__getitem__(namespace, name)
                    if present
                    else _MISSING_ATTRIBUTE
                )
                ports.append(
                    _RawCanvasScenePort(
                        canvas,
                        name,
                        namespace,
                        None,
                        present,
                        value,
                    )
                )

        seen_descriptors: set[int] = set()
        for owner in type(canvas).__mro__:
            for name in ("_scene", "scene_obj"):
                descriptor = owner.__dict__.get(name)
                if (
                    type(descriptor) is not MemberDescriptorType
                    or id(descriptor) in seen_descriptors
                ):
                    continue
                seen_descriptors.add(id(descriptor))
                member = cast(MemberDescriptorType, descriptor)
                try:
                    value = member.__get__(canvas, type(canvas))
                except AttributeError:
                    present = False
                    value = _MISSING_ATTRIBUTE
                else:
                    present = True
                ports.append(
                    _RawCanvasScenePort(
                        canvas,
                        name,
                        None,
                        member,
                        present,
                        value,
                    )
                )

        by_identity = {
            id(port.value): port.value
            for port in ports
            if port.present and port.value is not None
        }
        if len(by_identity) > 1:
            raise RuntimeError("ambiguous callback-free canvas scene roots")
        if not by_identity:
            return None
        scene = next(iter(by_identity.values()))
        authority = cls(scene, tuple(ports))
        authority.verify()
        return authority

    def current_roots(self) -> tuple[object, ...]:
        values: list[object] = []
        seen: set[int] = set()
        for port in self.ports:
            value = port.current()
            if value is _MISSING_ATTRIBUTE or value is None or id(value) in seen:
                continue
            seen.add(id(value))
            values.append(value)
        return tuple(values)

    def verify(self) -> None:
        if any(not port.is_exact() for port in self.ports):
            raise RuntimeError("canvas scene root identity changed")

    def restore(self) -> None:
        for ports in (self.ports, tuple(reversed(self.ports))):
            for port in ports:
                port.restore()
            try:
                self.verify()
            except BaseException:
                continue
            return
        raise RuntimeError("canvas scene roots could not be restored")


@dataclass(frozen=True, slots=True)
class _RawSceneMembershipRoot:
    """Callback-free identity port for an exact fake scene's ``_items`` list."""

    scene: object
    namespace: dict | None
    descriptor: MemberDescriptorType | None
    backing: list

    @classmethod
    def capture(cls, scene: object) -> _RawSceneMembershipRoot | None:
        try:
            namespace_value = object.__getattribute__(scene, "__dict__")
        except (AttributeError, TypeError):
            namespace = None
        else:
            namespace = namespace_value if isinstance(namespace_value, dict) else None

        candidates: list[
            tuple[dict | None, MemberDescriptorType | None, list]
        ] = []
        if namespace is not None:
            candidate = dict.get(namespace, "_items", _MISSING_ATTRIBUTE)
            if isinstance(candidate, list):
                candidates.append((namespace, None, candidate))

        seen_descriptors: set[int] = set()
        for owner in type(scene).__mro__:
            descriptor = owner.__dict__.get("_items")
            if (
                type(descriptor) is not MemberDescriptorType
                or id(descriptor) in seen_descriptors
            ):
                continue
            seen_descriptors.add(id(descriptor))
            member = cast(MemberDescriptorType, descriptor)
            try:
                candidate = member.__get__(scene, type(scene))
            except AttributeError:
                continue
            if isinstance(candidate, list):
                candidates.append((None, member, candidate))

        by_identity = {id(candidate[2]): candidate for candidate in candidates}
        if len(by_identity) > 1:
            raise RuntimeError("ambiguous callback-free scene _items backings")
        if not by_identity:
            return None
        # A data-descriptor slot is the live attribute authority when both a
        # slot and a manually injected namespace alias point at the same list.
        equivalent = tuple(by_identity.values())
        namespace_port, descriptor_port, backing = next(iter(equivalent))
        descriptor_candidate = next(
            (candidate for candidate in candidates if candidate[1] is not None),
            None,
        )
        if descriptor_candidate is not None:
            namespace_port, descriptor_port, backing = descriptor_candidate
        return cls(scene, namespace_port, descriptor_port, backing)

    def is_exact(self) -> bool:
        if self.namespace is not None:
            return dict.get(
                self.namespace,
                "_items",
                _MISSING_ATTRIBUTE,
            ) is self.backing
        descriptor = self.descriptor
        if descriptor is None:
            return False
        try:
            return descriptor.__get__(self.scene, type(self.scene)) is self.backing
        except AttributeError:
            return False

    def restore(self, contents: tuple[object, ...]) -> None:
        if self.namespace is not None:
            dict.__setitem__(self.namespace, "_items", self.backing)
        elif self.descriptor is not None:
            self.descriptor.__set__(self.scene, self.backing)
        else:
            raise RuntimeError("scene _items root has no callback-free restore port")
        list.__setitem__(self.backing, slice(None), contents)
        if not self.is_exact():
            raise RuntimeError("scene _items root identity was not restored")


@dataclass(frozen=True, slots=True)
class _GraphicsSceneClearPorts:
    scene: Any
    clear: Callable[..., Any]
    clear_selection: Callable[..., Any] | None
    block_signals: Callable[..., Any] | None
    signals_blocked: Callable[..., Any] | None
    items: Callable[..., Any] | None
    items_before_clear: tuple[object, ...] | None
    add_item: Callable[..., Any] | None
    remove_item: Callable[..., Any] | None
    raw_items_root: _RawSceneMembershipRoot | None
    qt_items_before_clear: tuple[QGraphicsItem, ...] | None
    qt_base_clear: Callable[..., Any] | None


_SERVICE_RUNTIME_ALIASES: tuple[tuple[str, str], ...] = (
    ("graph", "graph_state"),
    ("rotation", "rotation_state"),
    ("rotation_preview", "rotation_preview_state"),
    ("insert_state", "insert_state"),
    ("marks", "mark_registry"),
)


@dataclass(frozen=True, slots=True)
class _ResetServiceAliasSnapshot:
    service: object
    aliases: tuple[tuple[str, object], ...]

    @classmethod
    def capture(
        cls,
        service: object,
        owned: _ResetOwnedAuthoritySnapshot,
    ) -> _ResetServiceAliasSnapshot:
        roots = {
            name: state
            for name, present, state in owned.state_roots
            if present
        }
        aliases: list[tuple[str, object]] = []
        for service_name, runtime_name in _SERVICE_RUNTIME_ALIASES:
            service_present, _current = _raw_optional_attribute(
                service,
                service_name,
            )
            if not service_present:
                # A few deliberately sparse test/service doubles construct the
                # service via ``__new__`` and do not expose cached aliases.
                continue
            if runtime_name not in roots:
                raise RuntimeError(
                    "scene reset has no canonical runtime root for "
                    f"service alias {service_name!r}"
                )
            aliases.append((service_name, roots[runtime_name]))
        return cls(service=service, aliases=tuple(aliases))

    def restore(self) -> None:
        for name, expected in self.aliases:
            _set_raw_attribute(self.service, name, expected)

    def verify(self) -> None:
        for name, expected in self.aliases:
            if _raw_attribute(self.service, name) is not expected:
                raise RuntimeError(
                    f"scene reset changed service alias {name!r}"
                )


@dataclass(frozen=True, slots=True)
class _PreResetAuthority:
    scene: object
    scene_root: _RawCanvasSceneRoot | None
    model: object
    selection_info: SelectionInfoState
    selection_callback: Callable[[str, str], None] | None
    services: Any
    history_service: object
    document_state: dict | None
    owned: _ResetOwnedAuthoritySnapshot
    service_aliases: _ResetServiceAliasSnapshot


@dataclass(frozen=True, slots=True)
class _RawHistoryAuthoritySnapshot:
    """Callback-free savepoint used before public history ports are entered."""

    service_namespace: dict
    state_name: str
    state: object
    state_namespace: dict
    history_name: str
    redo_name: str
    history: list
    redo_stack: list
    history_items: tuple
    redo_items: tuple
    policy: tuple[tuple[str, str | None, object], ...]

    @classmethod
    def capture(cls, service: object) -> _RawHistoryAuthoritySnapshot | None:
        try:
            service_namespace = object.__getattribute__(service, "__dict__")
        except (AttributeError, TypeError):
            return None
        if not isinstance(service_namespace, dict):
            return None

        candidates: list[tuple[str, object, dict, str, str, list, list]] = []
        for state_name, state in tuple(dict.items(service_namespace)):
            try:
                state_namespace = object.__getattribute__(state, "__dict__")
            except (AttributeError, TypeError):
                continue
            if not isinstance(state_namespace, dict):
                continue
            history_roots = tuple(
                (name, value)
                for name in ("history", "_history")
                if isinstance(
                    value := dict.get(
                        state_namespace,
                        name,
                        _MISSING_ATTRIBUTE,
                    ),
                    list,
                )
            )
            redo_roots = tuple(
                (name, value)
                for name in ("redo_stack", "_redo_stack")
                if isinstance(
                    value := dict.get(
                        state_namespace,
                        name,
                        _MISSING_ATTRIBUTE,
                    ),
                    list,
                )
            )
            for history_name, history in history_roots:
                for redo_name, redo_stack in redo_roots:
                    if history is redo_stack:
                        continue
                    candidates.append(
                        (
                            state_name,
                            state,
                            state_namespace,
                            history_name,
                            redo_name,
                            history,
                            redo_stack,
                        )
                    )
        if not candidates:
            return None

        candidate_groups: dict[
            tuple[int, int, int],
            list[tuple[str, object, dict, str, str, list, list]],
        ] = {}
        for candidate in candidates:
            _name, state, _namespace, _history_name, _redo_name, history, redo = (
                candidate
            )
            candidate_groups.setdefault(
                (id(state), id(history), id(redo)),
                [],
            ).append(candidate)
        if len(candidate_groups) != 1:
            raise RuntimeError(
                "ambiguous callback-free scene-reset history stack backings"
            )

        equivalent_candidates = next(iter(candidate_groups.values()))
        equivalent_candidates.sort(
            key=lambda value: (
                value[0] != "state",
                value[3] != "history",
                value[4] != "redo_stack",
            )
        )
        (
            state_name,
            state,
            state_namespace,
            history_name,
            redo_name,
            history,
            redo_stack,
        ) = equivalent_candidates[0]

        policy: list[tuple[str, str | None, object]] = []
        for public_name in ("enabled", "limit"):
            policy_roots = tuple(
                (storage_name, dict.__getitem__(state_namespace, storage_name))
                for storage_name in (public_name, f"_{public_name}")
                if storage_name in state_namespace
            )
            if len(policy_roots) > 1:
                raise RuntimeError(
                    "ambiguous callback-free scene-reset history policy "
                    f"backing {public_name!r}"
                )
            if not policy_roots:
                policy.append((public_name, None, _MISSING_ATTRIBUTE))
                continue
            storage_name, value = policy_roots[0]
            policy.append((public_name, storage_name, value))

        return cls(
            service_namespace=service_namespace,
            state_name=state_name,
            state=state,
            state_namespace=state_namespace,
            history_name=history_name,
            redo_name=redo_name,
            history=history,
            redo_stack=redo_stack,
            history_items=tuple(list.__iter__(history)),
            redo_items=tuple(list.__iter__(redo_stack)),
            policy=tuple(policy),
        )

    @staticmethod
    def _same_items(actual: list, expected: tuple) -> bool:
        values = tuple(list.__iter__(actual))
        return len(values) == len(expected) and all(
            value is expected_value
            for value, expected_value in zip(values, expected, strict=True)
        )

    @staticmethod
    def _same_snapshot_items(actual: tuple, expected: tuple) -> bool:
        return len(actual) == len(expected) and all(
            value is expected_value
            for value, expected_value in zip(actual, expected, strict=True)
        )

    def _restore_roots_and_policy(self) -> None:
        dict.__setitem__(self.service_namespace, self.state_name, self.state)
        dict.__setitem__(self.state_namespace, self.history_name, self.history)
        dict.__setitem__(self.state_namespace, self.redo_name, self.redo_stack)
        for public_name, storage_name, value in self.policy:
            for candidate_name in (public_name, f"_{public_name}"):
                if candidate_name != storage_name:
                    self.state_namespace.pop(candidate_name, None)
            if storage_name is not None:
                dict.__setitem__(self.state_namespace, storage_name, value)

    def restore(self) -> None:
        self._restore_roots_and_policy()
        list.__setitem__(self.history, slice(None), self.history_items)
        list.__setitem__(self.redo_stack, slice(None), self.redo_items)
        self._restore_roots_and_policy()
        self.verify(empty=False)

    def discard(self) -> None:
        self._restore_roots_and_policy()
        list.__setitem__(self.history, slice(None), ())
        list.__setitem__(self.redo_stack, slice(None), ())
        self._restore_roots_and_policy()
        self.verify(empty=True)

    def matches_snapshot(
        self,
        snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
    ) -> bool:
        """Compare live captures with the callback-free preflight authority."""

        try:
            self.verify(empty=False)
        except BaseException:
            return False
        if not (
            snapshot is not None
            and snapshot.state is self.state
            and snapshot.history is self.history
            and snapshot.redo_stack is self.redo_stack
            and self._same_snapshot_items(
                snapshot.history_items,
                self.history_items,
            )
            and self._same_snapshot_items(
                snapshot.redo_items,
                self.redo_items,
            )
        ):
            return False

        captured_policy = (
            () if policy_snapshot is None else policy_snapshot.ports
        )
        captured_by_name = {port.name: port.value for port in captured_policy}
        if len(captured_by_name) != len(captured_policy):
            return False
        for public_name, storage_name, expected in self.policy:
            if storage_name is not None:
                if public_name not in captured_by_name or not _authority_leaf_matches(
                    captured_by_name[public_name],
                    expected,
                ):
                    return False
            elif public_name in captured_by_name:
                return False
        return len(captured_by_name) == sum(
            1 for _name, storage_name, _value in self.policy
            if storage_name is not None
        )

    def verify(self, *, empty: bool) -> None:
        if dict.get(self.service_namespace, self.state_name) is not self.state:
            raise RuntimeError("scene reset changed the raw history-state root")
        if dict.get(self.state_namespace, self.history_name) is not self.history:
            raise RuntimeError("scene reset changed the raw undo-list root")
        if dict.get(self.state_namespace, self.redo_name) is not self.redo_stack:
            raise RuntimeError("scene reset changed the raw redo-list root")
        expected_history = () if empty else self.history_items
        expected_redo = () if empty else self.redo_items
        if not self._same_items(self.history, expected_history):
            raise RuntimeError("scene reset changed raw undo-list contents")
        if not self._same_items(self.redo_stack, expected_redo):
            raise RuntimeError("scene reset changed raw redo-list contents")
        for public_name, storage_name, expected in self.policy:
            raw_roots = tuple(
                (candidate_name, dict.__getitem__(self.state_namespace, candidate_name))
                for candidate_name in (public_name, f"_{public_name}")
                if candidate_name in self.state_namespace
            )
            if storage_name is None:
                exact = not raw_roots
            else:
                exact = (
                    len(raw_roots) == 1
                    and raw_roots[0][0] == storage_name
                    and _authority_leaf_matches(raw_roots[0][1], expected)
                )
            if not exact:
                raise RuntimeError(
                    f"scene reset changed raw history policy {public_name!r}"
                )


class _ResetSnapshotCanvasProxy:
    __slots__ = ("_canvas", "_scene")

    def __init__(self, canvas: object, scene: object) -> None:
        object.__setattr__(self, "_canvas", canvas)
        object.__setattr__(self, "_scene", scene)

    def scene(self) -> object:
        return self._scene

    def __getattr__(self, name: str) -> object:
        return getattr(self._canvas, name)

    def __setattr__(self, name: str, value: object) -> None:
        setattr(self._canvas, name, value)


class CanvasSceneResetService:
    def __init__(self, canvas, *, hit_testing_service) -> None:
        self.canvas = canvas
        self.hit_testing_service = hit_testing_service
        self.graph = graph_state_for(canvas)
        self.rotation = rotation_state_for(canvas)
        self.rotation_preview = rotation_preview_state_for(canvas)
        self.insert_state = insert_state_for(canvas)
        self.marks = mark_registry_for(canvas)
        self._empty_status_publication_active = False

    def _callback_free_scene_backing(
        self,
        scene_root: _RawCanvasSceneRoot | None = None,
    ) -> object:
        """Return one conventional raw scene root without crossing a getter."""

        authority = scene_root or _RawCanvasSceneRoot.capture(self.canvas)
        return authority.scene if authority is not None else _MISSING_ATTRIBUTE

    def _capture_scene_root_and_qt_items(
        self,
        scene_root: _RawCanvasSceneRoot | None = None,
    ) -> tuple[object, tuple[QGraphicsItem, ...] | None]:
        scene: object | None
        if isinstance(self.canvas, QGraphicsView):
            scene = QGraphicsView.scene(self.canvas)
        else:
            raw_scene = self._callback_free_scene_backing(scene_root)
            if raw_scene is not _MISSING_ATTRIBUTE:
                scene = raw_scene
            else:
                scene_method = _capture_optional_callable(self.canvas, "scene")
                if scene_method is None:
                    raise AttributeError("canvas has no callable scene accessor")
                scene = scene_method()
        if scene is None:
            raise RuntimeError("canvas scene accessor returned no scene")
        qt_items_before_clear = (
            tuple(QGraphicsScene.items(scene))
            if isinstance(scene, QGraphicsScene)
            else None
        )
        return scene, qt_items_before_clear

    def _capture_preflight_recovery_ports(
        self,
        scene: object,
        qt_items_before_clear: tuple[QGraphicsItem, ...] | None,
    ) -> _GraphicsSceneClearPorts | None:
        qt_ports = self._qt_base_clear_ports(scene, qt_items_before_clear)
        if qt_ports is not None:
            return qt_ports

        # An ordinary Python method is still executable extension code.  Do not
        # call a fake scene's public ``items()`` before a recovery authority
        # exists.  Exact supported fakes keep their membership in a built-in
        # ``_items`` list; bind that storage through list's base operations so
        # later live-port capture can neither hide nor mutate membership.
        raw_items_root = _RawSceneMembershipRoot.capture(scene)

        items: Callable[[], tuple[object, ...]] | None = None
        if raw_items_root is not None:
            backing = raw_items_root.backing

            def raw_items() -> tuple[object, ...]:
                return tuple(list.__iter__(backing))

            items = raw_items
        items_before_clear = items() if items is not None else None
        clear = _capture_statically_bound_callable(scene, "clear")
        if clear is None:
            def unavailable_static_clear() -> None:
                raise RuntimeError(
                    "scene has no callback-free clear port for recovery"
                )

            clear = unavailable_static_clear
        return _GraphicsSceneClearPorts(
            scene=scene,
            clear=clear,
            clear_selection=None,
            block_signals=None,
            signals_blocked=None,
            items=items,
            items_before_clear=items_before_clear,
            add_item=_capture_statically_bound_callable(scene, "addItem"),
            remove_item=_capture_statically_bound_callable(scene, "removeItem"),
            raw_items_root=raw_items_root,
            qt_items_before_clear=None,
            qt_base_clear=None,
        )

    def _live_scene_root(
        self,
        scene_root: _RawCanvasSceneRoot | None = None,
    ) -> object:
        scene: object | None
        if isinstance(self.canvas, QGraphicsView):
            scene = QGraphicsView.scene(self.canvas)
        else:
            if scene_root is not None:
                scene_root.verify()
            raw_scene = self._callback_free_scene_backing(scene_root)
            if raw_scene is not _MISSING_ATTRIBUTE:
                scene = raw_scene
            else:
                scene_method = _capture_optional_callable(self.canvas, "scene")
                if scene_method is None:
                    raise AttributeError("canvas has no callable scene accessor")
                scene = scene_method()
        if scene is None:
            raise RuntimeError("canvas scene accessor returned no scene")
        return scene

    def _restore_live_scene_root(
        self,
        captured_scene: object,
        scene_root: _RawCanvasSceneRoot | None = None,
    ) -> None:
        # The Qt base accessor legitimately returns ``None`` after a hostile
        # publication hook detaches the scene. Do not route that state through
        # ``_live_scene_root()``, whose public-access contract rejects a missing
        # scene before the captured root can be reattached.
        if not isinstance(self.canvas, QGraphicsView) and scene_root is not None:
            cleanup_error: BaseException | None = None
            for current_scene in scene_root.current_roots():
                if current_scene is captured_scene:
                    continue
                try:
                    clear = _capture_optional_callable(current_scene, "clear")
                    if clear is not None:
                        clear()
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            scene_root.restore()
            scene_root.verify()
            if cleanup_error is not None:
                raise cleanup_error
            return

        current_scene = (
            QGraphicsView.scene(self.canvas)
            if isinstance(self.canvas, QGraphicsView)
            else self._live_scene_root()
        )
        if current_scene is captured_scene:
            return
        if isinstance(current_scene, QGraphicsScene):
            with blocked_scene_signals(
                current_scene,
                block_signals=partial(QObject.blockSignals, current_scene),
                signals_blocked=partial(QObject.signalsBlocked, current_scene),
            ):
                QGraphicsScene.clear(current_scene)
        elif current_scene is not None:
            clear = _capture_optional_callable(current_scene, "clear")
            if clear is not None:
                clear()
        if not isinstance(self.canvas, QGraphicsView):
            raise RuntimeError("scene reset cannot restore a replaced fake scene root")
        if not isinstance(captured_scene, QGraphicsScene):
            raise RuntimeError("captured Qt view scene root is not a graphics scene")
        QGraphicsView.setScene(self.canvas, captured_scene)
        if QGraphicsView.scene(self.canvas) is not captured_scene:
            raise RuntimeError("scene reset could not restore the captured scene root")

    def _capture_pre_reset_authority(
        self,
        scene: object,
        selection_info: SelectionInfoState,
        *,
        scene_root: _RawCanvasSceneRoot | None = None,
        owned: _ResetOwnedAuthoritySnapshot | None = None,
        service_aliases: _ResetServiceAliasSnapshot | None = None,
        services: object = _MISSING_ATTRIBUTE,
        history_service: object = _MISSING_ATTRIBUTE,
    ) -> _PreResetAuthority:
        owned = owned or _ResetOwnedAuthoritySnapshot.capture(self.canvas)
        service_aliases = service_aliases or _ResetServiceAliasSnapshot.capture(
            self,
            owned,
        )
        # A publication hook from an earlier reset may have replaced one of
        # these cached aliases. Rebind them to the canonical runtime roots
        # before any new reset operation can act through the stale objects.
        service_aliases.restore()
        service_aliases.verify()
        if services is _MISSING_ATTRIBUTE:
            services_value = _capture_optional_attribute(self.canvas, "services")
            services = (
                None if services_value is _MISSING_ATTRIBUTE else services_value
            )
        if history_service is _MISSING_ATTRIBUTE:
            history_value = (
                _capture_optional_attribute(services, "history_service")
                if services is not None
                else _MISSING_ATTRIBUTE
            )
            history_service = (
                None if history_value is _MISSING_ATTRIBUTE else history_value
            )
        model = owned.model if owned.model_present else _MISSING_ATTRIBUTE
        return _PreResetAuthority(
            scene=scene,
            scene_root=(
                scene_root
                if scene_root is not None or isinstance(self.canvas, QGraphicsView)
                else _RawCanvasSceneRoot.capture(self.canvas)
            ),
            model=model,
            selection_info=selection_info,
            selection_callback=cast(
                Callable[[str, str], None] | None,
                _raw_attribute(selection_info, "callback"),
            ),
            services=services,
            history_service=history_service,
            # Live item serialization is a separate fallible pre-clear phase.
            # Publishing the callback-free roots first lets that phase restore
            # exact state or converge on a conservative empty reset.
            document_state=None,
            owned=owned,
            service_aliases=service_aliases,
        )

    def _capture_pre_reset_document_state(
        self,
        authority: _PreResetAuthority,
    ) -> _PreResetAuthority:
        if not isinstance(authority.scene, QGraphicsScene) or not isinstance(
            authority.model,
            MoleculeModel,
        ):
            return authority
        proxy = _ResetSnapshotCanvasProxy(self.canvas, authority.scene)
        return replace(
            authority,
            document_state=snapshot_canvas_document_state(proxy),
        )

    def _restore_live_authority_roots(
        self,
        authority: _PreResetAuthority,
        owned: _ResetOwnedAuthoritySnapshot,
        *,
        restore_contents: bool = True,
    ) -> None:
        self._restore_live_scene_root(authority.scene, authority.scene_root)
        current_services = _capture_optional_attribute(self.canvas, "services")
        if (
            current_services is _MISSING_ATTRIBUTE
            or current_services is not authority.services
        ):
            self.canvas.services = authority.services
        if (
            authority.services is not None
            and _capture_optional_attribute(authority.services, "history_service")
            is not authority.history_service
        ):
            authority.services.history_service = authority.history_service
        if restore_contents:
            owned.restore(self.canvas)
        else:
            owned.restore_roots(self.canvas)
        authority.service_aliases.restore()

    def _verify_live_authority_roots(
        self,
        authority: _PreResetAuthority,
        owned: _ResetOwnedAuthoritySnapshot,
    ) -> None:
        if self._live_scene_root(authority.scene_root) is not authority.scene:
            raise RuntimeError("scene reset changed the live scene root")
        current_services = _capture_optional_attribute(self.canvas, "services")
        if (
            None if current_services is _MISSING_ATTRIBUTE else current_services
        ) is not authority.services:
            raise RuntimeError("scene reset changed the services root")
        current_history = (
            _capture_optional_attribute(authority.services, "history_service")
            if authority.services is not None
            else _MISSING_ATTRIBUTE
        )
        if (
            None if current_history is _MISSING_ATTRIBUTE else current_history
        ) is not authority.history_service:
            raise RuntimeError("scene reset changed the history service root")
        owned.verify(self.canvas)
        authority.service_aliases.verify()

    def _capture_graphics_scene_clear_ports(
        self,
        scene: object | None = None,
        qt_items_before_clear: tuple[QGraphicsItem, ...] | None = None,
        preflight_ports: _GraphicsSceneClearPorts | None = None,
    ) -> _GraphicsSceneClearPorts:
        if scene is None:
            scene, qt_items_before_clear = self._capture_scene_root_and_qt_items()

        # Reuse the callback-free Qt base or raw fake-list membership frozen by
        # preflight.  Public ``items``/``addItem``/``removeItem`` methods are
        # arbitrary extension code and are not needed on the normal reset path.
        # The direct helper path without preflight retains its sparse-fake
        # behavior for tests and narrow internal callers.
        if preflight_ports is not None:
            items = preflight_ports.items
            items_before_clear = preflight_ports.items_before_clear
            add_item = preflight_ports.add_item
            remove_item = preflight_ports.remove_item
            raw_items_root = preflight_ports.raw_items_root
        else:
            items = _capture_optional_callable(scene, "items")
            if items is None and isinstance(scene, QObject):
                raise AttributeError("canvas scene has no callable items port")
            items_before_clear = tuple(items()) if items is not None else None
            add_item = _capture_optional_callable(scene, "addItem")
            remove_item = _capture_optional_callable(scene, "removeItem")
            raw_items_root = None

        # Capture every remaining port before the first reset mutation.  In
        # particular, a fail-once descriptor must abort cleanly instead of being
        # treated as an absent optional port and then succeeding after state was
        # changed.
        clear_selection = _capture_optional_callable(scene, "clearSelection")
        clear = _capture_optional_callable(scene, "clear")
        block_signals = _capture_optional_callable(scene, "blockSignals")
        signals_blocked = (
            _capture_optional_callable(scene, "signalsBlocked")
            if block_signals is not None
            else None
        )
        if clear is None:
            raise AttributeError("canvas scene has no callable clear port")
        return _GraphicsSceneClearPorts(
            scene=scene,
            clear=clear,
            clear_selection=clear_selection,
            block_signals=block_signals,
            signals_blocked=signals_blocked,
            items=items,
            items_before_clear=items_before_clear,
            add_item=add_item,
            remove_item=remove_item,
            raw_items_root=raw_items_root,
            qt_items_before_clear=qt_items_before_clear,
            qt_base_clear=(
                partial(QGraphicsScene.clear, scene)
                if isinstance(scene, QGraphicsScene)
                else None
            ),
        )

    @staticmethod
    def _qt_scene_was_destructively_changed(
        ports: _GraphicsSceneClearPorts,
    ) -> bool:
        before = ports.qt_items_before_clear
        if before is None:
            return True
        try:
            current = tuple(QGraphicsScene.items(ports.scene))
            if len(current) != len(before) or {id(item) for item in current} != {
                id(item) for item in before
            }:
                return True
            for item in before:
                if sip.isdeleted(item) or QGraphicsItem.scene(item) is not ports.scene:
                    return True
        except BaseException:
            # An unreadable wrapper after clear entry is itself evidence that
            # recovery must not attempt to preserve pre-clear commands.
            return True
        return False

    @staticmethod
    def _scene_membership_was_changed(
        ports: _GraphicsSceneClearPorts,
    ) -> bool:
        """Compare the strongest captured scene-membership authority available."""

        if ports.qt_items_before_clear is not None:
            return CanvasSceneResetService._qt_scene_was_destructively_changed(ports)
        if ports.raw_items_root is not None and not ports.raw_items_root.is_exact():
            return True
        before = ports.items_before_clear
        if before is None:
            return False
        if ports.items is None:
            return True
        try:
            current = tuple(ports.items())
        except BaseException:
            return True
        return len(current) != len(before) or any(
            actual is not expected
            for actual, expected in zip(current, before, strict=True)
        )

    @staticmethod
    def _restore_non_qt_scene_membership(
        ports: _GraphicsSceneClearPorts,
    ) -> bool:
        """Restore an exact fake scene when it exposes reversible item ports."""

        if ports.qt_items_before_clear is not None:
            return False
        before = ports.items_before_clear
        if before is None or ports.items is None:
            return False
        if not CanvasSceneResetService._scene_membership_was_changed(ports):
            return True
        if ports.raw_items_root is not None:
            try:
                ports.raw_items_root.restore(before)
                return not CanvasSceneResetService._scene_membership_was_changed(
                    ports
                )
            except BaseException:
                return False
        if ports.add_item is None or ports.remove_item is None:
            return False
        for _attempt in range(2):
            try:
                current = tuple(ports.items())
                for item in current:
                    ports.remove_item(item)
                for item in before:
                    ports.add_item(item)
                if not CanvasSceneResetService._scene_membership_was_changed(ports):
                    return True
            except BaseException:
                continue
        return False

    @staticmethod
    def _qt_base_clear_ports(
        scene: object,
        qt_items_before_clear: tuple[QGraphicsItem, ...] | None,
    ) -> _GraphicsSceneClearPorts | None:
        if qt_items_before_clear is None or not isinstance(scene, QGraphicsScene):
            return None
        qt_base_clear = partial(QGraphicsScene.clear, scene)
        return _GraphicsSceneClearPorts(
            scene=scene,
            clear=qt_base_clear,
            clear_selection=None,
            block_signals=partial(QObject.blockSignals, scene),
            signals_blocked=partial(QObject.signalsBlocked, scene),
            items=partial(QGraphicsScene.items, scene),
            items_before_clear=tuple(qt_items_before_clear),
            add_item=partial(QGraphicsScene.addItem, scene),
            remove_item=partial(QGraphicsScene.removeItem, scene),
            raw_items_root=None,
            qt_items_before_clear=qt_items_before_clear,
            qt_base_clear=qt_base_clear,
        )

    @staticmethod
    def _qt_destructive_recovery_ports(
        ports: _GraphicsSceneClearPorts,
    ) -> _GraphicsSceneClearPorts:
        """Bypass unsafe extension ports after scene destruction is possible."""

        qt_ports = CanvasSceneResetService._qt_base_clear_ports(
            ports.scene,
            ports.qt_items_before_clear,
        )
        if qt_ports is not None:
            return qt_ports
        if ports.items_before_clear is None:
            return ports
        # Exact fake scenes have no callback-free Qt base, but once membership
        # changed, a broken signal-blocking extension must not prevent the reset
        # from converging on an empty scene. The captured clear port is the
        # narrowest remaining destructive authority; skip optional selection and
        # signal hooks during fail-closed recovery.
        return _GraphicsSceneClearPorts(
            scene=ports.scene,
            clear=ports.clear,
            clear_selection=None,
            block_signals=None,
            signals_blocked=None,
            items=ports.items,
            items_before_clear=ports.items_before_clear,
            add_item=ports.add_item,
            remove_item=ports.remove_item,
            raw_items_root=ports.raw_items_root,
            qt_items_before_clear=None,
            qt_base_clear=None,
        )

    def _pre_destructive_authorities_are_exact(
        self,
        *,
        scene_clear_ports: _GraphicsSceneClearPorts,
        authority: _PreResetAuthority,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        history_snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
    ) -> bool:
        if (
            scene_clear_ports.items_before_clear is not None
            and self._scene_membership_was_changed(scene_clear_ports)
        ):
            return False

        def callback_is_exact() -> bool:
            try:
                return _raw_attribute(selection_info, "callback") is selection_callback
            except BaseException:
                return False

        if not callback_is_exact():
            return False
        try:
            current_services = _capture_optional_attribute(self.canvas, "services")
            current_history = (
                _capture_optional_attribute(authority.services, "history_service")
                if authority.services is not None
                else _MISSING_ATTRIBUTE
            )
            if (
                self._live_scene_root(authority.scene_root) is not authority.scene
                or (
                    None if current_services is _MISSING_ATTRIBUTE else current_services
                )
                is not authority.services
                or (None if current_history is _MISSING_ATTRIBUTE else current_history)
                is not authority.history_service
                or selection_info_state_for(self.canvas) is not authority.selection_info
                or (
                    authority.document_state is not None
                    and snapshot_canvas_document_state(
                        _ResetSnapshotCanvasProxy(self.canvas, authority.scene)
                    )
                    != authority.document_state
                )
            ):
                return False
        except BaseException:
            return False
        try:
            authority.owned.verify(self.canvas)
            authority.service_aliases.verify()
        except BaseException:
            return False
        if history_snapshot is not None:
            try:
                self._verify_history_and_policy(
                    history_snapshot,
                    policy_snapshot,
                    empty=False,
                    reverse=False,
                    phase="scene reset pre-destructive verification",
                )
            except BaseException:
                return False
        # History/policy getters are extension boundaries; close again on the
        # callback-free runtime and Qt membership authorities.
        try:
            authority.owned.verify(self.canvas)
            authority.service_aliases.verify()
            return (
                callback_is_exact()
                and self._live_scene_root(authority.scene_root) is authority.scene
                and selection_info_state_for(self.canvas) is authority.selection_info
                and not (
                    scene_clear_ports.items_before_clear is not None
                    and self._scene_membership_was_changed(scene_clear_ports)
                )
            )
        except BaseException:
            return False

    @staticmethod
    def _clear_uncaptured_history_stacks(
        history_service: object,
        original_error: BaseException,
    ) -> None:
        """Best-effort callback-free discard when public capture never completed.

        A hostile ``state`` descriptor can fail before ``HistoryStackSnapshot``
        exists.  The normal service and supported fakes keep that state in an
        instance attribute (occasionally behind ``_state``); clear any directly
        reachable built-in stacks without re-entering the failing descriptor.
        """

        try:
            namespace = object.__getattribute__(history_service, "__dict__")
        except (AttributeError, TypeError):
            return
        if not isinstance(namespace, dict):
            return
        candidates: list[object] = []
        for name in ("state", "_state", "history_state"):
            if name in namespace:
                candidates.append(dict.__getitem__(namespace, name))
        seen: set[int] = set()
        for state in candidates:
            if id(state) in seen:
                continue
            seen.add(id(state))
            try:
                state_namespace = object.__getattribute__(state, "__dict__")
            except (AttributeError, TypeError):
                continue
            if not isinstance(state_namespace, dict):
                continue
            for name in ("history", "redo_stack"):
                stack = state_namespace.get(name, _MISSING_ATTRIBUTE)
                if not isinstance(stack, list):
                    continue
                try:
                    list.__setitem__(stack, slice(None), ())
                except BaseException as clear_error:
                    _add_reset_recovery_note(original_error, clear_error)

    def _recover_pre_clear_failure(
        self,
        *,
        original_error: BaseException,
        base_clear_ports: _GraphicsSceneClearPorts | None,
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        empty_model: MoleculeModel,
        history_snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        raw_history_snapshot: _RawHistoryAuthoritySnapshot | None,
        authority: _PreResetAuthority,
        phase: str,
    ) -> None:
        """Classify every fallible pre-clear boundary under one recovery gate."""

        destructive_or_unknown = False
        if base_clear_ports is not None and self._scene_membership_was_changed(
            base_clear_ports
        ):
            destructive_or_unknown = not (
                base_clear_ports.qt_items_before_clear is None
                and self._restore_non_qt_scene_membership(base_clear_ports)
            )
        if not destructive_or_unknown:
            try:
                exact_history_snapshot = history_snapshot
                exact_policy_snapshot = policy_snapshot
                if raw_history_snapshot is not None:
                    raw_history_snapshot.restore()
                    if not raw_history_snapshot.matches_snapshot(
                        history_snapshot,
                        policy_snapshot,
                    ):
                        exact_history_snapshot = None
                        exact_policy_snapshot = None
                self._close_callback_and_history_authority(
                    original_error=original_error,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=exact_history_snapshot,
                    policy_snapshot=exact_policy_snapshot,
                    discard_history=False,
                    phase=phase,
                    authority=authority,
                    owned=authority.owned,
                )
                if raw_history_snapshot is not None:
                    raw_history_snapshot.restore()
                if base_clear_ports is not None:
                    destructive_or_unknown = not (
                        self._pre_destructive_authorities_are_exact(
                            scene_clear_ports=base_clear_ports,
                            authority=authority,
                            selection_info=selection_info,
                            selection_callback=selection_callback,
                            history_snapshot=exact_history_snapshot,
                            policy_snapshot=exact_policy_snapshot,
                        )
                    )
                if (
                    not destructive_or_unknown
                    and raw_history_snapshot is not None
                ):
                    raw_history_snapshot.verify(empty=False)
            except BaseException as recovery_error:
                _add_reset_recovery_note(original_error, recovery_error)
                destructive_or_unknown = base_clear_ports is not None
        if not destructive_or_unknown:
            return

        assert base_clear_ports is not None
        if history_snapshot is None:
            for _attempt in range(2):
                try:
                    history_snapshot = HistoryStackSnapshot.capture(
                        authority.history_service
                    )
                except BaseException as capture_error:
                    _add_reset_recovery_note(original_error, capture_error)
                    continue
                break
        if history_snapshot is not None and policy_snapshot is None:
            for _attempt in range(2):
                try:
                    policy_snapshot = RecordingHistoryPolicySnapshot.capture(
                        history_snapshot
                    )
                except BaseException as capture_error:
                    _add_reset_recovery_note(original_error, capture_error)
                    continue
                break
        if history_snapshot is None:
            self._clear_uncaptured_history_stacks(
                authority.history_service,
                original_error,
            )
        self._finish_failed_clear_consistently(
            original_error=original_error,
            scene_clear_ports=base_clear_ports,
            selection_style=selection_style,
            selection_info=selection_info,
            selection_callback=selection_callback,
            empty_model=empty_model,
            history_snapshot=history_snapshot,
            policy_snapshot=policy_snapshot,
            authority=authority,
        )
        if raw_history_snapshot is not None:
            raw_history_snapshot.discard()

    def _clear_graphics_scene_without_callbacks(
        self,
        ports: _GraphicsSceneClearPorts | None = None,
        *,
        mark_destructive_started: Callable[[], None] | None = None,
        mark_clear_invoked: Callable[[], None] | None = None,
    ) -> None:
        ports = ports or self._capture_graphics_scene_clear_ports()

        def clear_scene_root() -> None:
            is_qt_scene = ports.qt_items_before_clear is not None
            if not is_qt_scene and mark_destructive_started is not None:
                mark_destructive_started()
            if mark_clear_invoked is not None:
                mark_clear_invoked()
            try:
                ports.clear()
            except BaseException:
                if (
                    is_qt_scene
                    and mark_destructive_started is not None
                    and self._qt_scene_was_destructively_changed(ports)
                ):
                    mark_destructive_started()
                raise
            if is_qt_scene and mark_destructive_started is not None:
                mark_destructive_started()

        if ports.block_signals is None:
            clear_scene_root()
            if (
                ports.clear_selection is not None
                and ports.qt_items_before_clear is None
            ):
                ports.clear_selection()
            return
        with blocked_scene_signals(
            ports.scene,
            block_signals=ports.block_signals,
            signals_blocked=ports.signals_blocked,
        ):
            clear_scene_root()
            if (
                ports.clear_selection is not None
                and ports.qt_items_before_clear is None
            ):
                ports.clear_selection()

    @staticmethod
    def _clear_selection_runtime_state(
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
    ) -> Callable[[str, str], None] | None:
        selection_callback = selection_info.callback
        selection_style.selected_items.clear()
        selection_style.suspend_outline = False
        selection_info.signature = None
        selection_info.pending_signature = None
        selection_info.cache = ("", "")
        selection_info.rdkit_warmup_pending = False
        return selection_callback

    @staticmethod
    def _set_selection_callback_verified(
        selection_info: SelectionInfoState,
        callback: Callable[[str, str], None] | None,
    ) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                selection_info.callback = callback
                if selection_info.callback is not callback:
                    raise RuntimeError(
                        "selection callback setter did not restore identity"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "scene reset could not set the selection callback authority",
            errors,
        )

    def _apply_clear_without_publication(
        self,
        scene_clear_ports: _GraphicsSceneClearPorts,
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
        *,
        empty_model: MoleculeModel | None = None,
        silent_reassert: bool = False,
        mark_destructive_started: Callable[[], None] | None = None,
        mark_clear_invoked: Callable[[], None] | None = None,
    ) -> MoleculeModel:
        # There must be no reset mutation before this call. Signal-block entry
        # can still fail safely while the old scene and all runtime roots are
        # intact; once ``clear`` begins, recovery must converge on an empty
        # canvas because Qt may already have destroyed C++ item wrappers.
        self._clear_graphics_scene_without_callbacks(
            scene_clear_ports,
            mark_destructive_started=mark_destructive_started,
            mark_clear_invoked=mark_clear_invoked,
        )
        if not silent_reassert:
            self._set_selection_callback_verified(selection_info, None)
        self._clear_selection_runtime_state(
            selection_style,
            selection_info,
        )
        clear_selection_outlines_for(self.canvas)
        set_active_handles_for(self.canvas, [])
        set_handle_target_for(self.canvas, None)
        # A preview group owns references to graphics from the current model.
        # Scene signals were blocked and dropped during destruction; discard
        # the stale wrapper graph immediately after the destructive boundary.
        self.rotation_preview.reset()
        set_hover_items_for(self.canvas, [])
        set_hover_atom_id_for(self.canvas, None)
        set_hover_bond_id_for(self.canvas, None)
        target_model = empty_model if empty_model is not None else MoleculeModel()
        if empty_model is not None:
            target_model.atoms.clear()
            target_model.bonds.clear()
            target_model.next_atom_id = 0
            target_model.atom_annotations.clear()
        set_model_for(self.canvas, target_model)
        if silent_reassert:
            mark_spatial_index_dirty_for(self.canvas)
        else:
            self.hit_testing_service.mark_spatial_index_dirty()
        clear_atom_coords_3d_for(self.canvas)
        self.rotation.reset_all()
        clear_atom_graphics_for(self.canvas)
        self.graph.reset()
        clear_bond_graphics_for(self.canvas)
        clear_scene_item_collections_for(self.canvas)
        clear_groups_for(self.canvas)
        self.marks.clear()
        if not silent_reassert:
            clear_template_preview_for(self.canvas)
            clear_benzene_preview_for(self.canvas)
            clear_smiles_preview_for(self.canvas)
            apply_insert_session_state_for(self.canvas, clear_insert_session())
        self._clear_insert_runtime_directly()
        return target_model

    def _clear_insert_runtime_directly(self) -> None:
        state = self.insert_state
        state.smiles_active = False
        state.smiles_preview_model = None
        state.smiles_preview_items.clear()
        state.smiles_preview_bond_items.clear()
        state.smiles_preview_atom_items.clear()
        state.smiles_preview_center = None
        state.smiles_preview_smiles = None
        state.template_active = False
        state.template_ring_size = None
        state.template_ring_style = None
        state.template_preview_items.clear()
        state.template_preview_lines.clear()
        state.template_preview_dots.clear()
        state.benzene_preview_items.clear()

    @staticmethod
    def _raw_history_matches(
        snapshot: HistoryStackSnapshot,
        *,
        empty: bool,
    ) -> bool:
        if _raw_attribute(snapshot.service, "state") is not snapshot.state:
            return False
        if _raw_attribute(snapshot.state, "history") is not snapshot.history:
            return False
        if _raw_attribute(snapshot.state, "redo_stack") is not snapshot.redo_stack:
            return False
        expected_history = () if empty else snapshot.history_items
        expected_redo = () if empty else snapshot.redo_items
        actual_history = tuple(list.__iter__(snapshot.history))
        actual_redo = tuple(list.__iter__(snapshot.redo_stack))
        return (
            len(actual_history) == len(expected_history)
            and all(
                actual is expected
                for actual, expected in zip(
                    actual_history,
                    expected_history,
                    strict=True,
                )
            )
            and len(actual_redo) == len(expected_redo)
            and all(
                actual is expected
                for actual, expected in zip(
                    actual_redo,
                    expected_redo,
                    strict=True,
                )
            )
        )

    @staticmethod
    def _empty_captured_history_once(
        snapshot: HistoryStackSnapshot,
        *,
        reverse: bool,
    ) -> None:
        snapshot.state_port.apply_once()
        stack_ports = (
            (snapshot.redo_port, snapshot.history_port)
            if reverse
            else (snapshot.history_port, snapshot.redo_port)
        )
        for port in stack_ports:
            port.setter(port.value)
            port.replace_items(slice(None), ())

    @staticmethod
    def _restore_history_and_policy_once(
        *,
        original_error: BaseException,
        history_snapshot: HistoryStackSnapshot,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        discard_history: bool,
        phase: str,
        reverse: bool,
    ) -> None:
        if reverse and policy_snapshot is not None:
            policy_snapshot.restore_once(reverse=True)
        if discard_history:
            CanvasSceneResetService._empty_captured_history_once(
                history_snapshot,
                reverse=reverse,
            )
        elif not history_snapshot.restore_silently(
            original_error,
            phase=phase,
        ):
            raise RuntimeError(f"{phase} could not restore history authority")
        if not reverse and policy_snapshot is not None:
            policy_snapshot.restore_once()

    @staticmethod
    def _verify_history_and_policy(
        history_snapshot: HistoryStackSnapshot,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        *,
        empty: bool,
        reverse: bool,
        phase: str,
    ) -> None:
        def verify_stacks() -> None:
            if not CanvasSceneResetService._raw_history_matches(
                history_snapshot,
                empty=empty,
            ):
                raise RuntimeError(f"{phase} did not close history roots and contents")

        verify_stacks()
        if policy_snapshot is None:
            return
        policy_snapshot.verify(reverse=reverse)
        # Policy getters are extension boundaries and can rewrite stack roots.
        # Close verification on the captured raw lists and identities again.
        verify_stacks()

    def _close_callback_and_history_authority(
        self,
        *,
        original_error: BaseException,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        history_snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        discard_history: bool,
        phase: str,
        authority: _PreResetAuthority,
        owned: _ResetOwnedAuthoritySnapshot,
    ) -> None:
        errors: list[BaseException] = []
        for attempt in range(2):
            try:
                reverse = bool(attempt)
                self._restore_live_authority_roots(authority, owned)

                def restore_callback() -> None:
                    self._set_selection_callback_verified(
                        selection_info,
                        selection_callback,
                    )

                def restore_history(_reverse: bool = reverse) -> None:
                    if history_snapshot is None:
                        return
                    self._restore_history_and_policy_once(
                        original_error=original_error,
                        history_snapshot=history_snapshot,
                        policy_snapshot=policy_snapshot,
                        discard_history=discard_history,
                        phase=phase,
                        reverse=_reverse,
                    )

                def verify_callback() -> None:
                    if (
                        _raw_attribute(selection_info, "callback")
                        is not selection_callback
                    ):
                        raise RuntimeError(f"{phase} did not restore callback identity")

                def verify_history(_reverse: bool = reverse) -> None:
                    if history_snapshot is None:
                        return
                    self._verify_history_and_policy(
                        history_snapshot,
                        policy_snapshot,
                        empty=discard_history,
                        reverse=_reverse,
                        phase=phase,
                    )

                if not reverse:
                    # Callback setters can poison history; history is final.
                    restore_callback()
                    restore_history()
                    self._restore_live_authority_roots(authority, owned)
                    verify_callback()
                    verify_history()
                    self._verify_live_authority_roots(authority, owned)
                else:
                    # History setters can poison callbacks; callback is final.
                    restore_history()
                    restore_callback()
                    self._restore_live_authority_roots(authority, owned)
                    verify_history()
                    verify_callback()
                    self._verify_live_authority_roots(authority, owned)
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            f"{phase} callback/history authority did not converge",
            errors,
        )

    def _verify_clear_authorities(
        self,
        *,
        scene_clear_ports: _GraphicsSceneClearPorts,
        empty_model: MoleculeModel,
        empty_document_state: dict,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        history_snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        history_first: bool = False,
        history_must_be_empty: bool = False,
        authority: _PreResetAuthority | None = None,
        owned: _ResetOwnedAuthoritySnapshot | None = None,
    ) -> None:
        def verify_history() -> None:
            if history_snapshot is None:
                return
            if not history_must_be_empty and not history_snapshot.is_exact():
                raise RuntimeError("scene reset history was re-mutated")
            self._verify_history_and_policy(
                history_snapshot,
                policy_snapshot,
                empty=history_must_be_empty,
                reverse=history_first,
                phase="scene reset verification",
            )

        def verify_document() -> None:
            snapshot_proxy = _ResetSnapshotCanvasProxy(
                self.canvas,
                scene_clear_ports.scene,
            )
            if snapshot_canvas_document_state(snapshot_proxy) != empty_document_state:
                raise RuntimeError("scene reset document state was re-mutated")

        def verify_scene() -> None:
            if (
                authority is not None
                and self._live_scene_root(authority.scene_root) is not authority.scene
            ):
                raise RuntimeError("scene reset changed the live scene root")
            raw_items_root = scene_clear_ports.raw_items_root
            if raw_items_root is not None:
                if not raw_items_root.is_exact():
                    raise RuntimeError(
                        "scene reset changed the callback-free scene membership root"
                    )
                if tuple(list.__iter__(raw_items_root.backing)):
                    raise RuntimeError(
                        "scene reset left graphics items in the live raw membership root"
                    )
                return
            if scene_clear_ports.items is None:
                return
            scene = scene_clear_ports.scene
            # A Python QGraphicsScene subclass can override ``items`` and return
            # an empty sequence while re-populating another reset authority.
            # Production scenes therefore close on Qt's base implementation.
            current_items = (
                tuple(QGraphicsScene.items(scene))
                if isinstance(scene, QGraphicsScene)
                else tuple(scene_clear_ports.items())
            )
            if current_items:
                raise RuntimeError("scene reset left graphics items behind")

        def verify_model_callback_free() -> None:
            try:
                namespace = object.__getattribute__(self.canvas, "__dict__")
            except BaseException:
                current_model = object.__getattribute__(self.canvas, "model")
            else:
                current_model = (
                    dict.__getitem__(namespace, "model")
                    if isinstance(namespace, dict) and "model" in namespace
                    else object.__getattribute__(self.canvas, "model")
                )
            if current_model is not empty_model:
                raise RuntimeError("scene reset model identity was re-mutated")

        def verify_callback_identity() -> None:
            if authority is not None:
                current_services = _capture_optional_attribute(self.canvas, "services")
                if (
                    None if current_services is _MISSING_ATTRIBUTE else current_services
                ) is not authority.services:
                    raise RuntimeError("scene reset changed the services root")
                current_history = (
                    _capture_optional_attribute(authority.services, "history_service")
                    if authority.services is not None
                    else _MISSING_ATTRIBUTE
                )
                if (
                    None if current_history is _MISSING_ATTRIBUTE else current_history
                ) is not authority.history_service:
                    raise RuntimeError("scene reset changed the history service root")
                if selection_info_state_for(self.canvas) is not selection_info:
                    raise RuntimeError("scene reset changed selection-info root")
            current_callback = object.__getattribute__(selection_info, "callback")
            if current_callback is not selection_callback:
                raise RuntimeError("scene reset changed selection callback identity")

        def verify_owned_authority() -> None:
            if authority is None or owned is None:
                return
            self._verify_live_authority_roots(authority, owned)

        if not history_first:
            verify_owned_authority()
            verify_model_callback_free()
            verify_scene()
            verify_callback_identity()
            verify_document()
            verify_history()
            return

        # Reverse the independent authorities after the forward sweep.  History
        # list iterators/config getters are observer-controlled and may return
        # exact values while re-mutating the just-cleared canvas.  Run them
        # first, then close on the document and callback-free Qt/model roots;
        # another history read must not be the final operation.
        verify_history()
        verify_document()
        verify_callback_identity()
        verify_scene()
        verify_model_callback_free()
        verify_owned_authority()

    def _finish_failed_clear_consistently(
        self,
        *,
        original_error: BaseException,
        scene_clear_ports: _GraphicsSceneClearPorts,
        selection_style: SelectionStyleState,
        selection_info: SelectionInfoState,
        selection_callback: Callable[[str, str], None] | None,
        empty_model: MoleculeModel,
        history_snapshot: HistoryStackSnapshot | None,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
        authority: _PreResetAuthority,
    ) -> None:
        """Finish an irreversible scene clear after a mid-apply failure.

        Once ``QGraphicsScene.clear`` has run, its C++ items cannot be safely
        reattached. The only authoritative failure state is therefore the same
        fully empty canvas the operation was producing, with history and the
        callback root restored exactly.
        """

        recovery_ports = self._qt_destructive_recovery_ports(scene_clear_ports)
        recovery_errors: list[BaseException] = []
        last_empty_owned: _ResetOwnedAuthoritySnapshot | None = None
        for _attempt in range(2):
            try:
                self._restore_live_authority_roots(
                    authority,
                    authority.owned,
                    restore_contents=False,
                )
                _set_raw_attribute(self.canvas, "model", empty_model)
                self._apply_clear_without_publication(
                    recovery_ports,
                    selection_style,
                    selection_info,
                    empty_model=empty_model,
                    silent_reassert=True,
                )
                if recovery_ports.raw_items_root is not None:
                    # A hostile fake ``clear`` can empty the captured list and
                    # then publish a replacement ``_items`` root containing new
                    # members.  Make the captured callback-free list the final
                    # canonical empty membership authority before freezing the
                    # recovered runtime.
                    recovery_ports.raw_items_root.restore(())
                last_empty_owned = _ResetOwnedAuthoritySnapshot.capture(self.canvas)
                self._close_callback_and_history_authority(
                    original_error=original_error,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    discard_history=True,
                    phase="failed destructive scene reset",
                    authority=authority,
                    owned=last_empty_owned,
                )
                snapshot_proxy = _ResetSnapshotCanvasProxy(
                    self.canvas,
                    recovery_ports.scene,
                )
                empty_document_state = snapshot_canvas_document_state(snapshot_proxy)
                self._verify_clear_authorities(
                    scene_clear_ports=recovery_ports,
                    empty_model=empty_model,
                    empty_document_state=empty_document_state,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    history_first=True,
                    history_must_be_empty=True,
                    authority=authority,
                    owned=last_empty_owned,
                )
            except BaseException as recovery_error:
                recovery_errors.append(recovery_error)
                continue
            return

        # Preserve the operation's primary exception, but make every failed
        # attempt discoverable without allowing diagnostic hooks to skip a
        # final callback-root repair.
        for recorded_error in recovery_errors:
            _add_reset_recovery_note(original_error, recorded_error)
        if last_empty_owned is None:
            try:
                self._restore_live_authority_roots(
                    authority,
                    authority.owned,
                    restore_contents=False,
                )
                _set_raw_attribute(self.canvas, "model", empty_model)
                last_empty_owned = _ResetOwnedAuthoritySnapshot.capture(self.canvas)
            except BaseException as snapshot_error:
                _add_reset_recovery_note(original_error, snapshot_error)
        try:
            if last_empty_owned is None:
                return
            self._close_callback_and_history_authority(
                original_error=original_error,
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
                policy_snapshot=policy_snapshot,
                discard_history=True,
                phase="final failed destructive scene reset",
                authority=authority,
                owned=last_empty_owned,
            )
        except BaseException as final_recovery_error:
            _add_reset_recovery_note(original_error, final_recovery_error)

    def clear_scene(self) -> None:  # noqa: C901
        # Freeze every callback-free runtime/history root before resolving a
        # live non-Qt ``scene`` port. A successful getter is still extension
        # code and must not be allowed to redefine the reset baseline.
        selection_style = selection_style_state_for(self.canvas)
        selection_info = selection_info_state_for(self.canvas)
        selection_callback = cast(
            Callable[[str, str], None] | None,
            _raw_attribute(selection_info, "callback"),
        )
        pre_scene_owned = _ResetOwnedAuthoritySnapshot.capture(self.canvas)
        pre_scene_aliases = _ResetServiceAliasSnapshot.capture(
            self,
            pre_scene_owned,
        )
        pre_scene_aliases.restore()
        pre_scene_aliases.verify()
        services_present, services_value = _raw_optional_attribute(
            self.canvas,
            "services",
        )
        services = services_value if services_present else None
        history_present, history_value = (
            _raw_optional_attribute(services, "history_service")
            if services is not None
            else (False, _MISSING_ATTRIBUTE)
        )
        history_service = history_value if history_present else None
        raw_history_snapshot = _RawHistoryAuthoritySnapshot.capture(
            history_service
        )
        empty_model = MoleculeModel()
        history_snapshot: HistoryStackSnapshot | None = None
        policy_snapshot: RecordingHistoryPolicySnapshot | None = None

        def restore_pre_scene_authorities(original_error: BaseException) -> None:
            try:
                pre_scene_owned.restore(self.canvas)
                if services_present:
                    _set_raw_attribute(self.canvas, "services", services)
                else:
                    _delete_raw_attribute(self.canvas, "services")
                if services is not None:
                    if history_present:
                        _set_raw_attribute(
                            services,
                            "history_service",
                            history_service,
                        )
                    else:
                        _delete_raw_attribute(services, "history_service")
                pre_scene_aliases.restore()
                if raw_history_snapshot is not None:
                    raw_history_snapshot.restore()
                pre_scene_owned.restore(self.canvas)
                pre_scene_aliases.restore()
            except BaseException as recovery_error:
                _add_reset_recovery_note(original_error, recovery_error)

        def verify_pre_scene_authorities() -> None:
            current_services_present, current_services = _raw_optional_attribute(
                self.canvas,
                "services",
            )
            if current_services_present is not services_present or (
                services_present and current_services is not services
            ):
                raise RuntimeError("scene getter changed the services root")
            if services is not None:
                current_history_present, current_history = _raw_optional_attribute(
                    services,
                    "history_service",
                )
                if current_history_present is not history_present or (
                    history_present and current_history is not history_service
                ):
                    raise RuntimeError(
                        "scene getter changed the history-service root"
                    )
            pre_scene_owned.verify(self.canvas)
            pre_scene_aliases.verify()
            if raw_history_snapshot is not None:
                raw_history_snapshot.verify(empty=False)

        try:
            scene_root = (
                None
                if isinstance(self.canvas, QGraphicsView)
                else _RawCanvasSceneRoot.capture(self.canvas)
            )
            scene, qt_items_before_clear = self._capture_scene_root_and_qt_items(
                scene_root
            )
            base_clear_ports = self._capture_preflight_recovery_ports(
                scene,
                qt_items_before_clear,
            )
        except BaseException as original_error:
            restore_pre_scene_authorities(original_error)
            raise

        authority = _PreResetAuthority(
            scene=scene,
            scene_root=scene_root,
            model=(
                pre_scene_owned.model
                if pre_scene_owned.model_present
                else _MISSING_ATTRIBUTE
            ),
            selection_info=selection_info,
            selection_callback=selection_callback,
            services=services,
            history_service=history_service,
            document_state=None,
            owned=pre_scene_owned,
            service_aliases=pre_scene_aliases,
        )

        try:
            verify_pre_scene_authorities()
        except BaseException as scene_capture_error:
            try:
                self._recover_pre_clear_failure(
                    original_error=scene_capture_error,
                    base_clear_ports=base_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=None,
                    policy_snapshot=None,
                    raw_history_snapshot=raw_history_snapshot,
                    authority=authority,
                    phase="scene reset scene-getter contamination",
                )
            except BaseException as recovery_error:
                _add_reset_recovery_note(scene_capture_error, recovery_error)
            raise RuntimeError(
                "scene reset scene getter changed a preflight authority"
            ) from scene_capture_error

        try:
            authority = self._capture_pre_reset_document_state(authority)
        except BaseException as original_error:
            try:
                self._recover_pre_clear_failure(
                    original_error=original_error,
                    base_clear_ports=base_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=None,
                    policy_snapshot=None,
                    raw_history_snapshot=raw_history_snapshot,
                    authority=authority,
                    phase="scene reset document preflight failure",
                )
            except BaseException as recovery_error:
                _add_reset_recovery_note(original_error, recovery_error)
            raise

        try:
            history_snapshot = HistoryStackSnapshot.capture(
                authority.history_service
            )
            policy_snapshot = (
                RecordingHistoryPolicySnapshot.capture(history_snapshot)
                if history_snapshot is not None
                else None
            )
            if raw_history_snapshot is not None and not (
                raw_history_snapshot.matches_snapshot(
                    history_snapshot,
                    policy_snapshot,
                )
            ):
                raise RuntimeError(
                    "scene reset history preflight changed callback-free authority"
                )
            if history_snapshot is not None:
                self._verify_history_and_policy(
                    history_snapshot,
                    policy_snapshot,
                    empty=False,
                    reverse=False,
                    phase="scene reset preflight",
                )
            if raw_history_snapshot is not None and not (
                raw_history_snapshot.matches_snapshot(
                    history_snapshot,
                    policy_snapshot,
                )
            ):
                raise RuntimeError(
                    "scene reset history preflight changed callback-free authority"
                )
        except BaseException as original_error:
            try:
                self._recover_pre_clear_failure(
                    original_error=original_error,
                    base_clear_ports=base_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    raw_history_snapshot=raw_history_snapshot,
                    authority=authority,
                    phase="scene reset history preflight failure",
                )
            except BaseException as recovery_error:
                _add_reset_recovery_note(original_error, recovery_error)
            raise

        try:
            scene_clear_ports = self._capture_graphics_scene_clear_ports(
                scene,
                qt_items_before_clear,
                base_clear_ports,
            )
        except BaseException as original_error:
            try:
                self._recover_pre_clear_failure(
                    original_error=original_error,
                    base_clear_ports=base_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    raw_history_snapshot=raw_history_snapshot,
                    authority=authority,
                    phase="scene reset port-capture failure",
                )
            except BaseException as recovery_error:
                _add_reset_recovery_note(original_error, recovery_error)
            raise

        if base_clear_ports is not None and not (
            self._pre_destructive_authorities_are_exact(
                scene_clear_ports=base_clear_ports,
                authority=authority,
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
                policy_snapshot=policy_snapshot,
            )
        ):
            capture_error = RuntimeError(
                "scene reset port capture changed a pre-destructive authority"
            )
            try:
                self._recover_pre_clear_failure(
                    original_error=capture_error,
                    base_clear_ports=base_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    raw_history_snapshot=raw_history_snapshot,
                    authority=authority,
                    phase="scene reset poisoned port capture",
                )
            except BaseException as recovery_error:
                _add_reset_recovery_note(capture_error, recovery_error)
            raise capture_error

        destructive_started = False
        discard_history = bool(qt_items_before_clear)

        def mark_destructive_started() -> None:
            nonlocal destructive_started
            destructive_started = True

        should_publish = callable(selection_callback) and not getattr(
            self,
            "_empty_status_publication_active",
            False,
        )

        empty_owned: _ResetOwnedAuthoritySnapshot | None = None
        try:
            empty_model = self._apply_clear_without_publication(
                scene_clear_ports,
                selection_style,
                selection_info,
                empty_model=empty_model,
                mark_destructive_started=mark_destructive_started,
            )
            empty_owned = _ResetOwnedAuthoritySnapshot.capture(self.canvas)
            self._close_callback_and_history_authority(
                original_error=RuntimeError("scene reset authority close failed"),
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
                policy_snapshot=policy_snapshot,
                discard_history=discard_history,
                phase="scene reset finalization",
                authority=authority,
                owned=empty_owned,
            )
            snapshot_proxy = _ResetSnapshotCanvasProxy(
                self.canvas,
                scene_clear_ports.scene,
            )
            empty_document_state = snapshot_canvas_document_state(snapshot_proxy)
            # Never publish empty status until the callback-free scene root is
            # both the captured identity and actually empty.
            self._verify_clear_authorities(
                scene_clear_ports=scene_clear_ports,
                empty_model=empty_model,
                empty_document_state=empty_document_state,
                selection_info=selection_info,
                selection_callback=selection_callback,
                history_snapshot=history_snapshot,
                policy_snapshot=policy_snapshot,
                history_must_be_empty=discard_history,
                authority=authority,
                owned=empty_owned,
            )
            if not should_publish:
                self._verify_clear_authorities(
                    scene_clear_ports=scene_clear_ports,
                    empty_model=empty_model,
                    empty_document_state=empty_document_state,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    history_first=True,
                    history_must_be_empty=discard_history,
                    authority=authority,
                    owned=empty_owned,
                )
        except BaseException as original_error:
            if (
                not destructive_started
                and scene_clear_ports.items_before_clear is not None
                and self._scene_membership_was_changed(scene_clear_ports)
            ):
                if not self._restore_non_qt_scene_membership(scene_clear_ports):
                    destructive_started = True
            if not destructive_started and authority.scene_root is not None:
                try:
                    authority.scene_root.verify()
                except BaseException:
                    try:
                        self._restore_live_scene_root(
                            authority.scene,
                            authority.scene_root,
                        )
                    except BaseException as scene_root_error:
                        _add_reset_recovery_note(
                            original_error,
                            scene_root_error,
                        )
            if (
                not destructive_started
                and base_clear_ports is not None
                and not self._pre_destructive_authorities_are_exact(
                    scene_clear_ports=base_clear_ports,
                    authority=authority,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                )
            ):
                destructive_started = True
            if destructive_started:
                self._finish_failed_clear_consistently(
                    original_error=original_error,
                    scene_clear_ports=scene_clear_ports,
                    selection_style=selection_style,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    empty_model=empty_model,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    authority=authority,
                )
            else:
                try:
                    self._close_callback_and_history_authority(
                        original_error=original_error,
                        selection_info=selection_info,
                        selection_callback=selection_callback,
                        history_snapshot=history_snapshot,
                        policy_snapshot=policy_snapshot,
                        discard_history=False,
                        phase="pre-destructive scene reset failure",
                        authority=authority,
                        owned=authority.owned,
                    )
                except BaseException as recovery_error:
                    _add_reset_recovery_note(original_error, recovery_error)
            raise

        if not should_publish:
            return
        assert empty_owned is not None

        publication_error: BaseException | None = None
        self._empty_status_publication_active = True
        try:
            assert selection_callback is not None
            selection_callback("", "")
        except BaseException as error:
            publication_error = error
        finally:
            self._empty_status_publication_active = False

        reassert_ports = self._qt_destructive_recovery_ports(scene_clear_ports)
        reassert_errors: list[BaseException] = []
        for attempt in range(2):
            diagnostic = RuntimeError("scene reset post-publication reassertion failed")
            try:
                self._restore_live_authority_roots(authority, empty_owned)
                self._set_selection_callback_verified(selection_info, None)
                if attempt == 0:
                    self._apply_clear_without_publication(
                        reassert_ports,
                        selection_style,
                        selection_info,
                        empty_model=empty_model,
                        silent_reassert=True,
                    )
                if attempt == 1:
                    self._apply_clear_without_publication(
                        reassert_ports,
                        selection_style,
                        selection_info,
                        empty_model=empty_model,
                        silent_reassert=True,
                    )
                self._close_callback_and_history_authority(
                    original_error=diagnostic,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    discard_history=discard_history,
                    phase="scene reset post-publication",
                    authority=authority,
                    owned=empty_owned,
                )
                self._verify_clear_authorities(
                    scene_clear_ports=reassert_ports,
                    empty_model=empty_model,
                    empty_document_state=empty_document_state,
                    selection_info=selection_info,
                    selection_callback=selection_callback,
                    history_snapshot=history_snapshot,
                    policy_snapshot=policy_snapshot,
                    history_first=True,
                    history_must_be_empty=discard_history,
                    authority=authority,
                    owned=empty_owned,
                )
            except BaseException as error:
                reassert_errors.append(error)
                continue
            break
        else:
            if publication_error is None:
                final_error: BaseException = BaseExceptionGroup(
                    "scene reset remained non-authoritative",
                    reassert_errors,
                )
            else:
                final_error = publication_error
                for reassert_error in reassert_errors:
                    try:
                        publication_error.add_note(
                            "Scene reset recovery also failed: "
                            f"{type(reassert_error).__name__}: {reassert_error}"
                        )
                    except BaseException:
                        pass
            self._finish_failed_clear_consistently(
                original_error=final_error,
                scene_clear_ports=scene_clear_ports,
                selection_style=selection_style,
                selection_info=selection_info,
                selection_callback=selection_callback,
                empty_model=empty_model,
                history_snapshot=history_snapshot,
                policy_snapshot=policy_snapshot,
                authority=authority,
            )
            raise final_error

        if publication_error is not None:
            raise publication_error


__all__ = ["CanvasSceneResetService"]
