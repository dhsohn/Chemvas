from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from core.history import (
    CompositeCommand,
    HistoryCommand,
    HistoryTransactionRestoreResult,
    MoveAtomsCommand,
)
from PyQt6 import sip
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

import ui.atom_coords_access as _atom_coords_access_module
import ui.canvas_atom_graphics_state as _atom_graphics_state_module
import ui.canvas_bond_graphics_state as _bond_graphics_state_module
import ui.canvas_history_service as _history_service_module
import ui.canvas_hit_testing_service as _hit_testing_service_module
import ui.canvas_model_access as _canvas_model_access_module
import ui.canvas_model_state as _canvas_model_state_module
import ui.canvas_move_controller as _move_controller_module
import ui.canvas_service_ports as _canvas_service_ports_module
import ui.canvas_style_controller as _style_controller_module
import ui.graphics_items as _graphics_items_module
import ui.handle_state as _handle_state_module
import ui.move_access as _move_access_module
import ui.selection_outline_service as _outline_service_module
import ui.selection_service_access as _selection_service_access_module
import ui.selection_style_state as _selection_style_state_module
import ui.spatial_index_state as _spatial_index_state_module
from ui.canvas_delete_transaction import (
    _ContainerGraphSnapshot,
    _ObjectStateSnapshot,
    _SceneItemExactSnapshot,
)
from ui.canvas_history_state import CanvasHistoryState
from ui.canvas_model_access import bond_for_id
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
    restore_history_transaction_for_history,
)
from ui.history_command_snapshot import HistoryCommandSnapshot
from ui.history_commands import MoveItemsCommand
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.move_access import move_atoms_for, move_item_for, shift_selection_outlines_for
from ui.scene_rect_snapshot import scene_rect_is_automatic
from ui.selection_collection_access import independent_selection_items
from ui.selection_service_access import refresh_selection_outline_for
from ui.selection_style_access import suspend_selection_outline_for
from ui.tool_context import ToolContext

_DRAG_DELTA_EPSILON = 1e-6
_MISSING_DRAG_LOCAL = object()
_MISSING_DRAG_HISTORY_POLICY = object()
_TRUSTED_MOVE_ATOMS_FOR = move_atoms_for
_TRUSTED_MOVE_ITEM_FOR = move_item_for
_TRUSTED_SHIFT_SELECTION_OUTLINES_FOR = shift_selection_outlines_for
_TRUSTED_QT_PRIMITIVE_PORT_NAMES = (
    "transformOriginPoint",
    "setTransformOriginPoint",
    "transform",
    "setTransform",
    "rotation",
    "setRotation",
    "scale",
    "setScale",
    "pos",
    "setPos",
    "opacity",
    "setOpacity",
    "zValue",
    "setZValue",
    "line",
    "setLine",
    "path",
    "setPath",
    "polygon",
    "setPolygon",
    "rect",
    "setRect",
    "pen",
    "setPen",
    "brush",
    "setBrush",
    "font",
    "setFont",
    "defaultTextColor",
    "setDefaultTextColor",
    "toHtml",
    "setHtml",
    "textInteractionFlags",
    "setTextInteractionFlags",
)
_TRUSTED_QT_DIRECT_SNAPSHOT_ATTRIBUTES = (
    "_hit_padding",
    "_hit_radius",
    "_layout",
    "_typographic",
    "_stack_element_rect",
)
_TRUSTED_QT_PYTHON_PRIMITIVE_PORTS = {
    "setFont": (_graphics_items_module.AtomLabelItem.setFont,),
}
_TRUSTED_DRAG_MODULE_PORTS = tuple(
    (module, name, getattr(module, name))
    for module, names in (
        (
            _move_access_module,
            (
                "move_service_from_canvas",
                "move_controller_for_access",
                "selection_service_from_canvas",
            ),
        ),
        (
            _move_controller_module,
            (
                "active_handles_for",
                "atom_coords_3d_for_id",
                "atom_dots_for",
                "atom_for_id",
                "atom_items_for",
                "bond_items_for_id",
                "handle_target_for",
                "mark_center_for",
                "normalized_shape_kind",
                "set_atom_coords_3d_for_id",
                "shape_path",
                "update_bond_geometry_for",
            ),
        ),
        (
            _canvas_model_access_module,
            ("atom_for_id", "atoms_for", "model_for"),
        ),
        (_canvas_model_state_module, ("ensure_canvas_state",)),
        (
            _atom_coords_access_module,
            (
                "atom_coords_3d_for",
                "atom_coords_3d_state_for",
                "ensure_canvas_state",
            ),
        ),
        (
            _atom_graphics_state_module,
            ("atom_graphics_state_for", "ensure_canvas_state"),
        ),
        (
            _bond_graphics_state_module,
            (
                "bond_graphics_state_for",
                "bond_items_for",
                "ensure_canvas_state",
            ),
        ),
        (
            _hit_testing_service_module,
            ("mark_spatial_index_dirty_for",),
        ),
        (
            _spatial_index_state_module,
            ("ensure_canvas_state", "spatial_index_state_for"),
        ),
        (
            _handle_state_module,
            ("ensure_canvas_state", "handle_state_for"),
        ),
        (_canvas_service_ports_module, ("canvas_services_for",)),
        (_style_controller_module, ("selection_style_state_for",)),
        (
            _selection_service_access_module,
            ("selection_service_for_access",),
        ),
        (_outline_service_module, ("selection_outlines_for",)),
        (
            _selection_style_state_module,
            ("ensure_canvas_state", "selection_style_state_for"),
        ),
    )
    for name in names
)


def _trusted_drag_module_ports_are_current() -> bool:
    try:
        return all(
            getattr(module, name) is expected
            for module, name, expected in _TRUSTED_DRAG_MODULE_PORTS
        )
    except (AttributeError, TypeError):
        return False


def _has_exact_type(target: object, module: str, name: str) -> bool:
    target_type = type(target)
    return target_type.__module__ == module and target_type.__name__ == name


def _has_exact_callback_free_production_history_state(
    history_service: object,
) -> bool:
    """Validate the production history roots without invoking a live descriptor."""

    if type(history_service) is not _history_service_module.CanvasHistoryService:
        return False
    service_type = type(history_service)
    service_type_namespace = vars(service_type)
    if (
        service_type_namespace.get("__getattribute__", object.__getattribute__)
        is not object.__getattribute__
        or service_type_namespace.get("__setattr__", object.__setattr__)
        is not object.__setattr__
        or service_type_namespace.get("state", _MISSING_DRAG_LOCAL)
        is not _MISSING_DRAG_LOCAL
    ):
        return False
    try:
        service_namespace = object.__getattribute__(history_service, "__dict__")
    except (AttributeError, TypeError):
        return False
    if type(service_namespace) is not dict:
        return False
    state = dict.get(service_namespace, "state", _MISSING_DRAG_LOCAL)
    if type(state) is not CanvasHistoryState:
        return False
    state_type = type(state)
    state_type_namespace = vars(state_type)
    if (
        state_type_namespace.get("__getattribute__", object.__getattribute__)
        is not object.__getattribute__
        or state_type_namespace.get("__setattr__", object.__setattr__)
        is not object.__setattr__
    ):
        return False
    class_limit = state_type_namespace.get("limit", _MISSING_DRAG_LOCAL)
    if (
        state_type_namespace.get("history", _MISSING_DRAG_LOCAL)
        is not _MISSING_DRAG_LOCAL
        or state_type_namespace.get("redo_stack", _MISSING_DRAG_LOCAL)
        is not _MISSING_DRAG_LOCAL
        or state_type_namespace.get("enabled", _MISSING_DRAG_LOCAL) is not True
        or type(class_limit) is not int
        or class_limit != 100
    ):
        return False
    try:
        state_namespace = object.__getattribute__(state, "__dict__")
    except (AttributeError, TypeError):
        return False
    if type(state_namespace) is not dict:
        return False
    history = dict.get(state_namespace, "history", _MISSING_DRAG_LOCAL)
    redo_stack = dict.get(state_namespace, "redo_stack", _MISSING_DRAG_LOCAL)
    enabled = dict.get(state_namespace, "enabled", _MISSING_DRAG_LOCAL)
    limit = dict.get(state_namespace, "limit", _MISSING_DRAG_LOCAL)
    return (
        type(history) is list
        and type(redo_stack) is list
        and history is not redo_stack
        and type(enabled) is bool
        and type(limit) is int
        and limit >= 0
    )


def _has_exact_bound_method(
    target: object,
    *,
    module: str,
    type_name: str,
    method_name: str,
) -> bool:
    if not _has_exact_type(target, module, type_name):
        return False
    try:
        bound = getattr(target, method_name)
        static = inspect.getattr_static(type(target), method_name)
    except (AttributeError, TypeError):
        return False
    return callable(bound) and getattr(bound, "__func__", None) is static


