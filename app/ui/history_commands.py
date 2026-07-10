from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from core.history import HistoryCommand
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsTextItem,
)

from ui.atom_coords_access import atom_coords_3d_for_id
from ui.atom_label_access import add_or_update_atom_label
from ui.canvas_group_state import (
    CanvasSceneGroup,
    group_state_for,
    register_group_for,
    remove_group_for,
    restore_group_for,
)
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.canvas_scene_items_state import SCENE_ITEM_COLLECTION_ATTRS
from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.canvas_state_lookup import canvas_state_object
from ui.history_canvas_access import (
    set_atom_positions_for_history as _set_atom_positions_for_history,
)
from ui.move_access import (
    move_item_for,
    refresh_selection_outline_for_canvas,
)
from ui.scene_item_access import (
    apply_scene_item_state as _apply_scene_item_state,
)
from ui.scene_item_access import (
    create_scene_item_from_state as _create_scene_item_from_state,
)
from ui.scene_item_access import (
    item_is_in_canvas_scene as _item_is_in_canvas_scene,
)
from ui.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from ui.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)
from ui.scene_item_state import scene_item_state_for


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


def _scene_items_snapshot(canvas) -> list | None:
    try:
        scene = canvas.scene()
    except (AttributeError, RuntimeError):
        return None
    items_method = getattr(scene, "items", None)
    if not callable(items_method):
        return None
    try:
        return list(items_method())
    except RuntimeError:
        return None


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
    ("line", "setLine"),
    ("path", "setPath"),
    ("polygon", "setPolygon"),
    ("rect", "setRect"),
    ("pen", "setPen"),
    ("brush", "setBrush"),
    ("font", "setFont"),
    ("defaultTextColor", "setDefaultTextColor"),
)

_ATOM_GRAPHICS_DIRECT_ATTRIBUTES = (
    "_hit_padding",
    "_hit_radius",
    "_layout",
    "_typographic",
    "_stack_element_rect",
)


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
    if isinstance(item, QGraphicsEllipseItem) and setter_name == "setRect":
        QGraphicsEllipseItem.setRect(item, cast(QRectF, value))
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
    }:
        setter = getattr(QGraphicsItem, setter_name)
        setter(item, value)
        return
    setter = getattr(item, setter_name, None)
    if callable(setter):
        setter(value)


