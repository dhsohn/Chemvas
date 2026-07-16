from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass
from functools import partial
from typing import Any, Protocol, cast

from core.model import Bond
from PyQt6.QtCore import QRectF

from ui.atom_coords_access import atom_coords_3d_state_for
from ui.canvas_model_state import model_for
from ui.canvas_rotation_state import CanvasRotationState
from ui.history_commands import (
    _UNAVAILABLE_ITEM_VALUE,
    _BondPrimitiveGraphicsSnapshot,
    _graphics_item_is_deleted,
    _restore_bond_primitive_graphics_snapshots,
    _restore_scene_runtime_snapshot,
    _scene_item_topology_snapshots,
    _SceneRuntimeSnapshot,
    _SceneSelectionSnapshot,
    _verify_scene_runtime_identity,
)
from ui.scene_rect_snapshot import SceneRectSnapshot

_MISSING_ATTRIBUTE = object()
_PRIMITIVE_SETTER_GETTERS = {
    "setTransformOriginPoint": "transformOriginPoint",
    "setTransform": "transform",
    "setRotation": "rotation",
    "setScale": "scale",
    "setPos": "pos",
    "setOpacity": "opacity",
    "setZValue": "zValue",
    "setLine": "line",
    "setPath": "path",
    "setPolygon": "polygon",
    "setRect": "rect",
    "setPen": "pen",
    "setBrush": "brush",
    "setFont": "font",
    "setDefaultTextColor": "defaultTextColor",
    "setHtml": "toHtml",
    "setTextInteractionFlags": "textInteractionFlags",
}


def _values_match(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    try:
        return bool(actual == expected)
    except BaseException:
        return False


@dataclass(slots=True)
class _BoundAttributePort:
    """A capture-time attribute authority immune to later port replacement."""

    owner: object
    name: str
    present: bool
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]
    deleter: Callable[[], object] | None
    require_identity: bool = False

    @classmethod
    def capture(
        cls,
        owner: object,
        name: str,
        *,
        value: object = _MISSING_ATTRIBUTE,
        require_identity: bool = False,
    ) -> _BoundAttributePort:
        present = (
            inspect.getattr_static(owner, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        )
        if value is _MISSING_ATTRIBUTE and present:
            value = getattr(owner, name)

        try:
            namespace = object.__getattribute__(owner, "__dict__")
        except (AttributeError, TypeError):
            namespace = _MISSING_ATTRIBUTE
        descriptor = inspect.getattr_static(type(owner), name, _MISSING_ATTRIBUTE)
        descriptor_setter = (
            inspect.getattr_static(descriptor, "__set__", _MISSING_ATTRIBUTE)
            if descriptor is not _MISSING_ATTRIBUTE
            else _MISSING_ATTRIBUTE
        )
        if isinstance(namespace, dict) and (
            name in namespace or descriptor_setter is _MISSING_ATTRIBUTE
        ):
            getter = partial(dict.__getitem__, namespace, name)
            setter = partial(dict.__setitem__, namespace, name)
            deleter: Callable[[], object] | None = partial(
                dict.__delitem__,
                namespace,
                name,
            )
        elif descriptor is not _MISSING_ATTRIBUTE:
            descriptor_getter = inspect.getattr_static(
                descriptor,
                "__get__",
                _MISSING_ATTRIBUTE,
            )
            if not callable(descriptor_getter) or not callable(descriptor_setter):
                raise RuntimeError(f"attribute {name!r} has no exact restore port")
            getter = partial(descriptor_getter, descriptor, owner, type(owner))
            setter = partial(descriptor_setter, descriptor, owner)
            descriptor_deleter = inspect.getattr_static(
                descriptor,
                "__delete__",
                _MISSING_ATTRIBUTE,
            )
            deleter = (
                partial(descriptor_deleter, descriptor, owner)
                if callable(descriptor_deleter)
                else None
            )
        else:
            getattribute = inspect.getattr_static(
                type(owner),
                "__getattribute__",
                _MISSING_ATTRIBUTE,
            )
            setattribute = inspect.getattr_static(
                type(owner),
                "__setattr__",
                _MISSING_ATTRIBUTE,
            )
            delattribute = inspect.getattr_static(
                type(owner),
                "__delattr__",
                _MISSING_ATTRIBUTE,
            )
            if not callable(getattribute) or not callable(setattribute):
                raise RuntimeError(f"attribute {name!r} has no bound object ports")
            getter = partial(getattribute, owner, name)
            setter = partial(setattribute, owner, name)
            deleter = (
                partial(delattribute, owner, name) if callable(delattribute) else None
            )
        return cls(
            owner,
            name,
            present,
            value,
            getter,
            setter,
            deleter,
            require_identity,
        )

    def apply(self) -> None:
        if self.present:
            self.setter(self.value)
            return
        try:
            self.getter()
        except (AttributeError, KeyError):
            return
        if self.deleter is None:
            raise RuntimeError(f"attribute {self.name!r} cannot be removed exactly")
        self.deleter()

    def matches(self) -> bool:
        try:
            actual = self.getter()
        except (AttributeError, KeyError):
            return not self.present
        except BaseException:
            return False
        if not self.present:
            return False
        if self.require_identity:
            return actual is self.value
        return _values_match(actual, self.value)


@dataclass(slots=True)
class _MutableContainerSnapshot:
    target: object
    kind: str
    contents: tuple[Any, ...]

    def restore(self) -> None:
        if self.kind == "dict":
            target = self.target
            assert isinstance(target, dict)
            dict.clear(target)
            dict.update(target, self.contents)
        elif self.kind == "list":
            target = self.target
            assert isinstance(target, list)
            list.__setitem__(target, slice(None), self.contents)
        else:
            target = self.target
            assert isinstance(target, set)
            set.clear(target)
            set.update(target, self.contents)

    def matches(self) -> bool:
        if self.kind == "dict":
            target = self.target
            assert isinstance(target, dict)
            actual = tuple(dict.items(target))
            return len(actual) == len(self.contents) and all(
                actual_key is expected_key and actual_value is expected_value
                for (actual_key, actual_value), (expected_key, expected_value) in zip(
                    actual,
                    self.contents,
                    strict=True,
                )
            )
        if self.kind == "list":
            target = self.target
            assert isinstance(target, list)
            actual = tuple(list.__iter__(target))
            return len(actual) == len(self.contents) and all(
                actual_item is expected_item
                for actual_item, expected_item in zip(
                    actual,
                    self.contents,
                    strict=True,
                )
            )
        target = self.target
        assert isinstance(target, set)
        actual = tuple(set.__iter__(target))
        return len(actual) == len(self.contents) and all(
            any(actual_item is expected_item for actual_item in actual)
            for expected_item in self.contents
        )


class _MutableContainerGraphSnapshot:
    def __init__(self) -> None:
        self.snapshots: dict[int, _MutableContainerSnapshot] = {}
        self.immutable_seen: set[int] = set()

    def capture(self, value: object) -> None:
        if isinstance(value, dict):
            if id(value) in self.snapshots:
                return
            contents = tuple(dict.items(value))
            self.snapshots[id(value)] = _MutableContainerSnapshot(
                value,
                "dict",
                contents,
            )
            for key, item in contents:
                self.capture(key)
                self.capture(item)
            return
        if isinstance(value, list):
            if id(value) in self.snapshots:
                return
            contents = tuple(list.__iter__(value))
            self.snapshots[id(value)] = _MutableContainerSnapshot(
                value,
                "list",
                contents,
            )
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, set):
            if id(value) in self.snapshots:
                return
            contents = tuple(set.__iter__(value))
            self.snapshots[id(value)] = _MutableContainerSnapshot(
                value,
                "set",
                contents,
            )
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, tuple):
            if id(value) in self.immutable_seen:
                return
            self.immutable_seen.add(id(value))
            for item in value:
                self.capture(item)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for snapshot in self.snapshots.values():
            try:
                snapshot.restore()
            except BaseException as error:
                errors.append(error)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for snapshot in self.snapshots.values():
            try:
                if not snapshot.matches():
                    raise RuntimeError("mutable container did not match its savepoint")
            except BaseException as error:
                errors.append(error)
        return errors


@dataclass(slots=True)
class _ObjectAttributeSnapshot:
    target: object
    ports: tuple[_BoundAttributePort, ...]

    @classmethod
    def capture(
        cls,
        target: object,
        names: Sequence[str],
        containers: _MutableContainerGraphSnapshot,
    ) -> _ObjectAttributeSnapshot:
        ports: list[_BoundAttributePort] = []
        for name in names:
            if (
                inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
                is _MISSING_ATTRIBUTE
            ):
                continue
            value = getattr(target, name)
            port = _BoundAttributePort.capture(
                target,
                name,
                value=value,
                require_identity=True,
            )
            ports.append(port)
            containers.capture(value)
        return cls(target, tuple(ports))

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for port in self.ports:
            try:
                port.apply()
            except BaseException as error:
                errors.append(error)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for port in self.ports:
            try:
                if not port.matches():
                    raise RuntimeError(
                        f"field {port.name!r} did not match its savepoint"
                    )
            except BaseException as error:
                errors.append(error)
        return errors