def _has_callback_free_qt_snapshot_ports(item: object) -> bool:
    """Reject Python descriptors before the selection-sized snapshot reads them."""

    if not isinstance(item, QGraphicsItem) or sip.isdeleted(item):
        return False
    item_type = type(item)
    getattr_port = inspect.getattr_static(
        item_type,
        "__getattr__",
        _MISSING_DRAG_LOCAL,
    )
    if (
        inspect.getattr_static(item_type, "__getattribute__")
        is not object.__getattribute__
        or inspect.getattr_static(item_type, "__setattr__")
        is not object.__setattr__
        or (
            getattr_port is not _MISSING_DRAG_LOCAL
            and type(getattr_port).__module__ != "sip"
        )
    ):
        return False
    try:
        namespace = object.__getattribute__(item, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    for name in _TRUSTED_QT_PRIMITIVE_PORT_NAMES:
        static = inspect.getattr_static(item, name, _MISSING_DRAG_LOCAL)
        if static is _MISSING_DRAG_LOCAL:
            continue
        if type(static).__module__ == "sip":
            continue
        trusted_python_ports = _TRUSTED_QT_PYTHON_PRIMITIVE_PORTS.get(
            name,
            (),
        )
        if not any(static is expected for expected in trusted_python_ports):
            return False
    for name in _TRUSTED_QT_DIRECT_SNAPSHOT_ATTRIBUTES:
        static = inspect.getattr_static(item, name, _MISSING_DRAG_LOCAL)
        if static is _MISSING_DRAG_LOCAL:
            continue
        class_static = inspect.getattr_static(
            type(item),
            name,
            _MISSING_DRAG_LOCAL,
        )
        if (
            type(namespace) is not dict
            or not dict.__contains__(namespace, name)
            or class_static is not _MISSING_DRAG_LOCAL
        ):
            return False
    return True


def _has_trusted_qt_item_ports(item: object, scene: object) -> bool:
    if not isinstance(item, QGraphicsItem) or not _has_callback_free_qt_snapshot_ports(
        item
    ):
        return False
    try:
        if item.scene() is not scene:
            return False
        item_change = inspect.getattr_static(type(item), "itemChange")
        if type(item_change).__module__ != "sip":
            return False
        for name in ("data", "setData", "moveBy", "pos", "setPos", "scene"):
            static = inspect.getattr_static(item, name, _MISSING_DRAG_LOCAL)
            if type(static).__module__ != "sip" or not inspect.isbuiltin(
                getattr(item, name)
            ):
                return False
    except (AttributeError, RuntimeError, TypeError):
        return False
    return True


def _reject_unsafe_qt_snapshot_ports(item: object) -> None:
    if isinstance(item, QGraphicsItem) and not _has_callback_free_qt_snapshot_ports(
        item
    ):
        raise RuntimeError(
            "Selection drag requires callback-free Qt snapshot ports"
        )


def _has_trusted_selection_item_mutation_surface(item: QGraphicsItem) -> bool:
    try:
        kind = item.data(0)
        if kind == "mark":
            payload = item.data(1)
            return payload is None or type(payload) is dict
        if kind == "shape":
            return (
                type(item.data(1)) is dict
                and inspect.isbuiltin(cast(Any, item).setPath)
            )
        if kind in {"orbital", "ts_bracket"}:
            payload = item.data(1)
            return payload is None or type(payload) is dict
        if kind in {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "note",
        }:
            payload = item.data(2)
            return payload is None or type(payload) is dict
    except (AttributeError, RuntimeError, TypeError):
        return False
    return True


@dataclass(frozen=True, slots=True)
class _DragBoundAttribute:
    owner: object
    name: str
    value: object
    identity: bool = True

    def restore(self) -> None:
        setattr(self.owner, self.name, self.value)

    def verify(self) -> None:
        actual = getattr(self.owner, self.name)
        if actual is self.value:
            return
        if not self.identity:
            try:
                if bool(actual == self.value):
                    return
            except BaseException:
                pass
        raise RuntimeError(f"drag authority {self.name!r} changed")


@dataclass(frozen=True, slots=True)
class _DragMappingEntry:
    key: object
    present: bool
    value: object
    list_contents: tuple[object, ...] | None


@dataclass(frozen=True, slots=True)
class _DragMappingPort:
    owner: object
    name: str
    mapping: dict
    entries: tuple[_DragMappingEntry, ...]

    @classmethod
    def capture(
        cls,
        owner: object,
        name: str,
        keys: set[int],
    ) -> _DragMappingPort:
        mapping = getattr(owner, name)
        if type(mapping) is not dict:
            raise RuntimeError(f"trusted drag requires a plain {name} mapping")
        return cls(
            owner=owner,
            name=name,
            mapping=mapping,
            entries=tuple(
                _DragMappingEntry(
                    key=key,
                    present=key in mapping,
                    value=mapping.get(key),
                    list_contents=(
                        tuple(mapping[key])
                        if key in mapping and type(mapping[key]) is list
                        else None
                    ),
                )
                for key in keys
            ),
        )

    def restore(self) -> None:
        setattr(self.owner, self.name, self.mapping)
        for entry in self.entries:
            if not entry.present:
                dict.pop(self.mapping, entry.key, None)
                continue
            if type(entry.value) is list and entry.list_contents is not None:
                list.__setitem__(entry.value, slice(None), entry.list_contents)
            dict.__setitem__(self.mapping, entry.key, entry.value)

    def verify(self) -> None:
        if getattr(self.owner, self.name) is not self.mapping:
            raise RuntimeError(f"drag mapping root {self.name!r} changed")
        for entry in self.entries:
            if (entry.key in self.mapping) is not entry.present:
                raise RuntimeError(
                    f"drag mapping entry {self.name}[{entry.key!r}] changed"
                )
            if not entry.present:
                continue
            actual = self.mapping[entry.key]
            if actual is not entry.value:
                raise RuntimeError(
                    f"drag mapping value {self.name}[{entry.key!r}] changed"
                )
            if entry.list_contents is not None:
                if len(actual) != len(entry.list_contents) or any(
                    current is not expected
                    for current, expected in zip(
                        actual,
                        entry.list_contents,
                        strict=True,
                    )
                ):
                    raise RuntimeError(
                        f"drag mapping list {self.name}[{entry.key!r}] changed"
                    )


@dataclass(frozen=True, slots=True)
class _DragListPort:
    owner: object
    name: str
    value: list
    contents: tuple[object, ...]

    @classmethod
    def capture(cls, owner: object, name: str) -> _DragListPort:
        value = getattr(owner, name)
        if type(value) is not list:
            raise RuntimeError(f"trusted drag requires a plain {name} list")
        return cls(owner, name, value, tuple(value))

    def restore(self) -> None:
        list.__setitem__(self.value, slice(None), self.contents)
        setattr(self.owner, self.name, self.value)

    def verify(self) -> None:
        if getattr(self.owner, self.name) is not self.value:
            raise RuntimeError(f"drag list root {self.name!r} changed")
        if len(self.value) != len(self.contents) or any(
            current is not expected
            for current, expected in zip(
                self.value,
                self.contents,
                strict=True,
            )
        ):
            raise RuntimeError(f"drag list contents {self.name!r} changed")


@dataclass(slots=True)
class _TrustedSelectionDragSnapshot:
    """Selection-sized savepoint for the callback-free production move path."""

    canvas: object
    history_service: object
    services: object
    runtime_state: object
    model: object
    scene: QGraphicsScene
    scene_rect: QRectF
    roots: tuple[_DragBoundAttribute, ...]
    mappings: tuple[_DragMappingPort, ...]
    lists: tuple[_DragListPort, ...]
    objects: tuple[_ObjectStateSnapshot, ...]
    containers: _ContainerGraphSnapshot
    items: tuple[_SceneItemExactSnapshot, ...]
    atom_ids: frozenset[int]
    selection_items: tuple[object, ...]
    bond_ids: frozenset[int]
    boundary_bond_ids: frozenset[int]
    affected_items: tuple[QGraphicsItem, ...]
    affected_ring_items: tuple[QGraphicsItem, ...]
    affected_ring_bindings: tuple[tuple[QGraphicsItem, tuple[int, ...]], ...]
    ring_atom_entries: tuple[tuple[int, bool, object], ...]
    requires_full_move: bool
    fallback_snapshot: object | None = None

    @staticmethod
    def _production_roots(
        canvas: object,
        context: ToolContext,
        history_service: object,
    ) -> tuple[Any, Any, Any, Any, QGraphicsScene] | None:
        if not _trusted_drag_module_ports_are_current():
            return None
        if not _has_exact_type(canvas, "ui.canvas_view", "CanvasView"):
            return None
        if type(context) is not ToolContext:
            return None
        try:
            canvas_namespace = object.__getattribute__(canvas, "__dict__")
            context_namespace = object.__getattribute__(context, "__dict__")
        except (AttributeError, TypeError):
            return None
        if type(canvas_namespace) is not dict or type(context_namespace) is not dict:
            return None
        services = dict.get(canvas_namespace, "services", _MISSING_DRAG_LOCAL)
        runtime_state = dict.get(
            canvas_namespace,
            "runtime_state",
            _MISSING_DRAG_LOCAL,
        )
        model = dict.get(canvas_namespace, "model", _MISSING_DRAG_LOCAL)
        if (
            dict.get(context_namespace, "canvas", _MISSING_DRAG_LOCAL) is not canvas
            or not _has_exact_type(
                services,
                "ui.canvas_service_types",
                "CanvasServices",
            )
            or not _has_exact_type(
                runtime_state,
                "ui.canvas_runtime_state",
                "CanvasRuntimeState",
            )
            or not _has_exact_type(model, "core.model", "MoleculeModel")
        ):
            return None
        move_controller = getattr(services, "move_controller", None)
        hit_testing_service = getattr(services, "hit_testing_service", None)
        selection_controller = getattr(services, "selection_controller", None)
        outline_service = getattr(selection_controller, "outline_service", None)
        style_controller = getattr(services, "style_controller", None)
        mark_registry = getattr(runtime_state, "mark_registry", None)
        if not all(
            (
                _has_exact_bound_method(
                    move_controller,
                    module="ui.canvas_move_controller",
                    type_name="CanvasMoveController",
                    method_name="move_atoms",
                ),
                _has_exact_bound_method(
                    move_controller,
                    module="ui.canvas_move_controller",
                    type_name="CanvasMoveController",
                    method_name="move_item",
                ),
                _has_exact_bound_method(
                    move_controller,
                    module="ui.canvas_move_controller",
                    type_name="CanvasMoveController",
                    method_name="move_atom",
                ),
                _has_exact_bound_method(
                    move_controller,
                    module="ui.canvas_move_controller",
                    type_name="CanvasMoveController",
                    method_name="move_rings_for_atoms",
                ),
                _has_exact_bound_method(
                    move_controller,
                    module="ui.canvas_move_controller",
                    type_name="CanvasMoveController",
                    method_name="_shift_active_handles_for",
                ),
                _has_exact_type(
                    hit_testing_service,
                    "ui.canvas_hit_testing_service",
                    "CanvasHitTestingService",
                ),
                _has_exact_bound_method(
                    hit_testing_service,
                    module="ui.canvas_hit_testing_service",
                    type_name="CanvasHitTestingService",
                    method_name="mark_spatial_index_dirty",
                ),
                _has_exact_type(
                    mark_registry,
                    "ui.canvas_mark_registry",
                    "CanvasMarkRegistry",
                ),
                _has_exact_bound_method(
                    mark_registry,
                    module="ui.canvas_mark_registry",
                    type_name="CanvasMarkRegistry",
                    method_name="get_for_atom",
                ),
                _has_exact_bound_method(
                    selection_controller,
                    module="ui.selection_controller",
                    type_name="SelectionController",
                    method_name="shift_selection_outlines",
                ),
                _has_exact_bound_method(
                    outline_service,
                    module="ui.selection_outline_service",
                    type_name="SelectionOutlineService",
                    method_name="shift_selection_outlines",
                ),
                _has_exact_bound_method(
                    style_controller,
                    module="ui.canvas_style_controller",
                    type_name="CanvasStyleController",
                    method_name="suspend_selection_outline",
                ),
                _has_exact_bound_method(
                    context,
                    module="ui.tool_context",
                    type_name="ToolContext",
                    method_name="suspend_selection_outline",
                ),
                _has_exact_bound_method(
                    context,
                    module="ui.tool_context",
                    type_name="ToolContext",
                    method_name="_call_port",
                ),
                _has_exact_type(
                    history_service,
                    "ui.canvas_history_service",
                    "CanvasHistoryService",
                ),
                _has_exact_callback_free_production_history_state(
                    history_service
                ),
                dict.get(
                    context_namespace,
                    "history_service",
                    _MISSING_DRAG_LOCAL,
                )
                is history_service,
                dict.get(
                    context_namespace,
                    "selection_controller",
                    _MISSING_DRAG_LOCAL,
                )
                is selection_controller,
                dict.get(
                    context_namespace,
                    "style_controller",
                    _MISSING_DRAG_LOCAL,
                )
                is style_controller,
                getattr(move_controller, "canvas", None) is canvas,
                getattr(move_controller, "hit_testing_service", None)
                is hit_testing_service,
                getattr(move_controller, "marks", None) is mark_registry,
                getattr(hit_testing_service, "canvas", None) is canvas,
                getattr(selection_controller, "canvas", None) is canvas,
                getattr(outline_service, "canvas", None) is canvas,
                getattr(style_controller, "canvas", None) is canvas,
            )
        ):
            return None
        scene_getter = getattr(canvas, "scene", None)
        if not inspect.isbuiltin(scene_getter):
            return None
        scene = scene_getter()
        if type(scene) is not QGraphicsScene or scene_rect_is_automatic(scene):
            return None
        return services, runtime_state, model, move_controller, scene

    @classmethod
    def capture(
        cls,
        canvas: object,
        context: ToolContext,
        history_service: object,
        *,
        atom_ids: set[int],
        selection_items: list[object],
        bond_ids: set[int],
        boundary_bond_ids: set[int],
    ) -> _TrustedSelectionDragSnapshot | None:
        production = cls._production_roots(canvas, context, history_service)
        if production is None:
            return None
        services, runtime, model, _move_controller, scene = production
        containers = _ContainerGraphSnapshot()
        object_snapshots: list[_ObjectStateSnapshot] = []

        atom_mapping = _DragMappingPort.capture(model, "atoms", atom_ids)
        for entry in atom_mapping.entries:
            if not entry.present or entry.value is None:
                continue
            if not _has_exact_type(entry.value, "core.model", "Atom"):
                return None
            snapshot = _ObjectStateSnapshot.capture(entry.value, containers)
            if snapshot is not None:
                object_snapshots.append(snapshot)

        coords_state = runtime.atom_coords_3d_state
        atom_graphics_state = runtime.atom_graphics_state
        bond_graphics_state = runtime.bond_graphics_state
        mark_registry = runtime.mark_registry
        scene_items_state = runtime.scene_items_state
        outline_state = runtime.selection_outline_state
        handle_state = runtime.handle_state
        selection_style = runtime.selection_style_state
        spatial_index = runtime.spatial_index_state
        if not all(
            (
                _has_exact_type(
                    coords_state,
                    "ui.atom_coords_access",
                    "CanvasAtomCoords3DState",
                ),
                _has_exact_type(
                    atom_graphics_state,
                    "ui.canvas_atom_graphics_state",
                    "CanvasAtomGraphicsState",
                ),
                _has_exact_type(
                    bond_graphics_state,
                    "ui.canvas_bond_graphics_state",
                    "CanvasBondGraphicsState",
                ),
                _has_exact_type(
                    scene_items_state,
                    "ui.canvas_scene_items_state",
                    "CanvasSceneItemsState",
                ),
                _has_exact_type(
                    outline_state,
                    "ui.selection_outline_state",
                    "SelectionOutlineState",
                ),
                _has_exact_type(
                    handle_state,
                    "ui.handle_state",
                    "CanvasHandleState",
                ),
                _has_exact_type(
                    selection_style,
                    "ui.selection_style_state",
                    "SelectionStyleState",
                ),
                _has_exact_type(
                    spatial_index,
                    "ui.spatial_index_state",
                    "CanvasSpatialIndexState",
                ),
            )
        ):
            return None
        affected_bond_ids = set(bond_ids) | set(boundary_bond_ids)
        mappings = (
            atom_mapping,
            _DragMappingPort.capture(
                coords_state,
                "atom_coords_3d",
                atom_ids,
            ),
            _DragMappingPort.capture(
                atom_graphics_state,
                "atom_items",
                atom_ids,
            ),
            _DragMappingPort.capture(
                atom_graphics_state,
                "atom_dots",
                atom_ids,
            ),
            _DragMappingPort.capture(
                bond_graphics_state,
                "bond_items",
                affected_bond_ids,
            ),
            _DragMappingPort.capture(mark_registry, "by_atom", atom_ids),
        )

        affected: list[object] = list(selection_items)
        for item in selection_items:
            if not isinstance(item, QGraphicsItem):
                return None
            _reject_unsafe_qt_snapshot_ports(item)
            if not _has_trusted_selection_item_mutation_surface(item):
                return None
        for mapping in mappings[2:4]:
            affected.extend(
                entry.value
                for entry in mapping.entries
                if entry.present and entry.value is not None
            )
        for entry in mappings[4].entries:
            if entry.present and type(entry.value) is list:
                affected.extend(entry.value)
        for entry in mappings[5].entries:
            if entry.present and type(entry.value) is list:
                affected.extend(entry.value)

        affected_rings: list[QGraphicsItem] = []
        affected_ring_bindings: list[
            tuple[QGraphicsItem, tuple[int, ...]]
        ] = []
        ring_atom_entries: dict[int, tuple[bool, object]] = {}
        if atom_ids:
            ring_items = scene_items_state.ring_items
            if type(ring_items) is not list:
                return None
            for ring in ring_items:
                if not _has_trusted_qt_item_ports(ring, scene):
                    return None
                ring_atom_ids = ring.data(2)
                if type(ring_atom_ids) is not list:
                    continue
                if not all(type(atom_id) is int for atom_id in ring_atom_ids):
                    return None
                if not atom_ids.isdisjoint(ring_atom_ids):
                    if not inspect.isbuiltin(getattr(ring, "setPolygon", None)):
                        return None
                    for ring_atom_id in ring_atom_ids:
                        ring_atom = model.atoms.get(ring_atom_id)
                        if ring_atom is not None and not _has_exact_type(
                            ring_atom,
                            "core.model",
                            "Atom",
                        ):
                            return None
                        ring_atom_entries.setdefault(
                            ring_atom_id,
                            (
                                ring_atom_id in model.atoms,
                                ring_atom,
                            ),
                        )
                    affected_rings.append(ring)
                    affected_ring_bindings.append(
                        (ring, tuple(ring_atom_ids))
                    )
                    affected.append(ring)

        outline_list = _DragListPort.capture(outline_state, "outlines")
        handle_list = _DragListPort.capture(handle_state, "active_handles")
        affected.extend(outline_list.contents)
        affected.extend(handle_list.contents)
        unique_items: list[QGraphicsItem] = []
        seen_items: set[int] = set()
        for item in affected:
            if id(item) in seen_items:
                continue
            _reject_unsafe_qt_snapshot_ports(item)
            if not _has_trusted_qt_item_ports(item, scene):
                return None
            seen_items.add(id(item))
            unique_items.append(cast(QGraphicsItem, item))

        item_snapshots: list[_SceneItemExactSnapshot] = []
        for item in unique_items:
            item_snapshot = _SceneItemExactSnapshot.capture(item, containers)
            if item_snapshot is None:
                return None
            item_snapshots.append(item_snapshot)

        roots = (
            _DragBoundAttribute(canvas, "services", services),
            _DragBoundAttribute(canvas, "runtime_state", runtime),
            _DragBoundAttribute(canvas, "model", model),
            _DragBoundAttribute(runtime, "atom_coords_3d_state", coords_state),
            _DragBoundAttribute(runtime, "atom_graphics_state", atom_graphics_state),
            _DragBoundAttribute(runtime, "bond_graphics_state", bond_graphics_state),
            _DragBoundAttribute(runtime, "mark_registry", mark_registry),
            _DragBoundAttribute(runtime, "scene_items_state", scene_items_state),
            _DragBoundAttribute(runtime, "selection_outline_state", outline_state),
            _DragBoundAttribute(runtime, "handle_state", handle_state),
            _DragBoundAttribute(runtime, "selection_style_state", selection_style),
            _DragBoundAttribute(runtime, "spatial_index_state", spatial_index),
            _DragBoundAttribute(selection_style, "suspend_outline", selection_style.suspend_outline, identity=False),
            _DragBoundAttribute(handle_state, "target", handle_state.target),
            _DragBoundAttribute(spatial_index, "dirty", spatial_index.dirty, identity=False),
            _DragBoundAttribute(spatial_index, "cell_size", spatial_index.cell_size, identity=False),
            _DragBoundAttribute(spatial_index, "atom_grid", spatial_index.atom_grid),
            _DragBoundAttribute(spatial_index, "bond_grid", spatial_index.bond_grid),
            _DragBoundAttribute(
                spatial_index,
                "indexed_atom_count",
                spatial_index.indexed_atom_count,
                identity=False,
            ),
            _DragBoundAttribute(
                spatial_index,
                "indexed_bond_slot_count",
                spatial_index.indexed_bond_slot_count,
                identity=False,
            ),
        )
        return cls(
            canvas=canvas,
            history_service=history_service,
            services=services,
            runtime_state=runtime,
            model=model,
            scene=scene,
            scene_rect=QRectF(scene.sceneRect()),
            roots=roots,
            mappings=mappings,
            lists=(outline_list, handle_list),
            objects=tuple(object_snapshots),
            containers=containers,
            items=tuple(item_snapshots),
            atom_ids=frozenset(atom_ids),
            selection_items=tuple(selection_items),
            bond_ids=frozenset(bond_ids),
            boundary_bond_ids=frozenset(boundary_bond_ids),
            affected_items=tuple(unique_items),
            affected_ring_items=tuple(affected_rings),
            affected_ring_bindings=tuple(affected_ring_bindings),
            ring_atom_entries=tuple(
                (atom_id, present, value)
                for atom_id, (present, value) in ring_atom_entries.items()
            ),
            requires_full_move=(
                bool(boundary_bond_ids)
                or any(
                    cast(Any, item).data(0) == "mark"
                    for item in selection_items
                )
            ),
        )

    def targets_match(self, tool: SelectionDragMixin) -> bool:
        return (
            tool._selection_atom_ids == set(self.atom_ids)
            and tool._drag_bond_ids == set(self.bond_ids)
            and tool._drag_boundary_bond_ids
            == set(self.boundary_bond_ids)
            and len(tool._selection_items) == len(self.selection_items)
            and all(
                actual is expected
                for actual, expected in zip(
                    tool._selection_items,
                    self.selection_items,
                    strict=True,
                )
            )
        )

    def _capture_authority_is_current(self) -> bool:
        try:
            for root in self.roots:
                if root.identity and getattr(root.owner, root.name) is not root.value:
                    return False
            for mapping in self.mappings:
                if getattr(mapping.owner, mapping.name) is not mapping.mapping:
                    return False
                for entry in mapping.entries:
                    if (entry.key in mapping.mapping) is not entry.present:
                        return False
                    if not entry.present or mapping.name == "atom_coords_3d":
                        continue
                    actual = mapping.mapping[entry.key]
                    if actual is not entry.value:
                        return False
                    if entry.list_contents is not None and (
                        type(actual) is not list
                        or len(actual) != len(entry.list_contents)
                        or any(
                            current is not expected
                            for current, expected in zip(
                                actual,
                                entry.list_contents,
                                strict=True,
                            )
                        )
                    ):
                        return False
            for list_port in self.lists:
                if getattr(list_port.owner, list_port.name) is not list_port.value:
                    return False
                if len(list_port.value) != len(list_port.contents) or any(
                    current is not expected
                    for current, expected in zip(
                        list_port.value,
                        list_port.contents,
                        strict=True,
                    )
                ):
                    return False
        except BaseException:
            return False
        return True

    def ports_are_trusted(self, tool: SelectionDragMixin) -> bool:
        if self.requires_full_move:
            return False
        if (
            move_atoms_for is not _TRUSTED_MOVE_ATOMS_FOR
            or move_item_for is not _TRUSTED_MOVE_ITEM_FOR
            or shift_selection_outlines_for
            is not _TRUSTED_SHIFT_SELECTION_OUTLINES_FOR
        ):
            return False
        production = self._production_roots(
            self.canvas,
            tool.context,
            self.history_service,
        )
        if production is None:
            return False
        services, runtime, model, _move_controller, scene = production
        if (
            services is not self.services
            or runtime is not self.runtime_state
            or model is not self.model
            or scene is not self.scene
            or QRectF(scene.sceneRect()) != self.scene_rect
            or not self._capture_authority_is_current()
        ):
            return False
        if not all(
            _has_trusted_qt_item_ports(item, self.scene)
            for item in self.affected_items
        ):
            return False
        try:
            if not all(
                _has_trusted_selection_item_mutation_surface(
                    cast(QGraphicsItem, item)
                )
                for item in self.selection_items
            ):
                return False
            for ring, expected_atom_ids in self.affected_ring_bindings:
                current_atom_ids = ring.data(2)
                if (
                    type(current_atom_ids) is not list
                    or tuple(current_atom_ids) != expected_atom_ids
                    or not inspect.isbuiltin(cast(Any, ring).setPolygon)
                ):
                    return False
            atoms = cast(Any, self.model).atoms
            for atom_id, present, value in self.ring_atom_entries:
                if (atom_id in atoms) is not present:
                    return False
                if present and atoms[atom_id] is not value:
                    return False
        except BaseException:
            return False
        return True

    def promote_to_full(self) -> None:
        if self.fallback_snapshot is not None:
            return
        snapshot = capture_history_transaction_for_history(
            self.canvas,
            history_service=self.history_service,
        )
        self.fallback_snapshot = snapshot

    def _restore_once(self, *, reverse: bool) -> list[BaseException]:
        errors: list[BaseException] = []
        groups: tuple[tuple[object, ...], ...] = (
            tuple(self.roots),
            tuple(self.mappings),
            tuple(self.objects),
            (self.containers,),
            tuple(self.items),
            tuple(self.lists),
        )
        ordered_groups = tuple(reversed(groups)) if reverse else groups
        for group in ordered_groups:
            values = tuple(reversed(group)) if reverse else group
            for value in values:
                try:
                    restore_errors = cast(Any, value).restore()
                    if isinstance(restore_errors, list):
                        errors.extend(restore_errors)
                except BaseException as error:
                    errors.append(error)
        return errors

    def _verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        if (
            getattr(self.canvas, "services", None) is not self.services
            or getattr(self.canvas, "runtime_state", None) is not self.runtime_state
            or getattr(self.canvas, "model", None) is not self.model
            or cast(Any, self.canvas).scene() is not self.scene
        ):
            errors.append(RuntimeError("trusted drag root authority changed"))
        if QRectF(self.scene.sceneRect()) != self.scene_rect:
            errors.append(RuntimeError("trusted drag scene rect changed"))
        for value in (*self.roots, *self.mappings, *self.lists):
            try:
                cast(Any, value).verify()
            except BaseException as error:
                errors.append(error)
        errors.extend(self.containers.verify())
        for object_snapshot in self.objects:
            errors.extend(object_snapshot.verify())
        for item_snapshot in self.items:
            errors.extend(item_snapshot.verify())
        for item in self.affected_items:
            try:
                if item.scene() is not self.scene:
                    raise RuntimeError("trusted drag item membership changed")
            except BaseException as error:
                errors.append(error)
        return errors

    def restore_with_result(self) -> HistoryTransactionRestoreResult:
        errors: list[BaseException] = []
        fallback_authoritative = True
        fallback = self.fallback_snapshot
        if fallback is not None:
            try:
                result = cast(Any, fallback).restore_with_result()
            except BaseException as error:
                errors.append(error)
                fallback_authoritative = False
            else:
                errors.extend(result.errors)
                fallback_authoritative = bool(result.authoritative)

        local_authoritative = False
        for attempt in range(2):
            errors.extend(self._restore_once(reverse=bool(attempt)))
            verification_errors = self._verify()
            if not verification_errors:
                local_authoritative = True
                break
            errors.extend(verification_errors)
        return HistoryTransactionRestoreResult(
            authoritative=fallback_authoritative and local_authoritative,
            fallback_to_inverse=False,
            errors=tuple(errors),
        )

    def release(self) -> None:
        fallback = self.fallback_snapshot
        if fallback is None:
            return
        release = getattr(fallback, "release", None)
        if callable(release):
            release()


@dataclass(frozen=True, slots=True)
class _DragHistoryPolicyPort:
    """Capture-bound scalar history policy with callback-safe raw ports."""

    name: str
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]

    @staticmethod
    def _values_match(actual: object, expected: object) -> bool:
        if actual is expected:
            return True
        if type(actual) is not type(expected):
            return False
        return bool(actual == expected)

    def matches(self, expected: object) -> bool:
        return self._values_match(self.getter(), expected)

    def apply_once(self) -> None:
        if not self.matches(self.value):
            self.setter(self.value)

    def apply_expected_once(self, expected: object) -> None:
        if not self.matches(expected):
            self.setter(expected)

    def verify(self, expected: object) -> None:
        if not self.matches(expected):
            raise RuntimeError(f"drag history policy {self.name!r} changed")


