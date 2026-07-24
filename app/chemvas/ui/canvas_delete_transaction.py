from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from types import MemberDescriptorType
from typing import Any, cast

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.history_commands import (
    _atom_primitive_graphics_snapshots,
    _restore_bond_primitive_graphics_snapshots,
    _restore_scene_runtime_identity_final,
    _restore_scene_runtime_snapshot,
    _scene_runtime_snapshot,
    _SceneRuntimeSnapshot,
    _verify_scene_runtime_identity,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    ContainerGraphSnapshot as _ContainerGraphSnapshot,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    ObjectStateSnapshot as _ObjectStateSnapshot,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    SceneItemExactSnapshot as _SceneItemExactSnapshot,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
)

_SCENE_ITEM_DATA_ROLES = (0, 1, 2, 6, 9, 20, 21, 22)
_UNAVAILABLE_SCENE_ITEM_DATA = object()
_MISSING_ATTRIBUTE = object()


def _exact_value_matches(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    if isinstance(expected, (dict, list, set)):
        return False
    try:
        return bool(actual == expected)
    except BaseException:
        return False


def _semantic_value_matches(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    try:
        return bool(actual == expected)
    except BaseException:
        return False


def _collect_restore_errors(
    operation,
    destination: list[BaseException],
) -> None:
    try:
        result = operation()
    except BaseException as exc:
        destination.append(exc)
        return
    try:
        destination.extend(result)
    except BaseException as exc:
        destination.append(exc)


def _add_delete_rollback_note(
    original_error: BaseException,
    secondary_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Delete rollback also encountered "
                f"{type(secondary_error).__name__}: {secondary_error}"
            )
    except BaseException:
        return


def _capture_optional_attribute(
    target: object,
    name: str,
    *,
    default: object = None,
) -> object:
    """Read a capture root once, propagating errors from live descriptors."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        ):
            raise
        return default


def _capture_canvas_state_object(canvas, name: str) -> object | None:
    public_name = name[1:] if name.startswith("_") else name
    runtime_state = _capture_optional_attribute(canvas, "runtime_state")
    if runtime_state is not None:
        state = _capture_optional_attribute(runtime_state, public_name)
        if state is not None:
            return state
    return _capture_optional_attribute(canvas, public_name)


def _capture_raw_canvas_model_authority(
    canvas: object,
    containers: _ContainerGraphSnapshot,
) -> tuple[object | None, Callable[[BaseException], None]]:
    """Capture the production/backing model without invoking ``canvas.model``."""

    try:
        namespace_value = object.__getattribute__(canvas, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    else:
        namespace = namespace_value if isinstance(namespace_value, dict) else None

    root_key: str | None = None
    root_descriptor: MemberDescriptorType | None = None
    if namespace is not None and dict.__contains__(namespace, "model"):
        root_key = "model"
        model = dict.__getitem__(namespace, root_key)
    elif namespace is not None and dict.__contains__(namespace, "_model"):
        # Common property-backed lightweight canvas used by extensions/tests.
        root_key = "_model"
        model = dict.__getitem__(namespace, root_key)
    else:
        static_model = inspect.getattr_static(
            canvas,
            "model",
            _MISSING_ATTRIBUTE,
        )
        if isinstance(static_model, MemberDescriptorType):
            root_descriptor = static_model
            model = static_model.__get__(canvas, type(canvas))
        elif static_model is _MISSING_ATTRIBUTE:
            model = None
        else:
            # An arbitrary descriptor can mutate an otherwise unreachable model
            # before raising. Without a callback-free root there is no rollback
            # authority, so fail closed before invoking it.
            raise RuntimeError(
                "delete capture requires a callback-free canvas model authority"
            )

    model_namespace: dict[str, object] | None = None
    model_namespace_items: tuple[tuple[str, object], ...] = ()
    model_slots: list[tuple[MemberDescriptorType, object]] = []
    if model is not None:
        try:
            model_namespace_value = object.__getattribute__(model, "__dict__")
        except (AttributeError, TypeError):
            model_namespace_value = None
        if isinstance(model_namespace_value, dict):
            model_namespace = model_namespace_value
            model_namespace_items = tuple(
                (key, dict.__getitem__(model_namespace, key))
                for key in tuple(dict.__iter__(model_namespace))
            )
            for _key, value in model_namespace_items:
                containers.capture(value)
        else:
            for name in ("atoms", "bonds", "next_atom_id", "atom_annotations"):
                descriptor = inspect.getattr_static(
                    type(model),
                    name,
                    _MISSING_ATTRIBUTE,
                )
                if isinstance(descriptor, MemberDescriptorType):
                    value = descriptor.__get__(model, type(model))
                    model_slots.append((descriptor, value))
                    containers.capture(value)

    def restore(original_error: BaseException) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            attempt_errors: list[BaseException] = []
            try:
                if model_namespace is not None:
                    dict.clear(model_namespace)
                    dict.update(model_namespace, model_namespace_items)
                for descriptor, value in model_slots:
                    descriptor.__set__(model, value)
                if namespace is not None and root_key is not None:
                    dict.__setitem__(namespace, root_key, model)
                elif root_descriptor is not None:
                    root_descriptor.__set__(canvas, model)
            except BaseException as error:
                attempt_errors.append(error)
            attempt_errors.extend(containers.restore())
            if not attempt_errors:
                return
            errors.extend(attempt_errors)
        for recorded_error in errors:
            _add_delete_rollback_note(original_error, recorded_error)

    return model, restore


_DELETE_MUTATED_RUNTIME_FIELDS = (
    "graph_state",
    "atom_coords_3d_state",
    "atom_graphics_state",
    "bond_graphics_state",
    "mark_registry",
    "spatial_index_state",
    "handle_state",
    "hover_preview_state",
    "selection_style_state",
    "selection_outline_state",
    "selection_info_state",
    "scene_items_state",
    "group_state",
    "scene_clipboard_state",
    "insert_state",
    "rotation_state",
    "smiles_input_state",
    "history_state",
)


@dataclass(slots=True)
class _DeleteRawObjectSnapshot:
    """Callback-free object authority for a not-yet-published capture."""

    target: object
    namespace: dict[str, object] | None
    namespace_items: tuple[tuple[str, object], ...]
    slots: tuple[tuple[MemberDescriptorType, bool, object], ...]

    @classmethod
    def capture(
        cls,
        target: object,
        containers: _ContainerGraphSnapshot,
    ) -> _DeleteRawObjectSnapshot:
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
                containers.capture(value)

        captured_slots: list[tuple[MemberDescriptorType, bool, object]] = []
        seen_descriptors: set[int] = set()
        for owner in type(target).__mro__:
            for descriptor in owner.__dict__.values():
                if (
                    not isinstance(descriptor, MemberDescriptorType)
                    or id(descriptor) in seen_descriptors
                ):
                    continue
                seen_descriptors.add(id(descriptor))
                try:
                    value = descriptor.__get__(target, type(target))
                except AttributeError:
                    captured_slots.append((descriptor, False, _MISSING_ATTRIBUTE))
                    continue
                captured_slots.append((descriptor, True, value))
                containers.capture(value)
        return cls(
            target=target,
            namespace=namespace,
            namespace_items=namespace_items,
            slots=tuple(captured_slots),
        )

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        try:
            if self.namespace is not None:
                dict.clear(self.namespace)
                dict.update(self.namespace, self.namespace_items)
        except BaseException as error:
            errors.append(error)
        for descriptor, present, value in self.slots:
            try:
                if present:
                    descriptor.__set__(self.target, value)
                else:
                    try:
                        descriptor.__delete__(self.target)
                    except AttributeError:
                        pass
            except BaseException as error:
                errors.append(error)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        try:
            if self.namespace is not None:
                actual = tuple(self.namespace.items())
                exact = len(actual) == len(self.namespace_items) and all(
                    actual_key == expected_key and actual_value is expected_value
                    for (actual_key, actual_value), (
                        expected_key,
                        expected_value,
                    ) in zip(actual, self.namespace_items, strict=True)
                )
                if not exact:
                    raise RuntimeError(
                        "delete partial capture changed a raw object namespace"
                    )
        except BaseException as error:
            errors.append(error)
        for descriptor, present, expected in self.slots:
            try:
                try:
                    actual = descriptor.__get__(self.target, type(self.target))
                except AttributeError:
                    if present:
                        raise RuntimeError(
                            "delete partial capture removed a captured slot"
                        ) from None
                    continue
                if not present or actual is not expected:
                    raise RuntimeError(
                        "delete partial capture changed a raw object slot"
                    )
            except BaseException as error:
                errors.append(error)
        return errors


def _has_callback_free_delete_object_state(value: object) -> bool:
    if isinstance(value, (type, QObject)) or inspect.isroutine(value):
        return False
    try:
        namespace = object.__getattribute__(value, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict):
        return True
    return any(
        isinstance(descriptor, MemberDescriptorType)
        for owner in type(value).__mro__
        for descriptor in owner.__dict__.values()
    )


def _callback_free_delete_scene_members(scene: object) -> tuple[object, ...]:
    roots: list[object] = []
    try:
        namespace_value = object.__getattribute__(scene, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    else:
        namespace = namespace_value if isinstance(namespace_value, dict) else None
    if namespace is not None:
        roots.extend(dict.__getitem__(namespace, key) for key in tuple(namespace))
    for owner in type(scene).__mro__:
        for descriptor in owner.__dict__.values():
            if not isinstance(descriptor, MemberDescriptorType):
                continue
            try:
                roots.append(descriptor.__get__(scene, type(scene)))
            except AttributeError:
                continue

    members: list[object] = []
    seen_containers: set[int] = set()
    seen_objects = {id(scene)}

    def visit(value: object) -> None:
        if type(value) is dict:
            if id(value) in seen_containers:
                return
            seen_containers.add(id(value))
            for key, child in tuple(cast(dict, value).items()):
                visit(key)
                visit(child)
            return
        if type(value) in {list, set, tuple}:
            if id(value) in seen_containers:
                return
            seen_containers.add(id(value))
            for child in tuple(cast(Any, value)):
                visit(child)
            return
        if id(value) in seen_objects or not _has_callback_free_delete_object_state(
            value
        ):
            return
        seen_objects.add(id(value))
        members.append(value)

    for root in roots:
        visit(root)
    return tuple(members)


@dataclass(slots=True)
class _DeleteRawCaptureAuthority:
    containers: _ContainerGraphSnapshot
    objects: list[_DeleteRawObjectSnapshot]
    object_ids: set[int]

    @classmethod
    def capture_canvas(cls, canvas: object) -> _DeleteRawCaptureAuthority:
        authority = cls(_ContainerGraphSnapshot(), [], set())
        if not isinstance(canvas, QGraphicsView):
            # Own side effects from resolving a lightweight canvas's live
            # ``scene`` descriptor. Production views use the Qt base port.
            authority.capture_object(canvas)
        return authority

    def capture_object(self, target: object) -> None:
        if id(target) in self.object_ids:
            return
        self.object_ids.add(id(target))
        self.objects.append(_DeleteRawObjectSnapshot.capture(target, self.containers))

    def capture_scene(self, scene: object | None) -> None:
        if scene is None or isinstance(scene, QGraphicsScene):
            return
        self.capture_object(scene)
        for member in _callback_free_delete_scene_members(scene):
            self.capture_object(member)


def _delete_scene_for_capture(canvas) -> object | None:
    if isinstance(canvas, QGraphicsView):
        return QGraphicsView.scene(canvas)
    scene_method = _capture_optional_attribute(canvas, "scene")
    if not callable(scene_method):
        return None
    return scene_method()


def _delete_scene_items_for_capture(
    scene: object | None,
) -> tuple[object, ...]:
    if scene is None:
        return ()
    if isinstance(scene, QGraphicsScene):
        return tuple(QGraphicsScene.items(scene))
    items = _capture_optional_attribute(scene, "items")
    if not callable(items):
        return ()
    return tuple(items())


def _unwind_failed_delete_capture(
    original_error: BaseException,
    *,
    canvas: object,
    model: object,
    containers: _ContainerGraphSnapshot,
    raw_containers: _ContainerGraphSnapshot,
    objects: tuple[_ObjectStateSnapshot, ...],
    raw_objects: tuple[_DeleteRawObjectSnapshot, ...],
    scene_runtime: _SceneRuntimeSnapshot | None,
    scene_items: tuple[_SceneItemExactSnapshot, ...],
    scene_rect_snapshot: SceneRectSnapshot | None,
) -> None:
    errors: list[BaseException] = []
    _collect_restore_errors(containers.restore, errors)
    for object_snapshot in objects:
        _collect_restore_errors(object_snapshot.restore, errors)
    if model is not _MISSING_ATTRIBUTE:
        try:
            cast(Any, canvas).model = model
        except BaseException as error:
            errors.append(error)
    if scene_runtime is not None:
        try:
            errors.extend(
                _restore_scene_runtime_snapshot(
                    scene_runtime,
                    collect_errors=True,
                    defer_scene_identity_errors=True,
                )
            )
        except BaseException as error:
            errors.append(error)
    for item_snapshot in scene_items:
        _collect_restore_errors(item_snapshot.restore, errors)
    if scene_rect_snapshot is not None and scene_rect_snapshot.active:
        try:
            scene_rect_snapshot.restore()
        except BaseException as error:
            errors.append(error)

    # Raw namespaces are the earliest authority.  Reassert them after every
    # live restore callback, then repair their nested built-in containers and
    # verify the whole preflight graph.  A retry handles one-shot interruption
    # without replacing the exception that caused capture to abort.
    for _attempt in range(2):
        attempt_errors: list[BaseException] = []
        for raw_snapshot in raw_objects:
            attempt_errors.extend(raw_snapshot.restore())
        attempt_errors.extend(raw_containers.restore())
        for raw_snapshot in raw_objects:
            attempt_errors.extend(raw_snapshot.restore())
            attempt_errors.extend(raw_snapshot.verify())
        attempt_errors.extend(raw_containers.verify())
        if not attempt_errors:
            break
        errors.extend(attempt_errors)
    for recorded_error in errors:
        _add_delete_rollback_note(original_error, recorded_error)


@dataclass(slots=True)
class CanvasDeleteTransactionSnapshot:
    canvas: Any
    canvas_model: object
    history_service: object | None
    containers: _ContainerGraphSnapshot
    objects: tuple[_ObjectStateSnapshot, ...]
    scene_runtime: _SceneRuntimeSnapshot
    atom_primitive_graphics: tuple[Any, ...]
    scene_items: tuple[_SceneItemExactSnapshot, ...]
    scene: Any | None
    scene_rect_snapshot: SceneRectSnapshot | None
    scene_items_bounding_rect_getter: Any | None
    notify_history_change: Callable[[], object] | None
    history_notification_published: bool = False

    @classmethod
    def capture(
        cls,
        canvas,
        *,
        history_service=None,
        guard_scene_rect: bool = False,
    ) -> CanvasDeleteTransactionSnapshot:
        containers = _ContainerGraphSnapshot()
        raw_authority = _DeleteRawCaptureAuthority.capture_canvas(canvas)

        notify_history_change_value = _capture_optional_attribute(
            history_service,
            "notify_change",
        )
        notify_history_change = (
            notify_history_change_value
            if callable(notify_history_change_value)
            else None
        )
        objects: list[_ObjectStateSnapshot] = []
        snapshots_by_target: dict[int, _ObjectStateSnapshot] = {}

        def append(
            target: object | None,
            *,
            names: tuple[str, ...] | None = None,
        ) -> _ObjectStateSnapshot | None:
            if target is None:
                return None
            existing = snapshots_by_target.get(id(target))
            if existing is not None:
                return existing
            snapshot = _ObjectStateSnapshot.capture(
                target,
                containers,
                names=names,
            )
            if snapshot is None:
                return None
            snapshots_by_target[id(target)] = snapshot
            objects.append(snapshot)
            return snapshot

        def captured_value(
            target: object | None,
            snapshot: _ObjectStateSnapshot | None,
            name: str,
        ) -> object:
            if snapshot is not None and name in snapshot.attributes:
                return snapshot.attributes[name]
            return _capture_optional_attribute(target, name)

        model: object = _MISSING_ATTRIBUTE
        runtime_states: dict[str, object | None] = {}
        runtime_snapshots: dict[str, _ObjectStateSnapshot | None] = {}
        raw_model, restore_raw_model = _capture_raw_canvas_model_authority(
            canvas,
            containers,
        )
        try:
            model = _capture_optional_attribute(canvas, "model")
            if model is not raw_model:
                raise RuntimeError(
                    "delete capture canvas model changed during live preflight"
                )
            model_snapshot = append(
                model,
                names=("next_atom_id", "atom_annotations", "atoms", "bonds"),
            )
            # Reuse the exact values already read by the model snapshot. A live
            # descriptor can be side-effecting or fail on a second read; silently
            # treating that AttributeError as an absent collection would omit the
            # mutable Atom/Bond leaves from the savepoint.
            atoms = captured_value(model, model_snapshot, "atoms")
            if isinstance(atoms, dict):
                for atom in tuple(atoms.values()):
                    append(atom)
            bonds = captured_value(model, model_snapshot, "bonds")
            if isinstance(bonds, (list, tuple)):
                for bond in tuple(bonds):
                    append(bond)
            for name in _DELETE_MUTATED_RUNTIME_FIELDS:
                # A publication checkpoint intentionally excludes history:
                # pushing the command is the expected delta being published,
                # while the caller verifies that delta with its independently
                # captured HistoryStackSnapshot/checkpoint. Including the
                # runtime-owned alias here would reject every successful push
                # as a canvas mutation even when ``history_service=None`` was
                # explicitly requested for that purpose.
                if name == "history_state" and history_service is None:
                    runtime_states[name] = None
                    runtime_snapshots[name] = None
                    continue
                state = _capture_canvas_state_object(canvas, name)
                runtime_states[name] = state
                runtime_snapshots[name] = append(state)
            group_state = runtime_states["group_state"]
            groups = captured_value(
                group_state,
                runtime_snapshots["group_state"],
                "groups",
            )
            if isinstance(groups, dict):
                for group in groups.values():
                    append(group)
            append(_capture_optional_attribute(history_service, "state"))

            # Lightweight test canvases use this list as their history stack.
            # Capturing it also makes a mutate-then-raise fake push transactional.
            append(canvas, names=("pushed_commands",))
        except BaseException as original_error:
            restore_raw_model(original_error)
            _unwind_failed_delete_capture(
                original_error,
                canvas=canvas,
                model=model,
                containers=containers,
                raw_containers=raw_authority.containers,
                objects=tuple(objects),
                raw_objects=tuple(raw_authority.objects),
                scene_runtime=None,
                scene_items=(),
                scene_rect_snapshot=None,
            )
            raise

        object_snapshots = tuple(objects)
        scene_item_snapshots: list[_SceneItemExactSnapshot] = []
        scene_item_seen: set[int] = set()
        scene_runtime: _SceneRuntimeSnapshot | None = None
        scene: object | None = None
        scene_rect_snapshot: SceneRectSnapshot | None = None
        scene_items_bounding_rect_getter = None
        atom_primitive_graphics: tuple[Any, ...] = ()

        def capture_scene_item(scene_item: object) -> None:
            if scene_item is None or id(scene_item) in scene_item_seen:
                return
            scene_item_seen.add(id(scene_item))
            snapshot = _SceneItemExactSnapshot.capture(scene_item, containers)
            if snapshot is not None:
                scene_item_snapshots.append(snapshot)

        try:
            # Capture every live Qt item's base metadata and primitive state
            # before the shared scene-runtime reader invokes extension
            # callbacks such as ``data``.  If one of those callbacks mutates a
            # different item and terminates, the partial authority below can
            # restore that item even though no public transaction object exists.
            scene = _delete_scene_for_capture(canvas)
            # Establish raw scene/item/container authority before both the
            # live ``items`` descriptor lookup and its invocation.
            raw_authority.capture_scene(scene)
            initial_scene_items = _delete_scene_items_for_capture(scene)
            for scene_item in initial_scene_items:
                capture_scene_item(scene_item)

            scene_runtime = _scene_runtime_snapshot(canvas, strict=True)
            runtime_scene = getattr(scene_runtime, "scene", None)
            if scene is None:
                scene = runtime_scene
            elif (
                runtime_scene is not None
                and scene_runtime.scene_items is not None
                and runtime_scene is not scene
            ):
                raise RuntimeError(
                    "delete capture scene identity changed during preflight"
                )
            for scene_item in scene_runtime.scene_items or ():
                capture_scene_item(scene_item)

            scene_items_state = runtime_states["scene_items_state"]
            registered_ring_items = captured_value(
                scene_items_state,
                runtime_snapshots["scene_items_state"],
                "ring_items",
            )
            if isinstance(registered_ring_items, (list, tuple)):
                for scene_item in registered_ring_items:
                    capture_scene_item(scene_item)

            atom_primitive_graphics = _atom_primitive_graphics_snapshots(
                canvas,
                strict=True,
            )
            if scene is not None:
                items_bounding_rect = _capture_optional_attribute(
                    scene,
                    "itemsBoundingRect",
                )
                scene_items_bounding_rect_getter = (
                    items_bounding_rect if callable(items_bounding_rect) else None
                )
                scene_rect_snapshot = SceneRectSnapshot.capture(
                    scene,
                    guard_growth=guard_scene_rect,
                    scene_items_bounding_rect_getter=(scene_items_bounding_rect_getter),
                )
        except BaseException as original_error:
            _unwind_failed_delete_capture(
                original_error,
                canvas=canvas,
                model=model,
                containers=containers,
                raw_containers=raw_authority.containers,
                objects=object_snapshots,
                raw_objects=tuple(raw_authority.objects),
                scene_runtime=scene_runtime,
                scene_items=tuple(scene_item_snapshots),
                scene_rect_snapshot=scene_rect_snapshot,
            )
            raise

        assert scene_runtime is not None
        exact_scene_items = tuple(scene_item_snapshots)

        return cls(
            canvas=canvas,
            canvas_model=model,
            history_service=history_service,
            containers=containers,
            objects=object_snapshots,
            scene_runtime=scene_runtime,
            atom_primitive_graphics=atom_primitive_graphics,
            scene_items=exact_scene_items,
            scene=scene,
            scene_rect_snapshot=scene_rect_snapshot,
            scene_items_bounding_rect_getter=(scene_items_bounding_rect_getter),
            notify_history_change=notify_history_change,
        )

    def _verify_exact_authorities(
        self,
        *,
        include_rect: bool = True,
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        rect_snapshot = self.scene_rect_snapshot
        if include_rect and rect_snapshot is not None:
            try:
                if not _exact_value_matches(
                    rect_snapshot.live_rect(),
                    rect_snapshot.baseline_rect,
                ):
                    raise RuntimeError("delete rollback scene rect was re-mutated")
                if (
                    scene_rect_is_automatic(rect_snapshot.tracker.scene)
                    is not rect_snapshot.automatic
                ):
                    raise RuntimeError("delete rollback scene-rect mode was re-mutated")
                if rect_snapshot.tracker.depth != 0:
                    raise RuntimeError(
                        "delete rollback scene-rect guard remained active"
                    )
            except BaseException as exc:
                errors.append(exc)
        errors.extend(self.containers.verify())
        for snapshot in self.objects:
            errors.extend(snapshot.verify())
        if self.canvas.model is not self.canvas_model:
            errors.append(
                RuntimeError("delete rollback canvas-model identity was re-mutated")
            )
        for scene_item in self.scene_items:
            errors.extend(scene_item.verify())
        try:
            _verify_scene_runtime_identity(self.scene_runtime)
        except BaseException as exc:
            errors.append(exc)
        return errors

    def _restore_raw_authorities(
        self,
        errors: list[BaseException],
    ) -> None:
        _collect_restore_errors(self.containers.restore, errors)
        for snapshot in self.objects:
            _collect_restore_errors(snapshot.restore, errors)
        try:
            self.canvas.model = self.canvas_model
        except BaseException as exc:
            errors.append(exc)
        try:
            errors.extend(
                _restore_scene_runtime_snapshot(
                    self.scene_runtime,
                    collect_errors=True,
                    defer_scene_identity_errors=True,
                )
            )
        except BaseException as exc:
            errors.append(exc)
        for scene_item in self.scene_items:
            _collect_restore_errors(scene_item.restore, errors)
        _collect_restore_errors(
            lambda: _restore_bond_primitive_graphics_snapshots(
                self.scene_runtime.bond_primitive_graphics,
            ),
            errors,
        )
        _collect_restore_errors(
            lambda: _restore_bond_primitive_graphics_snapshots(
                self.atom_primitive_graphics,
            ),
            errors,
        )
        for scene_item in self.scene_items:
            _collect_restore_errors(scene_item.restore, errors)
        _collect_restore_errors(
            lambda: _restore_scene_runtime_identity_final(self.scene_runtime),
            errors,
        )

    def _silent_authority_pass(
        self,
    ) -> tuple[list[BaseException], list[BaseException]]:
        errors: list[BaseException] = []
        secondary_errors: list[BaseException] = []
        self._restore_raw_authorities(errors)
        rect_snapshot = self.scene_rect_snapshot
        if rect_snapshot is not None:
            recovery_errors = getattr(rect_snapshot, "recovery_errors", None)
            prior_recovery_count = (
                len(recovery_errors) if isinstance(recovery_errors, list) else 0
            )
            try:
                if rect_snapshot.active:
                    rect_snapshot.restore()
                else:
                    rect_snapshot.reassert()
            except BaseException as exc:
                errors.append(exc)
            if isinstance(recovery_errors, list):
                secondary_errors.extend(recovery_errors[prior_recovery_count:])
        errors.extend(self._verify_exact_authorities())
        return errors, secondary_errors

    def _reassert_after_notification(
        self,
        critical_errors: list[BaseException],
        secondary_errors: list[BaseException],
    ) -> None:
        recovered_pass_errors: list[BaseException] = []
        for attempt in range(2):
            pass_errors, pass_secondary = self._silent_authority_pass()
            secondary_errors.extend(pass_secondary)
            if not pass_errors:
                secondary_errors.extend(recovered_pass_errors)
                return
            if attempt == 0:
                recovered_pass_errors.extend(pass_errors)
                continue
            secondary_errors.extend(recovered_pass_errors)
            critical_errors.extend(pass_errors)

    def restore_with_result(self) -> RestoreOutcome:
        """Run the full absolute restore and classify its failures.

        Core model/container/scene/raw-graphics failures make the snapshot
        non-authoritative, but they do not make relative inverse commands safe:
        the full pass has already touched independent state. Canonical redraw
        and history notification failures are secondary once the raw savepoint
        has been restored.
        """

        critical_errors: list[BaseException] = []
        secondary_errors: list[BaseException] = []

        collect_errors = _collect_restore_errors

        collect_errors(self.containers.restore, critical_errors)
        for snapshot in self.objects:
            collect_errors(snapshot.restore, critical_errors)

        try:
            self.canvas.model = self.canvas_model
        except BaseException as exc:
            critical_errors.append(exc)

        try:
            critical_errors.extend(
                _restore_scene_runtime_snapshot(
                    self.scene_runtime,
                    collect_errors=True,
                    defer_scene_identity_errors=True,
                )
            )
        except BaseException as exc:
            critical_errors.append(exc)

        for scene_item in self.scene_items:
            collect_errors(scene_item.restore, critical_errors)

        # Ring removal can refresh surviving bond primitives in place. The
        # restored model, ring collection, and original graphics mappings are
        # now live again, so refresh those same item objects canonically.
        try:
            renderer = _capture_optional_attribute(self.canvas, "bond_renderer")
            update_bond_geometry = _capture_optional_attribute(
                renderer,
                "update_bond_geometry",
            )
            bonds = _capture_optional_attribute(
                self.canvas_model,
                "bonds",
                default=(),
            )
            if callable(update_bond_geometry):
                for bond_id, bond in enumerate(cast(Any, bonds)):
                    if bond is None:
                        continue
                    try:
                        update_bond_geometry(bond_id)
                    except BaseException as exc:
                        secondary_errors.append(exc)
        except BaseException as exc:
            # Canonical redraw is a dependent repair after the model and raw
            # savepoints. A live descriptor or iterator may terminate here;
            # record it, but never let it skip final raw authority, rect-last
            # recovery, history notification, or the structured result.
            secondary_errors.append(exc)
        finally:
            # A renderer callback may mutate a primitive before raising, and
            # the same callback may fail persistently during rollback. Keep the
            # canonical refresh as a best-effort repair for dependent geometry,
            # but make the exact pre-transaction raw graphics savepoint the
            # final authority so rollback itself cannot leave a partial line,
            # path, polygon, transform, or style mutation behind.
            collect_errors(
                lambda: _restore_bond_primitive_graphics_snapshots(
                    self.scene_runtime.bond_primitive_graphics,
                ),
                critical_errors,
            )
            collect_errors(
                lambda: _restore_bond_primitive_graphics_snapshots(
                    self.atom_primitive_graphics,
                ),
                critical_errors,
            )
            for scene_item in self.scene_items:
                collect_errors(scene_item.restore, critical_errors)

        # Raw scene-item restoration above includes zValue and other primitive
        # setters that can change the scene's final stacking after the earlier
        # runtime repair. Re-run the identity repair against the captured bound
        # ports and verify only after restoring the original signal-blocking
        # state; a custom unblock callback may itself mutate the scene.
        collect_errors(
            lambda: _restore_scene_runtime_identity_final(self.scene_runtime),
            critical_errors,
        )

        # Releasing the temporary explicit guard switches an automatic Qt
        # scene rect back to grow-only tracking. Canonical renderer refreshes
        # above can transiently move a primitive far away before raising, and
        # the final raw restore then shrinks the item without shrinking Qt's
        # cached automatic rect. Restore the exact rect only after every raw
        # geometry authority has run so no transient repair can poison it.
        if self.scene_rect_snapshot is not None:
            rect_recovery_errors = getattr(
                self.scene_rect_snapshot,
                "recovery_errors",
                None,
            )
            prior_recovery_count = (
                len(rect_recovery_errors)
                if isinstance(rect_recovery_errors, list)
                else 0
            )
            try:
                self.scene_rect_snapshot.restore()
            except BaseException as first_error:
                # A fail-once Qt/custom setter can mutate before raising. The
                # scene-rect savepoint deliberately remains active in that
                # case, so consume its supported idempotent retry before
                # deciding whether the absolute rollback is authoritative.
                secondary_errors.append(first_error)
                try:
                    self.scene_rect_snapshot.restore()
                except BaseException as retry_error:
                    critical_errors.append(retry_error)
            if not getattr(self.scene_rect_snapshot, "active", False) and isinstance(
                rect_recovery_errors, list
            ):
                secondary_errors.extend(
                    RuntimeError(
                        "scene-rect restore failed transiently before exact recovery: "
                        f"{type(error).__name__}: {error}"
                    )
                    for error in rect_recovery_errors[prior_recovery_count:]
                )
        try:
            # Scene-rect restoration is intentionally after the raw/final
            # identity repair, but a custom rect setter can still mutate the
            # scene while returning normally. Verify the captured bound ports
            # once more before publishing the history notification.
            _verify_scene_runtime_identity(self.scene_runtime)
        except BaseException as exc:
            critical_errors.append(exc)

        # A successful setter call is not an authority boundary. Verify the
        # entire captured graph, model identity, scene runtime, primitives, and
        # rect before allowing any observer to see rollback completion.
        try:
            critical_errors.extend(self._verify_exact_authorities())
        except BaseException as exc:
            critical_errors.append(exc)

        notify_history_change = self.notify_history_change
        if (
            not critical_errors
            and callable(notify_history_change)
            and not self.history_notification_published
        ):
            # Consume publication before entering untrusted callback code. A
            # callback that raises or re-mutates state is still one observable
            # publication and must never be repeated by an outer restore retry.
            self.history_notification_published = True
            try:
                notify_history_change()
            except BaseException as exc:
                secondary_errors.append(exc)
            # Notification is untrusted transaction code. Reassert without
            # notifying again; rect callbacks receive their own guarded preflight.
            self._reassert_after_notification(
                critical_errors,
                secondary_errors,
            )
        return RestoreOutcome(
            authoritative=not critical_errors,
            fallback_to_inverse=False,
            errors=tuple((*critical_errors, *secondary_errors)),
        )

    def restore(self) -> list[BaseException]:
        return list(self.restore_with_result().errors)

    def release(self) -> None:
        if self.scene_rect_snapshot is None:
            return
        self.scene_rect_snapshot.release(
            authoritative_scene_bounds_getter=(
                self.scene_items_bounding_rect_getter
                if callable(self.scene_items_bounding_rect_getter)
                else None
            )
        )


@contextmanager
def canvas_delete_transaction(
    canvas,
    *,
    history_service=None,
) -> Iterator[None]:
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history_service,
        guard_scene_rect=True,
    )
    try:
        yield
        snapshot.release()
    except BaseException as original_error:
        try:
            rollback_errors = snapshot.restore()
        except BaseException as caught_rollback_error:
            rollback_errors = [caught_rollback_error]
        for secondary_error in rollback_errors:
            _add_delete_rollback_note(original_error, secondary_error)
        raise


__all__ = [
    "CanvasDeleteTransactionSnapshot",
    "canvas_delete_transaction",
]