def _optional_live_attribute(
    target: object | None,
    name: str,
    *,
    default: object = None,
) -> object:
    """Read a statically present attribute exactly once.

    ``getattr(..., default)`` and ``hasattr`` both treat an ``AttributeError``
    raised *inside* a live descriptor as if the field were absent.  Rotation
    preview capture must instead abort before mutation when a present rollback
    root is unreadable, while continuing to support lightweight fakes that
    genuinely omit optional state.
    """

    if target is None:
        return default
    if inspect.getattr_static(target, name, _MISSING_ATTRIBUTE) is _MISSING_ATTRIBUTE:
        return default
    return getattr(target, name)


def _optional_canvas_state_object(canvas: object, name: str) -> object | None:
    public_name = name[1:] if name.startswith("_") else name
    runtime_state = _optional_live_attribute(canvas, "runtime_state")
    if runtime_state is not None:
        state = _optional_live_attribute(runtime_state, public_name)
        if state is not None:
            return state
    return _optional_live_attribute(canvas, public_name)


class _RotationPreviewPorts(Protocol):
    @property
    def canvas(self) -> object: ...

    @property
    def move_controller(self) -> object | None: ...

    @property
    def rotation(self) -> CanvasRotationState: ...

    @property
    def bonds(self) -> Sequence[Bond | None]: ...

    def atom_positions(
        self,
        atom_ids: set[int],
    ) -> dict[int, tuple[float, float]]: ...


def _field_names_for_object(target: object) -> tuple[str, ...]:
    if is_dataclass(target) and not isinstance(target, type):
        return tuple(item.name for item in fields(target))
    try:
        namespace = object.__getattribute__(target, "__dict__")
    except (AttributeError, TypeError):
        namespace = _MISSING_ATTRIBUTE
    if isinstance(namespace, dict):
        return tuple(namespace)
    return tuple(
        name
        for name in ("element", "x", "y", "color", "explicit_label")
        if inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
        is not _MISSING_ATTRIBUTE
    )


def _state_root_port(
    canvas: object,
    runtime_state: object | None,
    name: str,
    value: object,
) -> _BoundAttributePort:
    for owner in (runtime_state, canvas):
        if owner is None:
            continue
        if (
            inspect.getattr_static(owner, name, _MISSING_ATTRIBUTE)
            is _MISSING_ATTRIBUTE
        ):
            continue
        candidate = getattr(owner, name)
        if candidate is value:
            return _BoundAttributePort.capture(
                owner,
                name,
                value=value,
                require_identity=True,
            )
    raise RuntimeError(f"canvas does not publish the captured {name!r} root")