@dataclass(frozen=True, slots=True)
class HistoryCheckpoint:
    history_items: tuple[object, ...]
    redo_items: tuple[object, ...]
    enabled: object
    limit: object


@dataclass(frozen=True, slots=True)
class _DragHistoryAuthority:
    """Immutable begin-bound history authority retained outside the token."""

    history_service: object
    history_push: Callable[[HistoryCommand], object]
    history_stacks: HistoryStackSnapshot
    begin_history_checkpoint: HistoryCheckpoint
    history_policy_ports: tuple[_DragHistoryPolicyPort, ...]


@dataclass(slots=True)
class _DragTransactionToken:
    """One published drag owner and its inspectable compatibility fields."""

    history_service: object
    history_push: Callable[[HistoryCommand], object] | None = None
    history_stacks: HistoryStackSnapshot | None = None
    begin_history_checkpoint: HistoryCheckpoint | None = None
    history_policy_ports: tuple[_DragHistoryPolicyPort, ...] = ()
    history_authority: _DragHistoryAuthority | None = None
    canvas_snapshot: object | None = None


@dataclass(frozen=True, slots=True)
class _DragTransactionAuthority:
    """One immutable owner for both history and canvas begin savepoints."""

    token: _DragTransactionToken
    history: _DragHistoryAuthority
    canvas_snapshot: object


