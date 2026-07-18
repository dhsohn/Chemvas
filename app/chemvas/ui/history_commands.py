from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from chemvas.core.history import (
    HistoryCommand,
    capture_history_transaction_for_command,
    release_history_transaction_for_command,
    restore_history_transaction_for_command,
)
from chemvas.domain.transactions import (
    add_recovery_error_note as _add_rollback_error_note,
)
from chemvas.ui.atom_coords_access import atom_coords_3d_for_id
from chemvas.ui.atom_label_access import add_or_update_atom_label
from chemvas.ui.canvas_group_state import (
    CanvasSceneGroup,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from chemvas.ui.canvas_model_access import atom_for_id, bond_for_id
from chemvas.ui.canvas_scene_items_state import SCENE_ITEM_COLLECTION_ATTRS
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.canvas_state_lookup import canvas_state_object
from chemvas.ui.history_atom_position_restore import (
    set_atom_positions_for_history as _set_atom_positions_for_history,
)
from chemvas.ui.move_access import (
    move_item_for,
    refresh_selection_outline_for_canvas,
)
from chemvas.ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from chemvas.ui.scene_item_access import (
    create_scene_item_from_state as _create_scene_item_from_state,
)
from chemvas.ui.scene_item_access import (
    item_is_in_canvas_scene as _item_is_in_canvas_scene,
)
from chemvas.ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from chemvas.ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot

_MISSING_SNAPSHOT_ATTRIBUTE = object()


def _snapshot_attribute(
    target: object,
    name: str,
    *,
    strict: bool,
) -> object:
    """Read an optional capture field once without hiding descriptor errors."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            strict
            and inspect.getattr_static(
                target,
                name,
                _MISSING_SNAPSHOT_ATTRIBUTE,
            )
            is not _MISSING_SNAPSHOT_ATTRIBUTE
        ):
            raise
        return _MISSING_SNAPSHOT_ATTRIBUTE


def _snapshot_canvas_state_object(
    canvas,
    name: str,
    *,
    strict: bool,
) -> object | None:
    if not strict:
        return canvas_state_object(canvas, name)
    public_name = name[1:] if name.startswith("_") else name
    runtime_state = _snapshot_attribute(canvas, "runtime_state", strict=True)
    if runtime_state is not _MISSING_SNAPSHOT_ATTRIBUTE and runtime_state is not None:
        state = _snapshot_attribute(runtime_state, public_name, strict=True)
        if state is not _MISSING_SNAPSHOT_ATTRIBUTE and state is not None:
            return state
    state = _snapshot_attribute(canvas, public_name, strict=True)
    if state is _MISSING_SNAPSHOT_ATTRIBUTE:
        return None
    return state


def _run_rollback_step(
    original_error: BaseException,
    phase: str,
    operation: Callable[[], Any],
    *,
    default: Any = None,
) -> Any:
    try:
        return operation()
    except BaseException as rollback_error:
        _add_rollback_error_note(
            original_error,
            rollback_error,
            phase=phase,
        )
        return default


def _run_absolute_restore_step(
    original_error: BaseException | None,
    phase: str,
    operation: Callable[[], Any],
    *,
    default: Any = None,
    errors: list[BaseException] | None = None,
) -> Any:
    """Run a normally-strict restore step, making it best-effort in rollback."""
    if errors is not None:
        try:
            return operation()
        except BaseException as error:
            errors.append(error)
            return default
    if original_error is None:
        return operation()
    return _run_rollback_step(
        original_error,
        phase,
        operation,
        default=default,
    )


def _run_suppressed_restore_step(
    original_error: BaseException | None,
    phase: str,
    operation: Callable[[], Any],
    *,
    default: Any = None,
    errors: list[BaseException] | None = None,
) -> Any:
    """Preserve suppress(Exception) semantics outside an active rollback."""
    if errors is not None:
        try:
            return operation()
        except BaseException as error:
            errors.append(error)
            return default
    if original_error is not None:
        return _run_rollback_step(
            original_error,
            phase,
            operation,
            default=default,
        )
    try:
        return operation()
    except Exception:
        return default


def _scene_item_membership(canvas, item) -> bool | None:
    """Return an item's scene membership without treating unknown as detached."""
    if item is None:
        return False
    try:
        scene = canvas.scene()
    except (AttributeError, RuntimeError):
        return None
    scene_method = getattr(item, "scene", None)
    if not callable(scene_method):
        return None
    try:
        return scene_method() is scene
    except RuntimeError:
        return None


def _scene_items_and_getter_from_scene(
    scene,
    *,
    strict: bool = False,
) -> tuple[list | None, Callable[[], Any] | None]:
    if scene is None:
        return None, None
    items_method = _snapshot_attribute(scene, "items", strict=strict)
    if not callable(items_method):
        complete_scene_api = all(
            callable(_snapshot_attribute(scene, method_name, strict=strict))
            for method_name in (
                "addItem",
                "removeItem",
                "blockSignals",
                "signalsBlocked",
                "selectedItems",
                "focusItem",
                "setFocusItem",
            )
        )
        if strict and (isinstance(scene, QObject) or complete_scene_api):
            raise RuntimeError("live scene does not expose an items snapshot")
        return None, None
    try:
        return list(items_method()), items_method
    except RuntimeError:
        if strict:
            raise
        return None, None


def _scene_items_from_scene(scene, *, strict: bool = False) -> list | None:
    items, _getter = _scene_items_and_getter_from_scene(
        scene,
        strict=strict,
    )
    return items


def _scene_items_snapshot(canvas, *, strict: bool = False) -> list | None:
    scene_method = getattr(canvas, "scene", None)
    if not callable(scene_method):
        return None
    try:
        scene = scene_method()
    except (AttributeError, RuntimeError):
        if strict:
            raise
        return None
    return _scene_items_from_scene(scene, strict=strict)


def _new_top_level_scene_items(canvas, before: list | None) -> list:
    """Find items attached by an operation that raised before returning one."""
    if before is None:
        return []
    after = _scene_items_snapshot(canvas)
    if after is None:
        return []
    before_ids = {id(item) for item in before}
    added = [item for item in after if id(item) not in before_ids]
    added_ids = {id(item) for item in added}
    top_level: list = []
    for item in added:
        parent_method = getattr(item, "parentItem", None)
        try:
            parent = parent_method() if callable(parent_method) else None
        except RuntimeError:
            parent = None
        if parent is not None and id(parent) in added_ids:
            continue
        top_level.append(item)
    return top_level


@dataclass(slots=True)
class _ListAttributeSnapshot:
    owner: object
    attribute: str
    list_object: list
    contents: list


@dataclass(slots=True)
class _MarkRegistrySnapshot:
    registry: Any
    mapping_object: dict
    entries: list[tuple[object, object, list | None]]


@dataclass(slots=True)
class _SelectionVisualSnapshot:
    item: object
    pen: object
    data_6: object


@dataclass(slots=True)
class _VisibilitySnapshot:
    item: object
    visible: bool
    rect: object
    pen: object
    brush: object


_BOND_PRIMITIVE_GRAPHICS_PROPERTIES = (
    ("transformOriginPoint", "setTransformOriginPoint"),
    ("transform", "setTransform"),
    ("rotation", "setRotation"),
    ("scale", "setScale"),
    ("pos", "setPos"),
    ("opacity", "setOpacity"),
    ("zValue", "setZValue"),
    ("line", "setLine"),
    ("path", "setPath"),
    ("polygon", "setPolygon"),
    ("rect", "setRect"),
    ("pen", "setPen"),
    ("brush", "setBrush"),
    ("font", "setFont"),
    ("defaultTextColor", "setDefaultTextColor"),
    ("toHtml", "setHtml"),
    ("textInteractionFlags", "setTextInteractionFlags"),
)

_ATOM_GRAPHICS_DIRECT_ATTRIBUTES = (
    "_hit_padding",
    "_hit_radius",
    "_layout",
    "_typographic",
    "_stack_element_rect",
)


def _graphics_item_is_deleted(item: object) -> bool:
    return isinstance(item, QGraphicsItem) and sip.isdeleted(item)


def _restore_primitive_graphics_property(
    item: object,
    setter_name: str,
    value: object,
) -> None:
    # Use Qt's base implementations for the atom primitives. A subclass hook
    # can be the persistently failing callback that triggered rollback; calling
    # it again would make the raw savepoint unable to repair the item.
    if isinstance(item, QGraphicsTextItem):
        if setter_name == "setFont":
            QGraphicsTextItem.setFont(item, cast(QFont, value))
            return
        if setter_name == "setDefaultTextColor":
            QGraphicsTextItem.setDefaultTextColor(item, cast(QColor, value))
            return
        if setter_name == "setHtml":
            QGraphicsTextItem.setHtml(item, cast(str, value))
            return
        if setter_name == "setTextInteractionFlags":
            QGraphicsTextItem.setTextInteractionFlags(
                item,
                cast(Qt.TextInteractionFlag, value),
            )
            return
    if isinstance(item, QGraphicsEllipseItem) and setter_name == "setRect":
        QGraphicsEllipseItem.setRect(item, cast(QRectF, value))
        return
    if isinstance(item, QGraphicsPolygonItem) and setter_name == "setPolygon":
        QGraphicsPolygonItem.setPolygon(item, cast(QPolygonF, value))
        return
    if isinstance(item, QAbstractGraphicsShapeItem):
        if setter_name == "setPen":
            QAbstractGraphicsShapeItem.setPen(item, cast(QPen, value))
            return
        if setter_name == "setBrush":
            QAbstractGraphicsShapeItem.setBrush(item, cast(QBrush, value))
            return
    if isinstance(item, QGraphicsItem) and setter_name in {
        "setTransformOriginPoint",
        "setTransform",
        "setRotation",
        "setScale",
        "setPos",
        "setOpacity",
        "setZValue",
    }:
        setter = getattr(QGraphicsItem, setter_name)
        setter(item, value)
        return
    setter = _snapshot_attribute(item, setter_name, strict=True)
    if not callable(setter):
        raise RuntimeError(f"primitive graphics restore cannot call {setter_name}")
    setter(value)


@dataclass(slots=True)
class _BondPrimitiveGraphicsSnapshot:
    item: object
    properties: tuple[tuple[str, object], ...]
    direct_attributes: tuple[tuple[str, object], ...]

    @classmethod
    def capture(
        cls,
        item: object,
        *,
        strict: bool = False,
    ) -> _BondPrimitiveGraphicsSnapshot | None:
        if _graphics_item_is_deleted(item):
            return None
        properties: list[tuple[str, object]] = []
        for getter_name, setter_name in _BOND_PRIMITIVE_GRAPHICS_PROPERTIES:
            getter = _snapshot_attribute(item, getter_name, strict=strict)
            setter = _snapshot_attribute(item, setter_name, strict=strict)
            if not callable(getter) or not callable(setter):
                continue
            try:
                value = getter()
            except RuntimeError:
                if strict:
                    raise
                continue
            properties.append((setter_name, value))
        direct_attribute_values: list[tuple[str, object]] = []
        for name in _ATOM_GRAPHICS_DIRECT_ATTRIBUTES:
            value = _snapshot_attribute(item, name, strict=strict)
            if value is _MISSING_SNAPSHOT_ATTRIBUTE:
                continue
            direct_attribute_values.append((name, value))
        direct_attributes = tuple(direct_attribute_values)
        if not properties and not direct_attributes:
            return None
        return cls(
            item=item,
            properties=tuple(properties),
            direct_attributes=direct_attributes,
        )

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for setter_name, value in self.properties:
            try:
                _restore_primitive_graphics_property(
                    self.item,
                    setter_name,
                    value,
                )
            except BaseException as exc:
                errors.append(exc)
        if self.direct_attributes:
            try:
                if isinstance(self.item, QGraphicsItem):
                    QGraphicsItem.prepareGeometryChange(self.item)
                for name, value in self.direct_attributes:
                    setattr(self.item, name, value)
            except BaseException as exc:
                errors.append(exc)
        return errors


def _bond_primitive_graphics_snapshots(
    canvas,
    *,
    strict: bool = False,
) -> tuple[_BondPrimitiveGraphicsSnapshot, ...]:
    state = _snapshot_canvas_state_object(
        canvas,
        "bond_graphics_state",
        strict=strict,
    )
    mapping = _snapshot_attribute(state, "bond_items", strict=strict)
    if not isinstance(mapping, dict):
        return ()
    snapshots: list[_BondPrimitiveGraphicsSnapshot] = []
    seen: set[int] = set()
    for items in mapping.values():
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            snapshot = _BondPrimitiveGraphicsSnapshot.capture(
                item,
                strict=strict,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _atom_primitive_graphics_snapshots(
    canvas,
    *,
    strict: bool = False,
) -> tuple[_BondPrimitiveGraphicsSnapshot, ...]:
    state = _snapshot_canvas_state_object(
        canvas,
        "atom_graphics_state",
        strict=strict,
    )
    mappings = (
        _snapshot_attribute(state, "atom_items", strict=strict),
        _snapshot_attribute(state, "atom_dots", strict=strict),
    )
    snapshots: list[_BondPrimitiveGraphicsSnapshot] = []
    seen: set[int] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for item in mapping.values():
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            snapshot = _BondPrimitiveGraphicsSnapshot.capture(
                item,
                strict=strict,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _restore_bond_primitive_graphics_snapshots(
    snapshots: tuple[_BondPrimitiveGraphicsSnapshot, ...],
) -> list[BaseException]:
    errors: list[BaseException] = []
    for snapshot in snapshots:
        errors.extend(snapshot.restore())
    return errors


@dataclass(slots=True)
class _SceneSelectionSnapshot:
    item: object
    selected: bool
    getter: Callable[[], object]
    setter: Callable[[bool], object]


@dataclass(slots=True)
class _SceneItemTopologySnapshot:
    """Capture-bound parent/z/stacking authorities for one scene item."""

    item: object
    parent: object | None
    parent_getter: Callable[[], object] | None
    parent_setter: Callable[[object | None], object] | None
    z_value: float | None
    z_getter: Callable[[], object] | None
    z_setter: Callable[[float], object] | None
    stack_before: Callable[[object], object] | None
    stacking_flags: QGraphicsItem.GraphicsItemFlag | None
    flags_getter: Callable[[], object] | None
    flags_setter: Callable[[object], object] | None


_SCENE_STACKING_FLAG_MASK = (
    QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent
    | QGraphicsItem.GraphicsItemFlag.ItemNegativeZStacksBehindParent
)


def _base_graphics_item_port(
    item: object,
    name: str,
) -> Callable[..., object] | None:
    if not isinstance(item, QGraphicsItem):
        return None
    method = getattr(QGraphicsItem, name, None)
    if not callable(method):
        return None
    return partial(method, item)


@dataclass(slots=True)
class _SceneRuntimeSnapshot:
    scene: object | None
    scene_items: list | None
    scene_items_getter: Callable[[], Any] | None
    scene_signals_blocked: bool | None
    scene_signals_blocked_getter: Callable[[], object] | None
    scene_block_signals_setter: Callable[[bool], object] | None
    focus_item: object | None
    focus_item_getter: Callable[[], object] | None
    focus_item_setter: Callable[[object | None], object] | None
    topology_states: list[_SceneItemTopologySnapshot]
    selected_states: list[_SceneSelectionSnapshot]
    visibility_states: list[_VisibilitySnapshot]
    selection_visuals: list[_SelectionVisualSnapshot]
    list_attributes: list[_ListAttributeSnapshot]
    mark_registry: _MarkRegistrySnapshot | None
    handle_state: Any | None
    handle_target: object | None
    selection_info_state: Any | None
    selection_info_values: dict[str, object]
    bond_primitive_graphics: tuple[_BondPrimitiveGraphicsSnapshot, ...]


def _scene_item_topology_snapshots(
    items: list,
    *,
    strict: bool = False,
) -> list[_SceneItemTopologySnapshot]:
    """Capture every item's topology ports before any transaction mutation.

    Some lightweight test/dummy scene items expose read-only parent/z ports.
    They remain verifiable, but an attempted change is authoritative only when
    the matching capture-bound setter exists. Real QGraphicsItems expose both
    halves of each contract.
    """

    snapshots: list[_SceneItemTopologySnapshot] = []
    for item in items:
        if _graphics_item_is_deleted(item):
            continue

        parent_getter: object = _base_graphics_item_port(item, "parentItem")
        parent_setter: object = _base_graphics_item_port(item, "setParentItem")
        if parent_getter is None:
            parent_getter = _snapshot_attribute(item, "parentItem", strict=strict)
        if parent_setter is None:
            parent_setter = _snapshot_attribute(item, "setParentItem", strict=strict)
        parent_ports_present = (
            parent_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
            or parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if strict and (
            parent_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
            and not callable(parent_getter)
        ):
            raise RuntimeError(
                "live scene item does not expose a callable parent getter"
            )
        if strict and (
            parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
            and not callable(parent_setter)
        ):
            raise RuntimeError(
                "live scene item does not expose a callable parent setter"
            )
        if callable(parent_getter):
            try:
                parent = parent_getter()
            except RuntimeError:
                if strict:
                    raise
                parent_getter = None
                parent_setter = None
                parent = None
        elif (
            strict
            and parent_ports_present
            and parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
        ):
            raise RuntimeError(
                "live scene item does not expose a readable parent contract"
            )
        else:
            parent_getter = None
            parent_setter = None
            parent = None

        z_getter: object = _base_graphics_item_port(item, "zValue")
        z_setter: object = _base_graphics_item_port(item, "setZValue")
        stack_before: object = _base_graphics_item_port(item, "stackBefore")
        if z_getter is None:
            z_getter = _snapshot_attribute(item, "zValue", strict=strict)
        if z_setter is None:
            z_setter = _snapshot_attribute(item, "setZValue", strict=strict)
        if stack_before is None:
            stack_before = _snapshot_attribute(item, "stackBefore", strict=strict)
        z_ports_present = (
            z_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
            or z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if strict and (
            z_getter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(z_getter)
        ):
            raise RuntimeError(
                "live scene item does not expose a callable stacking-depth getter"
            )
        if strict and (
            z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(z_setter)
        ):
            raise RuntimeError(
                "live scene item does not expose a callable stacking-depth setter"
            )
        if strict and (
            stack_before is not _MISSING_SNAPSHOT_ATTRIBUTE
            and not callable(stack_before)
        ):
            raise RuntimeError(
                "live scene item does not expose a callable sibling-stacking setter"
            )
        if callable(z_getter):
            try:
                z_value = float(cast(Any, z_getter()))
            except (RuntimeError, TypeError, ValueError):
                if strict:
                    raise
                z_getter = None
                z_setter = None
                z_value = None
        elif strict and z_ports_present and z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE:
            raise RuntimeError(
                "live scene item does not expose a readable stacking-depth contract"
            )
        else:
            z_getter = None
            z_setter = None
            z_value = None

        flags_getter = _base_graphics_item_port(item, "flags")
        flags_setter = _base_graphics_item_port(item, "setFlags")
        stacking_flags: QGraphicsItem.GraphicsItemFlag | None = None
        if flags_getter is not None and flags_setter is not None:
            stacking_flags = (
                cast(QGraphicsItem.GraphicsItemFlag, flags_getter())
                & _SCENE_STACKING_FLAG_MASK
            )

        snapshots.append(
            _SceneItemTopologySnapshot(
                item=item,
                parent=parent,
                parent_getter=(parent_getter if callable(parent_getter) else None),
                parent_setter=(parent_setter if callable(parent_setter) else None),
                z_value=z_value,
                z_getter=z_getter if callable(z_getter) else None,
                z_setter=z_setter if callable(z_setter) else None,
                stack_before=stack_before if callable(stack_before) else None,
                stacking_flags=stacking_flags,
                flags_getter=flags_getter,
                flags_setter=flags_setter,
            )
        )
    return snapshots


def _list_attribute_snapshot(
    owner: object | None,
    attribute: str,
    *,
    strict: bool = False,
) -> _ListAttributeSnapshot | None:
    if owner is None:
        return None
    value = _snapshot_attribute(owner, attribute, strict=strict)
    if not isinstance(value, list):
        return None
    return _ListAttributeSnapshot(owner, attribute, value, list(value))


def _mark_registry_snapshot(
    registry: object | None,
    *,
    strict: bool = False,
) -> _MarkRegistrySnapshot | None:
    if registry is None:
        return None
    mapping = _snapshot_attribute(registry, "by_atom", strict=strict)
    if not isinstance(mapping, dict):
        return None
    entries: list[tuple[object, object, list | None]] = []
    for key, value in mapping.items():
        entries.append((key, value, list(value) if isinstance(value, list) else None))
    return _MarkRegistrySnapshot(registry, mapping, entries)


def _selection_visual_snapshots(
    items: list,
    *,
    strict: bool = False,
) -> list[_SelectionVisualSnapshot]:
    snapshots: list[_SelectionVisualSnapshot] = []
    pending = list(items)
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if _graphics_item_is_deleted(item):
            continue
        child_items = _snapshot_attribute(item, "childItems", strict=strict)
        if callable(child_items):
            if strict:
                pending.extend(child_items())
            else:
                with contextlib.suppress(Exception):
                    pending.extend(child_items())
        pen_method = _snapshot_attribute(item, "pen", strict=strict)
        data_method = _snapshot_attribute(item, "data", strict=strict)
        if not callable(pen_method):
            continue
        try:
            pen = pen_method()
            data_6 = (
                data_method(6) if callable(data_method) else _UNAVAILABLE_ITEM_VALUE
            )
        except Exception:
            if strict:
                raise
            continue
        snapshots.append(_SelectionVisualSnapshot(item, pen, data_6))
    return snapshots


def _visibility_snapshots(
    items: list,
    *,
    strict: bool = False,
) -> list[_VisibilitySnapshot]:
    snapshots: list[_VisibilitySnapshot] = []
    for item in items:
        if _graphics_item_is_deleted(item):
            continue
        data_method = _snapshot_attribute(item, "data", strict=strict)
        if not callable(data_method):
            continue
        try:
            kind = data_method(0)
        except RuntimeError:
            if strict:
                raise
            continue
        if kind not in {"note_box", "note_select"}:
            continue
        is_visible = _snapshot_attribute(item, "isVisible", strict=strict)
        if not callable(is_visible):
            continue
        try:
            visible = bool(is_visible())
        except RuntimeError:
            if strict:
                raise
            continue
        values: list[object] = []
        for method_name in ("rect", "pen", "brush"):
            method = _snapshot_attribute(item, method_name, strict=strict)
            value: object = _UNAVAILABLE_ITEM_VALUE
            if callable(method):
                if strict:
                    value = method()
                else:
                    with contextlib.suppress(Exception):
                        value = method()
            values.append(value)
        snapshots.append(_VisibilitySnapshot(item, visible, *values))
    return snapshots


def _scene_runtime_snapshot(
    canvas,
    *,
    strict: bool = False,
    scene_override: object = _MISSING_SNAPSHOT_ATTRIBUTE,
) -> _SceneRuntimeSnapshot:
    scene: object | None
    if scene_override is not _MISSING_SNAPSHOT_ATTRIBUTE:
        scene = scene_override
    else:
        scene_method = _snapshot_attribute(canvas, "scene", strict=strict)
        if scene_method is _MISSING_SNAPSHOT_ATTRIBUTE or not callable(scene_method):
            scene = None
        else:
            try:
                scene = scene_method()
            except (AttributeError, RuntimeError):
                if strict:
                    raise
                scene = None
    scene_items, scene_items_getter = _scene_items_and_getter_from_scene(
        scene,
        strict=strict,
    )
    scene_signals_blocked = None
    signals_blocked_getter = _snapshot_attribute(
        scene,
        "signalsBlocked",
        strict=strict,
    )
    block_signals_setter = _snapshot_attribute(
        scene,
        "blockSignals",
        strict=strict,
    )
    signal_ports_present = (
        signals_blocked_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
        or block_signals_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
    )
    if callable(signals_blocked_getter) and callable(block_signals_setter):
        try:
            scene_signals_blocked = bool(signals_blocked_getter())
        except (AttributeError, RuntimeError):
            if strict:
                raise
            signals_blocked_getter = None
            block_signals_setter = None
    elif strict and signal_ports_present:
        raise RuntimeError(
            "live scene does not expose a complete signal-blocking contract"
        )
    else:
        signals_blocked_getter = None
        block_signals_setter = None
    focus_item_getter = _snapshot_attribute(scene, "focusItem", strict=strict)
    focus_item_setter = _snapshot_attribute(scene, "setFocusItem", strict=strict)
    focus_item = None
    focus_ports_present = (
        focus_item_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
        or focus_item_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
    )
    if callable(focus_item_getter) and callable(focus_item_setter):
        if strict:
            focus_item = focus_item_getter()
        else:
            try:
                focus_item = focus_item_getter()
            except (AttributeError, RuntimeError):
                focus_item_getter = None
                focus_item_setter = None
    elif strict and focus_ports_present:
        raise RuntimeError("live scene does not expose a complete focus contract")
    else:
        focus_item_getter = None
        focus_item_setter = None
    topology_states = _scene_item_topology_snapshots(
        scene_items or [],
        strict=strict,
    )
    selected_states: list[_SceneSelectionSnapshot] = []
    for item in scene_items or ():
        if _graphics_item_is_deleted(item):
            continue
        is_selected = _snapshot_attribute(item, "isSelected", strict=strict)
        set_selected = _snapshot_attribute(item, "setSelected", strict=strict)
        item_selection_access_present = (
            is_selected is not _MISSING_SNAPSHOT_ATTRIBUTE
            or set_selected is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if callable(is_selected) and callable(set_selected):
            try:
                selected_states.append(
                    _SceneSelectionSnapshot(
                        item=item,
                        selected=bool(is_selected()),
                        getter=is_selected,
                        setter=set_selected,
                    )
                )
            except (AttributeError, RuntimeError):
                if strict:
                    raise
        elif strict and item_selection_access_present:
            raise RuntimeError(
                "live scene item does not expose a complete selection contract"
            )

    list_attributes: list[_ListAttributeSnapshot] = []
    scene_items_state = _snapshot_canvas_state_object(
        canvas,
        "scene_items_state",
        strict=strict,
    )
    for attribute in SCENE_ITEM_COLLECTION_ATTRS:
        snapshot = _list_attribute_snapshot(
            scene_items_state,
            attribute,
            strict=strict,
        )
        if snapshot is not None:
            list_attributes.append(snapshot)
    handle_state = _snapshot_canvas_state_object(
        canvas,
        "handle_state",
        strict=strict,
    )
    handle_snapshot = _list_attribute_snapshot(
        handle_state,
        "active_handles",
        strict=strict,
    )
    if handle_snapshot is not None:
        list_attributes.append(handle_snapshot)
    selection_style_state = _snapshot_canvas_state_object(
        canvas,
        "selection_style_state",
        strict=strict,
    )
    selected_items_snapshot = _list_attribute_snapshot(
        selection_style_state,
        "selected_items",
        strict=strict,
    )
    selection_visuals = _selection_visual_snapshots(
        selected_items_snapshot.contents if selected_items_snapshot is not None else [],
        strict=strict,
    )
    if selected_items_snapshot is not None:
        list_attributes.append(selected_items_snapshot)
    selection_outline_state = _snapshot_canvas_state_object(
        canvas,
        "selection_outline_state",
        strict=strict,
    )
    outlines_snapshot = _list_attribute_snapshot(
        selection_outline_state,
        "outlines",
        strict=strict,
    )
    if outlines_snapshot is not None:
        list_attributes.append(outlines_snapshot)

    selection_info_state = _snapshot_canvas_state_object(
        canvas,
        "selection_info_state",
        strict=strict,
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
            value = _snapshot_attribute(
                selection_info_state,
                attribute,
                strict=strict,
            )
            if value is _MISSING_SNAPSHOT_ATTRIBUTE:
                continue
            selection_info_values[attribute] = value

    handle_target = _snapshot_attribute(handle_state, "target", strict=strict)
    if handle_target is _MISSING_SNAPSHOT_ATTRIBUTE:
        handle_target = None

    return _SceneRuntimeSnapshot(
        scene=scene,
        scene_items=scene_items,
        scene_items_getter=scene_items_getter,
        scene_signals_blocked=scene_signals_blocked,
        scene_signals_blocked_getter=(
            signals_blocked_getter if callable(signals_blocked_getter) else None
        ),
        scene_block_signals_setter=(
            block_signals_setter if callable(block_signals_setter) else None
        ),
        focus_item=focus_item,
        focus_item_getter=(focus_item_getter if callable(focus_item_getter) else None),
        focus_item_setter=(focus_item_setter if callable(focus_item_setter) else None),
        topology_states=topology_states,
        selected_states=selected_states,
        visibility_states=_visibility_snapshots(
            scene_items or [],
            strict=strict,
        ),
        selection_visuals=selection_visuals,
        list_attributes=list_attributes,
        mark_registry=_mark_registry_snapshot(
            _snapshot_canvas_state_object(
                canvas,
                "mark_registry",
                strict=strict,
            ),
            strict=strict,
        ),
        handle_state=handle_state,
        handle_target=handle_target,
        selection_info_state=selection_info_state,
        selection_info_values=selection_info_values,
        bond_primitive_graphics=_bond_primitive_graphics_snapshots(
            canvas,
            strict=strict,
        ),
    )


def _item_parent(item, *, strict: bool = False):
    parent_method = _snapshot_attribute(item, "parentItem", strict=strict)
    if not callable(parent_method):
        return None
    try:
        return parent_method()
    except RuntimeError:
        if strict:
            raise
        return None


def _item_z_value(item, *, strict: bool = False) -> float | None:
    z_method = _snapshot_attribute(item, "zValue", strict=strict)
    if not callable(z_method):
        return None
    try:
        return float(z_method())
    except (RuntimeError, TypeError, ValueError):
        if strict:
            raise
        return None


def _verify_scene_membership(
    scene,
    item,
    *,
    attached: bool,
    strict: bool = False,
) -> None:
    scene_method = _snapshot_attribute(item, "scene", strict=strict)
    if not callable(scene_method):
        return
    try:
        actual = scene_method() is scene
    except RuntimeError as error:
        raise RuntimeError("failed to verify restored scene-item membership") from error
    if actual is not attached:
        action = "attach" if attached else "detach"
        raise RuntimeError(f"scene restore failed to {action} an item")


def _direct_scene_remove(scene, item, *, strict: bool = False) -> None:
    remove_item = _snapshot_attribute(scene, "removeItem", strict=strict)
    if callable(remove_item):
        try:
            result = remove_item(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not remove an item") from error
        if result is False:
            raise RuntimeError("scene restore remove operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=False,
            strict=strict,
        )
        return
    detach = _snapshot_attribute(scene, "detach", strict=strict)
    if callable(detach):
        try:
            result = detach(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not detach an item") from error
        if result is False:
            raise RuntimeError("scene restore detach operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=False,
            strict=strict,
        )
        return
    raise RuntimeError("scene does not provide a direct item-removal operation")


def _direct_scene_add(scene, item, *, strict: bool = False) -> None:
    add_item = _snapshot_attribute(scene, "addItem", strict=strict)
    if callable(add_item):
        try:
            result = add_item(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not add an item") from error
        if result is False:
            raise RuntimeError("scene restore add operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=True,
            strict=strict,
        )
        return
    attach = _snapshot_attribute(scene, "attach", strict=strict)
    if callable(attach):
        try:
            result = attach(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not attach an item") from error
        if result is False:
            raise RuntimeError("scene restore attach operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=True,
            strict=strict,
        )
        return
    raise RuntimeError("scene does not provide a direct item-add operation")


def _item_is_attached_to_scene(
    scene,
    item,
    *,
    strict: bool = False,
) -> bool:
    scene_method = _snapshot_attribute(item, "scene", strict=strict)
    if not callable(scene_method):
        return False
    try:
        return scene_method() is scene
    except RuntimeError:
        if strict:
            raise
        return False


def _topology_depths(
    topology_states: list[_SceneItemTopologySnapshot],
) -> dict[int, int]:
    """Resolve every captured parent depth once and reject parent cycles."""

    states_by_item_id = {id(state.item): state for state in topology_states}
    depths: dict[int, int] = {}
    for start in topology_states:
        start_id = id(start.item)
        if start_id in depths:
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
                raise RuntimeError("scene runtime snapshot contains a parent cycle")
            positions[item_id] = len(path)
            path.append(current)
            current = states_by_item_id.get(id(current.parent))
        while path:
            resolved = path.pop()
            base_depth += 1
            depths[id(resolved.item)] = base_depth
    return depths


def _restore_scene_parent_topology(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    depths = _topology_depths(topology_states)
    ordered_states = sorted(
        topology_states,
        key=lambda state: depths[id(state.item)],
    )
    for state in ordered_states:
        getter = state.parent_getter
        if getter is None:
            continue
        try:
            if getter() is state.parent:
                continue
            setter = state.parent_setter
            if setter is None:
                raise RuntimeError(
                    "scene restore cannot repair a read-only item parent"
                )
            setter(state.parent)
            if getter() is not state.parent:
                raise RuntimeError(
                    "scene restore did not restore an item's exact parent identity"
                )
        except BaseException as restore_error:
            errors.append(restore_error)


def _restore_scene_z_values(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    for state in topology_states:
        getter = state.z_getter
        expected = state.z_value
        if getter is None or expected is None:
            continue
        try:
            if float(cast(Any, getter())) == expected:
                continue
            setter = state.z_setter
            if setter is None:
                raise RuntimeError(
                    "scene restore cannot repair a read-only item z value"
                )
            setter(expected)
            if float(cast(Any, getter())) != expected:
                raise RuntimeError(
                    "scene restore did not restore an item's exact z value"
                )
        except BaseException as restore_error:
            errors.append(restore_error)


def _restore_scene_stacking_flags(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    for state in topology_states:
        getter = state.flags_getter
        setter = state.flags_setter
        expected = state.stacking_flags
        if getter is None or setter is None or expected is None:
            continue
        try:
            current = cast(QGraphicsItem.GraphicsItemFlag, getter())
            if current & _SCENE_STACKING_FLAG_MASK == expected:
                continue
            restored = (current & ~_SCENE_STACKING_FLAG_MASK) | expected
            setter(restored)
            actual = cast(QGraphicsItem.GraphicsItemFlag, getter())
            if actual & _SCENE_STACKING_FLAG_MASK != expected:
                raise RuntimeError(
                    "scene restore did not restore an item's stacking flags"
                )
        except BaseException as restore_error:
            errors.append(restore_error)


def _verify_scene_item_topology(
    topology_states: list[_SceneItemTopologySnapshot],
) -> None:
    for state in topology_states:
        parent_getter = state.parent_getter
        if parent_getter is not None and parent_getter() is not state.parent:
            raise RuntimeError(
                "scene restore did not preserve an item's exact parent identity"
            )
        z_getter = state.z_getter
        if (
            z_getter is not None
            and state.z_value is not None
            and float(cast(Any, z_getter())) != state.z_value
        ):
            raise RuntimeError("scene restore did not preserve an item's exact z value")
        flags_getter = state.flags_getter
        if flags_getter is not None and state.stacking_flags is not None:
            actual_flags = cast(
                QGraphicsItem.GraphicsItemFlag,
                flags_getter(),
            )
            if actual_flags & _SCENE_STACKING_FLAG_MASK != state.stacking_flags:
                raise RuntimeError(
                    "scene restore did not preserve an item's stacking flags"
                )


def _restore_scene_stacking(
    snapshot: _SceneRuntimeSnapshot,
    *,
    errors: list[BaseException],
) -> None:
    expected_items = snapshot.scene_items
    items_getter = snapshot.scene_items_getter
    if expected_items is not None and items_getter is not None:
        try:
            current_items = list(items_getter())
            if len(current_items) == len(expected_items) and all(
                current is expected
                for current, expected in zip(
                    current_items,
                    expected_items,
                    strict=True,
                )
            ):
                return
        except BaseException as error:
            errors.append(error)
            return
    sibling_groups: dict[
        tuple[int, float],
        list[_SceneItemTopologySnapshot],
    ] = {}
    for state in snapshot.topology_states:
        z_value = state.z_value
        if z_value is None:
            continue
        sibling_groups.setdefault((id(state.parent), z_value), []).append(state)
    for siblings in sibling_groups.values():
        for higher, lower in zip(siblings, siblings[1:], strict=False):
            stack_before = lower.stack_before
            if not callable(stack_before):
                continue
            _run_suppressed_restore_step(
                None,
                "restoring scene-item stacking",
                partial(stack_before, higher.item),
                errors=errors,
            )


def _restore_scene_contents(
    snapshot: _SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None = None,
    errors: list[BaseException] | None = None,
    restore_attempts: int = 2,
) -> None:
    scene = snapshot.scene
    before = snapshot.scene_items
    if scene is None or before is None:
        return
    current_items_method = snapshot.scene_items_getter
    if not callable(current_items_method):
        if errors is not None:
            errors.append(RuntimeError("scene restore cannot read current items"))
        return
    if errors is not None:
        current = _run_absolute_restore_step(
            original_error,
            "reading current scene contents",
            lambda: list(current_items_method()),
            default=None,
            errors=errors,
        )
        if current is None:
            return
    elif original_error is None:
        try:
            current = list(current_items_method())
        except RuntimeError:
            return
    else:
        current = _run_rollback_step(
            original_error,
            "reading current scene contents",
            lambda: list(current_items_method()),
            default=None,
        )
        if current is None:
            return

    try:
        _restore_scene_signal_state(
            snapshot,
            True,
            phase="blocking scene signals for restore",
            original_error=original_error,
            errors=errors,
            max_attempts=restore_attempts,
        )
        before_ids = {id(item) for item in before}
        topology_by_item_id = {
            id(state.item): state for state in snapshot.topology_states
        }
        added = [item for item in current if id(item) not in before_ids]
        added_ids = {id(item) for item in added}
        for item in added:
            parent = _run_absolute_restore_step(
                original_error,
                "reading a newly added item's parent",
                partial(_item_parent, item, strict=errors is not None),
                errors=errors,
            )
            if parent is not None and id(parent) in added_ids:
                continue
            _run_absolute_restore_step(
                original_error,
                "removing an item absent from the scene snapshot",
                partial(
                    _direct_scene_remove,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )

        # Add roots before their children. Reverse the scene's top-to-bottom order
        # because newly added equal-z siblings stack above existing siblings.
        for item in reversed(before):
            attached = _run_absolute_restore_step(
                original_error,
                "reading scene-item membership",
                partial(
                    _item_is_attached_to_scene,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )
            if attached:
                continue
            topology_state = topology_by_item_id.get(id(item))
            parent = (
                topology_state.parent
                if topology_state is not None
                else _run_absolute_restore_step(
                    original_error,
                    "reading a snapshot item's parent",
                    partial(_item_parent, item, strict=errors is not None),
                    errors=errors,
                )
            )
            if parent is not None and id(parent) in before_ids:
                continue
            _run_absolute_restore_step(
                original_error,
                "reattaching a snapshot scene-item root",
                partial(
                    _direct_scene_add,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )
        for item in reversed(before):
            attached = _run_absolute_restore_step(
                original_error,
                "reading scene-item membership",
                partial(
                    _item_is_attached_to_scene,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )
            if not attached:
                _run_absolute_restore_step(
                    original_error,
                    "reattaching a snapshot scene item",
                    partial(
                        _direct_scene_add,
                        scene,
                        item,
                        strict=errors is not None,
                    ),
                    default=False,
                    errors=errors,
                )

        _restore_scene_focus(
            snapshot,
            original_error=original_error,
            errors=errors,
            max_attempts=restore_attempts,
        )
        _restore_scene_order_and_selection(
            snapshot,
            current_items_method,
            original_error=original_error,
            errors=errors,
            max_attempts=restore_attempts,
        )
    finally:
        if snapshot.scene_signals_blocked is not None:
            _restore_scene_signal_state(
                snapshot,
                snapshot.scene_signals_blocked,
                phase="restoring the scene signal-blocking state",
                original_error=original_error,
                errors=errors,
                max_attempts=restore_attempts,
            )


def _restore_scene_signal_state(
    snapshot: _SceneRuntimeSnapshot,
    blocked: bool,
    *,
    phase: str,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
    max_attempts: int = 2,
) -> None:
    getter = snapshot.scene_signals_blocked_getter
    setter = snapshot.scene_block_signals_setter
    if getter is None or setter is None:
        return

    def restore_once() -> None:
        setter(blocked)
        if bool(getter()) is not blocked:
            raise RuntimeError(
                "scene signal-blocking setter did not restore the requested state"
            )

    failures: list[BaseException] = []
    restored = False
    for _attempt in range(max_attempts):
        try:
            restore_once()
        except BaseException as restore_error:
            failures.append(restore_error)
            continue
        restored = True
        break

    if restored:
        if original_error is not None:
            for failure in failures:
                _add_rollback_error_note(
                    original_error,
                    failure,
                    phase=phase,
                )
        return
    if errors is not None:
        errors.extend(failures)
        return
    if original_error is not None:
        for failure in failures:
            _add_rollback_error_note(
                original_error,
                failure,
                phase=phase,
            )
        return
    first_error, *retry_errors = failures
    for retry_error in retry_errors:
        _add_rollback_error_note(
            first_error,
            retry_error,
            phase=f"retrying {phase}",
        )
    raise first_error


def _restore_expected_scene_membership(
    snapshot: _SceneRuntimeSnapshot,
    *,
    errors: list[BaseException],
) -> None:
    scene = snapshot.scene
    expected_items = snapshot.scene_items
    if scene is None or expected_items is None:
        return
    expected_ids = {id(item) for item in expected_items}
    topology_by_item_id = {id(state.item): state for state in snapshot.topology_states}

    def attach_if_missing(item: object) -> None:
        try:
            if _item_is_attached_to_scene(scene, item, strict=True):
                return
            _direct_scene_add(scene, item, strict=True)
        except BaseException as restore_error:
            errors.append(restore_error)

    for item in reversed(expected_items):
        state = topology_by_item_id.get(id(item))
        if state is not None and state.parent is not None:
            if id(state.parent) in expected_ids:
                continue
        attach_if_missing(item)
    for item in reversed(expected_items):
        attach_if_missing(item)


def _restore_scene_order_and_selection(
    snapshot: _SceneRuntimeSnapshot,
    current_items_method: Callable[[], Any],
    *,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
    max_attempts: int = 2,
) -> None:
    expected_items = snapshot.scene_items
    if expected_items is None:
        return

    failures: list[BaseException] = []
    for _attempt in range(max_attempts):
        attempt_errors: list[BaseException] = []
        # Stacking flags can synchronously change selection. Restore them before
        # selection so the latter remains the final writer for that dependency;
        # the second pass handles the reverse dependency as well.
        _restore_scene_stacking_flags(
            snapshot.topology_states,
            errors=attempt_errors,
        )
        # A selected item's setter may synchronously select a peer. Apply the
        # captured-false states last so those callbacks cannot repollute the
        # final selection set. ``sorted`` is stable, preserving scene order
        # within each state group.
        ordered_selection_states = sorted(
            snapshot.selected_states,
            key=lambda selection: not selection.selected,
        )
        for selection in ordered_selection_states:
            try:
                if not _item_is_attached_to_scene(
                    snapshot.scene,
                    selection.item,
                    strict=True,
                ):
                    raise RuntimeError(
                        "scene selection target is not attached after restore"
                    )
                selection.setter(selection.selected)
                if bool(selection.getter()) != selection.selected:
                    raise RuntimeError(
                        "scene restore did not restore an item's selection state"
                    )
            except BaseException as restore_error:
                attempt_errors.append(restore_error)
        # Selection callbacks may synchronously reparent items or alter their
        # z-depth. Keep topology as the final writer; on the second pass an
        # already-exact topology setter is skipped, so the reverse dependency
        # (a topology setter mutating selection) converges as well.
        _restore_scene_parent_topology(
            snapshot.topology_states,
            errors=attempt_errors,
        )
        _restore_expected_scene_membership(
            snapshot,
            errors=attempt_errors,
        )
        _restore_scene_z_values(
            snapshot.topology_states,
            errors=attempt_errors,
        )
        _restore_scene_stacking(
            snapshot,
            errors=attempt_errors,
        )
        try:
            _verify_scene_item_topology(snapshot.topology_states)
            for selection in snapshot.selected_states:
                if bool(selection.getter()) != selection.selected:
                    raise RuntimeError(
                        "scene topology restore changed an item's selection state"
                    )
            current_items = list(current_items_method())
            if len(current_items) != len(expected_items) or any(
                current is not expected
                for current, expected in zip(
                    current_items,
                    expected_items,
                    strict=True,
                )
            ):
                raise RuntimeError(
                    "scene restore did not restore the exact ordered item identity"
                )
        except BaseException as restore_error:
            attempt_errors.append(restore_error)
        if not attempt_errors:
            if original_error is not None:
                for failure in failures:
                    _add_rollback_error_note(
                        original_error,
                        failure,
                        phase="restoring scene order and selection",
                    )
            return
        failures.extend(attempt_errors)

    if errors is not None:
        errors.extend(failures)
        return
    if original_error is not None:
        for failure in failures:
            _add_rollback_error_note(
                original_error,
                failure,
                phase="restoring scene order and selection",
            )
        return
    first_error, *retry_errors = failures
    for retry_error in retry_errors:
        _add_rollback_error_note(
            first_error,
            retry_error,
            phase="retrying scene order and selection restore",
        )
    raise first_error


def _restore_scene_focus(
    snapshot: _SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
    max_attempts: int = 2,
) -> None:
    getter = snapshot.focus_item_getter
    setter = snapshot.focus_item_setter
    if getter is None or setter is None:
        return

    def restore_once() -> None:
        focus_item = snapshot.focus_item
        if focus_item is not None and not _item_is_attached_to_scene(
            snapshot.scene,
            focus_item,
            strict=True,
        ):
            raise RuntimeError("scene focus target is not attached after restore")
        setter(focus_item)
        if getter() is not focus_item:
            raise RuntimeError("scene restore did not restore the focus item")

    failures: list[BaseException] = []
    restored = False
    for _attempt in range(max_attempts):
        try:
            restore_once()
        except BaseException as restore_error:
            failures.append(restore_error)
            continue
        restored = True
        break

    if restored:
        if original_error is not None:
            for failure in failures:
                _add_rollback_error_note(
                    original_error,
                    failure,
                    phase="restoring the scene focus item",
                )
        return
    if errors is not None:
        errors.extend(failures)
        return
    if original_error is not None:
        for failure in failures:
            _add_rollback_error_note(
                original_error,
                failure,
                phase="restoring the scene focus item",
            )
        return
    first_error, *retry_errors = failures
    for retry_error in retry_errors:
        _add_rollback_error_note(
            first_error,
            retry_error,
            phase="retrying the scene focus-item restore",
        )
    raise first_error


def _verify_scene_runtime_identity(snapshot: _SceneRuntimeSnapshot) -> None:
    signals_getter = snapshot.scene_signals_blocked_getter
    if signals_getter is not None and snapshot.scene_signals_blocked is not None:
        if bool(signals_getter()) != snapshot.scene_signals_blocked:
            raise RuntimeError(
                "final scene restore did not preserve the signal-blocking state"
            )

    focus_getter = snapshot.focus_item_getter
    if focus_getter is not None and focus_getter() is not snapshot.focus_item:
        raise RuntimeError("final scene restore did not preserve focus identity")

    for selection in snapshot.selected_states:
        if bool(selection.getter()) != selection.selected:
            raise RuntimeError(
                "final scene restore did not preserve an item's selection state"
            )

    _verify_scene_item_topology(snapshot.topology_states)

    expected_items = snapshot.scene_items
    items_getter = snapshot.scene_items_getter
    if expected_items is None:
        return
    if items_getter is None:
        raise RuntimeError("final scene restore cannot read scene items")
    current_items = list(items_getter())
    if len(current_items) != len(expected_items) or any(
        current is not expected
        for current, expected in zip(
            current_items,
            expected_items,
            strict=True,
        )
    ):
        raise RuntimeError(
            "final scene restore did not preserve exact ordered item identity"
        )


def _restore_scene_runtime_identity_final(
    snapshot: _SceneRuntimeSnapshot,
) -> list[BaseException]:
    failures: list[BaseException] = []
    for _attempt in range(2):
        attempt_errors: list[BaseException] = []
        try:
            _restore_scene_contents(
                snapshot,
                errors=attempt_errors,
                restore_attempts=1,
            )
        except BaseException as restore_error:
            attempt_errors.append(restore_error)
        try:
            # This check deliberately runs after _restore_scene_contents has
            # restored the original blocked state. A custom unblock callback
            # can mutate focus, selection, or stacking after the repair pass.
            _verify_scene_runtime_identity(snapshot)
        except BaseException as verify_error:
            attempt_errors.append(verify_error)
        if not attempt_errors:
            return []
        failures.extend(attempt_errors)
    return failures


def _restore_list_attribute(snapshot: _ListAttributeSnapshot) -> None:
    snapshot.list_object[:] = snapshot.contents
    setattr(snapshot.owner, snapshot.attribute, snapshot.list_object)


def _restore_mark_registry(snapshot: _MarkRegistrySnapshot) -> None:
    snapshot.mapping_object.clear()
    for key, value, contents in snapshot.entries:
        if isinstance(value, list) and contents is not None:
            value[:] = contents
        snapshot.mapping_object[key] = value
    snapshot.registry.by_atom = snapshot.mapping_object


def _restore_selection_visual(snapshot: _SelectionVisualSnapshot) -> None:
    set_pen = _snapshot_attribute(snapshot.item, "setPen", strict=True)
    if callable(set_pen):
        set_pen(snapshot.pen)
    if snapshot.data_6 is _UNAVAILABLE_ITEM_VALUE:
        return
    set_data = _snapshot_attribute(snapshot.item, "setData", strict=True)
    if callable(set_data):
        set_data(6, snapshot.data_6)


def _restore_visibility(snapshot: _VisibilitySnapshot) -> None:
    for method_name, value in (
        ("setRect", snapshot.rect),
        ("setPen", snapshot.pen),
        ("setBrush", snapshot.brush),
    ):
        if value is _UNAVAILABLE_ITEM_VALUE:
            continue
        method = _snapshot_attribute(snapshot.item, method_name, strict=True)
        if callable(method):
            method(value)
    set_visible = _snapshot_attribute(snapshot.item, "setVisible", strict=True)
    if callable(set_visible):
        set_visible(snapshot.visible)


def _restore_scene_runtime_snapshot(
    snapshot: _SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None = None,
    collect_errors: bool = False,
    defer_scene_identity_errors: bool = False,
    restore_attempts: int = 2,
) -> list[BaseException]:
    errors: list[BaseException] | None = [] if collect_errors else None
    scene_errors = [] if collect_errors and defer_scene_identity_errors else errors
    try:
        _run_absolute_restore_step(
            original_error,
            "restoring absolute scene contents",
            lambda: _restore_scene_contents(
                snapshot,
                original_error=original_error,
                errors=scene_errors,
                restore_attempts=restore_attempts,
            ),
            errors=scene_errors,
        )
        for list_snapshot in snapshot.list_attributes:
            _run_suppressed_restore_step(
                original_error,
                f"restoring runtime list {list_snapshot.attribute}",
                partial(_restore_list_attribute, list_snapshot),
                errors=errors,
            )
        mark_registry = snapshot.mark_registry
        if mark_registry is not None:
            _run_suppressed_restore_step(
                original_error,
                "restoring the mark registry",
                partial(_restore_mark_registry, mark_registry),
                errors=errors,
            )
        for visibility_snapshot in snapshot.visibility_states:
            _run_suppressed_restore_step(
                original_error,
                "restoring selection-overlay visibility",
                partial(_restore_visibility, visibility_snapshot),
                errors=errors,
            )
        for visual_snapshot in snapshot.selection_visuals:
            _run_suppressed_restore_step(
                original_error,
                "restoring a selection visual",
                partial(_restore_selection_visual, visual_snapshot),
                errors=errors,
            )
        if snapshot.handle_state is not None:
            _run_suppressed_restore_step(
                original_error,
                "restoring the active handle target",
                lambda: setattr(
                    snapshot.handle_state, "target", snapshot.handle_target
                ),
                errors=errors,
            )
        if snapshot.selection_info_state is not None:
            for attribute, value in snapshot.selection_info_values.items():
                _run_suppressed_restore_step(
                    original_error,
                    f"restoring selection-info field {attribute}",
                    partial(
                        setattr,
                        snapshot.selection_info_state,
                        attribute,
                        value,
                    ),
                    errors=errors,
                )
    finally:
        # Ring attach/remove callbacks refresh surviving bond primitives in
        # place and can fail after a partial mutation. The exact raw graphics
        # savepoint must be the final restore phase, including when lifecycle
        # compensation itself invokes the same persistently failing callback.
        primitive_errors = _run_absolute_restore_step(
            original_error,
            "restoring raw bond primitives",
            lambda: _restore_bond_primitive_graphics_snapshots(
                snapshot.bond_primitive_graphics
            ),
            default=[],
            errors=errors,
        )
        if errors is not None:
            errors.extend(primitive_errors)
        elif original_error is not None:
            for primitive_error in primitive_errors:
                _add_rollback_error_note(
                    original_error,
                    primitive_error,
                    phase="restoring a raw bond primitive",
                )
    return errors or []


def _restore_scene_item_memberships(
    canvas,
    attempted: list[tuple[object, bool | None]],
    *,
    unknown_was_attached: bool,
    original_error: BaseException,
) -> None:
    desired_memberships = [
        (
            item,
            unknown_was_attached if was_attached is None else was_attached,
        )
        for item, was_attached in attempted
    ]
    # Remove newly attached items in reverse mutation order, then reattach
    # removed items in their original order so equal-z scene stacking is not
    # reversed by the compensation itself.
    for item, should_be_attached in reversed(desired_memberships):
        if should_be_attached:
            continue
        _run_rollback_step(
            original_error,
            "removing a newly attached scene item",
            partial(_remove_scene_item, canvas, item),
        )
    for item, should_be_attached in desired_memberships:
        if not should_be_attached:
            continue
        _run_rollback_step(
            original_error,
            "reattaching a removed scene item",
            partial(_restore_scene_item, canvas, item),
        )


def _release_scene_rect_snapshot(
    snapshot: SceneRectSnapshot | None,
) -> None:
    if snapshot is None:
        return
    if not snapshot.automatic or not snapshot.guarded:
        snapshot.release()
        return
    items_bounding_rect = snapshot.scene_items_bounding_rect_getter
    snapshot.release(
        authoritative_scene_bounds_getter=(
            items_bounding_rect if callable(items_bounding_rect) else None
        )
    )


def _capture_scene_rect_snapshot(scene) -> SceneRectSnapshot | None:
    items_bounding_rect = _snapshot_attribute(
        scene,
        "itemsBoundingRect",
        strict=True,
    )
    snapshot = SceneRectSnapshot.capture(scene)
    if snapshot is not None:
        snapshot.scene_items_bounding_rect_getter = (
            items_bounding_rect if callable(items_bounding_rect) else None
        )
    return snapshot


def _restore_scene_rect_snapshot(
    snapshot: SceneRectSnapshot | None,
    original_error: BaseException,
) -> None:
    def note_restore_error(error: BaseException, *, phase: str) -> None:
        if isinstance(error, BaseExceptionGroup):
            for nested_error in error.exceptions:
                note_restore_error(nested_error, phase=phase)
            return
        _add_rollback_error_note(
            original_error,
            error,
            phase=phase,
        )
        # Verified rect operations retain the second failed attempt as a note
        # on the first BaseException so that fail-before and mutate-then-fail
        # implementations can preserve the original control-flow type. Carry
        # that detail to the command's primary error as a separate note too;
        # otherwise one of the two rollback failures is silently lost.
        try:
            nested_notes = getattr(error, "__notes__", ())
            add_note = getattr(original_error, "add_note", None)
            if callable(add_note) and isinstance(nested_notes, (list, tuple)):
                for nested_note in nested_notes:
                    if not isinstance(nested_note, str):
                        continue
                    add_note(
                        "UI history rollback also recorded during "
                        f"{phase}: {nested_note}"
                    )
        except BaseException:
            pass

    def recovery_count() -> int:
        recovery_errors = getattr(snapshot, "recovery_errors", None)
        return len(recovery_errors) if isinstance(recovery_errors, list) else 0

    def note_recovered_errors(since: int, *, phase: str) -> None:
        recovery_errors = getattr(snapshot, "recovery_errors", None)
        if not isinstance(recovery_errors, list):
            return
        for error in recovery_errors[since:]:
            note_restore_error(error, phase=phase)

    if snapshot is None:
        return
    first_recovery_count = recovery_count()
    try:
        snapshot.restore()
    except BaseException as first_restore_error:
        note_restore_error(
            first_restore_error,
            phase="restoring the automatic scene rect",
        )
        if not snapshot.active:
            return
    else:
        note_recovered_errors(
            first_recovery_count,
            phase="recovering a transient automatic scene-rect restore failure",
        )
        if not snapshot.active:
            return
    second_recovery_count = recovery_count()
    try:
        snapshot.restore()
    except BaseException as second_restore_error:
        note_restore_error(
            second_restore_error,
            phase="retrying the automatic scene-rect restore",
        )
    else:
        note_recovered_errors(
            second_recovery_count,
            phase="recovering a transient automatic scene-rect retry failure",
        )


def _mutate_existing_scene_items_atomically(
    canvas,
    items: list,
    operation: Callable[[Any, Any], None],
    *,
    unknown_was_attached: bool,
) -> None:
    runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
    snapshots = [
        (item, _scene_item_membership(canvas, item))
        for item in items
        if item is not None
    ]
    attempted: list[tuple[object, bool | None]] = []
    scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        for snapshot in snapshots:
            attempted.append(snapshot)
            operation(canvas, snapshot[0])
        _release_scene_rect_snapshot(scene_rect_snapshot)
    except BaseException as original_error:
        _restore_scene_item_memberships(
            canvas,
            attempted,
            unknown_was_attached=unknown_was_attached,
            original_error=original_error,
        )
        _run_rollback_step(
            original_error,
            "restoring the absolute scene/runtime snapshot",
            partial(
                _restore_scene_runtime_snapshot,
                runtime_snapshot,
                original_error=original_error,
            ),
        )
        _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
        raise


def _create_scene_items_atomically(canvas, states: list[dict], items: list) -> None:
    original_items = list(items)
    runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
    scene_before = (
        list(runtime_snapshot.scene_items)
        if runtime_snapshot.scene_items is not None
        else None
    )
    created: list = []
    scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        for state in states:
            item = _create_scene_item_from_state(canvas, state)
            items.append(item)
            if item is not None:
                created.append(item)
        _release_scene_rect_snapshot(scene_rect_snapshot)
    except BaseException as original_error:
        created.extend(
            _run_rollback_step(
                original_error,
                "discovering partially created scene items",
                lambda: _new_top_level_scene_items(canvas, scene_before),
                default=[],
            )
        )
        seen: set[int] = set()
        for item in reversed(created):
            if id(item) in seen:
                continue
            seen.add(id(item))
            _run_rollback_step(
                original_error,
                "removing a partially created scene item",
                partial(_remove_scene_item, canvas, item),
            )
        items[:] = original_items
        _run_rollback_step(
            original_error,
            "restoring the absolute scene/runtime snapshot",
            partial(
                _restore_scene_runtime_snapshot,
                runtime_snapshot,
                original_error=original_error,
            ),
        )
        _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
        raise


@dataclass(slots=True)
class _GroupStateSnapshot:
    state: Any
    groups_object: dict[int, CanvasSceneGroup]
    groups: dict[int, CanvasSceneGroup]
    next_group_id: int
    expanding: bool


def _group_state_snapshot(canvas) -> _GroupStateSnapshot:
    state = group_state_for(canvas)
    return _GroupStateSnapshot(
        state=state,
        groups_object=state.groups,
        groups=dict(state.groups),
        next_group_id=state.next_group_id,
        expanding=state.expanding,
    )


def _restore_group_state(snapshot: _GroupStateSnapshot) -> None:
    snapshot.groups_object.clear()
    snapshot.groups_object.update(snapshot.groups)
    snapshot.state.groups = snapshot.groups_object
    snapshot.state.next_group_id = snapshot.next_group_id
    snapshot.state.expanding = snapshot.expanding


def _active_handle_position_snapshots(canvas) -> list[tuple[object, object]]:
    runtime_state = getattr(canvas, "runtime_state", None)
    handle_state = getattr(runtime_state, "handle_state", None)
    if handle_state is None:
        handle_state = getattr(canvas, "handle_state", None)
    handles = getattr(handle_state, "active_handles", ())
    snapshots: list[tuple[object, object]] = []
    for handle in handles:
        position_method = getattr(handle, "pos", None)
        if not callable(position_method):
            continue
        try:
            snapshots.append((handle, position_method()))
        except RuntimeError:
            continue
    return snapshots


def _restore_active_handle_positions(
    snapshots: list[tuple[object, object]],
    *,
    original_error: BaseException,
) -> None:
    for handle, position in snapshots:
        set_position = getattr(handle, "setPos", None)
        if not callable(set_position):
            continue
        _run_rollback_step(
            original_error,
            "restoring an active handle position",
            partial(set_position, position),
        )


_UNAVAILABLE_ITEM_VALUE = object()


@dataclass(slots=True)
class _MoveItemSnapshot:
    item: object
    state: dict
    position: object
    data_1: object
    data_2: object
    atom_positions: dict[int, tuple[float, float]]
    atom_coords_3d: dict[int, tuple[float, float, float]]


def _move_item_atom_ids(canvas, item) -> set[int]:
    data_method = getattr(item, "data", None)
    if not callable(data_method):
        return set()
    try:
        kind = data_method(0)
        item_id = data_method(1)
    except RuntimeError:
        return set()
    if kind == "atom" and isinstance(item_id, int):
        return {item_id}
    if kind != "bond" or not isinstance(item_id, int):
        return set()
    try:
        bond = bond_for_id(canvas, item_id)
    except (AttributeError, RuntimeError):
        return set()
    if bond is None:
        return set()
    return {
        atom_id
        for atom_id in (getattr(bond, "a", None), getattr(bond, "b", None))
        if isinstance(atom_id, int)
    }


def _model_move_snapshots(
    canvas,
    item,
) -> tuple[
    dict[int, tuple[float, float]],
    dict[int, tuple[float, float, float]],
]:
    positions: dict[int, tuple[float, float]] = {}
    coords_3d: dict[int, tuple[float, float, float]] = {}
    for atom_id in _move_item_atom_ids(canvas, item):
        try:
            atom = atom_for_id(canvas, atom_id)
        except (AttributeError, RuntimeError):
            continue
        if atom is None:
            continue
        positions[atom_id] = (float(atom.x), float(atom.y))
        try:
            coord = atom_coords_3d_for_id(canvas, atom_id)
        except (AttributeError, RuntimeError):
            coord = None
        if coord is not None:
            coords_3d[atom_id] = coord
    return positions, coords_3d


def _move_item_snapshot(canvas, item) -> _MoveItemSnapshot:
    position: object = _UNAVAILABLE_ITEM_VALUE
    position_method = getattr(item, "pos", None)
    if callable(position_method):
        try:
            position = position_method()
        except RuntimeError:
            pass

    data_values: list[object] = []
    data_method = getattr(item, "data", None)
    for index in (1, 2):
        value: object = _UNAVAILABLE_ITEM_VALUE
        if callable(data_method):
            try:
                current = data_method(index)
                value = dict(current) if isinstance(current, dict) else current
            except RuntimeError:
                pass
        data_values.append(value)

    atom_positions, atom_coords_3d = _model_move_snapshots(canvas, item)
    return _MoveItemSnapshot(
        item=item,
        state=scene_item_state_for(canvas, item),
        position=position,
        data_1=data_values[0],
        data_2=data_values[1],
        atom_positions=atom_positions,
        atom_coords_3d=atom_coords_3d,
    )


def _restore_raw_move_item_state(
    snapshot: _MoveItemSnapshot,
    *,
    original_error: BaseException,
) -> bool:
    restored = False
    if snapshot.position is not _UNAVAILABLE_ITEM_VALUE:
        set_position = getattr(snapshot.item, "setPos", None)
        if callable(set_position):
            try:
                set_position(snapshot.position)
                restored = True
            except BaseException as rollback_error:
                _add_rollback_error_note(
                    original_error,
                    rollback_error,
                    phase="restoring a moved item's raw position",
                )

    set_data = getattr(snapshot.item, "setData", None)
    if not callable(set_data):
        return restored
    for index, value in ((1, snapshot.data_1), (2, snapshot.data_2)):
        if value is _UNAVAILABLE_ITEM_VALUE:
            continue
        try:
            set_data(index, value)
            restored = True
        except BaseException as rollback_error:
            _add_rollback_error_note(
                original_error,
                rollback_error,
                phase=f"restoring a moved item's raw data slot {index}",
            )
    return restored


@dataclass
class MoveItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True
    history_transaction_owns_exact_state = True

    items: list
    dx: float
    dy: float

    def _apply(self, canvas, dx: float, dy: float) -> None:
        attempted: list[_MoveItemSnapshot] = []
        transaction = capture_history_transaction_for_command(canvas)
        handle_snapshots: list[tuple[object, object]] = []
        try:
            snapshots = [
                _move_item_snapshot(canvas, item)
                for item in self.items
                if item is not None and _item_is_in_canvas_scene(canvas, item)
            ]
            handle_snapshots = _active_handle_position_snapshots(canvas)
            for snapshot in snapshots:
                attempted.append(snapshot)
                move_item_for(canvas, snapshot.item, dx, dy, update_selection=False)
            refresh_selection_outline_for_canvas(canvas)
            release_history_transaction_for_command(canvas, transaction)
        except BaseException as original_error:
            atom_positions: dict[int, tuple[float, float]] = {}
            atom_coords_3d: dict[int, tuple[float, float, float]] = {}
            for snapshot in attempted:
                atom_positions.update(snapshot.atom_positions)
                atom_coords_3d.update(snapshot.atom_coords_3d)
            if atom_positions:
                # Atom and bond moves mutate model coordinates, bound marks,
                # 3D coordinates, the spatial index, bonds, and ring fills in
                # addition to the grabbed graphics item. Restore those absolute
                # savepoints before normalizing each graphics item below.
                _run_rollback_step(
                    original_error,
                    "restoring absolute atom positions after a move",
                    lambda: _set_atom_positions_for_history(
                        canvas,
                        atom_positions,
                        update_selection=False,
                        coords_3d=atom_coords_3d or None,
                    ),
                )
            for snapshot in reversed(attempted):
                raw_restored = _restore_raw_move_item_state(
                    snapshot,
                    original_error=original_error,
                )
                if snapshot.state:
                    try:
                        _apply_scene_item_state(canvas, snapshot.item, snapshot.state)
                        continue
                    except BaseException as rollback_error:
                        _add_rollback_error_note(
                            original_error,
                            rollback_error,
                            phase="canonically restoring a moved scene item",
                        )
                        # Canonical apply can mutate before raising. Reapply the
                        # raw savepoint last so its partial state cannot leak.
                        raw_restored = (
                            _restore_raw_move_item_state(
                                snapshot,
                                original_error=original_error,
                            )
                            or raw_restored
                        )
                if raw_restored:
                    continue
                _run_rollback_step(
                    original_error,
                    "inversely moving a scene item",
                    partial(
                        move_item_for,
                        canvas,
                        snapshot.item,
                        -dx,
                        -dy,
                        update_selection=False,
                    ),
                )
            _restore_active_handle_positions(
                handle_snapshots,
                original_error=original_error,
            )
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after a move",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            # A bulk position setter can restore one mutable Atom and then
            # terminate before later atoms, labels, rings, or 3D coordinates.
            # Make the full pre-command transaction savepoint authoritative
            # after every local best-effort repair.
            restore_result = _run_rollback_step(
                original_error,
                "restoring the exact move transaction",
                partial(
                    restore_history_transaction_for_command,
                    canvas,
                    transaction,
                    original_error,
                ),
            )
            if restore_result is not None:
                for exact_restore_error in restore_result.errors:
                    _add_rollback_error_note(
                        original_error,
                        exact_restore_error,
                        phase="restoring the exact move transaction",
                    )
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, -self.dx, -self.dy)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.dx, self.dy)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item: object
    before_state: dict
    after_state: dict

    def _apply(self, canvas, state: dict, rollback_state: dict) -> None:
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            _apply_scene_item_state(canvas, self.item, state)
            refresh_selection_outline_for_canvas(canvas)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring a scene item's prior state",
                lambda: _apply_scene_item_state(canvas, self.item, rollback_state),
            )
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after a scene-item update",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            # Outline refresh clears the old scene items before rebuilding. If
            # that rebuild raises, applying the item state back is insufficient:
            # restore the exact pre-command outline membership/list identity and
            # other selection runtime state as well.
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        if not self.items:
            _create_scene_items_atomically(canvas, self.item_states, self.items)
            return
        _mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _restore_scene_item,
            unknown_was_attached=False,
        )

    def undo(self, canvas) -> None:
        _mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )


@dataclass
class DeleteSceneItemsCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    item_states: list[dict]
    items: list = field(default_factory=list)

    def redo(self, canvas) -> None:
        _mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _remove_scene_item,
            unknown_was_attached=True,
        )

    def undo(self, canvas) -> None:
        if not self.items:
            _create_scene_items_atomically(canvas, self.item_states, self.items)
            return
        _mutate_existing_scene_items_atomically(
            canvas,
            self.items,
            _restore_scene_item,
            unknown_was_attached=False,
        )


@dataclass
class GroupSceneItemsCommand(HistoryCommand):
    atom_ids: set[int]
    items: list
    absorbed: list[tuple[int, CanvasSceneGroup]] = field(default_factory=list)
    group_id: int | None = None

    def redo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        previous_group_id = self.group_id
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            for absorbed_id, _ in self.absorbed:
                remove_group_for(canvas, absorbed_id)
            if self.group_id is None:
                self.group_id = register_group_for(canvas, self.atom_ids, self.items)
            else:
                restore_group_for(
                    canvas,
                    self.group_id,
                    CanvasSceneGroup(set(self.atom_ids), list(self.items)),
                )
            # The dashed group box is part of the selection outline; without a
            # refresh, undo/redo would leave a stale box (and its hit-test area).
            refresh_selection_outline_for_canvas(canvas)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            self.group_id = previous_group_id
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after grouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            if self.group_id is not None:
                remove_group_for(canvas, self.group_id)
            for absorbed_id, group in self.absorbed:
                restore_group_for(canvas, absorbed_id, group)
            refresh_selection_outline_for_canvas(canvas)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after ungrouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    def redo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            for group_id, _ in self.removed:
                remove_group_for(canvas, group_id)
            refresh_selection_outline_for_canvas(canvas)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after grouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            for group_id, group in self.removed:
                restore_group_for(canvas, group_id, group)
            refresh_selection_outline_for_canvas(canvas)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring group state",
                lambda: _restore_group_state(snapshot),
            )
            _run_rollback_step(
                original_error,
                "refreshing the selection outline after ungrouping",
                lambda: refresh_selection_outline_for_canvas(canvas),
            )
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise


@dataclass
class ChangeAtomLabelCommand(HistoryCommand):
    history_transaction_snapshot_covers_state = True

    atom_id: int
    before_element: str
    after_element: str
    before_explicit_label: bool
    after_explicit_label: bool
    before_smiles_input: str | None
    after_smiles_input: str | None

    def _apply(
        self,
        canvas,
        element: str,
        explicit_label: bool,
        smiles_input: str | None,
        rollback_element: str,
        rollback_explicit_label: bool,
        rollback_smiles_input: str | None,
    ) -> None:
        runtime_snapshot = _scene_runtime_snapshot(canvas, strict=True)
        scene_rect_snapshot = _capture_scene_rect_snapshot(runtime_snapshot.scene)
        try:
            add_or_update_atom_label(
                canvas,
                self.atom_id,
                element,
                clear_smiles=False,
                record=False,
                allow_merge=False,
                show_carbon=explicit_label,
            )
            set_last_smiles_input_for(canvas, smiles_input)
            _release_scene_rect_snapshot(scene_rect_snapshot)
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "restoring the prior atom label",
                lambda: add_or_update_atom_label(
                    canvas,
                    self.atom_id,
                    rollback_element,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=rollback_explicit_label,
                ),
            )
            _run_rollback_step(
                original_error,
                "restoring the prior SMILES input",
                lambda: set_last_smiles_input_for(canvas, rollback_smiles_input),
            )
            _run_rollback_step(
                original_error,
                "restoring the absolute scene/runtime snapshot",
                partial(
                    _restore_scene_runtime_snapshot,
                    runtime_snapshot,
                    original_error=original_error,
                ),
            )
            _restore_scene_rect_snapshot(scene_rect_snapshot, original_error)
            raise

    def undo(self, canvas) -> None:
        self._apply(
            canvas,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
        )

    def redo(self, canvas) -> None:
        self._apply(
            canvas,
            self.after_element,
            self.after_explicit_label,
            self.after_smiles_input,
            self.before_element,
            self.before_explicit_label,
            self.before_smiles_input,
        )


__all__ = [
    "AddSceneItemsCommand",
    "ChangeAtomLabelCommand",
    "DeleteSceneItemsCommand",
    "GroupSceneItemsCommand",
    "MoveItemsCommand",
    "UngroupSceneItemsCommand",
    "UpdateSceneItemCommand",
]
