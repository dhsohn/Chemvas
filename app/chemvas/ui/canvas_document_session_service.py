from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from functools import partial
from pathlib import Path
from types import MemberDescriptorType
from typing import Any, cast

from PyQt6.QtCore import QObject, QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from chemvas.core.document_io import (
    atomic_write_text,
    atomic_write_via_temp,
    read_document,
    write_document,
)
from chemvas.core.molfile import MolfileError, MolfileLimitError, write_molfile
from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.core.svg_roundtrip import (
    CHEMVAS_SVG_SCOPE_SELECTION,
    CHEMVAS_SVG_SCOPE_SHEET,
    create_editable_svg_payload,
    embed_chemvas_document_in_svg,
)
from chemvas.domain.document import (
    deserialize_model_state,
    selection_payload_to_canvas_state,
)
from chemvas.ui.canvas_document_export_access import export_canvas_scene_for
from chemvas.ui.canvas_document_state import (
    apply_document_settings,
    restore_document_groups,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    restore_document_projection_state,
    snapshot_canvas_document_state,
    snapshot_canvas_document_state_with_warnings,
)
from chemvas.ui.canvas_format_access import (
    clipboard_selection_version_for,
    file_format_version_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import bonds_for, set_model_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_scene_reset_access import clear_scene_for
from chemvas.ui.rdkit_adapter_access import (
    model_to_mol_block_for,
    model_to_xyz_block_for,
    preload_rdkit_for,
    rdkit_adapter_for,
    rdkit_is_loaded_for,
    rdkit_last_error_for,
)
from chemvas.ui.renderer_style_access import (
    bond_length_pt_for,
    bond_length_px_for,
    bond_line_width_for,
)
from chemvas.ui.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from chemvas.ui.selection_collection_access import (
    selected_ids_for,
    selection_items_for_copy_for,
)
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_style_access import set_selected_highlight_items_for
from chemvas.ui.structure_payload_access import (
    build_3d_conversion_payload_for,
    build_selected_3d_conversion_payload_for,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    SceneRectStateSnapshot,
    scene_rect_is_automatic,
    view_scene_rect_is_explicit,
)


@dataclass(frozen=True, slots=True)
class _HistoryAliasSnapshot:
    name: str
    owner: object
    owner_getter: Callable[[], object]
    owner_setter: Callable[[object], object]
    service_getter: Callable[[], object]
    service_setter: Callable[[object], object]

    def restore(self, service: object) -> None:
        self.owner_setter(self.owner)
        self.service_setter(service)
        self.verify(service)

    def verify(self, service: object) -> None:
        if self.owner_getter() is not self.owner:
            raise RuntimeError(f"document {self.name} history owner identity changed")
        if self.service_getter() is not service:
            raise RuntimeError(f"document {self.name} history service identity changed")


@dataclass(frozen=True, slots=True)
class _HistoryStateSnapshot:
    service: object
    state: object
    history: list
    history_items: tuple[Any, ...]
    redo_stack: list
    redo_items: tuple[Any, ...]
    enabled: bool
    state_getter: Callable[[], object]
    state_setter: Callable[[object], object]
    history_getter: Callable[[], object]
    history_setter: Callable[[object], object]
    redo_getter: Callable[[], object]
    redo_setter: Callable[[object], object]
    enabled_getter: Callable[[], object]
    enabled_setter: Callable[[bool], object]
    clear_port: Callable[[], object]
    aliases: tuple[_HistoryAliasSnapshot, ...]


_NO_CONTAINER_CONTENTS = object()
_MISSING_ATTRIBUTE = object()
_DOCUMENT_STACKING_FLAG_MASK = (
    QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent
    | QGraphicsItem.GraphicsItemFlag.ItemNegativeZStacksBehindParent
)


def _qt_base_port(target: object, owner: type, name: str) -> object:
    if not isinstance(target, owner):
        return _MISSING_ATTRIBUTE
    port = getattr(owner, name, None)
    if not callable(port):
        return _MISSING_ATTRIBUTE
    return partial(port, target)


def _qt_scene_transaction_port(scene: object, name: str) -> object:
    """Bind Qt scene ports without executing extension descriptors.

    Read-only authority always comes from QGraphicsScene itself. For mutation
    ports, ordinary Python method overrides remain part of the extension
    contract and can be bound callback-free from the class dictionary. A
    property or other live descriptor is not safe to invoke during capture, so
    it falls back to the Qt base implementation.
    """

    base_port = _qt_base_port(scene, QGraphicsScene, name)
    if base_port is _MISSING_ATTRIBUTE:
        return _MISSING_ATTRIBUTE
    if name in {
        "items",
        "sceneRect",
        "selectedItems",
        "focusItem",
        "signalsBlocked",
        "itemsBoundingRect",
    }:
        return base_port
    implementation = inspect.getattr_static(type(scene), name, _MISSING_ATTRIBUTE)
    if inspect.isfunction(implementation):
        return partial(implementation, scene)
    return base_port


# CanvasSceneResetService and the document-state restore helpers mutate only
# these runtime records. Keep this explicit so lifecycle-owning QObject fields
# (the RDKit idle timer/bridge) are never snapshotted or assigned reflectively.
_DOCUMENT_MUTATED_RUNTIME_FIELDS = (
    "sheet_setup_state",
    "selection_info_state",
    "graph_state",
    "group_state",
    "insert_state",
    "atom_coords_3d_state",
    "atom_graphics_state",
    "bond_graphics_state",
    "mark_registry",
    "spatial_index_state",
    "rotation_state",
    "handle_state",
    "selection_style_state",
    "selection_outline_state",
    "text_style_state",
    "tool_settings_state",
    "hover_preview_state",
    "scene_items_state",
    "smiles_input_state",
)


def _capture_optional_attribute(
    target: object,
    name: str,
    *,
    default: object = None,
) -> object:
    """Read one optional capture root without hiding live descriptor errors."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(
                target,
                name,
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        ):
            raise
        return default


def _add_scene_recovery_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(
            f"Document scene recovery also failed while {phase}: "
            f"{type(secondary_error).__name__}: {secondary_error}"
        )
    except BaseException:
        return


def _set_captured_scene_signals_blocked(
    block_signals,
    signals_blocked,
    blocked: bool,
) -> tuple[object, tuple[BaseException, ...]]:
    errors: list[BaseException] = []
    for _attempt in range(2):
        try:
            result = block_signals(blocked)
            if callable(signals_blocked) and bool(signals_blocked()) is not blocked:
                raise RuntimeError(
                    "scene blockSignals setter did not apply the requested state"
                )
        except BaseException as error:
            errors.append(error)
            continue
        return result, tuple(errors)
    first_error, second_error = errors
    _add_scene_recovery_note(
        first_error,
        second_error,
        phase="retrying a verified scene signal-state transition",
    )
    raise first_error


@contextmanager
def _blocked_captured_scene_signals(
    block_signals,
    signals_blocked,
):
    previous_blocked = bool(signals_blocked()) if callable(signals_blocked) else False
    original_error: BaseException | None = None
    entered = False
    try:
        try:
            returned_previous, entry_errors = _set_captured_scene_signals_blocked(
                block_signals,
                signals_blocked,
                True,
            )
        except BaseException as entry_error:
            try:
                _set_captured_scene_signals_blocked(
                    block_signals,
                    signals_blocked,
                    previous_blocked,
                )
            except BaseException as recovery_error:
                _add_scene_recovery_note(
                    entry_error,
                    recovery_error,
                    phase="restoring signals after a failed scene block",
                )
            raise
        if not callable(signals_blocked) and not entry_errors:
            previous_blocked = bool(returned_previous)
        entered = True
        yield
    except BaseException as error:
        original_error = error
        raise
    finally:
        if entered:
            try:
                _returned_previous, restore_errors = (
                    _set_captured_scene_signals_blocked(
                        block_signals,
                        signals_blocked,
                        previous_blocked,
                    )
                )
                if original_error is not None:
                    for repaired_error in restore_errors:
                        _add_scene_recovery_note(
                            original_error,
                            repaired_error,
                            phase="restoring the prior scene signal state",
                        )
            except BaseException as secondary_error:
                if original_error is not None:
                    _add_scene_recovery_note(
                        original_error,
                        secondary_error,
                        phase="restoring the prior scene signal state",
                    )
                else:
                    raise


@dataclass(frozen=True, slots=True)
class _AttributeSnapshot:
    value: Any
    contents: Any = _NO_CONTAINER_CONTENTS

    @classmethod
    def capture(cls, value: Any) -> _AttributeSnapshot:
        if isinstance(value, dict):
            return cls(value, dict(value))
        if isinstance(value, list):
            return cls(value, list(value))
        if isinstance(value, set):
            return cls(value, set(value))
        return cls(value)

    def restored_value(self) -> Any:
        if self.contents is _NO_CONTAINER_CONTENTS:
            return self.value
        if isinstance(self.value, dict):
            self.value.clear()
            self.value.update(self.contents)
        elif isinstance(self.value, list):
            self.value[:] = self.contents
        elif isinstance(self.value, set):
            self.value.clear()
            self.value.update(self.contents)
        return self.value

    def is_exact(self, current: Any) -> bool:
        if current is not self.value:
            return False
        if self.contents is _NO_CONTAINER_CONTENTS:
            return True
        if isinstance(self.value, dict):
            current_items = tuple(self.value.items())
            expected_items = tuple(self.contents.items())
            return len(current_items) == len(expected_items) and all(
                current_key is expected_key and current_value is expected_value
                for (current_key, current_value), (
                    expected_key,
                    expected_value,
                ) in zip(current_items, expected_items, strict=True)
            )
        if isinstance(self.value, list):
            return len(self.value) == len(self.contents) and all(
                current_item is expected_item
                for current_item, expected_item in zip(
                    self.value,
                    self.contents,
                    strict=True,
                )
            )
        if isinstance(self.value, set):
            return {id(item) for item in self.value} == {
                id(item) for item in self.contents
            }
        return False


@dataclass(frozen=True, slots=True)
class _ObjectStateSnapshot:
    target: Any
    attributes: dict[str, _AttributeSnapshot]

    def restore(self) -> None:
        for name, snapshot in self.attributes.items():
            setattr(self.target, name, snapshot.restored_value())

    def verify(self) -> None:
        for name, snapshot in self.attributes.items():
            if not snapshot.is_exact(getattr(self.target, name)):
                raise RuntimeError(
                    "document rollback did not restore exact object state: "
                    f"{type(self.target).__name__}.{name}"
                )


@dataclass(frozen=True, slots=True)
class _RawContainerSnapshot:
    target: object
    kind: str
    contents: tuple[object, ...]

    def restore(self) -> None:
        if self.kind == "dict":
            dictionary = cast(dict, self.target)
            dict.clear(dictionary)
            dict.update(
                dictionary,
                cast(tuple[tuple[object, object], ...], self.contents),
            )
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
            actual_ids = {id(value) for value in cast(set, self.target)}
            exact = actual_ids == {id(value) for value in self.contents}
        if not exact:
            raise RuntimeError("document partial scene capture changed a raw container")


@dataclass(frozen=True, slots=True)
class _RawObjectSnapshot:
    target: object
    namespace: dict[str, object] | None
    namespace_items: tuple[tuple[str, object], ...]
    slots: tuple[tuple[MemberDescriptorType, bool, object], ...]

    @classmethod
    def capture(
        cls,
        target: object,
        capture_container: Callable[[object], None],
    ) -> _RawObjectSnapshot:
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

        captured_slots: list[tuple[MemberDescriptorType, bool, object]] = []
        seen_descriptors: set[int] = set()
        for owner in type(target).__mro__:
            for descriptor in owner.__dict__.values():
                if not isinstance(descriptor, MemberDescriptorType):
                    continue
                if id(descriptor) in seen_descriptors:
                    continue
                seen_descriptors.add(id(descriptor))
                try:
                    value = descriptor.__get__(target, type(target))
                except AttributeError:
                    captured_slots.append((descriptor, False, _MISSING_ATTRIBUTE))
                    continue
                captured_slots.append((descriptor, True, value))
                capture_container(value)
        return cls(
            target=target,
            namespace=namespace,
            namespace_items=namespace_items,
            slots=tuple(captured_slots),
        )

    def restore(self) -> None:
        if self.namespace is not None:
            dict.clear(self.namespace)
            dict.update(self.namespace, self.namespace_items)
        for descriptor, present, value in self.slots:
            if present:
                descriptor.__set__(self.target, value)
                continue
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
                raise RuntimeError(
                    "document partial scene capture changed a raw object namespace"
                )
        for descriptor, present, expected in self.slots:
            try:
                actual = descriptor.__get__(self.target, type(self.target))
            except AttributeError:
                if present:
                    raise RuntimeError(
                        "document partial scene capture removed a captured slot"
                    ) from None
                continue
            if not present or actual is not expected:
                raise RuntimeError(
                    "document partial scene capture changed a raw object slot"
                )


@dataclass(frozen=True, slots=True)
class _PartialSceneCaptureSnapshot:
    objects: tuple[_RawObjectSnapshot, ...]
    containers: tuple[_RawContainerSnapshot, ...]

    @classmethod
    def capture(
        cls,
        scene: object,
        scene_items: tuple[object, ...],
    ) -> _PartialSceneCaptureSnapshot:
        containers: list[_RawContainerSnapshot] = []
        seen_containers: set[int] = set()

        def capture_container(value: object) -> None:
            if type(value) is dict:
                if id(value) in seen_containers:
                    return
                seen_containers.add(id(value))
                items = tuple(cast(dict, value).items())
                containers.append(
                    _RawContainerSnapshot(value, "dict", cast(tuple, items))
                )
                for key, child in items:
                    capture_container(key)
                    capture_container(child)
            elif type(value) is list:
                if id(value) in seen_containers:
                    return
                seen_containers.add(id(value))
                contents = tuple(cast(list, value))
                containers.append(_RawContainerSnapshot(value, "list", contents))
                for child in contents:
                    capture_container(child)
            elif type(value) is set:
                if id(value) in seen_containers:
                    return
                seen_containers.add(id(value))
                contents = tuple(cast(set, value))
                containers.append(_RawContainerSnapshot(value, "set", contents))
                for child in contents:
                    capture_container(child)
            elif type(value) is tuple:
                for child in cast(tuple, value):
                    capture_container(child)

        objects = tuple(
            _RawObjectSnapshot.capture(target, capture_container)
            for target in (scene, *scene_items)
        )
        return cls(objects=objects, containers=tuple(containers))

    def restore(self, original_error: BaseException) -> None:
        recorded_errors: list[BaseException] = []
        for _attempt in range(2):
            attempt_errors: list[BaseException] = []
            for object_snapshot in self.objects:
                try:
                    object_snapshot.restore()
                except BaseException as error:
                    attempt_errors.append(error)
            for container_snapshot in self.containers:
                try:
                    container_snapshot.restore()
                except BaseException as error:
                    attempt_errors.append(error)
            # A container may hold an object's namespace authority, while a
            # later container restore may have replaced one of its raw roots.
            # Reassert the object identities before verifying the whole graph.
            for object_snapshot in self.objects:
                try:
                    object_snapshot.restore()
                    object_snapshot.verify()
                except BaseException as error:
                    attempt_errors.append(error)
            for container_snapshot in self.containers:
                try:
                    container_snapshot.verify()
                except BaseException as error:
                    attempt_errors.append(error)
            if not attempt_errors:
                return
            recorded_errors.extend(attempt_errors)
        for recorded_error in recorded_errors:
            _add_scene_recovery_note(
                original_error,
                recorded_error,
                phase="unwinding a partial non-Qt scene capture",
            )


def _has_callback_free_object_state(value: object) -> bool:
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


def _callback_free_scene_graph_members(scene: object) -> tuple[object, ...]:
    """Find mutable objects reachable through the scene's raw containers.

    A non-Qt ``items()`` implementation is live extension code.  Preserve the
    item-like objects already held by its backing lists before invoking it, so
    a mutate-then-raise getter cannot move the baseline past its own mutation.
    The walk deliberately stops at each object leaf; only exact built-in
    containers are traversed, keeping capture linear in the raw scene graph.
    """

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
        if id(value) in seen_objects or not _has_callback_free_object_state(value):
            return
        seen_objects.add(id(value))
        members.append(value)

    for root in roots:
        visit(root)
    return tuple(members)


@dataclass(frozen=True, slots=True)
class _SelectedItemPorts:
    item: Any
    is_selected: Any
    set_selected: Any
    selected: bool

    def restore(self) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                if bool(self.is_selected()) is self.selected:
                    return
                self.set_selected(self.selected)
                if bool(self.is_selected()) is not self.selected:
                    raise RuntimeError(
                        "document rollback selection setter had no effect"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "document rollback could not restore item selection",
            errors,
        )


@dataclass(frozen=True, slots=True)
class _SceneRectCommitSavepoint:
    snapshot: SceneRectSnapshot
    scene_rect: QRectF
    automatic_attribute_present: bool
    automatic_attribute_value: object
    known_rect: QRectF
    baseline_rect: QRectF
    pending_rect: QRectF
    pending_expansions: dict
    pending_expansion_items: tuple
    pending_journal: list
    pending_journal_items: tuple
    depth: int
    internal_change: bool
    accept_internal_rect: bool
    observed_internal_rect: bool
    snapshot_active: bool

    @classmethod
    def capture(
        cls,
        snapshot: SceneRectSnapshot,
        scene: object,
        scene_rect_port,
    ) -> _SceneRectCommitSavepoint:
        automatic_attribute = "_chemvas_scene_rect_automatic"
        automatic_present = (
            inspect.getattr_static(
                scene,
                automatic_attribute,
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        )
        automatic_value = (
            getattr(scene, automatic_attribute)
            if automatic_present
            else _MISSING_ATTRIBUTE
        )
        tracker = snapshot.tracker
        return cls(
            snapshot=snapshot,
            scene_rect=QRectF(scene_rect_port()),
            automatic_attribute_present=automatic_present,
            automatic_attribute_value=automatic_value,
            known_rect=tracker.known_rect,
            baseline_rect=tracker.baseline_rect,
            pending_rect=tracker.pending_rect,
            pending_expansions=tracker.pending_expansions,
            pending_expansion_items=tuple(tracker.pending_expansions.items()),
            pending_journal=tracker.pending_journal,
            pending_journal_items=tuple(tracker.pending_journal),
            depth=tracker.depth,
            internal_change=tracker.internal_change,
            accept_internal_rect=tracker.accept_internal_rect,
            observed_internal_rect=tracker.observed_internal_rect,
            snapshot_active=snapshot.active,
        )

    def restore(self, scene: object, scene_set_rect_port) -> None:
        scene_set_rect_port(QRectF(self.scene_rect))
        automatic_attribute = "_chemvas_scene_rect_automatic"
        if self.automatic_attribute_present:
            setattr(
                scene,
                automatic_attribute,
                self.automatic_attribute_value,
            )
        elif (
            inspect.getattr_static(
                scene,
                automatic_attribute,
                _MISSING_ATTRIBUTE,
            )
            is not _MISSING_ATTRIBUTE
        ):
            delattr(scene, automatic_attribute)
        tracker = self.snapshot.tracker
        self.pending_expansions.clear()
        self.pending_expansions.update(self.pending_expansion_items)
        self.pending_journal[:] = self.pending_journal_items
        tracker.known_rect = self.known_rect
        tracker.baseline_rect = self.baseline_rect
        tracker.pending_rect = self.pending_rect
        tracker.pending_expansions = self.pending_expansions
        tracker.pending_journal = self.pending_journal
        tracker.depth = self.depth
        tracker.internal_change = self.internal_change
        tracker.accept_internal_rect = self.accept_internal_rect
        tracker.observed_internal_rect = self.observed_internal_rect
        self.snapshot.active = self.snapshot_active


@dataclass(frozen=True, slots=True)
class _SceneItemTopologySnapshot:
    item: object
    parent: object | None
    parent_getter: Callable[[], object]
    parent_setter: Callable[[object | None], object]
    z_value: float
    z_getter: Callable[[], float]
    z_setter: Callable[[float], object]
    stack_before: Callable[[object], object] | None
    stacking_flags: QGraphicsItem.GraphicsItemFlag | None
    flags_getter: Callable[[], object] | None
    flags_setter: Callable[[object], object] | None

    def restore_stacking_flags(self) -> None:
        if (
            self.stacking_flags is None
            or self.flags_getter is None
            or self.flags_setter is None
        ):
            return
        current = cast(QGraphicsItem.GraphicsItemFlag, self.flags_getter())
        if current & _DOCUMENT_STACKING_FLAG_MASK == self.stacking_flags:
            return
        restored = (current & ~_DOCUMENT_STACKING_FLAG_MASK) | self.stacking_flags
        self.flags_setter(restored)
        actual = cast(QGraphicsItem.GraphicsItemFlag, self.flags_getter())
        if actual & _DOCUMENT_STACKING_FLAG_MASK != self.stacking_flags:
            raise RuntimeError("document rollback did not restore item stacking flags")

    def restore_parent(self) -> None:
        if self.parent_getter() is self.parent:
            return
        self.parent_setter(self.parent)
        if self.parent_getter() is not self.parent:
            raise RuntimeError("document rollback did not restore item parent identity")

    def restore_z(self) -> None:
        if self.z_getter() == self.z_value:
            return
        self.z_setter(self.z_value)
        if self.z_getter() != self.z_value:
            raise RuntimeError("document rollback did not restore item z value")

    def verify(self) -> None:
        if self.parent_getter() is not self.parent:
            raise RuntimeError("document rollback changed item parent identity")
        if self.z_getter() != self.z_value:
            raise RuntimeError("document rollback changed item z value")
        if self.stacking_flags is not None and self.flags_getter is not None:
            actual = cast(QGraphicsItem.GraphicsItemFlag, self.flags_getter())
            if actual & _DOCUMENT_STACKING_FLAG_MASK != self.stacking_flags:
                raise RuntimeError("document rollback changed item stacking flags")


@dataclass(frozen=True, slots=True)
class _DetachedSceneSnapshot:
    canvas: object
    scene: Any
    all_scene_items: tuple[Any, ...]
    item_topology: tuple[_SceneItemTopologySnapshot, ...]
    top_level_items: tuple[Any, ...]
    scene_rect: Any
    scene_rect_snapshot: SceneRectSnapshot | None
    scene_rect_state_snapshot: SceneRectStateSnapshot | None
    scene_signals_blocked: bool | None
    view: Any | None
    view_scene_rect: Any | None
    view_scene_rect_explicit: bool
    view_transform: Any | None
    horizontal_scroll_bar: Any | None
    horizontal_scroll_value: int | None
    vertical_scroll_bar: Any | None
    vertical_scroll_value: int | None
    selected_items: tuple[Any, ...]
    selected_item_ports: tuple[_SelectedItemPorts, ...]
    focus_item: Any | None
    scene_items_port: Any
    scene_remove_item_port: Any
    scene_add_item_port: Any
    scene_rect_port: Any
    scene_set_rect_port: Any
    scene_selected_items_port: Any
    scene_focus_item_port: Any
    scene_set_focus_item_port: Any
    scene_block_signals_port: Any
    scene_signals_blocked_port: Any | None
    scene_items_bounding_rect_port: Any | None
    top_level_scene_ports: tuple[Any, ...]
    view_scene_rect_port: Any | None
    view_set_scene_rect_port: Any | None
    view_transform_port: Any | None
    view_set_transform_port: Any | None
    horizontal_scroll_value_port: Any | None
    horizontal_scroll_set_value_port: Any | None
    vertical_scroll_value_port: Any | None
    vertical_scroll_set_value_port: Any | None
    scene_rect_recovery_errors: list[BaseException]
    canvas_scene_port: Callable[[], object]
    canvas_set_scene_port: Callable[[object], object]
    selection_callbacks: tuple[Callable[[], object], ...]

    def _selection_signal(self):
        if not isinstance(self.scene, QGraphicsScene):
            return None
        return QGraphicsScene.selectionChanged.__get__(
            self.scene,
            type(self.scene),
        )

    def restore_canvas_scene_root(self) -> None:
        if self.canvas_scene_port() is not self.scene:
            self.canvas_set_scene_port(self.scene)
        if self.canvas_scene_port() is not self.scene:
            raise RuntimeError("document rollback did not restore canvas scene root")
        self.ensure_selection_wiring()

    def verify_canvas_scene_root(self) -> None:
        if self.canvas_scene_port() is not self.scene:
            raise RuntimeError("document transaction changed canvas scene root")

    def ensure_selection_wiring(self) -> None:
        signal = self._selection_signal()
        if signal is None:
            return
        for callback in self.selection_callbacks:
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass
            signal.connect(callback)

    @staticmethod
    def _topology_depths(
        snapshots: tuple[_SceneItemTopologySnapshot, ...],
    ) -> dict[int, int]:
        by_item = {id(snapshot.item): snapshot for snapshot in snapshots}
        depths: dict[int, int] = {}

        for start in snapshots:
            if id(start.item) in depths:
                continue
            path: list[_SceneItemTopologySnapshot] = []
            positions: dict[int, int] = {}
            current: _SceneItemTopologySnapshot | None = start
            base_depth = -1
            while current is not None:
                item_id = id(current.item)
                if item_id in depths:
                    base_depth = depths[item_id]
                    break
                if item_id in positions:
                    raise RuntimeError(
                        "document scene snapshot contains a parent cycle"
                    )
                positions[item_id] = len(path)
                path.append(current)
                current = by_item.get(id(current.parent))
            while path:
                resolved = path.pop()
                base_depth += 1
                depths[id(resolved.item)] = base_depth
        return depths

    def _restore_topology_and_stacking_once(self) -> list[BaseException]:
        snapshots = self.item_topology
        if not snapshots:
            return []
        depths = self._topology_depths(snapshots)
        errors: list[BaseException] = []
        for snapshot in snapshots:
            try:
                snapshot.restore_stacking_flags()
            except BaseException as error:
                errors.append(error)
        for snapshot in sorted(
            snapshots,
            key=lambda candidate: depths[id(candidate.item)],
        ):
            try:
                snapshot.restore_parent()
            except BaseException as error:
                errors.append(error)
        for snapshot in snapshots:
            try:
                snapshot.restore_z()
            except BaseException as error:
                errors.append(error)

        sibling_groups: dict[tuple[int, float], list[_SceneItemTopologySnapshot]] = {}
        for snapshot in snapshots:
            sibling_groups.setdefault(
                (id(snapshot.parent), snapshot.z_value),
                [],
            ).append(snapshot)
        try:
            before_stacking = tuple(self.scene_items_port())
            stacking_is_exact = len(before_stacking) == len(
                self.all_scene_items
            ) and all(
                current is expected
                for current, expected in zip(
                    before_stacking,
                    self.all_scene_items,
                    strict=True,
                )
            )
        except BaseException as error:
            errors.append(error)
            stacking_is_exact = False
        if not stacking_is_exact:
            for siblings in sibling_groups.values():
                for higher, lower in zip(siblings, siblings[1:], strict=False):
                    try:
                        if lower.stack_before is None:
                            raise RuntimeError(
                                "document scene item has no captured stacking port"
                            )
                        lower.stack_before(higher.item)
                    except BaseException as error:
                        errors.append(error)

        for snapshot in snapshots:
            try:
                snapshot.verify()
            except BaseException as error:
                errors.append(error)
        try:
            current_items = tuple(self.scene_items_port())
            if len(current_items) != len(self.all_scene_items) or any(
                current is not expected
                for current, expected in zip(
                    current_items,
                    self.all_scene_items,
                    strict=True,
                )
            ):
                raise RuntimeError(
                    "document rollback did not restore topology-aware scene order"
                )
        except BaseException as error:
            errors.append(error)
        return errors

    def detach(self) -> None:
        try:
            self.verify_canvas_scene_root()
            with _blocked_captured_scene_signals(
                self.scene_block_signals_port,
                self.scene_signals_blocked_port,
            ):
                for item, scene_port in zip(
                    self.top_level_items,
                    self.top_level_scene_ports,
                    strict=True,
                ):
                    self.scene_remove_item_port(item)
                    if scene_port() is self.scene:
                        raise RuntimeError(
                            "document detach did not remove a scene-item root"
                        )
        except BaseException as original_error:
            try:
                self.restore()
            except BaseException as secondary_error:
                _add_scene_recovery_note(
                    original_error,
                    secondary_error,
                    phase="reattaching a partially detached scene",
                )
            raise

    def restore(self) -> None:
        self.restore_canvas_scene_root()
        first_topology_errors: list[BaseException] = []
        with _blocked_captured_scene_signals(
            self.scene_block_signals_port,
            self.scene_signals_blocked_port,
        ):
            # QGraphicsScene.items() is topmost-first. Re-add bottommost-first
            # so equal-z stacking and parent/child history references survive.
            roots = tuple(
                zip(
                    self.top_level_items,
                    self.top_level_scene_ports,
                    strict=True,
                )
            )
            current_items = tuple(self.scene_items_port())
            scene_already_exact = len(current_items) == len(
                self.all_scene_items
            ) and all(
                current is expected
                for current, expected in zip(
                    current_items,
                    self.all_scene_items,
                    strict=True,
                )
            )
            if not scene_already_exact:
                saved_item_ids = {id(item) for item in self.all_scene_items}
                replacement_items = tuple(
                    item for item in current_items if id(item) not in saved_item_ids
                )
                replacement_item_ids = {id(item) for item in replacement_items}
                replacement_roots: list[object] = []
                for item in replacement_items:
                    parent_item = _capture_optional_attribute(
                        item,
                        "parentItem",
                    )
                    parent = parent_item() if callable(parent_item) else None
                    if parent is None or id(parent) not in replacement_item_ids:
                        replacement_roots.append(item)
                for item in replacement_roots:
                    self.scene_remove_item_port(item)
                remaining_replacement_ids = {
                    id(item)
                    for item in self.scene_items_port()
                    if id(item) not in saved_item_ids
                }
                if remaining_replacement_ids:
                    raise RuntimeError(
                        "document rollback could not remove replacement scene items"
                    )
                # A partial detach can leave an arbitrary suffix of roots in
                # the scene. Normalize every saved root to detached first;
                # otherwise appending missing roots cannot recover order.
                for item, scene_port in roots:
                    if scene_port() is not self.scene:
                        continue
                    self.scene_remove_item_port(item)
                    if scene_port() is self.scene:
                        raise RuntimeError(
                            "document rollback could not reset a scene-item root"
                        )
                reattach_roots = (
                    reversed(roots) if isinstance(self.scene, QObject) else iter(roots)
                )
                for item, scene_port in reattach_roots:
                    self.scene_add_item_port(item)
                    if scene_port() is not self.scene:
                        raise RuntimeError(
                            "document rollback did not reattach a scene-item root"
                        )
            # Membership alone is insufficient: a callback can keep every
            # captured wrapper live while changing child ownership or z-depth.
            # Restore the captured parent graph before z and sibling order.
            first_topology_errors.extend(self._restore_topology_and_stacking_once())
            if self.scene_rect_snapshot is not None:
                guard_recovery_count = len(self.scene_rect_snapshot.recovery_errors)
                self.scene_rect_snapshot.restore()
                assert self.scene_rect_state_snapshot is not None
                state_recovery_count = len(
                    self.scene_rect_state_snapshot.recovery_errors
                )
                self.scene_rect_state_snapshot.restore()
                self.scene_rect_recovery_errors.extend(
                    self.scene_rect_snapshot.recovery_errors[guard_recovery_count:]
                )
                self.scene_rect_recovery_errors.extend(
                    self.scene_rect_state_snapshot.recovery_errors[
                        state_recovery_count:
                    ]
                )
            else:
                self.scene_set_rect_port(self.scene_rect)
                self.scene._chemvas_scene_rect_automatic = False
            if self.view is not None:
                if self.view_scene_rect_explicit:
                    assert callable(self.view_set_scene_rect_port)
                    assert self.view_scene_rect is not None
                    self.view_set_scene_rect_port(QRectF(self.view_scene_rect))
                    self.view._chemvas_view_scene_rect_explicit = True
                else:
                    assert callable(self.view_set_scene_rect_port)
                    self.view_set_scene_rect_port(QRectF())
                    self.view._chemvas_view_scene_rect_explicit = False
                if self.view_transform is not None:
                    if callable(self.view_set_transform_port):
                        self.view_set_transform_port(self.view_transform)
            # Restore selected items first and captured-false peers last so a
            # selection callback cannot leave an unrelated peer newly selected.
            for selected_state in (True, False):
                for selected_item in self.selected_item_ports:
                    if selected_item.selected is selected_state:
                        selected_item.restore()
            self.scene_set_focus_item_port(self.focus_item)
            # Selection/focus restoration can ask a view to reveal an item.
            # Restore the exact pan last, after every operation that may scroll.
            if (
                callable(self.horizontal_scroll_set_value_port)
                and self.horizontal_scroll_value is not None
            ):
                self.horizontal_scroll_set_value_port(self.horizontal_scroll_value)
            if (
                callable(self.vertical_scroll_set_value_port)
                and self.vertical_scroll_value is not None
            ):
                self.vertical_scroll_set_value_port(self.vertical_scroll_value)
            # Selection, focus, view and pan callbacks are untrusted and can
            # synchronously change parent/z/sibling order. Topology is the
            # second and final writer; setters that succeeded in the first
            # pass are already exact and therefore skipped.
            final_topology_errors = self._restore_topology_and_stacking_once()
            if final_topology_errors:
                raise BaseExceptionGroup(
                    "document scene topology rollback failed after two passes",
                    [*first_topology_errors, *final_topology_errors],
                )
        if self.scene_signals_blocked is not None:
            _set_captured_scene_signals_blocked(
                self.scene_block_signals_port,
                self.scene_signals_blocked_port,
                self.scene_signals_blocked,
            )
        self.restore_canvas_scene_root()
        self._verify_restored_state()

    def _verify_restored_state(self) -> None:
        """Verify live UI state omitted from serialized document equality."""

        self.verify_canvas_scene_root()

        if (
            not callable(self.scene_rect_port)
            or self.scene_rect_port() != self.scene_rect
        ):
            raise RuntimeError("document rollback did not restore the scene rect")
        if (
            self.scene_rect_snapshot is not None
            and scene_rect_is_automatic(self.scene)
            is not self.scene_rect_snapshot.automatic
        ):
            raise RuntimeError("document rollback did not restore scene-rect mode")

        current_items = tuple(self.scene_items_port())
        if len(current_items) != len(self.all_scene_items) or any(
            current is not expected
            for current, expected in zip(
                current_items,
                self.all_scene_items,
                strict=False,
            )
        ):
            raise RuntimeError(
                "document rollback did not restore the exact scene-item set"
            )
        current_item_ids = {id(item) for item in current_items}
        for topology in self.item_topology:
            topology.verify()
        for item, scene_port in zip(
            self.top_level_items,
            self.top_level_scene_ports,
            strict=True,
        ):
            if id(item) not in current_item_ids:
                raise RuntimeError("document rollback omitted a top-level scene item")
            if scene_port() is not self.scene:
                raise RuntimeError(
                    "document rollback did not reattach a top-level scene item"
                )

        if callable(self.scene_selected_items_port):
            actual_ids = {id(item) for item in self.scene_selected_items_port()}
            expected_ids = {id(item) for item in self.selected_items}
            if actual_ids != expected_ids:
                raise RuntimeError(
                    "document rollback did not restore the selected-item set"
                )
        for selected_item in self.selected_item_ports:
            if bool(selected_item.is_selected()) is not selected_item.selected:
                raise RuntimeError("document rollback did not restore item selection")

        if (
            not callable(self.scene_focus_item_port)
            or self.scene_focus_item_port() is not self.focus_item
        ):
            raise RuntimeError("document rollback did not restore scene focus")

        if self.view is not None:
            if (
                not callable(self.view_scene_rect_port)
                or self.view_scene_rect_port() != self.view_scene_rect
            ):
                raise RuntimeError("document rollback did not restore the view rect")
            if (
                view_scene_rect_is_explicit(self.view)
                is not self.view_scene_rect_explicit
            ):
                raise RuntimeError("document rollback did not restore view-rect mode")
            if self.view_transform is not None:
                if (
                    not callable(self.view_transform_port)
                    or self.view_transform_port() != self.view_transform
                ):
                    raise RuntimeError(
                        "document rollback did not restore the view transform"
                    )

        for value_port, expected, axis in (
            (
                self.horizontal_scroll_value_port,
                self.horizontal_scroll_value,
                "horizontal",
            ),
            (
                self.vertical_scroll_value_port,
                self.vertical_scroll_value,
                "vertical",
            ),
        ):
            if value_port is None or expected is None:
                continue
            if not callable(value_port) or int(value_port()) != expected:
                raise RuntimeError(
                    f"document rollback did not restore {axis} viewport pan"
                )

        if self.scene_signals_blocked is not None:
            if (
                not callable(self.scene_signals_blocked_port)
                or bool(self.scene_signals_blocked_port())
                is not self.scene_signals_blocked
            ):
                raise RuntimeError(
                    "document rollback did not restore scene signal state"
                )

    def commit_replacement(self) -> None:
        self.verify_canvas_scene_root()
        snapshot = self.scene_rect_snapshot
        if snapshot is None:
            self.ensure_selection_wiring()
            return
        commit_savepoint = _SceneRectCommitSavepoint.capture(
            snapshot,
            self.scene,
            self.scene_rect_port,
        )
        target_automatic = scene_rect_is_automatic(self.scene)
        target_rect = QRectF(commit_savepoint.scene_rect)
        expanded_rect = None
        if target_automatic and callable(self.scene_items_bounding_rect_port):
            expanded_rect = QRectF(self.scene_items_bounding_rect_port())
        try:
            snapshot.commit_replacement(expanded_rect)
            if scene_rect_is_automatic(self.scene) is not target_automatic:
                raise RuntimeError(
                    "document replacement did not preserve scene-rect mode"
                )
            current_rect = QRectF(self.scene_rect_port())
            if target_automatic:
                if (
                    expanded_rect is not None
                    and not expanded_rect.isNull()
                    and not current_rect.contains(expanded_rect)
                ):
                    raise RuntimeError(
                        "document replacement automatic rect omitted target items"
                    )
            elif current_rect != target_rect:
                raise RuntimeError(
                    "document replacement did not preserve its explicit scene rect"
                )
            expected_depth = (
                max(0, commit_savepoint.depth - 1)
                if snapshot.automatic and snapshot.guarded
                else commit_savepoint.depth
            )
            if snapshot.active or snapshot.tracker.depth != expected_depth:
                raise RuntimeError(
                    "document replacement did not commit its scene-rect guard"
                )
            assert self.scene_rect_state_snapshot is not None
            self.scene_rect_state_snapshot.release()
            self.verify_canvas_scene_root()
            self.ensure_selection_wiring()
        except BaseException as original_error:
            # Keep the old-document savepoint usable when post-commit
            # verification discovers a no-op or partial finalizer.
            try:
                commit_savepoint.restore(
                    self.scene,
                    self.scene_set_rect_port,
                )
            except BaseException as rearm_error:
                _add_scene_recovery_note(
                    original_error,
                    rearm_error,
                    phase="re-arming the old scene-rect savepoint",
                )
            raise


@dataclass(slots=True)
class _DocumentStatusPublication:
    callback: Callable[[str, str], object] | None
    cache: tuple[str, str] | None
    published: bool = False

    def publish(self, original_error: BaseException) -> bool:
        if self.published:
            return False
        self.published = True
        if self.callback is None or self.cache is None:
            return False
        try:
            self.callback(*self.cache)
        except BaseException as publication_error:
            _add_scene_recovery_note(
                original_error,
                publication_error,
                phase="republishing the restored document selection status",
            )
        return True


@dataclass(frozen=True, slots=True)
class _CanvasRollbackSnapshot:
    document_state: dict
    model: Any
    object_states: tuple[_ObjectStateSnapshot, ...]
    scene: _DetachedSceneSnapshot | None
    status_publication: _DocumentStatusPublication

    def detach_scene_items(self) -> None:
        if self.scene is not None:
            self.scene.detach()

    def restore_live_state(self, canvas) -> None:
        if self.scene is not None:
            self.scene.restore_canvas_scene_root()
        canvas.model = self.model
        for snapshot in self.object_states:
            snapshot.restore()
        if self.scene is not None:
            self.scene.restore()
        # Reattaching and reselecting Qt items can refresh derived runtime
        # registries even while scene signals are blocked. Those registries
        # are rollback authority too, so make the captured object state the
        # final silent writer after every scene-side operation.
        for snapshot in self.object_states:
            snapshot.restore()

    def commit_replacement(self) -> None:
        if self.scene is not None:
            self.scene.verify_canvas_scene_root()
            self.scene.commit_replacement()
            self.scene.verify_canvas_scene_root()


def _snapshot_object_state(
    target: Any,
    *,
    names: tuple[str, ...] | None = None,
) -> _ObjectStateSnapshot | None:
    if names is None:
        if is_dataclass(target) and not isinstance(target, type):
            names = tuple(field.name for field in fields(target))
        else:
            namespace = getattr(target, "__dict__", None)
            if not isinstance(namespace, dict):
                return None
            names = tuple(namespace)
    # A later descriptor can mutate a field whose live value was already read
    # and then terminate before this function publishes its ordinary snapshot.
    # Establish a callback-free raw savepoint first so partial capture has an
    # owner even while the public snapshot is still under construction.
    raw_snapshot = _PartialSceneCaptureSnapshot.capture(target, ())
    attributes: dict[str, _AttributeSnapshot] = {}
    try:
        for name in names:
            if (
                inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
                is _MISSING_ATTRIBUTE
            ):
                continue
            # Static inspection distinguishes a genuinely absent optional field
            # from AttributeError raised inside a live property. Read each present
            # value exactly once so exact capture cannot silently omit it.
            attributes[name] = _AttributeSnapshot.capture(getattr(target, name))
    except BaseException as original_error:
        raw_snapshot.restore(original_error)
        raise
    if not attributes:
        return None
    return _ObjectStateSnapshot(target=target, attributes=attributes)


def _snapshot_canvas_scene_impl(  # noqa: C901
    canvas,
    *,
    publish_partial_capture: Callable[[_PartialSceneCaptureSnapshot], None],
) -> _DetachedSceneSnapshot | None:
    if not isinstance(canvas, QGraphicsView):
        # Own mutations performed while resolving a lightweight canvas's live
        # scene descriptor.  Real views use the callback-free Qt base port.
        publish_partial_capture(_PartialSceneCaptureSnapshot.capture(canvas, ()))
    scene_method = _qt_base_port(canvas, QGraphicsView, "scene")
    if scene_method is _MISSING_ATTRIBUTE:
        scene_method = _capture_optional_attribute(canvas, "scene")
    if not callable(scene_method):
        return None
    set_scene_method = _qt_base_port(canvas, QGraphicsView, "setScene")
    if set_scene_method is _MISSING_ATTRIBUTE:
        set_scene_method = _capture_optional_attribute(canvas, "setScene")
    if not callable(set_scene_method):

        def verify_immutable_scene_root(expected: object) -> None:
            if cast(Callable[[], object], scene_method)() is not expected:
                raise RuntimeError(
                    "live document canvas has no scene-root restore port"
                )

        set_scene_method = verify_immutable_scene_root
    scene = scene_method()
    if scene is None:
        return None

    if not isinstance(scene, QGraphicsScene):
        # This authority must precede both the live ``items`` descriptor lookup
        # and its invocation.  The later snapshot still owns mutations from
        # every subsequent port lookup, while this one can rewind ``items``
        # itself and the raw item objects already held by scene containers.
        publish_partial_capture(
            _PartialSceneCaptureSnapshot.capture(
                scene,
                _callback_free_scene_graph_members(scene),
            )
        )
    items_method = _qt_scene_transaction_port(scene, "items")
    if items_method is _MISSING_ATTRIBUTE:
        items_method = _capture_optional_attribute(scene, "items")
    if not callable(items_method):
        if isinstance(scene, QObject):
            raise RuntimeError("live document scene does not expose an items snapshot")
        return None
    scene_items = tuple(items_method())
    if not isinstance(scene, QGraphicsScene):
        publish_partial_capture(
            _PartialSceneCaptureSnapshot.capture(scene, scene_items)
        )

    scene_methods: dict[str, object] = {}
    for method in (
        "removeItem",
        "addItem",
        "sceneRect",
        "setSceneRect",
        "selectedItems",
        "focusItem",
        "setFocusItem",
        "blockSignals",
    ):
        port = _qt_scene_transaction_port(scene, method)
        if port is _MISSING_ATTRIBUTE:
            port = _capture_optional_attribute(scene, method)
        scene_methods[method] = port
    items_bounding_rect_method = _qt_scene_transaction_port(scene, "itemsBoundingRect")
    if items_bounding_rect_method is _MISSING_ATTRIBUTE:
        items_bounding_rect_method = _capture_optional_attribute(
            scene,
            "itemsBoundingRect",
        )
    if isinstance(scene, QObject) and not callable(items_bounding_rect_method):
        raise RuntimeError(
            "live document scene has no itemsBoundingRect transaction port"
        )
    missing_ports = tuple(
        name for name, port in scene_methods.items() if not callable(port)
    )
    if missing_ports:
        if scene_items or isinstance(scene, QObject):
            raise RuntimeError(
                "live document scene has incomplete transaction ports: "
                + ", ".join(missing_ports)
            )
        return None
    scene_rect_method = scene_methods["sceneRect"]
    set_scene_rect_method = scene_methods["setSceneRect"]
    remove_item_method = scene_methods["removeItem"]
    add_item_method = scene_methods["addItem"]
    selected_items_method = scene_methods["selectedItems"]
    focus_item_method = scene_methods["focusItem"]
    set_focus_item_method = scene_methods["setFocusItem"]
    block_signals_method = scene_methods["blockSignals"]
    assert callable(scene_rect_method)
    assert callable(set_scene_rect_method)
    assert callable(remove_item_method)
    assert callable(add_item_method)
    assert callable(selected_items_method)
    assert callable(focus_item_method)
    assert callable(set_focus_item_method)
    assert callable(block_signals_method)
    top_level_items: list[Any] = []
    top_level_scene_ports: list[Any] = []
    item_topology: list[_SceneItemTopologySnapshot] = []
    for item in scene_items:
        parent_item_method = _qt_base_port(item, QGraphicsItem, "parentItem")
        set_parent_item = _qt_base_port(item, QGraphicsItem, "setParentItem")
        z_value_method = _qt_base_port(item, QGraphicsItem, "zValue")
        set_z_value = _qt_base_port(item, QGraphicsItem, "setZValue")
        stack_before = _qt_base_port(item, QGraphicsItem, "stackBefore")
        flags_getter = _qt_base_port(item, QGraphicsItem, "flags")
        flags_setter = _qt_base_port(item, QGraphicsItem, "setFlags")
        if parent_item_method is _MISSING_ATTRIBUTE:
            parent_item_method = _capture_optional_attribute(item, "parentItem")
        if set_parent_item is _MISSING_ATTRIBUTE:
            set_parent_item = _capture_optional_attribute(item, "setParentItem")
        if z_value_method is _MISSING_ATTRIBUTE:
            z_value_method = _capture_optional_attribute(item, "zValue")
        if set_z_value is _MISSING_ATTRIBUTE:
            set_z_value = _capture_optional_attribute(item, "setZValue")
        if stack_before is _MISSING_ATTRIBUTE:
            stack_before = _capture_optional_attribute(item, "stackBefore")
        topology_ports = (
            parent_item_method,
            set_parent_item,
            z_value_method,
            set_z_value,
        )
        if isinstance(item, QGraphicsItem) and not all(
            callable(port) for port in topology_ports
        ):
            raise RuntimeError(
                "live document scene item has incomplete parent/z restore ports"
            )
        parent = parent_item_method() if callable(parent_item_method) else None
        if all(callable(port) for port in topology_ports):
            captured_z_getter = cast(Callable[[], float], z_value_method)
            stacking_flags = (
                cast(QGraphicsItem.GraphicsItemFlag, flags_getter())
                & _DOCUMENT_STACKING_FLAG_MASK
                if callable(flags_getter) and callable(flags_setter)
                else None
            )
            item_topology.append(
                _SceneItemTopologySnapshot(
                    item=item,
                    parent=parent,
                    parent_getter=cast(Callable[[], object], parent_item_method),
                    parent_setter=cast(
                        Callable[[object | None], object],
                        set_parent_item,
                    ),
                    z_value=float(captured_z_getter()),
                    z_getter=captured_z_getter,
                    z_setter=cast(Callable[[float], object], set_z_value),
                    stack_before=(
                        cast(Callable[[object], object], stack_before)
                        if callable(stack_before)
                        else None
                    ),
                    stacking_flags=stacking_flags,
                    flags_getter=(
                        cast(Callable[[], object], flags_getter)
                        if callable(flags_getter)
                        else None
                    ),
                    flags_setter=(
                        cast(Callable[[object], object], flags_setter)
                        if callable(flags_setter)
                        else None
                    ),
                )
            )
        if parent is not None:
            continue
        scene_port = _qt_base_port(item, QGraphicsItem, "scene")
        if scene_port is _MISSING_ATTRIBUTE:
            scene_port = _capture_optional_attribute(item, "scene")
        if not callable(scene_port):
            raise RuntimeError("live document scene root has no membership port")
        if scene_port() is not scene:
            raise RuntimeError("document scene items snapshot contains a detached root")
        top_level_items.append(item)
        top_level_scene_ports.append(scene_port)
    scene_rect = scene_rect_method()
    view = None
    view_scene_rect = None
    view_scene_rect_explicit = False
    view_transform = None
    horizontal_scroll_bar = None
    horizontal_scroll_value = None
    vertical_scroll_bar = None
    vertical_scroll_value = None
    horizontal_scroll_value_port = None
    horizontal_scroll_set_value_port = None
    vertical_scroll_value_port = None
    vertical_scroll_set_value_port = None
    view_transform_method = None
    view_set_transform = None
    view_scene_rect_method = _capture_optional_attribute(canvas, "sceneRect")
    view_set_scene_rect = _capture_optional_attribute(canvas, "setSceneRect")
    if callable(view_scene_rect_method) and callable(view_set_scene_rect):
        view = canvas
        view_scene_rect = view_scene_rect_method()
        view_scene_rect_explicit = view_scene_rect_is_explicit(canvas)
        view_transform_method = _capture_optional_attribute(canvas, "transform")
        view_set_transform = _capture_optional_attribute(canvas, "setTransform")
        if callable(view_transform_method) and callable(view_set_transform):
            view_transform = view_transform_method()
        horizontal_scroll_bar_method = _capture_optional_attribute(
            canvas,
            "horizontalScrollBar",
        )
        if callable(horizontal_scroll_bar_method):
            candidate = horizontal_scroll_bar_method()
            value_method = _capture_optional_attribute(candidate, "value")
            set_value_method = _capture_optional_attribute(candidate, "setValue")
            if callable(value_method) and callable(set_value_method):
                horizontal_scroll_bar = candidate
                horizontal_scroll_value = int(value_method())
                horizontal_scroll_value_port = value_method
                horizontal_scroll_set_value_port = set_value_method
        vertical_scroll_bar_method = _capture_optional_attribute(
            canvas,
            "verticalScrollBar",
        )
        if callable(vertical_scroll_bar_method):
            candidate = vertical_scroll_bar_method()
            value_method = _capture_optional_attribute(candidate, "value")
            set_value_method = _capture_optional_attribute(candidate, "setValue")
            if callable(value_method) and callable(set_value_method):
                vertical_scroll_bar = candidate
                vertical_scroll_value = int(value_method())
                vertical_scroll_value_port = value_method
                vertical_scroll_set_value_port = set_value_method
    selected_items = tuple(selected_items_method())
    selected_item_ids = {id(item) for item in selected_items}
    selected_item_ports: list[_SelectedItemPorts] = []
    for item in scene_items:
        is_selected = _capture_optional_attribute(
            item,
            "isSelected",
            default=_MISSING_ATTRIBUTE,
        )
        set_selected = _capture_optional_attribute(
            item,
            "setSelected",
            default=_MISSING_ATTRIBUTE,
        )
        item_selection_contract_present = (
            is_selected is not _MISSING_ATTRIBUTE
            or set_selected is not _MISSING_ATTRIBUTE
        )
        if not item_selection_contract_present:
            continue
        if not callable(is_selected) or not callable(set_selected):
            if (
                not isinstance(item, QGraphicsItem)
                and id(item) not in selected_item_ids
            ):
                continue
            raise RuntimeError("document item has incomplete selection ports")
        selected_item_ports.append(
            _SelectedItemPorts(
                item=item,
                is_selected=is_selected,
                set_selected=set_selected,
                selected=bool(is_selected()),
            )
        )
    captured_selected_ids = {
        id(item_state.item) for item_state in selected_item_ports if item_state.selected
    }
    if selected_item_ids != captured_selected_ids:
        raise RuntimeError(
            "scene selectedItems disagrees with captured item selection state"
        )
    focus_item = focus_item_method()
    signals_blocked = _qt_scene_transaction_port(scene, "signalsBlocked")
    if signals_blocked is _MISSING_ATTRIBUTE:
        signals_blocked = _capture_optional_attribute(scene, "signalsBlocked")
    scene_signals_blocked = (
        bool(signals_blocked()) if callable(signals_blocked) else None
    )

    def capture_selection_callbacks() -> tuple[Callable[[], object], ...]:
        values: list[Callable[[], object]] = []
        for name in (
            "handle_scene_selection_group_changed",
            "handle_scene_selection_outline_changed",
        ):
            callback = _capture_optional_attribute(canvas, name)
            if callable(callback):
                values.append(cast(Callable[[], object], callback))
        return tuple(values)

    # A few isolated unit fakes expose non-Qt sentinel rects. Preserve their
    # legacy raw restore path. For a real scene, any remaining fallible slot
    # lookup is owned by both the opened guard and the immediately preceding
    # raw rect-state savepoint.
    scene_rect_snapshot = None
    scene_rect_state_snapshot = None
    selection_callbacks: tuple[Callable[[], object], ...] = ()
    try:
        QRectF(scene_rect)
    except (TypeError, ValueError):
        selection_callbacks = capture_selection_callbacks()
    else:
        scene_rect_state_snapshot = SceneRectStateSnapshot.capture(
            scene,
            scene_rect_getter=scene_rect_method,
            set_scene_rect_setter=set_scene_rect_method,
        )
        try:
            scene_rect_snapshot = SceneRectSnapshot.capture(
                scene,
                scene_rect_getter=scene_rect_method,
                set_scene_rect_setter=set_scene_rect_method,
                scene_items_bounding_rect_getter=(
                    items_bounding_rect_method
                    if callable(items_bounding_rect_method)
                    else None
                ),
            )
            selection_callbacks = capture_selection_callbacks()
        except BaseException as original_error:
            # Opening the guard is itself a Qt mutation, and a later slot
            # descriptor can mutate the guarded rect before raising. Close any
            # published guard first, then restore the raw pre-guard authority.
            if scene_rect_snapshot is not None:
                try:
                    scene_rect_snapshot.restore()
                except BaseException as recovery_error:
                    _add_scene_recovery_note(
                        original_error,
                        recovery_error,
                        phase="closing a failed document scene-rect guard",
                    )
            try:
                scene_rect_state_snapshot.restore()
            except BaseException as recovery_error:
                _add_scene_recovery_note(
                    original_error,
                    recovery_error,
                    phase="unwinding a failed document scene-rect capture",
                )
            else:
                for (
                    recorded_recovery_error
                ) in scene_rect_state_snapshot.recovery_errors:
                    _add_scene_recovery_note(
                        original_error,
                        recorded_recovery_error,
                        phase="unwinding a failed document scene-rect capture",
                    )
            raise
    return _DetachedSceneSnapshot(
        canvas=canvas,
        scene=scene,
        all_scene_items=scene_items,
        item_topology=tuple(item_topology),
        top_level_items=tuple(top_level_items),
        scene_rect=scene_rect,
        scene_rect_snapshot=scene_rect_snapshot,
        scene_rect_state_snapshot=scene_rect_state_snapshot,
        scene_signals_blocked=scene_signals_blocked,
        view=view,
        view_scene_rect=view_scene_rect,
        view_scene_rect_explicit=view_scene_rect_explicit,
        view_transform=view_transform,
        horizontal_scroll_bar=horizontal_scroll_bar,
        horizontal_scroll_value=horizontal_scroll_value,
        vertical_scroll_bar=vertical_scroll_bar,
        vertical_scroll_value=vertical_scroll_value,
        selected_items=selected_items,
        selected_item_ports=tuple(selected_item_ports),
        focus_item=focus_item,
        scene_items_port=items_method,
        scene_remove_item_port=remove_item_method,
        scene_add_item_port=add_item_method,
        scene_rect_port=scene_rect_method,
        scene_set_rect_port=set_scene_rect_method,
        scene_selected_items_port=selected_items_method,
        scene_focus_item_port=focus_item_method,
        scene_set_focus_item_port=set_focus_item_method,
        scene_block_signals_port=block_signals_method,
        scene_signals_blocked_port=signals_blocked,
        scene_items_bounding_rect_port=(
            items_bounding_rect_method if callable(items_bounding_rect_method) else None
        ),
        top_level_scene_ports=tuple(top_level_scene_ports),
        view_scene_rect_port=(
            view_scene_rect_method if callable(view_scene_rect_method) else None
        ),
        view_set_scene_rect_port=(
            view_set_scene_rect if callable(view_set_scene_rect) else None
        ),
        view_transform_port=(
            view_transform_method if callable(view_transform_method) else None
        ),
        view_set_transform_port=(
            view_set_transform if callable(view_set_transform) else None
        ),
        horizontal_scroll_value_port=horizontal_scroll_value_port,
        horizontal_scroll_set_value_port=horizontal_scroll_set_value_port,
        vertical_scroll_value_port=vertical_scroll_value_port,
        vertical_scroll_set_value_port=vertical_scroll_set_value_port,
        scene_rect_recovery_errors=[],
        canvas_scene_port=cast(Callable[[], object], scene_method),
        canvas_set_scene_port=cast(
            Callable[[object], object],
            set_scene_method,
        ),
        selection_callbacks=selection_callbacks,
    )


def _snapshot_canvas_scene(canvas) -> _DetachedSceneSnapshot | None:
    partial_captures: list[_PartialSceneCaptureSnapshot] = []
    try:
        return _snapshot_canvas_scene_impl(
            canvas,
            publish_partial_capture=partial_captures.append,
        )
    except BaseException as original_error:
        for partial_capture in reversed(partial_captures):
            partial_capture.restore(original_error)
        raise


class CanvasDocumentSessionService:
    def __init__(
        self,
        canvas,
        *,
        hit_testing_service,
        graph_service,
        structure_build_service=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.hit_testing_service = hit_testing_service
        self.graph_service = graph_service
        self.structure_build_service = structure_build_service

    def snapshot_state(self) -> dict:
        return snapshot_canvas_document_state(self.canvas)

    def apply_state(self, state: dict) -> None:
        if self.structure_build_service is None:
            raise RuntimeError(
                "structure_build_service is required to apply document state"
            )
        history_snapshot = self._snapshot_history_state()
        rollback_snapshot = self._snapshot_live_canvas_state()
        try:
            self._set_history_enabled_verified(history_snapshot, False)
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
            )
            rollback_snapshot.detach_scene_items()
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
            )
            self._clear_detached_selection_state()
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
            )
        except BaseException as original_error:
            try:
                self._restore_previous_document(
                    rollback_snapshot,
                    history_snapshot,
                    original_error=original_error,
                )
            except BaseException as rollback_error:
                _add_scene_recovery_note(
                    original_error,
                    rollback_error,
                    phase="restoring the previous document",
                )
                try:
                    clear_scene_for(self.canvas)
                except BaseException as cleanup_error:
                    _add_scene_recovery_note(
                        original_error,
                        cleanup_error,
                        phase="clearing an unrecoverable document scene",
                    )
                try:
                    self._force_clear_captured_history(history_snapshot)
                except BaseException as cleanup_error:
                    _add_scene_recovery_note(
                        original_error,
                        cleanup_error,
                        phase="clearing unrecoverable document history",
                    )
            finally:
                self._restore_history_enabled(
                    history_snapshot,
                    original_error=original_error,
                )
            raise
        try:
            self._apply_state_contents(state)
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
            )
            # Every remaining fallible lifecycle step stays inside the old
            # document savepoint. The scene-rect commit is deliberately last:
            # after it succeeds there is no operation left that could report
            # failure while exposing the replacement as only half-committed.
            self._clear_captured_history(history_snapshot)
            self._restore_history_enabled(history_snapshot)
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
            )
            rollback_snapshot.commit_replacement()
            self._verify_transaction_roots(
                rollback_snapshot,
                history_snapshot,
                ensure_selection_wiring=True,
            )
        except BaseException as original_error:
            try:
                self._clear_target_for_rollback()
                self._restore_previous_document(
                    rollback_snapshot,
                    history_snapshot,
                    original_error=original_error,
                )
            except BaseException as rollback_error:
                # The previous document could not be reconstructed. Keep the
                # canvas internally consistent and discard commands that no
                # longer describe it rather than exposing a partially applied
                # target or rollback state.
                _add_scene_recovery_note(
                    original_error,
                    rollback_error,
                    phase="restoring the previous document",
                )
                try:
                    clear_scene_for(self.canvas)
                except BaseException as cleanup_error:
                    _add_scene_recovery_note(
                        original_error,
                        cleanup_error,
                        phase="clearing an unrecoverable document scene",
                    )
                try:
                    self._force_clear_captured_history(history_snapshot)
                except BaseException as cleanup_error:
                    _add_scene_recovery_note(
                        original_error,
                        cleanup_error,
                        phase="clearing unrecoverable document history",
                    )
            finally:
                self._restore_history_enabled(
                    history_snapshot,
                    original_error=original_error,
                )
            raise

    def _restore_history_enabled(
        self,
        snapshot: _HistoryStateSnapshot,
        *,
        original_error: BaseException | None = None,
    ) -> None:
        try:
            self._set_history_enabled_verified(
                snapshot,
                snapshot.enabled,
            )
        except BaseException as secondary_error:
            if original_error is None:
                raise
            _add_scene_recovery_note(
                original_error,
                secondary_error,
                phase="restoring the history enabled state",
            )

    def _verify_transaction_roots(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot,
        *,
        ensure_selection_wiring: bool = False,
    ) -> None:
        self._verify_history_roots(history_snapshot)
        scene_snapshot = rollback_snapshot.scene
        if scene_snapshot is None:
            return
        scene_snapshot.verify_canvas_scene_root()
        if ensure_selection_wiring:
            scene_snapshot.ensure_selection_wiring()

    def _verify_history_roots(
        self,
        snapshot: _HistoryStateSnapshot,
    ) -> None:
        if self.history is not snapshot.service:
            raise RuntimeError("document history service identity changed")
        for alias in snapshot.aliases:
            alias.verify(snapshot.service)
        if snapshot.state_getter() is not snapshot.state:
            raise RuntimeError("document history state identity changed")
        if snapshot.history_getter() is not snapshot.history:
            raise RuntimeError("document undo-list identity changed")
        if snapshot.redo_getter() is not snapshot.redo_stack:
            raise RuntimeError("document redo-list identity changed")

    def _clear_captured_history(
        self,
        snapshot: _HistoryStateSnapshot,
    ) -> None:
        self._verify_history_roots(snapshot)
        snapshot.clear_port()
        self._verify_history_roots(snapshot)
        if list.__len__(snapshot.history) or list.__len__(snapshot.redo_stack):
            raise RuntimeError("document history clear did not empty both stacks")

    def _force_clear_captured_history(
        self,
        snapshot: _HistoryStateSnapshot,
    ) -> None:
        self.history = snapshot.service
        for alias in snapshot.aliases:
            alias.restore(snapshot.service)
        snapshot.state_setter(snapshot.state)
        snapshot.history_setter(snapshot.history)
        snapshot.redo_setter(snapshot.redo_stack)
        snapshot.clear_port()
        self._verify_history_roots(snapshot)

    @staticmethod
    def _set_history_enabled_verified(
        snapshot: _HistoryStateSnapshot,
        enabled: bool,
    ) -> None:
        if bool(snapshot.enabled_getter()) is enabled:
            return
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                snapshot.enabled_setter(enabled)
                if bool(snapshot.enabled_getter()) is not enabled:
                    raise RuntimeError(
                        "history enabled setter did not apply the requested state"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return
        first_error, second_error = errors
        _add_scene_recovery_note(
            first_error,
            second_error,
            phase="retrying the history enabled-state restore",
        )
        raise first_error

    def _clear_target_for_rollback(self) -> None:
        try:
            clear_scene_for(self.canvas)
        except BaseException:
            # Scene reset is designed to be idempotent. A callback may fail
            # after clearing only one registry; retry once before declaring the
            # preserved previous document unrecoverable.
            clear_scene_for(self.canvas)

    def _restore_previous_document(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot,
        *,
        original_error: BaseException,
    ) -> None:
        try:
            rollback_snapshot.restore_live_state(self.canvas)
        except BaseException:
            # Re-attachment skips items already restored, so a fail-once scene
            # add or view setter can safely resume from the partial attempt.
            rollback_snapshot.restore_live_state(self.canvas)

        scene_snapshot = rollback_snapshot.scene
        if scene_snapshot is not None:
            for recovery_error in scene_snapshot.scene_rect_recovery_errors:
                _add_scene_recovery_note(
                    original_error,
                    recovery_error,
                    phase="restoring the previous document scene rect",
                )

        try:
            self._restore_history_state(history_snapshot)
        except BaseException:
            self._restore_history_state(history_snapshot)
        self._set_history_enabled_verified(
            history_snapshot,
            history_snapshot.enabled,
        )

        published_now = rollback_snapshot.status_publication.publish(original_error)
        if published_now:
            self._reassert_previous_document_after_status_publication(
                rollback_snapshot,
                history_snapshot,
            )
        self._verify_previous_document(
            rollback_snapshot,
            history_snapshot,
        )

    def _verify_previous_document(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot,
    ) -> None:
        if self.canvas.model is not rollback_snapshot.model:
            raise RuntimeError("document rollback changed model identity")
        for object_snapshot in rollback_snapshot.object_states:
            object_snapshot.verify()
        scene_snapshot = rollback_snapshot.scene
        if scene_snapshot is not None:
            scene_snapshot._verify_restored_state()
        self._verify_history_state(history_snapshot, include_enabled=True)

        try:
            restored_state = self.snapshot_state()
        except BaseException:
            # Qt-backed serialization can fail transiently while a prior
            # selection callback unwinds. Retry the read, never the callback.
            restored_state = self.snapshot_state()
        if restored_state != rollback_snapshot.document_state:
            raise RuntimeError("Failed to restore the previous canvas document state.")

    def _reassert_previous_document_after_status_publication(
        self,
        rollback_snapshot: _CanvasRollbackSnapshot,
        history_snapshot: _HistoryStateSnapshot,
    ) -> None:
        errors: list[BaseException] = []
        for attempt in range(2):
            try:
                if attempt == 0:
                    rollback_snapshot.restore_live_state(self.canvas)
                    self._restore_history_state(history_snapshot)
                    self._set_history_enabled_verified(
                        history_snapshot,
                        history_snapshot.enabled,
                    )
                else:
                    self._set_history_enabled_verified(
                        history_snapshot,
                        history_snapshot.enabled,
                    )
                    self._restore_history_state(history_snapshot)
                    rollback_snapshot.restore_live_state(self.canvas)
                self._verify_previous_document(
                    rollback_snapshot,
                    history_snapshot,
                )
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "document rollback was corrupted by status publication",
            errors,
        )

    def _apply_state_contents(self, state: dict) -> None:
        clear_scene_for(self.canvas)
        apply_document_settings(self.canvas, state)
        set_model_for(self.canvas, deserialize_model_state(state["model"]))
        self.graph_service.rebuild_bond_adjacency()
        restore_document_pre_model_items(self.canvas, state)
        restore_document_projection_state(self.canvas, state)
        self.structure_build_service.render_model()
        restore_document_post_model_items(self.canvas, state)
        restore_document_groups(self.canvas, state)
        self.hit_testing_service.mark_spatial_index_dirty()

    def _snapshot_live_canvas_state(self) -> _CanvasRollbackSnapshot:
        object_states: list[_ObjectStateSnapshot] = []
        seen_objects: set[int] = set()

        def append_snapshot(
            target: Any, *, names: tuple[str, ...] | None = None
        ) -> _ObjectStateSnapshot | None:
            if target is None or id(target) in seen_objects:
                return None
            snapshot = _snapshot_object_state(target, names=names)
            if snapshot is None:
                return None
            seen_objects.add(id(target))
            object_states.append(snapshot)
            return snapshot

        runtime_state = _capture_optional_attribute(
            self.canvas,
            "runtime_state",
        )
        if runtime_state is not None:
            for name in _DOCUMENT_MUTATED_RUNTIME_FIELDS:
                append_snapshot(_capture_optional_attribute(runtime_state, name))

        renderer = _capture_optional_attribute(self.canvas, "renderer")
        append_snapshot(renderer, names=("style",))
        append_snapshot(
            _capture_optional_attribute(self.canvas, "selection_style_state")
        )
        append_snapshot(
            _capture_optional_attribute(self.canvas, "selection_info_state")
        )
        append_snapshot(
            self.canvas,
            names=(
                "settings",
                "scene_items",
                "sheet_size",
                "sheet_orientation",
            ),
        )

        model = _capture_optional_attribute(self.canvas, "model")
        model_snapshot = append_snapshot(
            model,
            names=("atoms", "bonds", "next_atom_id", "atom_annotations"),
        )
        if model_snapshot is not None:
            atoms_snapshot = model_snapshot.attributes.get("atoms")
            atoms = atoms_snapshot.value if atoms_snapshot is not None else None
            if isinstance(atoms, dict):
                for atom in tuple(atoms.values()):
                    append_snapshot(atom)
            bonds_snapshot = model_snapshot.attributes.get("bonds")
            bonds = bonds_snapshot.value if bonds_snapshot is not None else None
            if isinstance(bonds, (list, tuple)):
                for bond in tuple(bonds):
                    if bond is not None:
                        append_snapshot(bond)

        selection_info = selection_info_state_for(self.canvas)
        status_callback_value = _capture_optional_attribute(
            selection_info,
            "callback",
        )
        status_cache_value = _capture_optional_attribute(
            selection_info,
            "cache",
        )
        status_publication = _DocumentStatusPublication(
            callback=(
                status_callback_value if callable(status_callback_value) else None
            ),
            cache=(
                (str(status_cache_value[0]), str(status_cache_value[1]))
                if isinstance(status_cache_value, tuple)
                and len(status_cache_value) == 2
                else None
            ),
        )

        scene_snapshot: _DetachedSceneSnapshot | None = None
        try:
            document_state = self.snapshot_state()
            scene_snapshot = _snapshot_canvas_scene(self.canvas)
        except BaseException as original_error:
            recovery_errors: list[BaseException] = []
            for _attempt in range(2):
                recovery_errors.clear()
                try:
                    self.canvas.model = model
                except BaseException as recovery_error:
                    recovery_errors.append(recovery_error)
                for object_snapshot in object_states:
                    try:
                        object_snapshot.restore()
                    except BaseException as recovery_error:
                        recovery_errors.append(recovery_error)
                if scene_snapshot is not None:
                    try:
                        scene_snapshot.restore()
                    except BaseException as recovery_error:
                        recovery_errors.append(recovery_error)
                try:
                    if self.canvas.model is not model:
                        raise RuntimeError(
                            "document capture unwind changed model identity"
                        )
                    for object_snapshot in object_states:
                        object_snapshot.verify()
                except BaseException as recovery_error:
                    recovery_errors.append(recovery_error)
                if not recovery_errors:
                    break
            for recorded_error in recovery_errors:
                _add_scene_recovery_note(
                    original_error,
                    recorded_error,
                    phase="unwinding a failed document snapshot capture",
                )
            raise
        return _CanvasRollbackSnapshot(
            document_state=document_state,
            model=model,
            object_states=tuple(object_states),
            scene=scene_snapshot,
            status_publication=status_publication,
        )

    def _clear_detached_selection_state(self) -> None:
        set_selected_highlight_items_for(self.canvas, [])
        runtime_state = getattr(self.canvas, "runtime_state", None)
        selection_info_state = (
            getattr(runtime_state, "selection_info_state", None)
            if runtime_state is not None
            else getattr(self.canvas, "selection_info_state", None)
        )
        if selection_info_state is None:
            return
        selection_info_state.signature = None
        selection_info_state.pending_signature = None
        selection_info_state.cache = ("", "")
        selection_info_state.rdkit_warmup_pending = False

    def _snapshot_history_aliases(self) -> tuple[_HistoryAliasSnapshot, ...]:
        canvas_getattribute = inspect.getattr_static(
            type(self.canvas),
            "__getattribute__",
            _MISSING_ATTRIBUTE,
        )
        canvas_setattribute = inspect.getattr_static(
            type(self.canvas),
            "__setattr__",
            _MISSING_ATTRIBUTE,
        )
        if not callable(canvas_getattribute) or not callable(canvas_setattribute):
            raise RuntimeError("document canvas has incomplete history-root ports")

        aliases: list[_HistoryAliasSnapshot] = []
        for root_name in ("runtime_state", "services"):
            if (
                inspect.getattr_static(
                    self.canvas,
                    root_name,
                    _MISSING_ATTRIBUTE,
                )
                is _MISSING_ATTRIBUTE
            ):
                continue
            owner = canvas_getattribute(self.canvas, root_name)
            if owner is None or (
                inspect.getattr_static(
                    owner,
                    "history_service",
                    _MISSING_ATTRIBUTE,
                )
                is _MISSING_ATTRIBUTE
            ):
                continue
            owner_getattribute = inspect.getattr_static(
                type(owner),
                "__getattribute__",
                _MISSING_ATTRIBUTE,
            )
            owner_setattribute = inspect.getattr_static(
                type(owner),
                "__setattr__",
                _MISSING_ATTRIBUTE,
            )
            if not callable(owner_getattribute) or not callable(owner_setattribute):
                raise RuntimeError(
                    f"document {root_name} has incomplete history alias ports"
                )
            alias_service = owner_getattribute(owner, "history_service")
            if alias_service is not self.history:
                raise RuntimeError(
                    f"document {root_name} history service identity differs at capture"
                )

            def owner_getter(
                _getattribute=canvas_getattribute,
                _canvas=self.canvas,
                _root_name=root_name,
            ) -> object:
                return _getattribute(_canvas, _root_name)

            def owner_setter(
                value: object,
                _setattribute=canvas_setattribute,
                _canvas=self.canvas,
                _root_name=root_name,
            ) -> object:
                return _setattribute(_canvas, _root_name, value)

            def service_getter(
                _getattribute=owner_getattribute,
                _owner=owner,
            ) -> object:
                return _getattribute(_owner, "history_service")

            def service_setter(
                value: object,
                _setattribute=owner_setattribute,
                _owner=owner,
            ) -> object:
                return _setattribute(_owner, "history_service", value)

            aliases.append(
                _HistoryAliasSnapshot(
                    name=root_name,
                    owner=owner,
                    owner_getter=owner_getter,
                    owner_setter=owner_setter,
                    service_getter=service_getter,
                    service_setter=service_setter,
                )
            )
        return tuple(aliases)

    def _snapshot_history_state(self) -> _HistoryStateSnapshot:
        history_aliases = self._snapshot_history_aliases()
        history_state = _capture_optional_attribute(self.history, "state")
        state_getattribute = inspect.getattr_static(
            type(history_state),
            "__getattribute__",
            _MISSING_ATTRIBUTE,
        )
        state_setattribute = inspect.getattr_static(
            type(history_state),
            "__setattr__",
            _MISSING_ATTRIBUTE,
        )
        service_getattribute = inspect.getattr_static(
            type(self.history),
            "__getattribute__",
            _MISSING_ATTRIBUTE,
        )
        service_setattribute = inspect.getattr_static(
            type(self.history),
            "__setattr__",
            _MISSING_ATTRIBUTE,
        )
        set_enabled = _capture_optional_attribute(
            self.history,
            "set_enabled",
        )
        clear_history = _capture_optional_attribute(
            self.history,
            "clear",
        )
        if not all(
            callable(port)
            for port in (
                state_getattribute,
                state_setattribute,
                service_getattribute,
                service_setattribute,
                set_enabled,
                clear_history,
            )
        ):
            raise RuntimeError("document history has incomplete enabled-state ports")

        history_value = state_getattribute(history_state, "history")
        redo_value = state_getattribute(history_state, "redo_stack")
        if not isinstance(history_value, list) or not isinstance(redo_value, list):
            raise RuntimeError("document history stacks must be mutable lists")

        def service_state_getter(
            _getattribute=service_getattribute,
            _service=self.history,
        ) -> object:
            return _getattribute(_service, "state")

        def service_state_setter(
            value: object,
            _setattribute=service_setattribute,
            _service=self.history,
        ) -> object:
            return _setattribute(_service, "state", value)

        def history_getter(
            _getattribute=state_getattribute,
            _state=history_state,
        ) -> object:
            return _getattribute(_state, "history")

        def history_setter(
            value: object,
            _setattribute=state_setattribute,
            _state=history_state,
        ) -> object:
            return _setattribute(_state, "history", value)

        def redo_getter(
            _getattribute=state_getattribute,
            _state=history_state,
        ) -> object:
            return _getattribute(_state, "redo_stack")

        def redo_setter(
            value: object,
            _setattribute=state_setattribute,
            _state=history_state,
        ) -> object:
            return _setattribute(_state, "redo_stack", value)

        def enabled_getter(
            _getattribute=state_getattribute,
            _state=history_state,
        ) -> object:
            return _getattribute(_state, "enabled")

        return _HistoryStateSnapshot(
            service=self.history,
            state=history_state,
            history=history_value,
            history_items=tuple(history_value),
            redo_stack=redo_value,
            redo_items=tuple(redo_value),
            enabled=bool(enabled_getter()),
            state_getter=service_state_getter,
            state_setter=service_state_setter,
            history_getter=history_getter,
            history_setter=history_setter,
            redo_getter=redo_getter,
            redo_setter=redo_setter,
            enabled_getter=enabled_getter,
            enabled_setter=cast(Callable[[bool], object], set_enabled),
            clear_port=cast(Callable[[], object], clear_history),
            aliases=history_aliases,
        )

    def _restore_history_state(self, snapshot: _HistoryStateSnapshot) -> None:
        errors: list[BaseException] = []
        for attempt in range(2):
            try:
                self.history = snapshot.service
                for alias in snapshot.aliases:
                    alias.restore(snapshot.service)
                if attempt == 0:
                    snapshot.state_setter(snapshot.state)
                    snapshot.history[:] = snapshot.history_items
                    snapshot.redo_stack[:] = snapshot.redo_items
                    snapshot.history_setter(snapshot.history)
                    snapshot.redo_setter(snapshot.redo_stack)
                else:
                    snapshot.redo_stack[:] = snapshot.redo_items
                    snapshot.redo_setter(snapshot.redo_stack)
                    snapshot.history[:] = snapshot.history_items
                    snapshot.history_setter(snapshot.history)
                    snapshot.state_setter(snapshot.state)
                self._verify_history_state(snapshot, include_enabled=False)
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "document history exact restore failed",
            errors,
        )

    def _verify_history_state(
        self,
        snapshot: _HistoryStateSnapshot,
        *,
        include_enabled: bool,
    ) -> None:
        self._verify_history_roots(snapshot)
        actual_history = tuple(snapshot.history)
        if len(actual_history) != len(snapshot.history_items) or any(
            actual is not expected
            for actual, expected in zip(
                actual_history,
                snapshot.history_items,
                strict=False,
            )
        ):
            raise RuntimeError("document undo-list contents changed")
        actual_redo = tuple(snapshot.redo_stack)
        if len(actual_redo) != len(snapshot.redo_items) or any(
            actual is not expected
            for actual, expected in zip(
                actual_redo,
                snapshot.redo_items,
                strict=False,
            )
        ):
            raise RuntimeError("document redo-list contents changed")
        if include_enabled and bool(snapshot.enabled_getter()) is not snapshot.enabled:
            raise RuntimeError("document history enabled state changed")

    def restore_state(self, state: dict) -> None:
        self.apply_state(state)

    def snapshot_state_with_warnings(self) -> tuple[dict, list[str]]:
        return snapshot_canvas_document_state_with_warnings(self.canvas)

    def save_to_file(self, path: str) -> list[str]:
        state, warnings = self.snapshot_state_with_warnings()
        write_document(path, state, file_format_version_for(self.canvas))
        return warnings

    def load_from_file(self, path: str) -> None:
        document = read_document(path)
        self.restore_state(document.state)

    def _build_xyz_payload(self, *, selected_only: bool = False):
        if selected_only:
            return build_selected_3d_conversion_payload_for(self.canvas)
        return build_3d_conversion_payload_for(self.canvas)

    def export_xyz(self, path: str, *, selected_only: bool = False) -> None:
        export_model, atom_annotations = self._build_xyz_payload(
            selected_only=selected_only
        )
        xyz_block = model_to_xyz_block_for(
            self.canvas, export_model, atom_annotations=atom_annotations
        )
        if xyz_block is None:
            message = rdkit_last_error_for(self.canvas) or "Failed to export 3D XYZ."
            raise ValueError(message)
        atomic_write_text(path, xyz_block)

    def export_mol(self, path: str, *, selected_only: bool = False) -> None:
        export_model, atom_annotations = self._build_xyz_payload(
            selected_only=selected_only
        )
        if not export_model.atoms:
            raise ValueError("There is no molecular structure to export.")
        try:
            block = write_molfile(export_model, atom_annotations=atom_annotations)
        except MolfileLimitError:
            # Hard V2000 capacity/range limits hold for any writer; falling
            # back to RDKit would either mask them or blame missing RDKit.
            raise
        except MolfileError as exc:
            # The structure uses abbreviation labels (Ph, CF3, ...) that are not
            # single elements. Fall back to RDKit, which expands them into explicit
            # atoms; without RDKit there is no way to expand them.
            block = model_to_mol_block_for(
                self.canvas, export_model, atom_annotations=atom_annotations
            )
            if block is None:
                reason = rdkit_last_error_for(self.canvas)
                if not reason or "not available" in reason.lower():
                    raise ValueError(
                        f"{exc} Install RDKit to expand these abbreviations automatically."
                    ) from exc
                raise ValueError(reason) from exc
        atomic_write_text(path, block)

    def export_xyz_async(
        self, path: str, *, on_success, on_error, selected_only: bool = False
    ) -> None:
        try:
            export_model, atom_annotations = self._build_xyz_payload(
                selected_only=selected_only
            )
        except Exception as exc:
            on_error(str(exc) or "Failed to export 3D XYZ.")
            return
        if not rdkit_is_loaded_for(self.canvas) and not preload_rdkit_for(self.canvas):
            on_error(
                rdkit_last_error_for(self.canvas)
                or "RDKit is not available in this environment."
            )
            return

        from chemvas.ui.rdkit_async_jobs import export_xyz_in_thread

        export_xyz_in_thread(
            self.canvas,
            rdkit_adapter=rdkit_adapter_for(self.canvas),
            model=export_model,
            atom_annotations=atom_annotations,
            path=path,
            on_success=on_success,
            on_error=on_error,
            rdkit_adapter_factory=RDKitAdapter,
        )

    def export_figure(
        self,
        path: str,
        *,
        fmt: str = "svg",
        scope: str = "sheet",
        dpi: int = 300,
        background: str = "transparent",
        sizing: str = "bond",
        editable_svg: bool = False,
    ) -> None:
        from chemvas.features.export import points_for_mm

        pad = max(2.0, bond_line_width_for(self.canvas) * 2.0)
        items = None
        if scope == "selection":
            items = selection_items_for_copy_for(self.canvas)
            if not items:
                raise ValueError("Select something to export, or choose Whole canvas.")

        unit_scale = 1.0
        target_width_pt = None
        if sizing == "bond":
            bond_length_px = bond_length_px_for(self.canvas)
            if bond_length_px > 0:
                unit_scale = bond_length_pt_for(self.canvas) / bond_length_px
        elif sizing == "col1":
            target_width_pt = points_for_mm(84.0)
        elif sizing == "col2":
            target_width_pt = points_for_mm(174.0)

        fmt = fmt.lower()
        target = Path(path)

        def render_to_temp(tmp: Path) -> None:
            export_canvas_scene_for(
                self.canvas,
                str(tmp),
                fmt=fmt,
                items=items,
                margin=pad,
                dpi=dpi,
                background=background,
                title="Chemvas drawing",
                unit_scale=unit_scale,
                target_width_pt=target_width_pt,
            )
            if fmt == "svg" and editable_svg:
                self._embed_editable_svg_payload(str(tmp), fmt=fmt, scope=scope)

        atomic_write_via_temp(target, render_to_temp)

    def _embed_editable_svg_payload(self, path: str, *, fmt: str, scope: str) -> None:
        if fmt.lower() != "svg":
            return
        if scope == "selection":
            state = self._selection_document_state()
            svg_scope = CHEMVAS_SVG_SCOPE_SELECTION
        else:
            state = self.snapshot_state()
            svg_scope = CHEMVAS_SVG_SCOPE_SHEET
        payload = create_editable_svg_payload(
            state,
            document_version=file_format_version_for(self.canvas),
            scope=svg_scope,
        )
        embed_chemvas_document_in_svg(path, payload)

    def _selection_document_state(self) -> dict:
        selected_items = selection_items_for_copy_for(self.canvas)
        explicit_atom_ids, bond_ids = selected_ids_for(self.canvas)
        selection_payload = build_selection_clipboard_payload_for_canvas(
            self.canvas,
            selected_items=selected_items,
            explicit_atom_ids=explicit_atom_ids,
            selected_bond_ids=bond_ids,
            bonds=bonds_for(self.canvas),
            ring_items=ring_items_for(self.canvas),
            marks_by_atom=mark_registry_for(self.canvas).by_atom,
            atom_state_getter=lambda atom_id: atom_state_dict_for(self.canvas, atom_id),
            bond_state_getter=bond_state_dict,
            scene_item_state_getter=lambda item: scene_item_state_for(
                self.canvas, item
            ),
            version=clipboard_selection_version_for(self.canvas),
        )
        if selection_payload is None:
            raise ValueError("Select something to export, or choose Whole canvas.")
        return selection_payload_to_canvas_state(
            selection_payload,
            self.snapshot_state()["settings"],
        )


__all__ = ["CanvasDocumentSessionService"]