@dataclass(frozen=True, slots=True)
class _DragHistoryPublication:
    token: _DragTransactionToken
    authority: _DragTransactionAuthority
    checkpoint: HistoryCheckpoint


@dataclass(slots=True)
class _ReplacementDragCheckpoint:
    """Absolute canvas checkpoint plus the current replacement-tool state."""

    token: _DragTransactionToken
    transaction_authority: _DragTransactionAuthority
    canvas_snapshot: object
    history_checkpoint: HistoryCheckpoint | None
    drag_selection: bool
    selection_atom_ids: frozenset[int]
    selection_items: tuple[object, ...]
    drag_bond_ids: frozenset[int]
    drag_boundary_bond_ids: frozenset[int]
    suspended_outline: bool
    selection_outline_was_suspended: bool
    start_pos: QPointF | None
    moved: bool
    total_delta: QPointF
    last_drag_time: object

    def restore_local(self, tool: SelectionDragMixin) -> None:
        tool._drag_selection = self.drag_selection
        tool._selection_atom_ids = set(self.selection_atom_ids)
        tool._selection_items = list(self.selection_items)
        tool._drag_bond_ids = set(self.drag_bond_ids)
        tool._drag_boundary_bond_ids = set(self.drag_boundary_bond_ids)
        tool._suspended_outline = self.suspended_outline
        tool._selection_outline_was_suspended = (
            self.selection_outline_was_suspended
        )
        tool._start_pos = (
            QPointF(self.start_pos) if self.start_pos is not None else None
        )
        tool._moved = self.moved
        tool._total_delta = QPointF(self.total_delta)
        if self.last_drag_time is _MISSING_DRAG_LOCAL:
            if hasattr(tool, "_last_drag_time"):
                delattr(tool, "_last_drag_time")
        else:
            cast(Any, tool)._last_drag_time = self.last_drag_time

    def verify_local(self, tool: SelectionDragMixin) -> None:
        if tool._drag_transaction is not self.token:
            raise RuntimeError("replacement drag owner changed during reapply")
        if tool._drag_selection is not self.drag_selection:
            raise RuntimeError("replacement drag active state changed during reapply")
        if tool._selection_atom_ids != set(self.selection_atom_ids):
            raise RuntimeError("replacement drag atom targets changed during reapply")
        if len(tool._selection_items) != len(self.selection_items) or any(
            actual is not expected
            for actual, expected in zip(
                tool._selection_items,
                self.selection_items,
                strict=True,
            )
        ):
            raise RuntimeError("replacement drag item targets changed during reapply")
        if tool._drag_bond_ids != set(self.drag_bond_ids):
            raise RuntimeError("replacement drag bond targets changed during reapply")
        if tool._drag_boundary_bond_ids != set(self.drag_boundary_bond_ids):
            raise RuntimeError(
                "replacement drag boundary targets changed during reapply"
            )
        if tool._suspended_outline is not self.suspended_outline:
            raise RuntimeError(
                "replacement drag outline suspension changed during reapply"
            )
        if (
            tool._selection_outline_was_suspended
            is not self.selection_outline_was_suspended
        ):
            raise RuntimeError(
                "replacement drag outline baseline changed during reapply"
            )
        if tool._start_pos != self.start_pos:
            raise RuntimeError("replacement drag start position changed during reapply")
        if tool._moved is not self.moved:
            raise RuntimeError("replacement drag movement state changed during reapply")
        if tool._total_delta != self.total_delta:
            raise RuntimeError("replacement drag delta changed during reapply")
        actual_last_drag_time = getattr(
            tool,
            "_last_drag_time",
            _MISSING_DRAG_LOCAL,
        )
        if actual_last_drag_time != self.last_drag_time:
            raise RuntimeError("replacement drag timing state changed during reapply")