@dataclass(slots=True)
class _BondPrimitiveGraphicsSnapshot:
    item: object
    properties: tuple[tuple[str, object], ...]
    direct_attributes: tuple[tuple[str, object], ...]

    @classmethod
    def capture(cls, item: object) -> _BondPrimitiveGraphicsSnapshot | None:
        properties: list[tuple[str, object]] = []
        for getter_name, setter_name in _BOND_PRIMITIVE_GRAPHICS_PROPERTIES:
            getter = getattr(item, getter_name, None)
            setter = getattr(item, setter_name, None)
            if not callable(getter) or not callable(setter):
                continue
            try:
                value = getter()
            except BaseException:
                continue
            properties.append((setter_name, value))
        direct_attributes = tuple(
            (name, getattr(item, name))
            for name in _ATOM_GRAPHICS_DIRECT_ATTRIBUTES
            if hasattr(item, name)
        )
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
) -> tuple[_BondPrimitiveGraphicsSnapshot, ...]:
    state = canvas_state_object(canvas, "bond_graphics_state")
    mapping = getattr(state, "bond_items", None)
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
            snapshot = _BondPrimitiveGraphicsSnapshot.capture(item)
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _atom_primitive_graphics_snapshots(
    canvas,
) -> tuple[_BondPrimitiveGraphicsSnapshot, ...]:
    state = canvas_state_object(canvas, "atom_graphics_state")
    mappings = (
        getattr(state, "atom_items", None),
        getattr(state, "atom_dots", None),
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
            snapshot = _BondPrimitiveGraphicsSnapshot.capture(item)
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
class _SceneRuntimeSnapshot:
    scene: object | None
    scene_items: list | None
    selected_states: list[tuple[object, bool]]
    visibility_states: list[_VisibilitySnapshot]
    selection_visuals: list[_SelectionVisualSnapshot]
    list_attributes: list[_ListAttributeSnapshot]
    mark_registry: _MarkRegistrySnapshot | None
    handle_state: Any | None
    handle_target: object | None
    selection_info_state: Any | None
    selection_info_values: dict[str, object]
    bond_primitive_graphics: tuple[_BondPrimitiveGraphicsSnapshot, ...]


def _list_attribute_snapshot(owner: object | None, attribute: str) -> _ListAttributeSnapshot | None:
    if owner is None:
        return None
    value = getattr(owner, attribute, None)
    if not isinstance(value, list):
        return None
    return _ListAttributeSnapshot(owner, attribute, value, list(value))


def _mark_registry_snapshot(registry: object | None) -> _MarkRegistrySnapshot | None:
    if registry is None:
        return None
    mapping = getattr(registry, "by_atom", None)
    if not isinstance(mapping, dict):
        return None
    entries: list[tuple[object, object, list | None]] = []
    for key, value in mapping.items():
        entries.append((key, value, list(value) if isinstance(value, list) else None))
    return _MarkRegistrySnapshot(registry, mapping, entries)


def _selection_visual_snapshots(items: list) -> list[_SelectionVisualSnapshot]:
    snapshots: list[_SelectionVisualSnapshot] = []
    pending = list(items)
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        child_items = getattr(item, "childItems", None)
        if callable(child_items):
            with contextlib.suppress(Exception):
                pending.extend(child_items())
        pen_method = getattr(item, "pen", None)
        data_method = getattr(item, "data", None)
        if not callable(pen_method):
            continue
        try:
            pen = pen_method()
            data_6 = data_method(6) if callable(data_method) else _UNAVAILABLE_ITEM_VALUE
        except Exception:
            continue
        snapshots.append(_SelectionVisualSnapshot(item, pen, data_6))
    return snapshots


def _visibility_snapshots(items: list) -> list[_VisibilitySnapshot]:
    snapshots: list[_VisibilitySnapshot] = []
    for item in items:
        data_method = getattr(item, "data", None)
        if not callable(data_method):
            continue
        try:
            kind = data_method(0)
        except RuntimeError:
            continue
        if kind not in {"note_box", "note_select"}:
            continue
        is_visible = getattr(item, "isVisible", None)
        if not callable(is_visible):
            continue
        try:
            visible = bool(is_visible())
        except RuntimeError:
            continue
        values: list[object] = []
        for method_name in ("rect", "pen", "brush"):
            method = getattr(item, method_name, None)
            value: object = _UNAVAILABLE_ITEM_VALUE
            if callable(method):
                with contextlib.suppress(Exception):
                    value = method()
            values.append(value)
        snapshots.append(_VisibilitySnapshot(item, visible, *values))
    return snapshots


def _scene_runtime_snapshot(canvas) -> _SceneRuntimeSnapshot:
    scene: object | None
    try:
        scene = canvas.scene()
    except (AttributeError, RuntimeError):
        scene = None
    scene_items = _scene_items_snapshot(canvas)
    selected_states: list[tuple[object, bool]] = []
    for item in scene_items or ():
        is_selected = getattr(item, "isSelected", None)
        if not callable(is_selected):
            continue
        try:
            selected_states.append((item, bool(is_selected())))
        except RuntimeError:
            continue

    list_attributes: list[_ListAttributeSnapshot] = []
    scene_items_state = canvas_state_object(canvas, "scene_items_state")
    for attribute in SCENE_ITEM_COLLECTION_ATTRS:
        snapshot = _list_attribute_snapshot(scene_items_state, attribute)
        if snapshot is not None:
            list_attributes.append(snapshot)
    handle_state = canvas_state_object(canvas, "handle_state")
    handle_snapshot = _list_attribute_snapshot(handle_state, "active_handles")
    if handle_snapshot is not None:
        list_attributes.append(handle_snapshot)
    selection_style_state = canvas_state_object(canvas, "selection_style_state")
    selected_items_snapshot = _list_attribute_snapshot(selection_style_state, "selected_items")
    selection_visuals = _selection_visual_snapshots(
        selected_items_snapshot.contents if selected_items_snapshot is not None else []
    )
    if selected_items_snapshot is not None:
        list_attributes.append(selected_items_snapshot)
    selection_outline_state = canvas_state_object(canvas, "selection_outline_state")
    outlines_snapshot = _list_attribute_snapshot(selection_outline_state, "outlines")
    if outlines_snapshot is not None:
        list_attributes.append(outlines_snapshot)

    selection_info_state = canvas_state_object(canvas, "selection_info_state")
    selection_info_values: dict[str, object] = {}
    if selection_info_state is not None:
        for attribute in (
            "signature",
            "pending_signature",
            "cache",
            "rdkit_warmup_pending",
            "last_interaction_time",
        ):
            if hasattr(selection_info_state, attribute):
                selection_info_values[attribute] = getattr(selection_info_state, attribute)

    return _SceneRuntimeSnapshot(
        scene=scene,
        scene_items=scene_items,
        selected_states=selected_states,
        visibility_states=_visibility_snapshots(scene_items or []),
        selection_visuals=selection_visuals,
        list_attributes=list_attributes,
        mark_registry=_mark_registry_snapshot(canvas_state_object(canvas, "mark_registry")),
        handle_state=handle_state,
        handle_target=getattr(handle_state, "target", None),
        selection_info_state=selection_info_state,
        selection_info_values=selection_info_values,
        bond_primitive_graphics=_bond_primitive_graphics_snapshots(canvas),
    )


def _item_parent(item):
    parent_method = getattr(item, "parentItem", None)
    if not callable(parent_method):
        return None
    try:
        return parent_method()
    except RuntimeError:
        return None


def _item_z_value(item) -> float | None:
    z_method = getattr(item, "zValue", None)
    if not callable(z_method):
        return None
    try:
        return float(z_method())
    except (RuntimeError, TypeError, ValueError):
        return None


def _direct_scene_remove(scene, item) -> bool:
    remove_item = getattr(scene, "removeItem", None)
    if callable(remove_item):
        try:
            remove_item(item)
            return True
        except RuntimeError:
            return False
    detach = getattr(scene, "detach", None)
    if callable(detach):
        try:
            detach(item)
            return True
        except RuntimeError:
            return False
    return False


def _direct_scene_add(scene, item) -> bool:
    add_item = getattr(scene, "addItem", None)
    if callable(add_item):
        try:
            add_item(item)
            return True
        except RuntimeError:
            return False
    attach = getattr(scene, "attach", None)
    if callable(attach):
        try:
            attach(item)
            return True
        except RuntimeError:
            return False
    return False


def _item_is_attached_to_scene(scene, item) -> bool:
    scene_method = getattr(item, "scene", None)
    if not callable(scene_method):
        return False
    try:
        return scene_method() is scene
    except RuntimeError:
        return False


def _restore_scene_stacking(scene_items: list) -> None:
    sibling_groups: dict[tuple[int, float], list] = {}
    for item in scene_items:
        z_value = _item_z_value(item)
        if z_value is None:
            continue
        sibling_groups.setdefault((id(_item_parent(item)), z_value), []).append(item)
    for siblings in sibling_groups.values():
        for higher, lower in zip(siblings, siblings[1:], strict=False):
            stack_before = getattr(lower, "stackBefore", None)
            if not callable(stack_before):
                continue
            with contextlib.suppress(Exception):
                stack_before(higher)


def _restore_scene_contents(snapshot: _SceneRuntimeSnapshot) -> None:
    scene = snapshot.scene
    before = snapshot.scene_items
    if scene is None or before is None:
        return
    current_items_method = getattr(scene, "items", None)
    if not callable(current_items_method):
        return
    try:
        current = list(current_items_method())
    except RuntimeError:
        return

    block_signals = getattr(scene, "blockSignals", None)
    previous_blocked: object = False
    if callable(block_signals):
        with contextlib.suppress(Exception):
            previous_blocked = block_signals(True)

    try:
        before_ids = {id(item) for item in before}
        added = [item for item in current if id(item) not in before_ids]
        added_ids = {id(item) for item in added}
        for item in added:
            parent = _item_parent(item)
            if parent is not None and id(parent) in added_ids:
                continue
            _direct_scene_remove(scene, item)

        # Add roots before their children. Reverse the scene's top-to-bottom order
        # because newly added equal-z siblings stack above existing siblings.
        for item in reversed(before):
            if _item_is_attached_to_scene(scene, item):
                continue
            parent = _item_parent(item)
            if parent is not None and id(parent) in before_ids:
                continue
            _direct_scene_add(scene, item)
        for item in reversed(before):
            if not _item_is_attached_to_scene(scene, item):
                _direct_scene_add(scene, item)

        _restore_scene_stacking(before)

        for item, selected in snapshot.selected_states:
            set_selected = getattr(item, "setSelected", None)
            if not callable(set_selected) or not _item_is_attached_to_scene(scene, item):
                continue
            with contextlib.suppress(Exception):
                set_selected(selected)
    finally:
        if callable(block_signals):
            with contextlib.suppress(Exception):
                block_signals(bool(previous_blocked))


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
    set_pen = getattr(snapshot.item, "setPen", None)
    if callable(set_pen):
        set_pen(snapshot.pen)
    if snapshot.data_6 is _UNAVAILABLE_ITEM_VALUE:
        return
    set_data = getattr(snapshot.item, "setData", None)
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
        method = getattr(snapshot.item, method_name, None)
        if callable(method):
            method(value)
    set_visible = getattr(snapshot.item, "setVisible", None)
    if callable(set_visible):
        set_visible(snapshot.visible)


def _restore_scene_runtime_snapshot(snapshot: _SceneRuntimeSnapshot) -> None:
    try:
        _restore_scene_contents(snapshot)
        for list_snapshot in snapshot.list_attributes:
            with contextlib.suppress(Exception):
                _restore_list_attribute(list_snapshot)
        if snapshot.mark_registry is not None:
            with contextlib.suppress(Exception):
                _restore_mark_registry(snapshot.mark_registry)
        for visibility_snapshot in snapshot.visibility_states:
            with contextlib.suppress(Exception):
                _restore_visibility(visibility_snapshot)
        for visual_snapshot in snapshot.selection_visuals:
            with contextlib.suppress(Exception):
                _restore_selection_visual(visual_snapshot)
        if snapshot.handle_state is not None:
            with contextlib.suppress(Exception):
                snapshot.handle_state.target = snapshot.handle_target
        if snapshot.selection_info_state is not None:
            for attribute, value in snapshot.selection_info_values.items():
                with contextlib.suppress(Exception):
                    setattr(snapshot.selection_info_state, attribute, value)
    finally:
        # Ring attach/remove callbacks refresh surviving bond primitives in
        # place and can fail after a partial mutation. The exact raw graphics
        # savepoint must be the final restore phase, including when lifecycle
        # compensation itself invokes the same persistently failing callback.
        _restore_bond_primitive_graphics_snapshots(
            snapshot.bond_primitive_graphics
        )


def _restore_scene_item_memberships(
    canvas,
    attempted: list[tuple[object, bool | None]],
    *,
    unknown_was_attached: bool,
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
        with contextlib.suppress(Exception):
            _remove_scene_item(canvas, item)
    for item, should_be_attached in desired_memberships:
        if not should_be_attached:
            continue
        with contextlib.suppress(Exception):
            _restore_scene_item(canvas, item)


def _mutate_existing_scene_items_atomically(
    canvas,
    items: list,
    operation: Callable[[Any, Any], None],
    *,
    unknown_was_attached: bool,
) -> None:
    runtime_snapshot = _scene_runtime_snapshot(canvas)
    snapshots = [
        (item, _scene_item_membership(canvas, item))
        for item in items
        if item is not None
    ]
    attempted: list[tuple[object, bool | None]] = []
    try:
        for snapshot in snapshots:
            attempted.append(snapshot)
            operation(canvas, snapshot[0])
    except Exception:
        _restore_scene_item_memberships(
            canvas,
            attempted,
            unknown_was_attached=unknown_was_attached,
        )
        _restore_scene_runtime_snapshot(runtime_snapshot)
        raise


def _create_scene_items_atomically(canvas, states: list[dict], items: list) -> None:
    original_items = list(items)
    runtime_snapshot = _scene_runtime_snapshot(canvas)
    scene_before = _scene_items_snapshot(canvas)
    created: list = []
    try:
        for state in states:
            item = _create_scene_item_from_state(canvas, state)
            items.append(item)
            if item is not None:
                created.append(item)
    except Exception:
        created.extend(_new_top_level_scene_items(canvas, scene_before))
        seen: set[int] = set()
        for item in reversed(created):
            if id(item) in seen:
                continue
            seen.add(id(item))
            with contextlib.suppress(Exception):
                _remove_scene_item(canvas, item)
        items[:] = original_items
        _restore_scene_runtime_snapshot(runtime_snapshot)
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


def _restore_active_handle_positions(snapshots: list[tuple[object, object]]) -> None:
    for handle, position in snapshots:
        set_position = getattr(handle, "setPos", None)
        if not callable(set_position):
            continue
        with contextlib.suppress(Exception):
            set_position(position)


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


def _restore_raw_move_item_state(snapshot: _MoveItemSnapshot) -> bool:
    restored = False
    if snapshot.position is not _UNAVAILABLE_ITEM_VALUE:
        set_position = getattr(snapshot.item, "setPos", None)
        if callable(set_position):
            try:
                set_position(snapshot.position)
                restored = True
            except Exception:
                pass

    set_data = getattr(snapshot.item, "setData", None)
    if not callable(set_data):
        return restored
    for index, value in ((1, snapshot.data_1), (2, snapshot.data_2)):
        if value is _UNAVAILABLE_ITEM_VALUE:
            continue
        try:
            set_data(index, value)
            restored = True
        except Exception:
            pass
    return restored


@dataclass
class MoveItemsCommand(HistoryCommand):
    items: list
    dx: float
    dy: float

    def _apply(self, canvas, dx: float, dy: float) -> None:
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        snapshots = [
            _move_item_snapshot(canvas, item)
            for item in self.items
            if item is not None and _item_is_in_canvas_scene(canvas, item)
        ]
        handle_snapshots = _active_handle_position_snapshots(canvas)
        attempted: list[_MoveItemSnapshot] = []
        try:
            for snapshot in snapshots:
                attempted.append(snapshot)
                move_item_for(canvas, snapshot.item, dx, dy, update_selection=False)
            refresh_selection_outline_for_canvas(canvas)
        except Exception:
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
                with contextlib.suppress(Exception):
                    _set_atom_positions_for_history(
                        canvas,
                        atom_positions,
                        update_selection=False,
                        coords_3d=atom_coords_3d or None,
                    )
            for snapshot in reversed(attempted):
                raw_restored = _restore_raw_move_item_state(snapshot)
                if snapshot.state:
                    try:
                        _apply_scene_item_state(canvas, snapshot.item, snapshot.state)
                        continue
                    except Exception:
                        # Canonical apply can mutate before raising. Reapply the
                        # raw savepoint last so its partial state cannot leak.
                        raw_restored = _restore_raw_move_item_state(snapshot) or raw_restored
                if raw_restored:
                    continue
                with contextlib.suppress(Exception):
                    move_item_for(
                        canvas,
                        snapshot.item,
                        -dx,
                        -dy,
                        update_selection=False,
                    )
            _restore_active_handle_positions(handle_snapshots)
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            # Selection refresh removes the old outline objects before it
            # creates their replacements. A persistent rebuild failure can
            # therefore leave partial outlines even after the moved model and
            # graphics have been compensated. Make the exact pre-command
            # scene/runtime savepoint authoritative last.
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, -self.dx, -self.dy)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.dx, self.dy)