@dataclass(slots=True)
class _CoreStateSnapshot:
    containers: _MutableContainerGraphSnapshot
    roots: tuple[_BoundAttributePort, ...]
    objects: tuple[_ObjectAttributeSnapshot, ...]
    rotation: CanvasRotationState
    rotation_snapshot: _ObjectAttributeSnapshot

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
    ) -> _CoreStateSnapshot:
        canvas = controller.canvas
        runtime_state = _optional_live_attribute(canvas, "runtime_state")
        containers = _MutableContainerGraphSnapshot()

        model_owner = (
            runtime_state
            if runtime_state is not None
            and inspect.getattr_static(
                runtime_state,
                "model",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
            else canvas
        )
        model_present = (
            inspect.getattr_static(
                model_owner,
                "model",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        )
        model_value = (
            cast(Any, model_owner).model if model_present else _MISSING_ATTRIBUTE
        )
        model_root = _BoundAttributePort.capture(
            model_owner,
            "model",
            value=model_value,
            require_identity=True,
        )
        model = model_for(canvas)
        if model_present and model_value is not model:
            raise RuntimeError("model root changed during rotation capture")
        model_snapshot = _ObjectAttributeSnapshot.capture(
            model,
            ("atoms",),
            containers,
        )
        atoms_port = next(
            (port for port in model_snapshot.ports if port.name == "atoms"),
            None,
        )
        if atoms_port is None or not isinstance(atoms_port.value, dict):
            raise RuntimeError("rotation preview requires an exact model atoms mapping")
        atom_snapshots = tuple(
            _ObjectAttributeSnapshot.capture(
                atom,
                _field_names_for_object(atom),
                containers,
            )
            for atom in tuple(dict.values(atoms_port.value))
        )

        coords_owner = (
            runtime_state
            if runtime_state is not None
            and inspect.getattr_static(
                runtime_state,
                "atom_coords_3d_state",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
            else canvas
        )
        coords_present = (
            inspect.getattr_static(
                coords_owner,
                "atom_coords_3d_state",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        )
        coords_value = (
            cast(Any, coords_owner).atom_coords_3d_state
            if coords_present
            else _MISSING_ATTRIBUTE
        )
        coords_root = _BoundAttributePort.capture(
            coords_owner,
            "atom_coords_3d_state",
            value=coords_value,
            require_identity=True,
        )
        coords_state = atom_coords_3d_state_for(canvas)
        if coords_present and coords_value is not coords_state:
            raise RuntimeError("3D coordinate state root changed during capture")
        coords_snapshot = _ObjectAttributeSnapshot.capture(
            coords_state,
            ("atom_coords_3d",),
            containers,
        )
        coords_port = next(
            (port for port in coords_snapshot.ports if port.name == "atom_coords_3d"),
            None,
        )
        if coords_port is None or not isinstance(coords_port.value, dict):
            raise RuntimeError("rotation preview requires an exact 3D coordinate map")

        rotation = controller.rotation
        controller_rotation_root = _BoundAttributePort.capture(
            controller,
            "rotation",
            value=rotation,
            require_identity=True,
        )
        canvas_rotation = _optional_canvas_state_object(canvas, "rotation_state")
        roots: list[_BoundAttributePort] = [
            model_root,
            coords_root,
            controller_rotation_root,
        ]
        if canvas_rotation is not None:
            roots.append(
                _state_root_port(
                    canvas,
                    runtime_state,
                    "rotation_state",
                    canvas_rotation,
                )
            )
        rotation_snapshot = _ObjectAttributeSnapshot.capture(
            rotation,
            tuple(item.name for item in fields(CanvasRotationState)),
            containers,
        )
        objects = (
            model_snapshot,
            *atom_snapshots,
            coords_snapshot,
            rotation_snapshot,
        )
        return cls(
            containers=containers,
            roots=tuple(roots),
            objects=objects,
            rotation=rotation,
            rotation_snapshot=rotation_snapshot,
        )

    def restore_once(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for root in self.roots:
            try:
                root.apply()
            except BaseException as error:
                errors.append(error)
        for snapshot in self.objects:
            errors.extend(snapshot.restore())
        errors.extend(self.containers.restore())
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for root in self.roots:
            try:
                if not root.matches():
                    raise RuntimeError(
                        f"root {root.name!r} did not match its savepoint"
                    )
            except BaseException as error:
                errors.append(error)
        for snapshot in self.objects:
            errors.extend(snapshot.verify())
        errors.extend(self.containers.verify())
        return errors


@dataclass(slots=True)
class _MappingEntriesSnapshot:
    """A copy-on-write savepoint for only the coordinate keys a frame owns."""

    mapping: dict
    entries: tuple[tuple[object, bool, object], ...]

    @classmethod
    def capture(
        cls,
        mapping: dict,
        keys: set[int],
    ) -> _MappingEntriesSnapshot:
        return cls(
            mapping=mapping,
            entries=tuple((key, key in mapping, mapping.get(key)) for key in keys),
        )

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for key, present, value in self.entries:
            try:
                if present:
                    dict.__setitem__(self.mapping, key, value)
                else:
                    dict.pop(self.mapping, key, None)
            except BaseException as error:
                errors.append(error)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for key, present, value in self.entries:
            try:
                if (key in self.mapping) is not present:
                    raise RuntimeError(f"affected coordinate {key!r} presence changed")
                if present and self.mapping[key] is not value:
                    raise RuntimeError(f"affected coordinate {key!r} identity changed")
            except BaseException as error:
                errors.append(error)
        return errors


@dataclass(slots=True)
class _AffectedCoreStateSnapshot:
    """Per-frame COW state; its cost scales with the rotating selection."""

    containers: _MutableContainerGraphSnapshot
    roots: tuple[_BoundAttributePort, ...]
    mapping_ports: tuple[_BoundAttributePort, ...]
    objects: tuple[_ObjectAttributeSnapshot, ...]
    coords_entries: _MappingEntriesSnapshot

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
    ) -> _AffectedCoreStateSnapshot:
        canvas = controller.canvas
        runtime_state = _optional_live_attribute(canvas, "runtime_state")
        containers = _MutableContainerGraphSnapshot()

        model_owner = (
            runtime_state
            if runtime_state is not None
            and inspect.getattr_static(runtime_state, "model", _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
            else canvas
        )
        model_present = (
            inspect.getattr_static(model_owner, "model", _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        )
        model_value = (
            cast(Any, model_owner).model if model_present else _MISSING_ATTRIBUTE
        )
        model_root = _BoundAttributePort.capture(
            model_owner,
            "model",
            value=model_value,
            require_identity=True,
        )
        model = model_for(canvas)
        if model_present and model_value is not model:
            raise RuntimeError("model root changed during affected rotation capture")
        atoms = _optional_live_attribute(model, "atoms", default=_MISSING_ATTRIBUTE)
        if not isinstance(atoms, dict):
            raise RuntimeError("rotation preview requires an exact model atoms mapping")
        atoms_port = _BoundAttributePort.capture(
            model,
            "atoms",
            value=atoms,
            require_identity=True,
        )
        atom_snapshots = tuple(
            _ObjectAttributeSnapshot.capture(
                atom,
                _field_names_for_object(atom),
                containers,
            )
            for atom_id in atom_ids
            if (atom := atoms.get(atom_id)) is not None
        )

        coords_owner = (
            runtime_state
            if runtime_state is not None
            and inspect.getattr_static(
                runtime_state,
                "atom_coords_3d_state",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
            else canvas
        )
        coords_present = (
            inspect.getattr_static(
                coords_owner,
                "atom_coords_3d_state",
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        )
        coords_value = (
            cast(Any, coords_owner).atom_coords_3d_state
            if coords_present
            else _MISSING_ATTRIBUTE
        )
        coords_root = _BoundAttributePort.capture(
            coords_owner,
            "atom_coords_3d_state",
            value=coords_value,
            require_identity=True,
        )
        coords_state = atom_coords_3d_state_for(canvas)
        if coords_present and coords_value is not coords_state:
            raise RuntimeError("3D coordinate state root changed during capture")
        coords = _optional_live_attribute(
            coords_state,
            "atom_coords_3d",
            default=_MISSING_ATTRIBUTE,
        )
        if not isinstance(coords, dict):
            raise RuntimeError("rotation preview requires an exact 3D coordinate map")
        coords_port = _BoundAttributePort.capture(
            coords_state,
            "atom_coords_3d",
            value=coords,
            require_identity=True,
        )

        rotation = controller.rotation
        controller_rotation_root = _BoundAttributePort.capture(
            controller,
            "rotation",
            value=rotation,
            require_identity=True,
        )
        roots: list[_BoundAttributePort] = [
            model_root,
            coords_root,
            controller_rotation_root,
        ]
        canvas_rotation = _optional_canvas_state_object(canvas, "rotation_state")
        if canvas_rotation is not None:
            roots.append(
                _state_root_port(
                    canvas,
                    runtime_state,
                    "rotation_state",
                    canvas_rotation,
                )
            )
        rotation_snapshot = _ObjectAttributeSnapshot.capture(
            rotation,
            tuple(item.name for item in fields(CanvasRotationState)),
            containers,
        )
        coord_keys = set(atom_ids)
        coord_keys.update(rotation.coord_atom_ids)
        coord_keys.update(rotation.base_coords)
        return cls(
            containers=containers,
            roots=tuple(roots),
            mapping_ports=(atoms_port, coords_port),
            objects=(*atom_snapshots, rotation_snapshot),
            coords_entries=_MappingEntriesSnapshot.capture(coords, coord_keys),
        )

    def restore_once(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for port in (*self.roots, *self.mapping_ports):
            try:
                port.apply()
            except BaseException as error:
                errors.append(error)
        for snapshot in self.objects:
            errors.extend(snapshot.restore())
        errors.extend(self.containers.restore())
        errors.extend(self.coords_entries.restore())
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for port in (*self.roots, *self.mapping_ports):
            try:
                if not port.matches():
                    raise RuntimeError(f"affected-state root {port.name!r} changed")
            except BaseException as error:
                errors.append(error)
        for snapshot in self.objects:
            errors.extend(snapshot.verify())
        errors.extend(self.containers.verify())
        errors.extend(self.coords_entries.verify())
        return errors


@dataclass(slots=True)
class _SceneRootSnapshot:
    scene: object | None
    getter: Callable[[], object]
    setter: Callable[[object], object] | None
    fallback_port: _BoundAttributePort | None

    @classmethod
    def capture(cls, canvas: object) -> _SceneRootSnapshot:
        getter = _optional_live_attribute(canvas, "scene")
        if not callable(getter):
            raise RuntimeError("rotation preview requires a bound scene getter")
        scene = getter()
        setter = _optional_live_attribute(canvas, "setScene")
        fallback_port = None
        if not callable(setter):
            setter = None
            if (
                inspect.getattr_static(canvas, "_scene", _MISSING_ATTRIBUTE)
                is not _MISSING_ATTRIBUTE
            ):
                fallback_port = _BoundAttributePort.capture(
                    canvas,
                    "_scene",
                    value=scene,
                    require_identity=True,
                )
        return cls(scene, getter, setter, fallback_port)

    def restore(self) -> None:
        if self.getter() is self.scene:
            return
        if self.setter is not None:
            self.setter(self.scene)
        elif self.fallback_port is not None:
            self.fallback_port.apply()
        else:
            raise RuntimeError("captured scene root cannot be restored")

    def verify(self) -> None:
        if self.getter() is not self.scene:
            raise RuntimeError("canvas scene root did not match its savepoint")


def _capture_full_scene_order_runtime(
    scene: object | None,
) -> _SceneRuntimeSnapshot:
    items_getter = _optional_live_attribute(
        scene,
        "items",
        default=_MISSING_ATTRIBUTE,
    )
    if scene is None or items_getter is _MISSING_ATTRIBUTE:
        scene_items = None
        items_getter = None
    elif not callable(items_getter):
        raise RuntimeError("live scene does not expose a callable items port")
    else:
        scene_items = list(items_getter())

    signals_getter = _optional_live_attribute(
        scene,
        "signalsBlocked",
        default=_MISSING_ATTRIBUTE,
    )
    signals_setter = _optional_live_attribute(
        scene,
        "blockSignals",
        default=_MISSING_ATTRIBUTE,
    )
    signal_ports_present = (
        signals_getter is not _MISSING_ATTRIBUTE
        or signals_setter is not _MISSING_ATTRIBUTE
    )
    if signal_ports_present and not (
        callable(signals_getter) and callable(signals_setter)
    ):
        raise RuntimeError("live scene has incomplete signal-blocking ports")
    signals_blocked = (
        bool(signals_getter())
        if callable(signals_getter) and callable(signals_setter)
        else None
    )

    focus_getter = _optional_live_attribute(
        scene,
        "focusItem",
        default=_MISSING_ATTRIBUTE,
    )
    focus_setter = _optional_live_attribute(
        scene,
        "setFocusItem",
        default=_MISSING_ATTRIBUTE,
    )
    focus_ports_present = (
        focus_getter is not _MISSING_ATTRIBUTE or focus_setter is not _MISSING_ATTRIBUTE
    )
    if focus_ports_present and not (callable(focus_getter) and callable(focus_setter)):
        raise RuntimeError("live scene has incomplete focus ports")
    focus_item = (
        focus_getter() if callable(focus_getter) and callable(focus_setter) else None
    )

    topology_states = _scene_item_topology_snapshots(
        scene_items or [],
        strict=True,
    )
    selected_states: list[_SceneSelectionSnapshot] = []
    for item in scene_items or ():
        if _graphics_item_is_deleted(item):
            continue
        selection_getter = _optional_live_attribute(
            item,
            "isSelected",
            default=_MISSING_ATTRIBUTE,
        )
        selection_setter = _optional_live_attribute(
            item,
            "setSelected",
            default=_MISSING_ATTRIBUTE,
        )
        item_selection_access_present = (
            selection_getter is not _MISSING_ATTRIBUTE
            or selection_setter is not _MISSING_ATTRIBUTE
        )
        if item_selection_access_present and not (
            callable(selection_getter) and callable(selection_setter)
        ):
            raise RuntimeError("live scene item has incomplete selection ports")
        if callable(selection_getter) and callable(selection_setter):
            selected_states.append(
                _SceneSelectionSnapshot(
                    item=item,
                    selected=bool(selection_getter()),
                    getter=selection_getter,
                    setter=selection_setter,
                )
            )

    return _SceneRuntimeSnapshot(
        scene=scene,
        scene_items=scene_items,
        scene_items_getter=items_getter if callable(items_getter) else None,
        scene_signals_blocked=signals_blocked,
        scene_signals_blocked_getter=(
            signals_getter if callable(signals_getter) else None
        ),
        scene_block_signals_setter=(
            signals_setter if callable(signals_setter) else None
        ),
        focus_item=focus_item,
        focus_item_getter=focus_getter if callable(focus_getter) else None,
        focus_item_setter=focus_setter if callable(focus_setter) else None,
        topology_states=topology_states,
        selected_states=selected_states,
        visibility_states=[],
        selection_visuals=[],
        list_attributes=[],
        mark_registry=None,
        handle_state=None,
        handle_target=None,
        selection_info_state=None,
        selection_info_values={},
        bond_primitive_graphics=(),
    )


def _capture_direct_scene_order_container(
    scene: object | None,
    expected_items: list | None,
) -> _MutableContainerSnapshot | None:
    if scene is None or expected_items is None:
        return None
    for name in ("_selected_items", "_items"):
        candidate = inspect.getattr_static(scene, name, _MISSING_ATTRIBUTE)
        if not isinstance(candidate, list):
            try:
                namespace = object.__getattribute__(scene, "__dict__")
            except (AttributeError, TypeError):
                continue
            candidate = namespace.get(name, _MISSING_ATTRIBUTE)
        if not isinstance(candidate, list):
            continue
        contents = tuple(list.__iter__(candidate))
        if len(contents) != len(expected_items) or any(
            actual is not expected
            for actual, expected in zip(contents, expected_items, strict=True)
        ):
            continue
        return _MutableContainerSnapshot(candidate, "list", contents)
    return None


def _verify_scene_runtime_snapshot_exact(  # noqa: C901
    snapshot: _SceneRuntimeSnapshot,
) -> list[BaseException]:
    errors: list[BaseException] = []

    try:
        _verify_scene_runtime_identity(snapshot)
    except BaseException as error:
        errors.append(error)

    for list_snapshot in snapshot.list_attributes:
        try:
            current = _optional_live_attribute(
                list_snapshot.owner,
                list_snapshot.attribute,
                default=_MISSING_ATTRIBUTE,
            )
            if not isinstance(current, list):
                raise RuntimeError(
                    f"runtime list {list_snapshot.attribute} is unavailable"
                )
            if current is not list_snapshot.list_object or len(current) != len(
                list_snapshot.contents
            ):
                raise RuntimeError(
                    f"runtime list {list_snapshot.attribute} identity changed"
                )
            if any(
                actual is not expected
                for actual, expected in zip(
                    current,
                    list_snapshot.contents,
                    strict=True,
                )
            ):
                raise RuntimeError(
                    f"runtime list {list_snapshot.attribute} contents changed"
                )
        except BaseException as error:
            errors.append(error)

    if snapshot.mark_registry is not None:
        mark_snapshot = snapshot.mark_registry
        try:
            current = _optional_live_attribute(
                mark_snapshot.registry,
                "by_atom",
                default=_MISSING_ATTRIBUTE,
            )
            if current is not mark_snapshot.mapping_object:
                raise RuntimeError("mark registry mapping identity changed")
            actual_entries = tuple(dict.items(mark_snapshot.mapping_object))
            if len(actual_entries) != len(mark_snapshot.entries):
                raise RuntimeError("mark registry entry count changed")
            for (actual_key, actual_value), (key, value, contents) in zip(
                actual_entries,
                mark_snapshot.entries,
                strict=True,
            ):
                if actual_key is not key or actual_value is not value:
                    raise RuntimeError("mark registry entry identity changed")
                if isinstance(value, list) and contents is not None:
                    if len(value) != len(contents) or any(
                        actual is not expected
                        for actual, expected in zip(value, contents, strict=True)
                    ):
                        raise RuntimeError("mark registry list contents changed")
        except BaseException as error:
            errors.append(error)

    if snapshot.handle_state is not None:
        try:
            if (
                _optional_live_attribute(
                    snapshot.handle_state,
                    "target",
                    default=_MISSING_ATTRIBUTE,
                )
                is not snapshot.handle_target
            ):
                raise RuntimeError("active handle target changed")
        except BaseException as error:
            errors.append(error)

    if snapshot.selection_info_state is not None:
        for attribute, expected in snapshot.selection_info_values.items():
            try:
                actual = _optional_live_attribute(
                    snapshot.selection_info_state,
                    attribute,
                    default=_MISSING_ATTRIBUTE,
                )
                if not _values_match(actual, expected):
                    raise RuntimeError(f"selection-info field {attribute} changed")
            except BaseException as error:
                errors.append(error)

    for visibility in snapshot.visibility_states:
        for getter_name, expected in (
            ("isVisible", visibility.visible),
            ("rect", visibility.rect),
            ("pen", visibility.pen),
            ("brush", visibility.brush),
        ):
            if expected is _UNAVAILABLE_ITEM_VALUE:
                continue
            try:
                getter = _optional_live_attribute(
                    visibility.item,
                    getter_name,
                    default=_MISSING_ATTRIBUTE,
                )
                if not callable(getter) or not _values_match(getter(), expected):
                    raise RuntimeError(f"selection visibility {getter_name} changed")
            except BaseException as error:
                errors.append(error)

    for visual in snapshot.selection_visuals:
        try:
            pen = _optional_live_attribute(
                visual.item,
                "pen",
                default=_MISSING_ATTRIBUTE,
            )
            if not callable(pen) or not _values_match(pen(), visual.pen):
                raise RuntimeError("selection visual pen changed")
            if visual.data_6 is not _UNAVAILABLE_ITEM_VALUE:
                data = _optional_live_attribute(
                    visual.item,
                    "data",
                    default=_MISSING_ATTRIBUTE,
                )
                if not callable(data) or not _values_match(data(6), visual.data_6):
                    raise RuntimeError("selection visual metadata changed")
        except BaseException as error:
            errors.append(error)

    for primitive in snapshot.bond_primitive_graphics:
        for setter_name, expected in primitive.properties:
            primitive_getter_name = _PRIMITIVE_SETTER_GETTERS.get(setter_name)
            if primitive_getter_name is None:
                continue
            try:
                getter = _optional_live_attribute(
                    primitive.item,
                    primitive_getter_name,
                    default=_MISSING_ATTRIBUTE,
                )
                if not callable(getter) or not _values_match(getter(), expected):
                    raise RuntimeError(f"primitive {primitive_getter_name} changed")
            except BaseException as error:
                errors.append(error)
        for attribute, expected in primitive.direct_attributes:
            try:
                actual = _optional_live_attribute(
                    primitive.item,
                    attribute,
                    default=_MISSING_ATTRIBUTE,
                )
                if not _values_match(actual, expected):
                    raise RuntimeError(f"primitive field {attribute} changed")
            except BaseException as error:
                errors.append(error)
    return errors


def _add_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(
            "Rotation preview rollback also failed during "
            f"{phase}: {type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        return


def _run_rollback_step(
    original_error: BaseException,
    phase: str,
    operation: Callable[[], None],
) -> None:
    try:
        operation()
    except BaseException as rollback_error:
        _add_rollback_note(
            original_error,
            rollback_error,
            phase=phase,
        )


def _affected_bond_ids(
    controller: _RotationPreviewPorts,
    atom_ids: set[int],
) -> set[int]:
    move_controller = controller.move_controller
    if move_controller is None:
        return set()
    bond_ids_for_atom_ids = _optional_live_attribute(
        move_controller,
        "bond_ids_for_atom_ids",
    )
    if callable(bond_ids_for_atom_ids):
        return set(bond_ids_for_atom_ids(atom_ids))
    return {
        bond_id
        for bond_id, bond in enumerate(controller.bonds)
        if bond is not None and (bond.a in atom_ids or bond.b in atom_ids)
    }


def _affected_ring_items(canvas, atom_ids: set[int]) -> list[object]:
    scene_items_state = _optional_canvas_state_object(canvas, "scene_items_state")
    rings = _optional_live_attribute(scene_items_state, "ring_items")
    if not isinstance(rings, list):
        return []
    affected: list[object] = []
    for ring in rings:
        if _graphics_item_is_deleted(ring):
            continue
        try:
            data = _optional_live_attribute(ring, "data")
            if not callable(data):
                continue
            ring_atom_ids = data(2)
        except BaseException:
            if _graphics_item_is_deleted(ring):
                continue
            raise
        if isinstance(ring_atom_ids, list) and not atom_ids.isdisjoint(ring_atom_ids):
            affected.append(ring)
    return affected


def _affected_atom_items(canvas, atom_ids: set[int]) -> list[object]:
    items: list[object] = []
    atom_graphics_state = _optional_canvas_state_object(canvas, "atom_graphics_state")
    for attribute in ("atom_items", "atom_dots"):
        mapping = _optional_live_attribute(atom_graphics_state, attribute)
        if not isinstance(mapping, dict):
            continue
        items.extend(mapping.get(atom_id) for atom_id in atom_ids)

    mark_registry = _optional_canvas_state_object(canvas, "mark_registry")
    marks_by_atom = _optional_live_attribute(mark_registry, "by_atom")
    if isinstance(marks_by_atom, dict):
        for atom_id in atom_ids:
            marks = marks_by_atom.get(atom_id)
            if isinstance(marks, list):
                items.extend(marks)
    return items


def _primitive_snapshots(
    items: list[object],
) -> tuple[_BondPrimitiveGraphicsSnapshot, ...]:
    snapshots: list[_BondPrimitiveGraphicsSnapshot] = []
    seen: set[int] = set()
    for item in items:
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        snapshot = _BondPrimitiveGraphicsSnapshot.capture(item, strict=True)
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


def _item_is_attached(
    scene: object | None,
    item: object,
    *,
    strict: bool = False,
) -> bool | None:
    if scene is None:
        return None
    item_scene = (
        _optional_live_attribute(item, "scene")
        if strict
        else getattr(item, "scene", None)
    )
    if not callable(item_scene):
        return None
    return item_scene() is scene


@dataclass(slots=True)
class _ItemRuntimeSnapshot:
    scene: object | None
    item: object
    attached: bool | None
    selected: bool | None
    selection_getter: Callable[[], object] | None
    selection_setter: Callable[[bool], object] | None
    scene_add_item: Callable[[object], object] | None
    scene_remove_item: Callable[[object], object] | None

    @classmethod
    def capture(
        cls,
        scene: object | None,
        item: object,
    ) -> _ItemRuntimeSnapshot:
        if _graphics_item_is_deleted(item):
            return cls(
                scene=scene,
                item=item,
                attached=None,
                selected=None,
                selection_getter=None,
                selection_setter=None,
                scene_add_item=None,
                scene_remove_item=None,
            )
        is_selected = _optional_live_attribute(item, "isSelected")
        set_selected = _optional_live_attribute(item, "setSelected")
        selected: bool | None = None
        selection_access_present = callable(is_selected) or callable(set_selected)
        if selection_access_present and not (
            callable(is_selected) and callable(set_selected)
        ):
            raise RuntimeError("rotation-preview item has incomplete selection ports")
        if callable(is_selected) and callable(set_selected):
            selected = bool(is_selected())
        add_item = _optional_live_attribute(scene, "addItem")
        remove_item = _optional_live_attribute(scene, "removeItem")
        scene_ports_present = callable(add_item) or callable(remove_item)
        if scene_ports_present and not (callable(add_item) and callable(remove_item)):
            raise RuntimeError("rotation-preview scene has incomplete item ports")
        return cls(
            scene=scene,
            item=item,
            attached=_item_is_attached(scene, item, strict=True),
            selected=selected,
            selection_getter=is_selected if callable(is_selected) else None,
            selection_setter=set_selected if callable(set_selected) else None,
            scene_add_item=add_item if callable(add_item) else None,
            scene_remove_item=remove_item if callable(remove_item) else None,
        )

    def restore(self) -> None:
        if _graphics_item_is_deleted(self.item):
            raise RuntimeError("captured rotation-preview item was deleted")
        attached = _item_is_attached(
            self.scene,
            self.item,
            strict=True,
        )
        if self.attached is True and attached is not True:
            if self.scene_add_item is None:
                raise RuntimeError("rotation-preview item cannot be reattached")
            self.scene_add_item(self.item)
        elif self.attached is False and attached is True:
            if self.scene_remove_item is None:
                raise RuntimeError("rotation-preview item cannot be detached")
            self.scene_remove_item(self.item)
        if self.selected is not None:
            if self.selection_setter is None:
                raise RuntimeError("rotation-preview selection cannot be restored")
            self.selection_setter(self.selected)


@dataclass(slots=True)
class _BondEntrySnapshot:
    bond_id: int
    was_present: bool
    value: object | None
    contents: tuple[object, ...] | None

    @classmethod
    def capture(
        cls,
        mapping: dict,
        bond_id: int,
    ) -> _BondEntrySnapshot:
        value = mapping.get(bond_id)
        return cls(
            bond_id=bond_id,
            was_present=bond_id in mapping,
            value=value,
            contents=tuple(value) if isinstance(value, list) else None,
        )

    def items(self) -> tuple[object, ...]:
        return self.contents or ()

    def restore(self, mapping: dict) -> None:
        if not self.was_present:
            mapping.pop(self.bond_id, None)
            return
        if isinstance(self.value, list) and self.contents is not None:
            self.value[:] = self.contents
        mapping[self.bond_id] = self.value


@dataclass(slots=True)
class _SceneSnapshot:
    scene: object | None
    bond_state: object | None
    bond_mapping: dict | None
    bond_entries: tuple[_BondEntrySnapshot, ...]
    outline_state: object | None
    outline_list: list | None
    outline_contents: tuple[object, ...]
    item_runtime: tuple[_ItemRuntimeSnapshot, ...]
    primitive_graphics: tuple[_BondPrimitiveGraphicsSnapshot, ...]
    selection_info_state: object | None
    selection_info_values: dict[str, object]

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
        *,
        scene: object | None,
        affected_ring_items: tuple[object, ...] | None = None,
    ) -> _SceneSnapshot:
        canvas = controller.canvas
        bond_state = _optional_canvas_state_object(canvas, "bond_graphics_state")
        candidate_mapping = _optional_live_attribute(bond_state, "bond_items")
        bond_mapping = (
            candidate_mapping if isinstance(candidate_mapping, dict) else None
        )
        bond_entries = (
            tuple(
                _BondEntrySnapshot.capture(bond_mapping, bond_id)
                for bond_id in _affected_bond_ids(controller, atom_ids)
            )
            if bond_mapping is not None
            else ()
        )

        outline_state = _optional_canvas_state_object(canvas, "selection_outline_state")
        candidate_outline_list = _optional_live_attribute(outline_state, "outlines")
        outline_list = (
            candidate_outline_list if isinstance(candidate_outline_list, list) else None
        )
        outline_contents = tuple(outline_list or ())

        items = _affected_atom_items(canvas, atom_ids)
        if affected_ring_items is None:
            items.extend(_affected_ring_items(canvas, atom_ids))
        else:
            items.extend(
                ring
                for ring in affected_ring_items
                if not _graphics_item_is_deleted(ring)
            )
        for entry in bond_entries:
            entry_items = entry.items()
            items.extend(entry_items)
        items.extend(outline_contents)

        unique_items: list[object] = []
        seen: set[int] = set()
        for item in items:
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            unique_items.append(item)

        selection_info_state = _optional_canvas_state_object(
            canvas,
            "selection_info_state",
        )
        selection_info_values: dict[str, object] = {}
        if selection_info_state is not None:
            for attribute in (
                "signature",
                "pending_signature",
                "cache",
                "rdkit_warmup_pending",
                "last_interaction_time",
            ):
                value = _optional_live_attribute(
                    selection_info_state,
                    attribute,
                    default=_MISSING_ATTRIBUTE,
                )
                if value is not _MISSING_ATTRIBUTE:
                    selection_info_values[attribute] = value

        return cls(
            scene=scene,
            bond_state=bond_state,
            bond_mapping=bond_mapping,
            bond_entries=bond_entries,
            outline_state=outline_state,
            outline_list=outline_list,
            outline_contents=outline_contents,
            item_runtime=tuple(
                _ItemRuntimeSnapshot.capture(scene, item) for item in unique_items
            ),
            primitive_graphics=_primitive_snapshots(unique_items),
            selection_info_state=selection_info_state,
            selection_info_values=selection_info_values,
        )

    def restore(self, original_error: BaseException) -> None:
        if self.bond_mapping is not None:
            for entry in self.bond_entries:
                _run_rollback_step(
                    original_error,
                    f"restoring bond graphics entry {entry.bond_id}",
                    partial(entry.restore, self.bond_mapping),
                )
            if self.bond_state is not None:
                _run_rollback_step(
                    original_error,
                    "restoring the bond graphics mapping",
                    partial(
                        setattr,
                        self.bond_state,
                        "bond_items",
                        self.bond_mapping,
                    ),
                )

        if self.outline_list is not None:
            outline_list = self.outline_list

            def restore_outline_list() -> None:
                outline_list[:] = self.outline_contents

            _run_rollback_step(
                original_error,
                "restoring the selection outline list",
                restore_outline_list,
            )
            if self.outline_state is not None:
                _run_rollback_step(
                    original_error,
                    "restoring the selection outline list identity",
                    partial(setattr, self.outline_state, "outlines", outline_list),
                )

        if self.selection_info_state is not None:
            for attribute, value in self.selection_info_values.items():
                _run_rollback_step(
                    original_error,
                    f"restoring selection-info field {attribute}",
                    partial(
                        setattr,
                        self.selection_info_state,
                        attribute,
                        value,
                    ),
                )

        for item_runtime in self.item_runtime:
            _run_rollback_step(
                original_error,
                "restoring affected rotation-preview item runtime",
                item_runtime.restore,
            )

        try:
            primitive_errors = _restore_bond_primitive_graphics_snapshots(
                self.primitive_graphics
            )
        except BaseException as primitive_restore_error:
            _add_rollback_note(
                original_error,
                primitive_restore_error,
                phase="restoring rotation-preview graphics",
            )
            return
        for primitive_error in primitive_errors:
            _add_rollback_note(
                original_error,
                primitive_error,
                phase="restoring rotation-preview graphics",
            )

    def verify(  # noqa: C901
        self,
        *,
        include_selection_info: bool = True,
        include_outline: bool = True,
        ignored_item_ids: frozenset[int] = frozenset(),
        ignored_selection_item_ids: frozenset[int] = frozenset(),
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        if self.bond_mapping is not None:
            try:
                current_mapping = _optional_live_attribute(
                    self.bond_state,
                    "bond_items",
                    default=_MISSING_ATTRIBUTE,
                )
                if current_mapping is not self.bond_mapping:
                    raise RuntimeError("bond graphics mapping identity changed")
            except BaseException as error:
                errors.append(error)
            for entry in self.bond_entries:
                try:
                    if (entry.bond_id in self.bond_mapping) is not entry.was_present:
                        raise RuntimeError(
                            f"bond graphics entry {entry.bond_id} presence changed"
                        )
                    if not entry.was_present:
                        continue
                    current = self.bond_mapping[entry.bond_id]
                    if current is not entry.value:
                        raise RuntimeError(
                            f"bond graphics entry {entry.bond_id} identity changed"
                        )
                    if isinstance(current, list) and entry.contents is not None:
                        if len(current) != len(entry.contents) or any(
                            actual is not expected
                            for actual, expected in zip(
                                current,
                                entry.contents,
                                strict=True,
                            )
                        ):
                            raise RuntimeError(
                                f"bond graphics entry {entry.bond_id} contents changed"
                            )
                except BaseException as error:
                    errors.append(error)

        if include_outline and self.outline_list is not None:
            try:
                current_outlines = _optional_live_attribute(
                    self.outline_state,
                    "outlines",
                    default=_MISSING_ATTRIBUTE,
                )
                if current_outlines is not self.outline_list:
                    raise RuntimeError("selection outline list identity changed")
                if len(self.outline_list) != len(self.outline_contents) or any(
                    actual is not expected
                    for actual, expected in zip(
                        self.outline_list,
                        self.outline_contents,
                        strict=True,
                    )
                ):
                    raise RuntimeError("selection outline list contents changed")
            except BaseException as error:
                errors.append(error)

        for snapshot in self.item_runtime:
            if id(snapshot.item) in ignored_item_ids:
                continue
            if _graphics_item_is_deleted(snapshot.item):
                errors.append(
                    RuntimeError("captured rotation-preview item was deleted")
                )
                continue
            try:
                if (
                    snapshot.attached is not None
                    and _item_is_attached(
                        self.scene,
                        snapshot.item,
                        strict=True,
                    )
                    is not snapshot.attached
                ):
                    raise RuntimeError("rotation-preview item membership changed")
                if (
                    snapshot.selected is not None
                    and id(snapshot.item) not in ignored_selection_item_ids
                ):
                    getter = _optional_live_attribute(snapshot.item, "isSelected")
                    if not callable(getter) or bool(getter()) != snapshot.selected:
                        raise RuntimeError("rotation-preview item selection changed")
            except BaseException as error:
                errors.append(error)

        if include_selection_info and self.selection_info_state is not None:
            for attribute, expected in self.selection_info_values.items():
                try:
                    actual = _optional_live_attribute(
                        self.selection_info_state,
                        attribute,
                        default=_MISSING_ATTRIBUTE,
                    )
                    if not _values_match(actual, expected):
                        raise RuntimeError(f"selection-info field {attribute} changed")
                except BaseException as error:
                    errors.append(error)

        for primitive in self.primitive_graphics:
            if id(primitive.item) in ignored_item_ids:
                continue
            for setter_name, expected in primitive.properties:
                getter_name = _PRIMITIVE_SETTER_GETTERS.get(setter_name)
                if getter_name is None:
                    continue
                try:
                    getter = _optional_live_attribute(
                        primitive.item,
                        getter_name,
                        default=_MISSING_ATTRIBUTE,
                    )
                    if not callable(getter) or not _values_match(
                        getter(),
                        expected,
                    ):
                        raise RuntimeError(
                            f"rotation-preview primitive {getter_name} changed"
                        )
                except BaseException as error:
                    errors.append(error)
            for attribute, expected in primitive.direct_attributes:
                try:
                    actual = _optional_live_attribute(
                        primitive.item,
                        attribute,
                        default=_MISSING_ATTRIBUTE,
                    )
                    if not _values_match(actual, expected):
                        raise RuntimeError(
                            f"rotation-preview primitive field {attribute} changed"
                        )
                except BaseException as error:
                    errors.append(error)
        return errors


@dataclass(slots=True)
class _UpdateSnapshot:
    canvas: object
    core_state: _CoreStateSnapshot
    scene_root: _SceneRootSnapshot
    targeted_scene_runtime: _SceneSnapshot
    full_scene_runtime: _SceneRuntimeSnapshot
    direct_scene_order: _MutableContainerSnapshot | None
    scene_items_bounding_rect: Callable[[], QRectF] | None
    scene_rect_snapshot: SceneRectSnapshot | None
    scene_rect_parent_depth: int | None
    scene_rect_restore_attempted: bool = False

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
        *,
        core_state: _CoreStateSnapshot | None = None,
        affected_ring_items: tuple[object, ...] | None = None,
    ) -> _UpdateSnapshot:
        canvas = controller.canvas
        if core_state is None:
            core_state = _CoreStateSnapshot.capture(controller)
        scene_root = _SceneRootSnapshot.capture(canvas)
        targeted_scene_runtime = _SceneSnapshot.capture(
            controller,
            atom_ids,
            scene=scene_root.scene,
            affected_ring_items=affected_ring_items,
        )
        full_scene_runtime = _capture_full_scene_order_runtime(scene_root.scene)
        direct_scene_order = _capture_direct_scene_order_container(
            scene_root.scene,
            full_scene_runtime.scene_items,
        )
        items_bounding_rect = _optional_live_attribute(
            scene_root.scene,
            "itemsBoundingRect",
        )
        scene_items_bounding_rect = (
            items_bounding_rect if callable(items_bounding_rect) else None
        )

        # The guard changes automatic Qt scenes to a temporary explicit rect.
        # Open it only after every other fallible capture has completed, so a
        # capture error can never strand that temporary mode without an owner.
        scene_rect_snapshot = SceneRectSnapshot.capture(scene_root.scene)
        scene_rect_parent_depth = (
            scene_rect_snapshot.tracker.depth - 1
            if scene_rect_snapshot is not None
            and scene_rect_snapshot.automatic
            and scene_rect_snapshot.guarded
            else None
        )
        return cls(
            canvas=canvas,
            core_state=core_state,
            scene_root=scene_root,
            targeted_scene_runtime=targeted_scene_runtime,
            full_scene_runtime=full_scene_runtime,
            direct_scene_order=direct_scene_order,
            scene_items_bounding_rect=scene_items_bounding_rect,
            scene_rect_snapshot=scene_rect_snapshot,
            scene_rect_parent_depth=scene_rect_parent_depth,
        )

    def release(self) -> None:
        snapshot = self.scene_rect_snapshot
        if snapshot is None:
            return
        expanded_rect = None
        if snapshot.automatic:
            items_bounding_rect = self.scene_items_bounding_rect
            if not callable(items_bounding_rect):
                raise AttributeError(
                    "Automatic rotation-preview scene requires itemsBoundingRect"
                )
            expanded_rect = QRectF(items_bounding_rect())
        snapshot.release(expanded_rect)

    def _restore_scene_rect(
        self,
        original_error: BaseException,
    ) -> list[BaseException]:
        snapshot = self.scene_rect_snapshot
        if snapshot is None or self.scene_rect_restore_attempted:
            return []
        # SceneRectSnapshot owns its verified two-attempt policy. Calling it a
        # second time here would turn the public maximum into four attempts.
        self.scene_rect_restore_attempted = True
        errors: list[BaseException] = []
        prior_recovery_count = len(snapshot.recovery_errors)
        try:
            snapshot.restore()
        except BaseException as restore_error:
            _add_rollback_note(
                original_error,
                restore_error,
                phase="restoring the rotation-preview scene rect",
            )
            if snapshot.active:
                errors.append(restore_error)
        for recovery_error in snapshot.recovery_errors[prior_recovery_count:]:
            _add_rollback_note(
                original_error,
                recovery_error,
                phase="restoring the rotation-preview scene rect",
            )
        if snapshot.active:
            errors.append(
                RuntimeError("rotation-preview scene rect remained non-authoritative")
            )
        return errors

    def _verify_scene_rect(self) -> list[BaseException]:
        snapshot = self.scene_rect_snapshot
        if snapshot is None:
            return []
        errors: list[BaseException] = []
        try:
            if snapshot.active:
                raise RuntimeError(
                    "rotation-preview scene rect savepoint is still active"
                )
            if self.scene_rect_parent_depth is not None and (
                snapshot.tracker.depth != self.scene_rect_parent_depth
            ):
                raise RuntimeError("rotation-preview scene rect depth changed")
            if (
                QRectF(cast(Any, snapshot.scene_rect_getter()))
                != snapshot.baseline_rect
            ):
                raise RuntimeError("rotation-preview scene rect value changed")
        except BaseException as error:
            errors.append(error)
        return errors

    def _restore_scene_once(self, original_error: BaseException) -> list[BaseException]:
        errors: list[BaseException] = []
        try:
            self.scene_root.restore()
        except BaseException as error:
            errors.append(error)
        try:
            self.targeted_scene_runtime.restore(original_error)
        except BaseException as error:
            errors.append(error)
        try:
            errors.extend(
                _restore_scene_runtime_snapshot(
                    self.full_scene_runtime,
                    collect_errors=True,
                    restore_attempts=1,
                )
            )
        except BaseException as error:
            errors.append(error)
        if self.direct_scene_order is not None:
            try:
                self.direct_scene_order.restore()
            except BaseException as error:
                errors.append(error)
        return errors

    def _verify_all(self) -> list[BaseException]:
        errors = self.core_state.verify()
        try:
            self.scene_root.verify()
        except BaseException as error:
            errors.append(error)
        errors.extend(self.targeted_scene_runtime.verify())
        errors.extend(_verify_scene_runtime_snapshot_exact(self.full_scene_runtime))
        if self.direct_scene_order is not None:
            try:
                if not self.direct_scene_order.matches():
                    raise RuntimeError("direct scene order did not match its savepoint")
            except BaseException as error:
                errors.append(error)
        errors.extend(self._verify_scene_rect())
        return errors

    def restore(self, original_error: BaseException) -> bool:
        accumulated_errors: list[BaseException] = []
        for _attempt in range(2):
            operation_errors = self.core_state.restore_once()
            operation_errors.extend(self._restore_scene_once(original_error))
            operation_errors.extend(self._restore_scene_rect(original_error))
            # Scene membership, selection and rect callbacks can mutate model,
            # coordinate or rotation state after their earlier repair. Reapply
            # the capture-bound core authority only after all such callbacks.
            operation_errors.extend(self.core_state.restore_once())
            verification_errors = self._verify_all()
            if not verification_errors:
                for error in (*accumulated_errors, *operation_errors):
                    _add_rollback_note(
                        original_error,
                        error,
                        phase="an earlier exact rotation-preview restore attempt",
                    )
                return True
            accumulated_errors.extend(operation_errors)
            accumulated_errors.extend(verification_errors)
        for error in accumulated_errors:
            _add_rollback_note(
                original_error,
                error,
                phase="restoring the exact rotation-preview savepoint",
            )
        _add_rollback_note(
            original_error,
            RuntimeError("rotation-preview rollback remained non-authoritative"),
            phase="verifying exact rollback authority",
        )
        return False


@dataclass(slots=True)
class _AffectedUpdateSnapshot:
    core_state: _AffectedCoreStateSnapshot
    scene_runtime: _SceneSnapshot

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
        *,
        scene: object | None,
        affected_ring_items: tuple[object, ...] | None = None,
    ) -> _AffectedUpdateSnapshot:
        return cls(
            core_state=_AffectedCoreStateSnapshot.capture(controller, atom_ids),
            scene_runtime=_SceneSnapshot.capture(
                controller,
                atom_ids,
                scene=scene,
                affected_ring_items=affected_ring_items,
            ),
        )

    def _remove_stale_baseline_items(
        self,
        baseline: _SceneSnapshot,
    ) -> list[BaseException]:
        expected_ids = {id(runtime.item) for runtime in self.scene_runtime.item_runtime}
        errors: list[BaseException] = []
        for runtime in baseline.item_runtime:
            if id(runtime.item) in expected_ids or runtime.attached is not True:
                continue
            try:
                attached = _item_is_attached(
                    runtime.scene,
                    runtime.item,
                    strict=True,
                )
                if attached is True:
                    if runtime.scene_remove_item is None:
                        raise RuntimeError(
                            "stale rotation-preview item cannot be detached"
                        )
                    runtime.scene_remove_item(runtime.item)
            except BaseException as error:
                errors.append(error)
        return errors

    def restore_once(
        self,
        original_error: BaseException,
        *,
        baseline: _SceneSnapshot,
        baseline_core: _CoreStateSnapshot | None,
    ) -> list[BaseException]:
        errors = self._remove_stale_baseline_items(baseline)
        try:
            self.scene_runtime.restore(original_error)
        except BaseException as error:
            errors.append(error)
        # Scene selection/membership callbacks are allowed to poison model or
        # rotation state. Re-establish the session-wide authority, then overlay
        # only the last successfully published affected values.
        if baseline_core is not None:
            errors.extend(baseline_core.restore_once())
        errors.extend(self.core_state.restore_once())
        return errors

    def verify(self) -> list[BaseException]:
        errors = self.core_state.verify()
        errors.extend(self.scene_runtime.verify())
        return errors


@dataclass(slots=True)
class _FinalPublicationSnapshot:
    """Expected selection/outline publication captured during finalization."""

    scene_runtime: _SceneSnapshot
    full_scene_runtime: _SceneRuntimeSnapshot

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
        *,
        scene: object | None,
        affected_ring_items: tuple[object, ...] | None = None,
    ) -> _FinalPublicationSnapshot:
        scene_runtime = _SceneSnapshot.capture(
            controller,
            atom_ids,
            scene=scene,
            affected_ring_items=affected_ring_items,
        )
        return cls(
            scene_runtime=scene_runtime,
            full_scene_runtime=_capture_full_scene_order_runtime(scene),
        )


@dataclass(slots=True)
class _RotationPreviewAuthority:
    """Session-wide global baseline plus a rolling affected-state checkpoint."""

    controller: _RotationPreviewPorts
    atom_ids: frozenset[int]
    affected_ring_items: tuple[object, ...]
    full_snapshot: _UpdateSnapshot
    rolling_snapshot: _AffectedUpdateSnapshot

    @classmethod
    def capture(
        cls,
        controller: _RotationPreviewPorts,
        atom_ids: set[int],
        *,
        core_state: _CoreStateSnapshot | None = None,
    ) -> _RotationPreviewAuthority:
        affected_ring_items = tuple(_affected_ring_items(controller.canvas, atom_ids))
        full_snapshot = _UpdateSnapshot.capture(
            controller,
            atom_ids,
            core_state=core_state,
            affected_ring_items=affected_ring_items,
        )
        try:
            rolling_snapshot = _AffectedUpdateSnapshot.capture(
                controller,
                atom_ids,
                scene=full_snapshot.scene_root.scene,
                affected_ring_items=affected_ring_items,
            )
        except BaseException as capture_error:
            full_snapshot.restore(capture_error)
            raise
        return cls(
            controller=controller,
            atom_ids=frozenset(atom_ids),
            affected_ring_items=affected_ring_items,
            full_snapshot=full_snapshot,
            rolling_snapshot=rolling_snapshot,
        )

    def _is_published_owner(self) -> bool:
        return getattr(self.controller, "_rotation_preview_authority", None) is self

    def _verify_atom_authority(self) -> None:
        if set(self.controller.rotation.atom_ids) != set(self.atom_ids):
            raise RuntimeError("rotation preview affected atom authority changed")
        root_errors: list[BaseException] = []
        for root in self.full_snapshot.core_state.roots:
            try:
                if not root.matches():
                    raise RuntimeError(f"rotation preview root {root.name!r} changed")
            except BaseException as error:
                root_errors.append(error)
        try:
            self.full_snapshot.scene_root.verify()
        except BaseException as error:
            root_errors.append(error)
        if root_errors:
            raise BaseExceptionGroup(
                "rotation preview root authority changed",
                root_errors,
            )

    def _verify_global_scene(
        self,
        expected_final: _FinalPublicationSnapshot | None = None,
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        try:
            self.full_snapshot.scene_root.verify()
        except BaseException as error:
            errors.append(error)

        baseline = self.full_snapshot.full_scene_runtime
        baseline_targeted = self.full_snapshot.targeted_scene_runtime
        rolling_targeted = self.rolling_snapshot.scene_runtime
        final_targeted = (
            expected_final.scene_runtime if expected_final is not None else None
        )
        affected_ids = {
            id(runtime.item)
            for runtime in (
                *baseline_targeted.item_runtime,
                *rolling_targeted.item_runtime,
                *(final_targeted.item_runtime if final_targeted is not None else ()),
            )
        }
        try:
            if baseline.scene_items is not None:
                if baseline.scene_items_getter is None:
                    raise RuntimeError("rotation scene items getter was lost")
                current_items = list(baseline.scene_items_getter())
                expected_unaffected = [
                    item
                    for item in baseline.scene_items
                    if id(item) not in affected_ids
                ]
                current_unaffected = [
                    item for item in current_items if id(item) not in affected_ids
                ]
                if not self._same_item_order(
                    current_unaffected,
                    expected_unaffected,
                ):
                    raise RuntimeError(
                        "unaffected rotation scene membership/order changed"
                    )
        except BaseException as error:
            errors.append(error)

        if baseline.scene_signals_blocked_getter is not None:
            try:
                if (
                    bool(baseline.scene_signals_blocked_getter())
                    != baseline.scene_signals_blocked
                ):
                    raise RuntimeError("rotation scene signal state changed")
            except BaseException as error:
                errors.append(error)
        if baseline.focus_item_getter is not None:
            try:
                if baseline.focus_item_getter() is not baseline.focus_item:
                    raise RuntimeError("rotation scene focus changed")
            except BaseException as error:
                errors.append(error)
        for selection in baseline.selected_states:
            if id(selection.item) in affected_ids:
                continue
            try:
                if bool(selection.getter()) != selection.selected:
                    raise RuntimeError("unaffected rotation scene selection changed")
            except BaseException as error:
                errors.append(error)

        expected_ids = {
            id(runtime.item)
            for runtime in (
                final_targeted.item_runtime
                if final_targeted is not None
                else rolling_targeted.item_runtime
            )
        }
        prior_runtime = (
            *baseline_targeted.item_runtime,
            *(rolling_targeted.item_runtime if final_targeted is not None else ()),
        )
        seen_prior_ids: set[int] = set()
        for runtime in prior_runtime:
            runtime_id = id(runtime.item)
            if runtime_id in seen_prior_ids:
                continue
            seen_prior_ids.add(runtime_id)
            if runtime_id in expected_ids or runtime.attached is not True:
                continue
            try:
                if (
                    _item_is_attached(
                        runtime.scene,
                        runtime.item,
                        strict=True,
                    )
                    is True
                ):
                    raise RuntimeError("stale affected scene item remained attached")
            except BaseException as error:
                errors.append(error)
        if final_targeted is None:
            errors.extend(rolling_targeted.verify(include_selection_info=False))
            return errors

        rolling_outline_ids = frozenset(
            id(item) for item in rolling_targeted.outline_contents
        )
        final_selection_item_ids = frozenset(
            id(runtime.item) for runtime in final_targeted.item_runtime
        )
        # Final selection restoration may replace only the outline objects and
        # their registry list, and it may republish a semantic ring selection
        # as its atom graphics. Keep the rolling checkpoint authoritative for
        # every affected atom/bond/ring primitive, while delegating selection
        # flags to the final snapshot captured after that publication.
        errors.extend(
            rolling_targeted.verify(
                include_selection_info=False,
                include_outline=False,
                ignored_item_ids=rolling_outline_ids,
                ignored_selection_item_ids=final_selection_item_ids,
            )
        )
        errors.extend(final_targeted.verify())
        assert expected_final is not None
        errors.extend(
            _verify_scene_runtime_snapshot_exact(
                expected_final.full_scene_runtime,
            )
        )
        return errors

    @staticmethod
    def _same_item_order(
        actual: Sequence[object],
        expected: Sequence[object],
    ) -> bool:
        return len(actual) == len(expected) and all(
            item is expected_item
            for item, expected_item in zip(actual, expected, strict=False)
        )

    def _verify_global_core(self) -> list[BaseException]:  # noqa: C901
        full = self.full_snapshot.core_state
        rolling = self.rolling_snapshot.core_state
        errors: list[BaseException] = []
        for root in full.roots:
            try:
                if not root.matches():
                    raise RuntimeError(f"global rotation root {root.name!r} changed")
            except BaseException as error:
                errors.append(error)

        affected_targets = {
            id(snapshot.target)
            for snapshot in rolling.objects
            if snapshot.target is not full.rotation
        }
        for snapshot in full.objects:
            if (
                snapshot.target is full.rotation
                or id(snapshot.target) in affected_targets
            ):
                continue
            errors.extend(snapshot.verify())

        atoms_mapping = None
        coords_mapping = None
        for snapshot in full.objects:
            for port in snapshot.ports:
                if port.name == "atoms" and isinstance(port.value, dict):
                    atoms_mapping = port.value
                elif port.name == "atom_coords_3d" and isinstance(
                    port.value,
                    dict,
                ):
                    coords_mapping = port.value
        if atoms_mapping is not None:
            atoms_snapshot = full.containers.snapshots.get(id(atoms_mapping))
            if atoms_snapshot is None or not atoms_snapshot.matches():
                errors.append(RuntimeError("global atom mapping changed"))

        affected_coord_keys = {
            key for key, _present, _value in rolling.coords_entries.entries
        }
        if coords_mapping is not None:
            coords_snapshot = full.containers.snapshots.get(id(coords_mapping))
            try:
                if coords_snapshot is None:
                    raise RuntimeError("global coordinate mapping snapshot was lost")
                expected_unaffected = tuple(
                    (key, value)
                    for key, value in coords_snapshot.contents
                    if key not in affected_coord_keys
                )
                actual_unaffected = tuple(
                    (key, value)
                    for key, value in dict.items(coords_mapping)
                    if key not in affected_coord_keys
                )
                if len(actual_unaffected) != len(expected_unaffected) or any(
                    actual_key != expected_key or actual_value is not expected_value
                    for (actual_key, actual_value), (
                        expected_key,
                        expected_value,
                    ) in zip(
                        actual_unaffected,
                        expected_unaffected,
                        strict=True,
                    )
                ):
                    raise RuntimeError("unaffected 3D coordinates changed")
            except BaseException as error:
                errors.append(error)

        skipped_container_ids = {
            id(mapping)
            for mapping in (atoms_mapping, coords_mapping)
            if mapping is not None
        }
        skipped_container_ids.update(rolling.containers.snapshots)
        for container_id, container_snapshot in full.containers.snapshots.items():
            if container_id in skipped_container_ids:
                continue
            try:
                if not container_snapshot.matches():
                    raise RuntimeError("unaffected mutable core container changed")
            except BaseException as error:
                errors.append(error)
        errors.extend(rolling.verify())
        return errors

    def capture_final_publication(self) -> _FinalPublicationSnapshot:
        if not self._is_published_owner():
            raise RuntimeError(
                "rotation preview owner changed before final publication capture"
            )
        self._verify_atom_authority()
        expected_final = _FinalPublicationSnapshot.capture(
            self.controller,
            set(self.atom_ids),
            scene=self.full_snapshot.scene_root.scene,
            affected_ring_items=self.affected_ring_items,
        )
        if not self._is_published_owner():
            raise RuntimeError(
                "rotation preview owner changed during final publication capture"
            )
        self._verify_atom_authority()
        return expected_final

    def verify_current_global(
        self,
        expected_final: _FinalPublicationSnapshot | None = None,
    ) -> None:
        # Scene reads can invoke user/Qt callbacks, so validate scene first and
        # core last. Nothing fallible runs between this check and clear_session.
        errors = self._verify_global_scene(expected_final)
        errors.extend(self._verify_global_core())
        if errors:
            raise BaseExceptionGroup(
                "rotation preview global authority changed",
                errors,
            )

    def restore(self, original_error: BaseException) -> bool:
        rolling = self.rolling_snapshot
        full_authoritative = self.full_snapshot.restore(original_error)
        accumulated_errors: list[BaseException] = []
        for _attempt in range(2):
            operation_errors = rolling.restore_once(
                original_error,
                baseline=self.full_snapshot.targeted_scene_runtime,
                baseline_core=self.full_snapshot.core_state,
            )
            verification_errors = rolling.verify()
            if not verification_errors:
                for error in (*accumulated_errors, *operation_errors):
                    _add_rollback_note(
                        original_error,
                        error,
                        phase="an earlier affected rotation-preview restore attempt",
                    )
                return full_authoritative
            accumulated_errors.extend(operation_errors)
            accumulated_errors.extend(verification_errors)
        for error in accumulated_errors:
            _add_rollback_note(
                original_error,
                error,
                phase="restoring the affected rotation-preview checkpoint",
            )
        return False

    def reapply_rolling(self, original_error: BaseException) -> bool:
        """Republish this owner after an older re-entrant owner rolls back."""

        accumulated_errors: list[BaseException] = []
        for _attempt in range(2):
            operation_errors = self.rolling_snapshot.restore_once(
                original_error,
                baseline=self.full_snapshot.targeted_scene_runtime,
                baseline_core=None,
            )
            verification_errors = self.rolling_snapshot.verify()
            if not verification_errors:
                for error in (*accumulated_errors, *operation_errors):
                    _add_rollback_note(
                        original_error,
                        error,
                        phase="reapplying a replacement rotation owner",
                    )
                return True
            accumulated_errors.extend(operation_errors)
            accumulated_errors.extend(verification_errors)
        for error in accumulated_errors:
            _add_rollback_note(
                original_error,
                error,
                phase="reapplying a replacement rotation owner",
            )
        return False

    def run_update(self, update: Callable[[], None]) -> None:
        previous = self.rolling_snapshot
        try:
            if not self._is_published_owner():
                raise RuntimeError("rotation preview owner changed before update")
            self._verify_atom_authority()
            update()
            if not self._is_published_owner():
                raise RuntimeError("rotation preview owner changed during update")
            self._verify_atom_authority()
            next_snapshot = _AffectedUpdateSnapshot.capture(
                self.controller,
                set(self.atom_ids),
                scene=self.full_snapshot.scene_root.scene,
                affected_ring_items=self.affected_ring_items,
            )
            if not self._is_published_owner():
                raise RuntimeError("rotation preview owner changed during checkpoint")
            self.rolling_snapshot = next_snapshot
        except BaseException as original_error:
            self.rolling_snapshot = previous
            self.restore(original_error)
            if self._is_published_owner():
                cast(Any, self.controller)._rotation_preview_authority = None
            transaction = getattr(
                self.controller,
                "_rotation_transaction",
                None,
            )
            if getattr(transaction, "preview", None) is self:
                cast(Any, transaction).preview = None
            raise

    def release(self) -> None:
        self.full_snapshot.release()


def capture_rotation_preview_authority(
    controller: _RotationPreviewPorts,
    atom_ids: set[int],
    *,
    core_state: _CoreStateSnapshot | None = None,
) -> _RotationPreviewAuthority:
    return _RotationPreviewAuthority.capture(
        controller,
        atom_ids,
        core_state=core_state,
    )


def run_rotation_preview_update(
    controller: _RotationPreviewPorts,
    atom_ids: set[int],
    update: Callable[[], None],
) -> None:
    # Standalone transaction tests and idle callers retain the one-shot exact
    # savepoint. An active rotation publishes one full authority and advances
    # only an affected-state rolling checkpoint on each pointer frame.
    if not atom_ids or set(controller.rotation.atom_ids) != atom_ids:
        snapshot = _UpdateSnapshot.capture(controller, atom_ids)
        try:
            update()
            snapshot.release()
        except BaseException as original_error:
            snapshot.restore(original_error)
            raise
        return

    authority = getattr(controller, "_rotation_preview_authority", None)
    if authority is None:
        authority = capture_rotation_preview_authority(controller, atom_ids)
        cast(Any, controller)._rotation_preview_authority = authority
        transaction = getattr(controller, "_rotation_transaction", None)
        if transaction is not None and getattr(transaction, "preview", None) is None:
            transaction.preview = authority
    if not isinstance(authority, _RotationPreviewAuthority):
        raise RuntimeError("rotation preview owner is incomplete")
    if authority.atom_ids != frozenset(atom_ids):
        raise RuntimeError("rotation preview owner targets changed atoms")
    authority.run_update(update)


__all__ = [
    "capture_rotation_preview_authority",
    "run_rotation_preview_update",
]