def _add_drag_rollback_note(
    primary_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(primary_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Selection drag recovery also encountered an error while "
                f"{phase}: {type(rollback_error).__name__}: {rollback_error}"
            )
    except BaseException:
        # Diagnostic hooks are outside the transaction authority. A broken hook
        # must never replace the input, termination, or history failure that
        # owns rollback.
        return


def atom_ids_with_bonds(canvas, atom_ids: set[int], bond_ids: set[int]) -> set[int]:
    expanded = set(atom_ids)
    for bond_id in bond_ids:
        bond = bond_for_id(canvas, bond_id)
        if bond is not None:
            expanded.add(bond.a)
            expanded.add(bond.b)
    return expanded


class SelectionDragMixin:
    # Provided by the host Tool subclass (SelectTool, MoveTool).
    context: ToolContext
    canvas: Any
    _drag_transaction: Any | None
    _drag_history_authority: _DragHistoryAuthority | None
    _drag_transaction_authority: _DragTransactionAuthority | None
    _drag_history_publication: _DragHistoryPublication | None

    def _reset_selection_drag_state(self) -> None:
        if self._drag_transaction is None:
            self._drag_history_authority = None
            self._drag_transaction_authority = None
            self._drag_history_publication = None
        self._drag_selection = False
        self._selection_atom_ids: set[int] = set()
        self._selection_items: list = []
        self._drag_bond_ids: set[int] = set()
        self._drag_boundary_bond_ids: set[int] = set()
        self._suspended_outline = False
        self._selection_outline_was_suspended = False
        self._start_pos: QPointF | None = None
        self._moved: bool = False
        self._total_delta: QPointF = QPointF(0.0, 0.0)

    @staticmethod
    def _capture_drag_history_policy(
        snapshot: HistoryStackSnapshot,
    ) -> tuple[_DragHistoryPolicyPort, ...]:
        state = snapshot.state
        getattribute = inspect.getattr_static(
            type(state),
            "__getattribute__",
            _MISSING_DRAG_HISTORY_POLICY,
        )
        setattribute = inspect.getattr_static(
            type(state),
            "__setattr__",
            _MISSING_DRAG_HISTORY_POLICY,
        )
        if not callable(getattribute) or not callable(setattribute):
            raise RuntimeError("drag history policy has incomplete bound ports")
        getattribute_port = cast(Callable[[object, str], object], getattribute)
        setattribute_port = cast(
            Callable[[object, str, object], object],
            setattribute,
        )
        ports: list[_DragHistoryPolicyPort] = []
        for name in ("enabled", "limit"):
            if (
                inspect.getattr_static(
                    state,
                    name,
                    _MISSING_DRAG_HISTORY_POLICY,
                )
                is _MISSING_DRAG_HISTORY_POLICY
            ):
                raise RuntimeError(
                    f"drag history requires a verifiable {name!r} policy"
                )

            def get_value(
                _getattribute=getattribute_port,
                _state=state,
                _name=name,
            ) -> object:
                return _getattribute(_state, _name)

            def set_value(
                value: object,
                _setattribute=setattribute_port,
                _state=state,
                _name=name,
            ) -> object:
                return _setattribute(_state, _name, value)

            value = get_value()
            if name == "enabled" and type(value) is not bool:
                raise RuntimeError("drag history enabled policy must be an exact bool")
            if name == "limit" and (type(value) is not int or value < 0):
                raise RuntimeError(
                    "drag history limit policy must be a non-negative exact int"
                )
            ports.append(
                _DragHistoryPolicyPort(
                    name=name,
                    value=value,
                    getter=get_value,
                    setter=set_value,
                )
            )
        return tuple(ports)

    @staticmethod
    def _history_checkpoint_for(
        authority: _DragHistoryAuthority,
    ) -> HistoryCheckpoint:
        policies = {
            port.name: port.value for port in authority.history_policy_ports
        }
        snapshot = authority.history_stacks
        return HistoryCheckpoint(
            history_items=tuple(snapshot.history_port.iterate()),
            redo_items=tuple(snapshot.redo_port.iterate()),
            enabled=policies["enabled"],
            limit=policies["limit"],
        )

    def _verify_bound_history_authority(
        self,
        authority: _DragHistoryAuthority,
        *,
        checkpoint: HistoryCheckpoint | None,
    ) -> None:
        snapshot = authority.history_stacks
        if checkpoint is None:
            snapshot.state_port.verify()
            if snapshot.history_port.getter() is not snapshot.history:
                raise RuntimeError(
                    "drag history-list identity changed during the interaction"
                )
            if snapshot.redo_port.getter() is not snapshot.redo_stack:
                raise RuntimeError(
                    "drag redo-list identity changed during the interaction"
                )
            return
        snapshot.verify_exact_items(
            history_items=checkpoint.history_items,
            redo_items=checkpoint.redo_items,
        )
        expected_policies = {
            "enabled": checkpoint.enabled,
            "limit": checkpoint.limit,
        }
        for port in authority.history_policy_ports:
            port.verify(expected_policies[port.name])
        # Policy getters are callbacks. Re-check state/list roots and finish
        # with callback-free raw list iteration so cross-root poisoning cannot
        # be accepted after a policy appeared correct.
        snapshot.verify_exact_items(
            history_items=checkpoint.history_items,
            redo_items=checkpoint.redo_items,
        )

    @staticmethod
    def _verify_drag_token_history_authority(
        token: _DragTransactionToken,
        authority: _DragHistoryAuthority,
    ) -> None:
        if token.history_service is not authority.history_service:
            raise RuntimeError("selection drag token history owner changed")
        if token.history_push is not authority.history_push:
            raise RuntimeError("selection drag token push port changed")
        if token.history_stacks is not authority.history_stacks:
            raise RuntimeError("selection drag token stack authority changed")
        if token.begin_history_checkpoint is not authority.begin_history_checkpoint:
            raise RuntimeError("selection drag token checkpoint changed")
        if token.history_policy_ports is not authority.history_policy_ports:
            raise RuntimeError("selection drag token policy authority changed")
        if token.history_authority is not authority:
            raise RuntimeError("selection drag token frozen authority changed")

    @classmethod
    def _verify_drag_token_transaction_authority(
        cls,
        token: _DragTransactionToken,
        authority: _DragTransactionAuthority,
    ) -> None:
        if authority.token is not token:
            raise RuntimeError("selection drag frozen owner changed")
        cls._verify_drag_token_history_authority(token, authority.history)
        if token.canvas_snapshot is not authority.canvas_snapshot:
            raise RuntimeError("selection drag token canvas authority changed")

    def _transaction_authority_for(
        self,
        token: _DragTransactionToken,
    ) -> _DragTransactionAuthority:
        authority = getattr(self, "_drag_transaction_authority", None)
        if not isinstance(authority, _DragTransactionAuthority):
            raise RuntimeError("Selection drag lost its local transaction authority")
        if self._drag_history_authority is not authority.history:
            raise RuntimeError("Selection drag local history authority changed")
        self._verify_drag_token_transaction_authority(token, authority)
        return authority

    def _history_authority_for(
        self,
        token: _DragTransactionToken,
    ) -> _DragHistoryAuthority:
        return self._transaction_authority_for(token).history

    def _ensure_drag_owner(
        self,
        token: _DragTransactionToken,
        *,
        checkpoint: HistoryCheckpoint | None,
        phase: str,
        authority: _DragHistoryAuthority | None = None,
        transaction_authority: _DragTransactionAuthority | None = None,
    ) -> None:
        if self._drag_transaction is not token:
            raise RuntimeError(f"selection drag owner changed while {phase}")
        bound_transaction_authority = (
            self._transaction_authority_for(token)
            if transaction_authority is None
            else transaction_authority
        )
        bound_authority = bound_transaction_authority.history
        if authority is not None and authority is not bound_authority:
            raise RuntimeError(
                f"selection drag history authority changed while {phase}"
            )
        if self._drag_transaction_authority is not bound_transaction_authority:
            raise RuntimeError(
                f"selection drag local transaction authority changed while {phase}"
            )
        if self._drag_history_authority is not bound_authority:
            raise RuntimeError(
                f"selection drag local history authority changed while {phase}"
            )
        self._verify_drag_token_transaction_authority(
            token,
            bound_transaction_authority,
        )
        try:
            current_history_service = self.context.history_service
        except BaseException as error:
            raise RuntimeError(
                f"selection drag could not verify its history owner while {phase}"
            ) from error
        if current_history_service is not bound_authority.history_service:
            raise RuntimeError(f"selection drag history owner changed while {phase}")
        if self._drag_transaction is not token:
            raise RuntimeError(f"selection drag owner changed while {phase}")
        if self._drag_transaction_authority is not bound_transaction_authority:
            raise RuntimeError(
                f"selection drag local transaction authority changed while {phase}"
            )
        if self._drag_history_authority is not bound_authority:
            raise RuntimeError(
                f"selection drag local history authority changed while {phase}"
            )
        self._verify_drag_token_transaction_authority(
            token,
            bound_transaction_authority,
        )
        self._verify_bound_history_authority(
            bound_authority,
            checkpoint=checkpoint,
        )
        if self._drag_transaction is not token:
            raise RuntimeError(f"selection drag owner changed while {phase}")
        if self._drag_transaction_authority is not bound_transaction_authority:
            raise RuntimeError(
                f"selection drag local transaction authority changed while {phase}"
            )
        if self._drag_history_authority is not bound_authority:
            raise RuntimeError(
                f"selection drag local history authority changed while {phase}"
            )
        self._verify_drag_token_transaction_authority(
            token,
            bound_transaction_authority,
        )

    @staticmethod
    def _restore_bound_history_checkpoint(
        authority: _DragHistoryAuthority,
        checkpoint: HistoryCheckpoint,
    ) -> tuple[bool, tuple[BaseException, ...]]:
        snapshot = authority.history_stacks
        errors: list[BaseException] = []
        expected_policies = {
            "enabled": checkpoint.enabled,
            "limit": checkpoint.limit,
        }

        def apply_stack(port: object, items: tuple[object, ...]) -> None:
            bound_port = cast(Any, port)
            bound_port.setter(bound_port.value)
            bound_port.replace_items(slice(None), items)

        for attempt in range(2):
            try:
                if attempt == 0:
                    snapshot.state_port.apply_once()
                    apply_stack(snapshot.history_port, checkpoint.history_items)
                    apply_stack(snapshot.redo_port, checkpoint.redo_items)
                    policy_ports = authority.history_policy_ports
                else:
                    policy_ports = tuple(
                        reversed(authority.history_policy_ports)
                    )
                for port in policy_ports:
                    port.apply_expected_once(expected_policies[port.name])
                if attempt != 0:
                    apply_stack(snapshot.redo_port, checkpoint.redo_items)
                    apply_stack(snapshot.history_port, checkpoint.history_items)
                    snapshot.state_port.apply_once()
                snapshot.verify_exact_items(
                    history_items=checkpoint.history_items,
                    redo_items=checkpoint.redo_items,
                )
                for port in authority.history_policy_ports:
                    port.verify(expected_policies[port.name])
                snapshot.verify_exact_items(
                    history_items=checkpoint.history_items,
                    redo_items=checkpoint.redo_items,
                )
            except BaseException as error:
                errors.append(error)
                continue
            return True, tuple(errors)
        return False, tuple(errors)

    @staticmethod
    def _restore_bound_history_authority(
        authority: _DragHistoryAuthority,
    ) -> tuple[bool, tuple[BaseException, ...]]:
        return SelectionDragMixin._restore_bound_history_checkpoint(
            authority,
            authority.begin_history_checkpoint,
        )

    def _compare_and_clear_drag_token(
        self,
        token: _DragTransactionToken,
        *,
        authority: _DragTransactionAuthority | None = None,
    ) -> bool:
        if self._drag_transaction is not token:
            return False
        if (
            authority is not None
            and self._drag_transaction_authority is not authority
        ):
            return False
        self._drag_transaction = None
        self._drag_history_authority = None
        self._drag_transaction_authority = None
        self._drag_history_publication = None
        return True

    def _begin_drag_transaction(
        self,
        *,
        atom_ids: set[int] | None = None,
        selection_items: list[object] | None = None,
        bond_ids: set[int] | None = None,
        boundary_bond_ids: set[int] | None = None,
    ) -> _DragTransactionToken:
        if self._drag_transaction is not None:
            raise RuntimeError("A selection drag transaction is already active")
        history_service = self.context.history_service
        token = _DragTransactionToken(history_service=history_service)
        history_authority: _DragHistoryAuthority | None = None
        transaction_authority: _DragTransactionAuthority | None = None
        # Publish a reservation before invoking any live descriptor/capture
        # port. A re-entrant press must observe this owner instead of starting a
        # second transaction that the outer capture could later overwrite.
        self._drag_transaction = token
        self._drag_transaction_authority = None
        try:
            if _has_exact_type(
                self.canvas,
                "ui.canvas_view",
                "CanvasView",
            ) and not _has_exact_callback_free_production_history_state(
                history_service
            ):
                raise RuntimeError(
                    "Selection drag requires an exact callback-free "
                    "production history state"
                )
            history_push = getattr(history_service, "push", None)
            if not callable(history_push):
                raise AttributeError(
                    "Selection drag requires a callable bound history push port"
                )
            token.history_push = history_push
            token.history_stacks = HistoryStackSnapshot.capture(history_service)
            if token.history_stacks is None:
                raise RuntimeError(
                    "Selection drag requires exact mutable history stacks"
                )
            token.history_policy_ports = self._capture_drag_history_policy(
                token.history_stacks
            )
            policy_values = {
                port.name: port.value for port in token.history_policy_ports
            }
            token.begin_history_checkpoint = HistoryCheckpoint(
                history_items=token.history_stacks.history_items,
                redo_items=token.history_stacks.redo_items,
                enabled=policy_values["enabled"],
                limit=policy_values["limit"],
            )
            history_authority = _DragHistoryAuthority(
                history_service=history_service,
                history_push=history_push,
                history_stacks=token.history_stacks,
                begin_history_checkpoint=token.begin_history_checkpoint,
                history_policy_ports=token.history_policy_ports,
            )
            token.history_authority = history_authority
            self._drag_history_authority = history_authority
            self._drag_history_publication = None
            self._verify_drag_token_history_authority(token, history_authority)
            self._verify_bound_history_authority(
                history_authority,
                checkpoint=history_authority.begin_history_checkpoint,
            )
            trusted_snapshot = (
                _TrustedSelectionDragSnapshot.capture(
                    self.canvas,
                    self.context,
                    history_service,
                    atom_ids=atom_ids,
                    selection_items=selection_items,
                    bond_ids=bond_ids or set(),
                    boundary_bond_ids=boundary_bond_ids or set(),
                )
                if atom_ids is not None and selection_items is not None
                else None
            )
            token.canvas_snapshot = trusted_snapshot
            if token.canvas_snapshot is None:
                token.canvas_snapshot = capture_history_transaction_for_history(
                    self.canvas,
                    history_service=history_service,
                )
            if token.canvas_snapshot is None:
                raise RuntimeError("Selection drag savepoint capture is incomplete")
            transaction_authority = _DragTransactionAuthority(
                token=token,
                history=history_authority,
                canvas_snapshot=token.canvas_snapshot,
            )
            self._drag_transaction_authority = transaction_authority
            self._ensure_drag_owner(
                token,
                checkpoint=history_authority.begin_history_checkpoint,
                phase="capturing its begin savepoint",
                authority=history_authority,
                transaction_authority=transaction_authority,
            )
        except BaseException as original_error:
            if transaction_authority is not None:
                self._restore_drag_transaction(
                    token,
                    original_error,
                    transaction_authority=transaction_authority,
                )
            else:
                if history_authority is not None:
                    restored, restore_errors = (
                        self._restore_bound_history_authority(
                            history_authority
                        )
                    )
                    for restore_error in restore_errors:
                        _add_drag_rollback_note(
                            original_error,
                            restore_error,
                            phase="restoring failed begin history authority",
                        )
                    if not restored:
                        _add_drag_rollback_note(
                            original_error,
                            RuntimeError(
                                "selection drag begin history rollback was not authoritative"
                            ),
                            phase="restoring failed begin history authority",
                        )
                self._compare_and_clear_drag_token(token)
            raise
        return token

    def _prepare_drag_mutation(
        self,
        token: _DragTransactionToken,
        *,
        require_full: bool = False,
        transaction_authority: _DragTransactionAuthority | None = None,
    ) -> None:
        bound_authority = (
            self._transaction_authority_for(token)
            if transaction_authority is None
            else transaction_authority
        )
        self._verify_drag_token_transaction_authority(token, bound_authority)
        snapshot = bound_authority.canvas_snapshot
        if not isinstance(snapshot, _TrustedSelectionDragSnapshot):
            return
        if not snapshot.targets_match(self):
            raise RuntimeError("Selection drag targets changed after capture")
        if snapshot.fallback_snapshot is not None:
            return
        if require_full or not snapshot.ports_are_trusted(self):
            # Capture before invoking the first custom/replaced port. The full
            # checkpoint owns unrelated state at this boundary; the selection-
            # sized baseline is replayed afterwards to return affected geometry
            # all the way to drag start.
            snapshot.promote_to_full()

    def _release_drag_transaction(
        self,
        token: _DragTransactionToken,
        *,
        checkpoint: HistoryCheckpoint | None,
        authority: _DragTransactionAuthority,
    ) -> None:
        snapshot = authority.canvas_snapshot
        if (
            isinstance(snapshot, _TrustedSelectionDragSnapshot)
            and snapshot.fallback_snapshot is None
        ):
            # A true-zero click has invoked no runtime publication. Verify the
            # capture-sized authority after the final history/context reads,
            # then release its known no-op local guard without crossing a live
            # full-snapshot port.
            self._ensure_drag_owner(
                token,
                checkpoint=checkpoint,
                phase="verifying its selection-sized savepoint",
                authority=authority.history,
                transaction_authority=authority,
            )
            if not snapshot.targets_match(self) or not snapshot.ports_are_trusted(
                self
            ):
                raise RuntimeError(
                    "Selection drag selection-sized authority changed before release"
                )
            snapshot.release()
            if not self._compare_and_clear_drag_token(
                token,
                authority=authority,
            ):
                raise RuntimeError(
                    "Selection drag owner changed before release completion"
                )
            return
        release_history_transaction_for_history(self.canvas, snapshot)
        self._ensure_drag_owner(
            token,
            checkpoint=checkpoint,
            phase="releasing its savepoint",
            authority=authority.history,
            transaction_authority=authority,
        )
        if not self._compare_and_clear_drag_token(
            token,
            authority=authority,
        ):
            raise RuntimeError("Selection drag owner changed before release completion")

    def _capture_replacement_drag_checkpoint(
        self,
        token: _DragTransactionToken,
    ) -> _ReplacementDragCheckpoint:
        transaction_authority = self._transaction_authority_for(token)
        history_authority = transaction_authority.history
        history_checkpoint = self._history_checkpoint_for(history_authority)
        self._ensure_drag_owner(
            token,
            checkpoint=history_checkpoint,
            phase="capturing its replacement checkpoint",
            authority=history_authority,
            transaction_authority=transaction_authority,
        )
        # Owner B already has the interaction's scene-rect guard. The rolling
        # checkpoint is an absolute state image, not another nested mutation
        # scope, so it must not open a second growth guard.
        canvas_snapshot = capture_history_transaction_for_history(
            self.canvas,
            history_service=history_authority.history_service,
            guard_scene_rect=False,
        )
        try:
            self._ensure_drag_owner(
                token,
                checkpoint=history_checkpoint,
                phase="finishing its replacement checkpoint",
                authority=history_authority,
                transaction_authority=transaction_authority,
            )
            return _ReplacementDragCheckpoint(
                token=token,
                transaction_authority=transaction_authority,
                canvas_snapshot=canvas_snapshot,
                history_checkpoint=history_checkpoint,
                drag_selection=self._drag_selection,
                selection_atom_ids=frozenset(self._selection_atom_ids),
                selection_items=tuple(self._selection_items),
                drag_bond_ids=frozenset(self._drag_bond_ids),
                drag_boundary_bond_ids=frozenset(
                    self._drag_boundary_bond_ids
                ),
                suspended_outline=self._suspended_outline,
                selection_outline_was_suspended=(
                    self._selection_outline_was_suspended
                ),
                start_pos=(
                    QPointF(self._start_pos)
                    if self._start_pos is not None
                    else None
                ),
                moved=self._moved,
                total_delta=QPointF(self._total_delta),
                last_drag_time=getattr(
                    self,
                    "_last_drag_time",
                    _MISSING_DRAG_LOCAL,
                ),
            )
        except BaseException:
            release_history_transaction_for_history(
                self.canvas,
                canvas_snapshot,
            )
            raise

    def _reapply_replacement_drag_checkpoint(
        self,
        checkpoint: _ReplacementDragCheckpoint,
    ) -> tuple[bool, tuple[BaseException, ...]]:
        errors: list[BaseException] = []
        token = checkpoint.token
        transaction_authority = checkpoint.transaction_authority
        history_authority = transaction_authority.history
        authoritative = False
        try:
            for _attempt in range(2):
                if self._drag_transaction is not token:
                    errors.append(
                        RuntimeError(
                            "replacement drag owner changed before reapply"
                        )
                    )
                    break
                try:
                    current_history_service = self.context.history_service
                except BaseException as error:
                    errors.append(error)
                    break
                if current_history_service is not history_authority.history_service:
                    errors.append(
                        RuntimeError(
                            "replacement drag history owner changed before reapply"
                        )
                    )
                    break

                try:
                    result = restore_history_transaction_for_history(
                        self.canvas,
                        checkpoint.canvas_snapshot,
                    )
                except BaseException as error:
                    errors.append(error)
                    canvas_authoritative = False
                else:
                    errors.extend(result.errors)
                    canvas_authoritative = result.authoritative
                checkpoint.restore_local(self)
                try:
                    self._ensure_drag_owner(
                        token,
                        checkpoint=checkpoint.history_checkpoint,
                        phase="reapplying its replacement checkpoint",
                        authority=history_authority,
                        transaction_authority=transaction_authority,
                    )
                    checkpoint.verify_local(self)
                except BaseException as error:
                    errors.append(error)
                    continue
                if canvas_authoritative:
                    authoritative = True
                    break
        finally:
            try:
                release_history_transaction_for_history(
                    self.canvas,
                    checkpoint.canvas_snapshot,
                )
            except BaseException as error:
                errors.append(error)
                authoritative = False
        return authoritative, tuple(errors)

    def _restore_drag_transaction(
        self,
        token: _DragTransactionToken,
        original_error: BaseException | None = None,
        *,
        transaction_authority: _DragTransactionAuthority | None = None,
    ) -> tuple[bool, bool]:
        bound_transaction_authority = (
            transaction_authority
            if transaction_authority is not None
            else getattr(self, "_drag_transaction_authority", None)
        )
        if not isinstance(bound_transaction_authority, _DragTransactionAuthority):
            authority_error = RuntimeError(
                "Selection drag cannot restore a missing local transaction authority"
            )
            if original_error is not None:
                _add_drag_rollback_note(
                    original_error,
                    authority_error,
                    phase="restoring the drag-start history authority",
                )
                return False, False
            raise authority_error
        bound_history_authority = bound_transaction_authority.history
        snapshot = bound_transaction_authority.canvas_snapshot

        rollback_errors: list[BaseException] = []
        replacement = self._drag_transaction
        replacement_authority = getattr(
            self,
            "_drag_transaction_authority",
            None,
        )
        replacement_token = (
            replacement
            if replacement is not token
            and isinstance(replacement, _DragTransactionToken)
            and isinstance(replacement_authority, _DragTransactionAuthority)
            and replacement_authority.token is replacement
            else None
        )
        replacement_checkpoint: _ReplacementDragCheckpoint | None = None
        if replacement_token is not None:
            try:
                replacement_checkpoint = (
                    self._capture_replacement_drag_checkpoint(
                        replacement_token,
                    )
                )
            except BaseException as error:
                rollback_errors.append(error)
        authoritative = False
        # Exact restore is deliberately idempotent. A fail-once Qt setter or
        # observer must not strand an otherwise recoverable interactive drag.
        for _attempt in range(2):
            try:
                result = restore_history_transaction_for_history(
                    self.canvas,
                    snapshot,
                )
            except BaseException as caught_error:
                rollback_errors.append(caught_error)
                canvas_authoritative = False
            else:
                rollback_errors.extend(result.errors)
                canvas_authoritative = result.authoritative
            history_authoritative, history_errors = (
                self._restore_bound_history_authority(
                    bound_history_authority
                )
            )
            rollback_errors.extend(history_errors)
            if canvas_authoritative and history_authoritative:
                authoritative = True
                break

        if replacement_checkpoint is not None:
            replacement_authoritative, replacement_errors = (
                self._reapply_replacement_drag_checkpoint(
                    replacement_checkpoint,
                )
            )
            rollback_errors.extend(replacement_errors)
            # B's current absolute checkpoint supersedes A's older baseline as
            # the final global authority. A's errors remain diagnostic, but a
            # verified B reapply is the state that must survive this unwind.
            authoritative = replacement_authoritative
        elif replacement_token is not None:
            authoritative = False

        if not authoritative and not rollback_errors:
            rollback_errors.append(
                RuntimeError("Selection drag exact rollback was not authoritative")
            )
        # A callback may corrupt only the controller's authority field while
        # the published owner is still this token. The frozen authority above
        # remains the rollback source; token identity is the CAS boundary that
        # distinguishes that corruption from a legitimate replacement owner.
        consumed = (
            self._compare_and_clear_drag_token(token) if authoritative else False
        )

        if original_error is not None:
            for recovery_error in rollback_errors:
                _add_drag_rollback_note(
                    original_error,
                    recovery_error,
                    phase="restoring the drag-start savepoint",
                )
            return authoritative, consumed
        # Cancellation has no owning failure to preserve. Once an idempotent
        # retry reaches an authoritative savepoint, fail-once recovery details
        # must not abort the tool switch/new press that requested cancellation.
        if authoritative:
            return True, consumed
        if rollback_errors:
            primary_error = rollback_errors[0]
            for recovery_error in rollback_errors[1:]:
                _add_drag_rollback_note(
                    primary_error,
                    recovery_error,
                    phase="retrying drag cancellation",
                )
            raise primary_error
        return False, False

    def _cancel_drag_transaction(
        self,
        token: _DragTransactionToken,
        original_error: BaseException | None = None,
        *,
        transaction_authority: _DragTransactionAuthority | None = None,
    ) -> tuple[bool, bool]:
        return self._restore_drag_transaction(
            token,
            original_error,
            transaction_authority=transaction_authority,
        )

    def _require_drag_token(self) -> _DragTransactionToken:
        token = self._drag_transaction
        if not isinstance(token, _DragTransactionToken):
            raise RuntimeError("Selection drag has no complete transaction owner")
        transaction_authority = getattr(
            self,
            "_drag_transaction_authority",
            None,
        )
        if (
            not isinstance(transaction_authority, _DragTransactionAuthority)
            or transaction_authority.token is not token
        ):
            raise RuntimeError("Selection drag begin capture is still in progress")
        return token

    @staticmethod
    def _expected_history_checkpoint_after_push(
        authority: _DragHistoryAuthority,
        command: HistoryCommand,
    ) -> HistoryCheckpoint:
        checkpoint = authority.begin_history_checkpoint
        if checkpoint.enabled is not True:
            raise RuntimeError("selection drag history was disabled at begin")
        history_items = [*checkpoint.history_items, command]
        history_limit = cast(int, checkpoint.limit)
        if len(history_items) > history_limit:
            history_items.pop(0)
        return HistoryCheckpoint(
            history_items=tuple(history_items),
            redo_items=(),
            enabled=checkpoint.enabled,
            limit=checkpoint.limit,
        )

    def _capture_drag_canvas_publication_checkpoint(
        self,
        authority: _DragTransactionAuthority,
    ) -> object | None:
        snapshot = authority.canvas_snapshot
        if not isinstance(snapshot, _TrustedSelectionDragSnapshot):
            return None
        if snapshot.fallback_snapshot is None:
            raise RuntimeError(
                "Selection drag cannot publish history without a full rollback guard"
            )
        return capture_history_transaction_for_history(
            self.canvas,
            history_service=authority.history.history_service,
            guard_scene_rect=False,
        )

    @staticmethod
    def _verify_drag_canvas_publication_checkpoint(snapshot: object) -> None:
        verify = getattr(snapshot, "verify_exact", None)
        if not callable(verify):
            raise RuntimeError(
                "Selection drag canvas publication checkpoint is not verifiable"
            )
        errors = tuple(verify())
        if errors:
            raise BaseExceptionGroup(
                "Selection drag canvas authority changed during history publication",
                list(errors),
            )

    def _push_drag_history(
        self,
        token: _DragTransactionToken,
        command: HistoryCommand,
    ) -> None:
        transaction_authority = self._transaction_authority_for(token)
        authority = transaction_authority.history
        self._ensure_drag_owner(
            token,
            checkpoint=authority.begin_history_checkpoint,
            phase="preparing its history command",
            authority=authority,
            transaction_authority=transaction_authority,
        )
        if self._drag_history_publication is not None:
            raise RuntimeError("Selection drag attempted a second history publication")
        canvas_checkpoint = self._capture_drag_canvas_publication_checkpoint(
            transaction_authority
        )
        command_snapshot = HistoryCommandSnapshot.capture(command)
        try:
            push_result = authority.history_push(command)
            if push_result is False:
                raise RuntimeError(
                    "Selection drag history push did not commit its command"
                )
            command_snapshot.verify()
            expected_checkpoint = self._expected_history_checkpoint_after_push(
                authority,
                command,
            )
            self._ensure_drag_owner(
                token,
                checkpoint=expected_checkpoint,
                phase="publishing its history command",
                authority=authority,
                transaction_authority=transaction_authority,
            )
            if canvas_checkpoint is not None:
                restored, restore_errors = (
                    self._restore_bound_history_checkpoint(
                        authority,
                        authority.begin_history_checkpoint,
                    )
                )
                if not restored:
                    errors = list(restore_errors) or [
                        RuntimeError(
                            "selection drag could not stage canvas verification"
                        )
                    ]
                    raise BaseExceptionGroup(
                        "Selection drag could not verify its published canvas",
                        errors,
                    )
                self._verify_drag_canvas_publication_checkpoint(canvas_checkpoint)
                restored, restore_errors = (
                    self._restore_bound_history_checkpoint(
                        authority,
                        expected_checkpoint,
                    )
                )
                if not restored:
                    errors = list(restore_errors) or [
                        RuntimeError(
                            "selection drag could not restore its published history"
                        )
                    ]
                    raise BaseExceptionGroup(
                        "Selection drag could not finalize its history publication",
                        errors,
                    )
                self._ensure_drag_owner(
                    token,
                    checkpoint=expected_checkpoint,
                    phase="verifying its published canvas and history",
                    authority=authority,
                    transaction_authority=transaction_authority,
                )
            command_snapshot.verify()
        except BaseException:
            command_snapshot.restore()
            raise
        finally:
            if canvas_checkpoint is not None:
                try:
                    release_history_transaction_for_history(
                        self.canvas,
                        canvas_checkpoint,
                    )
                except BaseException:
                    command_snapshot.restore()
                    raise
        try:
            command_snapshot.verify()
        except BaseException:
            command_snapshot.restore()
            raise
        if self._drag_history_publication is not None:
            raise RuntimeError(
                "Selection drag history publication marker was replaced"
            )
        self._drag_history_publication = _DragHistoryPublication(
            token=token,
            authority=transaction_authority,
            checkpoint=expected_checkpoint,
        )

    def _commit_drag_transaction(
        self,
        operation: Callable[[_DragTransactionToken], None],
        *,
        require_full: bool = True,
    ) -> _DragTransactionToken:
        token = self._require_drag_token()
        transaction_authority = getattr(
            self,
            "_drag_transaction_authority",
            None,
        )
        try:
            if not isinstance(transaction_authority, _DragTransactionAuthority):
                raise RuntimeError(
                    "Selection drag lost its local transaction authority"
                )
            history_authority = transaction_authority.history
            self._ensure_drag_owner(
                token,
                checkpoint=history_authority.begin_history_checkpoint,
                phase="starting commit",
                authority=history_authority,
                transaction_authority=transaction_authority,
            )
            self._drag_history_publication = None
            # Commit operations may publish history/selection callbacks. They
            # are the first deliberately extensible boundary in a trusted drag,
            # so upgrade immediately before them rather than penalizing press or
            # pointer frames with a document-wide scan.
            self._prepare_drag_mutation(
                token,
                require_full=require_full,
                transaction_authority=transaction_authority,
            )
            operation(token)
            publication = self._drag_history_publication
            post_commit_checkpoint = history_authority.begin_history_checkpoint
            if publication is not None:
                if publication.token is not token:
                    raise RuntimeError(
                        "Selection drag history publication owner changed"
                    )
                if publication.authority is not transaction_authority:
                    raise RuntimeError(
                        "Selection drag history publication authority changed"
                    )
                post_commit_checkpoint = publication.checkpoint
            self._ensure_drag_owner(
                token,
                checkpoint=post_commit_checkpoint,
                phase="finishing commit",
                authority=history_authority,
                transaction_authority=transaction_authority,
            )
            self._release_drag_transaction(
                token,
                checkpoint=post_commit_checkpoint,
                authority=transaction_authority,
            )
        except BaseException as original_error:
            self._restore_drag_transaction(
                token,
                original_error,
                transaction_authority=(
                    transaction_authority
                    if isinstance(
                        transaction_authority,
                        _DragTransactionAuthority,
                    )
                    else None
                ),
            )
            raise
        return token

    def _cancel_selection_drag(
        self,
        original_error: BaseException | None = None,
        *,
        token: _DragTransactionToken | None = None,
        transaction_authority: _DragTransactionAuthority | None = None,
    ) -> None:
        current = self._drag_transaction
        if token is None:
            if current is None:
                self._reset_selection_drag_state()
                return
            token = self._require_drag_token()
        try:
            self._cancel_drag_transaction(
                token,
                original_error,
                transaction_authority=transaction_authority,
            )
        finally:
            # Compare-and-swap consumption is the only authority to clear local
            # coordinates. If a callback installed owner B, these fields now
            # belong to B and the outer owner A must leave them untouched.
            if self._drag_transaction is None:
                self._reset_selection_drag_state()

    def _begin_selection_drag(self, atom_ids: set[int], selection_items: list, start_pos) -> bool:
        if not atom_ids and not selection_items:
            return False
        if self._drag_transaction is not None or self._drag_selection:
            self._cancel_selection_drag()

        selection_atom_ids = set(atom_ids)
        independent_items = independent_selection_items(
            selection_items,
            selection_atom_ids,
        )
        if selection_atom_ids:
            drag_bond_ids, drag_boundary_bond_ids = self.context.bond_sets_for_atoms(
                selection_atom_ids
            )
        else:
            drag_bond_ids = set()
            drag_boundary_bond_ids = set()
        outline_was_suspended = suspend_selection_outline_for(self.canvas)

        # Open the exact savepoint only after all target-discovery reads have
        # succeeded, and before the first user-visible drag mutation.
        self._begin_drag_transaction(
            atom_ids=selection_atom_ids,
            selection_items=independent_items,
            bond_ids=drag_bond_ids,
            boundary_bond_ids=drag_boundary_bond_ids,
        )
        self._drag_selection = True
        self._selection_atom_ids = selection_atom_ids
        self._selection_items = independent_items
        self._drag_bond_ids = drag_bond_ids
        self._drag_boundary_bond_ids = drag_boundary_bond_ids
        self._selection_outline_was_suspended = outline_was_suspended
        self._start_pos = start_pos
        self._last_drag_time = 0.0
        self._total_delta = QPointF(0.0, 0.0)
        return True

    @staticmethod
    def _drag_delta_is_effective(delta: QPointF) -> bool:
        return (
            abs(delta.x()) > _DRAG_DELTA_EPSILON
            or abs(delta.y()) > _DRAG_DELTA_EPSILON
        )

    def _drag_has_net_movement(self) -> bool:
        # The epsilon is only an input-frame filter, before any geometry is
        # changed. Once a frame was applied, every exact accumulated residual
        # must be represented by history; otherwise a sub-epsilon remainder
        # would survive without an undo command while redo stayed intact.
        return self._total_delta.x() != 0.0 or self._total_delta.y() != 0.0

    def _apply_drag_delta(self, delta: QPointF) -> None:
        if not self._drag_selection:
            return
        # Qt can deliver a move event at the exact press coordinate. Treat it
        # as a true no-op: invoking move/outline callbacks would mark the drag
        # as moved, suppress a handle-toggle click, and later clear redo with a
        # zero-distance history command.
        if not self._drag_delta_is_effective(delta):
            return
        token = self._require_drag_token()
        transaction_authority = self._transaction_authority_for(token)
        try:
            # The trusted production path is closed over exact Python/Qt ports,
            # so one validation owns this synchronous pointer frame. Repeating
            # the all-affected-item validation before every selected item would
            # turn an N-item drag into O(N²) work without adding a callback
            # boundary. Any open/custom port promotes here before the first
            # visible mutation instead.
            self._prepare_drag_mutation(
                token,
                transaction_authority=transaction_authority,
            )
            if not self._suspended_outline:
                self.context.suspend_selection_outline(True)
                self._ensure_drag_owner(
                    token,
                    checkpoint=token.begin_history_checkpoint,
                    phase="suspending its selection outline",
                )
            self._suspended_outline = True
            if self._selection_atom_ids:
                snapshot = transaction_authority.canvas_snapshot
                affected_ring_items = (
                    snapshot.affected_ring_items
                    if isinstance(snapshot, _TrustedSelectionDragSnapshot)
                    and snapshot.fallback_snapshot is None
                    else None
                )
                if affected_ring_items is None:
                    move_atoms_for(
                        self.canvas,
                        self._selection_atom_ids,
                        delta.x(),
                        delta.y(),
                        bond_ids=self._drag_bond_ids,
                        redraw_bond_ids=self._drag_boundary_bond_ids,
                        update_selection=False,
                    )
                else:
                    move_atoms_for(
                        self.canvas,
                        self._selection_atom_ids,
                        delta.x(),
                        delta.y(),
                        bond_ids=self._drag_bond_ids,
                        redraw_bond_ids=self._drag_boundary_bond_ids,
                        update_selection=False,
                        affected_ring_items=affected_ring_items,
                    )
                self._ensure_drag_owner(
                    token,
                    checkpoint=token.begin_history_checkpoint,
                    phase="moving its selected atoms",
                )
            for item in self._selection_items:
                move_item_for(
                    self.canvas,
                    item,
                    delta.x(),
                    delta.y(),
                    update_selection=False,
                )
                self._ensure_drag_owner(
                    token,
                    checkpoint=token.begin_history_checkpoint,
                    phase="moving one of its selected scene items",
                )
            shift_selection_outlines_for(self.canvas, delta.x(), delta.y())
            self._ensure_drag_owner(
                token,
                checkpoint=token.begin_history_checkpoint,
                phase="shifting its selection outlines",
            )
            self._total_delta += delta
            self._moved = True
        except BaseException as original_error:
            self._cancel_selection_drag(
                original_error,
                token=token,
                transaction_authority=transaction_authority,
            )
            raise

    def _build_move_command(self) -> HistoryCommand | None:
        if not self._drag_has_net_movement():
            return None
        commands: list[HistoryCommand] = []
        if self._selection_atom_ids:
            commands.append(
                MoveAtomsCommand(
                    atom_ids=set(self._selection_atom_ids),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                    bond_ids=set(self._drag_bond_ids) if self._drag_bond_ids else None,
                    redraw_bond_ids=set(self._drag_boundary_bond_ids) if self._drag_boundary_bond_ids else None,
                )
            )
        if self._selection_items:
            commands.append(
                MoveItemsCommand(
                    items=list(self._selection_items),
                    dx=self._total_delta.x(),
                    dy=self._total_delta.y(),
                )
            )
        if not commands:
            return None
        if len(commands) == 1:
            return commands[0]
        return CompositeCommand(commands)

    def _commit_selection_drag(self) -> None:
        self._require_drag_token()
        true_zero_click = (
            not self._moved
            and not self._drag_has_net_movement()
            and not self._suspended_outline
        )

        def commit(owner: _DragTransactionToken) -> None:
            if true_zero_click:
                if (
                    self._moved
                    or self._drag_has_net_movement()
                    or self._suspended_outline
                ):
                    raise RuntimeError(
                        "Selection drag true-zero state changed during commit"
                    )
                return
            if self._suspended_outline:
                self.context.suspend_selection_outline(
                    self._selection_outline_was_suspended
                )
                self._ensure_drag_owner(
                    owner,
                    checkpoint=owner.begin_history_checkpoint,
                    phase="restoring its selection-outline suspension",
                )
                self._suspended_outline = False
            if self._moved and self._drag_has_net_movement():
                refresh_selection_outline_for(self.canvas)
                self._ensure_drag_owner(
                    owner,
                    checkpoint=owner.begin_history_checkpoint,
                    phase="refreshing its committed selection outline",
                )
                command = self._build_move_command()
                if command is not None:
                    self._push_drag_history(owner, command)

        try:
            self._commit_drag_transaction(
                commit,
                require_full=not true_zero_click,
            )
        except BaseException:
            if self._drag_transaction is None:
                self._reset_selection_drag_state()
            raise
        self._reset_selection_drag_state()


__all__ = ["SelectionDragMixin", "atom_ids_with_bonds", "independent_selection_items"]