@dataclass
class UpdateSceneItemCommand(HistoryCommand):
    item: object
    before_state: dict
    after_state: dict

    def _apply(self, canvas, state: dict, rollback_state: dict) -> None:
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        try:
            _apply_scene_item_state(canvas, self.item, state)
            refresh_selection_outline_for_canvas(canvas)
        except Exception:
            with contextlib.suppress(Exception):
                _apply_scene_item_state(canvas, self.item, rollback_state)
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            # Outline refresh clears the old scene items before rebuilding. If
            # that rebuild raises, applying the item state back is insufficient:
            # restore the exact pre-command outline membership/list identity and
            # other selection runtime state as well.
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise

    def undo(self, canvas) -> None:
        self._apply(canvas, self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        self._apply(canvas, self.after_state, self.before_state)


@dataclass
class AddSceneItemsCommand(HistoryCommand):
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
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        previous_group_id = self.group_id
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
        except Exception:
            _restore_group_state(snapshot)
            self.group_id = previous_group_id
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        try:
            if self.group_id is not None:
                remove_group_for(canvas, self.group_id)
            for absorbed_id, group in self.absorbed:
                restore_group_for(canvas, absorbed_id, group)
            refresh_selection_outline_for_canvas(canvas)
        except Exception:
            _restore_group_state(snapshot)
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise


@dataclass
class UngroupSceneItemsCommand(HistoryCommand):
    removed: list[tuple[int, CanvasSceneGroup]]

    def redo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        try:
            for group_id, _ in self.removed:
                remove_group_for(canvas, group_id)
            refresh_selection_outline_for_canvas(canvas)
        except Exception:
            _restore_group_state(snapshot)
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise

    def undo(self, canvas) -> None:
        snapshot = _group_state_snapshot(canvas)
        runtime_snapshot = _scene_runtime_snapshot(canvas)
        try:
            for group_id, group in self.removed:
                restore_group_for(canvas, group_id, group)
            refresh_selection_outline_for_canvas(canvas)
        except Exception:
            _restore_group_state(snapshot)
            with contextlib.suppress(Exception):
                refresh_selection_outline_for_canvas(canvas)
            with contextlib.suppress(Exception):
                _restore_scene_runtime_snapshot(runtime_snapshot)
            raise


@dataclass
class ChangeAtomLabelCommand(HistoryCommand):
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
        except Exception:
            with contextlib.suppress(Exception):
                add_or_update_atom_label(
                    canvas,
                    self.atom_id,
                    rollback_element,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=rollback_explicit_label,
                )
            with contextlib.suppress(Exception):
                set_last_smiles_input_for(canvas, rollback_smiles_input)
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
