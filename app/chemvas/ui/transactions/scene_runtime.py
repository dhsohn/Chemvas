from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, cast

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF, Qt
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from chemvas.domain.transactions import run_rollback_step
from chemvas.ui.annotations.items import NoteItem
from chemvas.ui.canvas.canvas_scene_items_state import (
    DOCUMENT_COLLECTION_STATES,
    SCENE_ITEM_COLLECTION_ATTRS,
)
from chemvas.ui.scene.note_item_access import NoteTextState

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPolygonF

_MISSING_SNAPSHOT_ATTRIBUTE = object()
_UNAVAILABLE_ITEM_VALUE = object()


def _snapshot_attribute(
    target: object,
    name: str,
) -> object:
    """Read an optional production capture field."""

    return getattr(target, name, _MISSING_SNAPSHOT_ATTRIBUTE)


def _snapshot_runtime_state_object(
    canvas,
    name: str,
) -> object | None:
    runtime_state = _snapshot_attribute(canvas, "runtime_state")
    if runtime_state is _MISSING_SNAPSHOT_ATTRIBUTE or runtime_state is None:
        return None
    state = _snapshot_attribute(runtime_state, name)
    return None if state is _MISSING_SNAPSHOT_ATTRIBUTE else state


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
        except Exception as error:
            errors.append(error)
            return default
    if original_error is None:
        return operation()
    return run_rollback_step(
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
        except Exception as error:
            errors.append(error)
            return default
    if original_error is not None:
        return run_rollback_step(
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
    items_method = _snapshot_attribute(scene, "items")
    if not callable(items_method):
        complete_scene_api = all(
            callable(_snapshot_attribute(scene, method_name))
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
class _CollectionAttributeSnapshot:
    owner: object
    attribute: str
    collection_object: list | dict
    contents: list | dict


@dataclass(slots=True)
class _MarkRegistrySnapshot:
    registry: Any
    mapping_object: dict
    entries: list[tuple[object, object, list | None]]


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

_GRAPHICS_ITEM_DIRECT_ATTRIBUTES = (
    "_hit_padding",
    "_hit_radius",
    "_raw_text",
    "_layout",
    "_typographic",
    "_anchor_element",
    "_anchor_at_end",
    "_stack",
    "_stack_element_rect",
    "_glyph_run",
)


def graphics_item_is_deleted(item: object) -> bool:
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
        if setter_name == "setDocumentTextOption":
            document = item.document()
            assert document is not None
            document.setDefaultTextOption(cast("QTextOption", value))
            return
        if setter_name == "setFont":
            item.setFont(cast("QFont", value))
            return
        if setter_name == "setDefaultTextColor":
            item.setDefaultTextColor(cast("QColor", value))
            return
        if setter_name == "setHtml":
            item.setHtml(cast("str", value))
            return
        if setter_name == "setTextInteractionFlags":
            item.setTextInteractionFlags(cast("Qt.TextInteractionFlag", value))
            return
    if isinstance(item, QGraphicsEllipseItem) and setter_name == "setRect":
        item.setRect(cast("QRectF", value))
        return
    if isinstance(item, QGraphicsPolygonItem) and setter_name == "setPolygon":
        item.setPolygon(cast("QPolygonF", value))
        return
    if isinstance(item, QAbstractGraphicsShapeItem):
        if setter_name == "setPen":
            item.setPen(cast("QPen", value))
            return
        if setter_name == "setBrush":
            item.setBrush(cast("QBrush", value))
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
    setter = _snapshot_attribute(item, setter_name)
    if not callable(setter):
        raise RuntimeError(f"primitive graphics restore cannot call {setter_name}")
    setter(value)


@dataclass(slots=True)
class BondPrimitiveGraphicsSnapshot:
    item: object
    properties: tuple[tuple[str, object], ...]
    direct_attributes: tuple[tuple[str, object], ...]
    note_text: NoteTextState | None = None

    @classmethod
    def capture(
        cls,
        item: object,
    ) -> BondPrimitiveGraphicsSnapshot | None:
        if graphics_item_is_deleted(item):
            return None
        note_text = NoteTextState.capture(item) if isinstance(item, NoteItem) else None
        properties: list[tuple[str, object]] = []
        for getter_name, setter_name in _BOND_PRIMITIVE_GRAPHICS_PROPERTIES:
            if note_text is not None and setter_name in {
                "setHtml",
                "setDefaultTextColor",
                "setTextInteractionFlags",
            }:
                continue
            getter = _snapshot_attribute(item, getter_name)
            setter = _snapshot_attribute(item, setter_name)
            if not callable(getter) or not callable(setter):
                continue
            value = getter()
            properties.append((setter_name, value))
        if isinstance(item, QGraphicsTextItem):
            document = item.document()
            assert document is not None
            properties.append(
                (
                    "setDocumentTextOption",
                    QTextOption(document.defaultTextOption()),
                )
            )
        direct_attribute_values: list[tuple[str, object]] = []
        for name in _GRAPHICS_ITEM_DIRECT_ATTRIBUTES:
            value = _snapshot_attribute(item, name)
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
            note_text=note_text,
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
            except Exception as exc:
                errors.append(exc)
        if self.note_text is not None:
            try:
                assert isinstance(self.item, QGraphicsTextItem)
                self.note_text.apply(self.item)
            except Exception as exc:
                errors.append(exc)
        if self.direct_attributes:
            try:
                if isinstance(self.item, QGraphicsItem):
                    self.item.prepareGeometryChange()
                for name, value in self.direct_attributes:
                    setattr(self.item, name, value)
            except Exception as exc:
                errors.append(exc)
        return errors


def _bond_primitive_graphics_snapshots(
    canvas,
    *,
    bond_ids: frozenset[int] | None = None,
) -> tuple[BondPrimitiveGraphicsSnapshot, ...]:
    state = _snapshot_runtime_state_object(
        canvas,
        "bond_graphics_state",
    )
    mapping = _snapshot_attribute(state, "bond_items")
    if not isinstance(mapping, dict):
        return ()
    snapshots: list[BondPrimitiveGraphicsSnapshot] = []
    seen: set[int] = set()
    for bond_id, items in mapping.items():
        if bond_ids is not None and bond_id not in bond_ids:
            continue
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            snapshot = BondPrimitiveGraphicsSnapshot.capture(
                item,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def capture_atom_primitive_graphics(
    canvas,
    *,
    atom_ids: frozenset[int] | None = None,
) -> tuple[BondPrimitiveGraphicsSnapshot, ...]:
    state = _snapshot_runtime_state_object(
        canvas,
        "atom_graphics_state",
    )
    mappings = (
        _snapshot_attribute(state, "atom_items"),
        _snapshot_attribute(state, "atom_dots"),
    )
    snapshots: list[BondPrimitiveGraphicsSnapshot] = []
    seen: set[int] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for atom_id, item in mapping.items():
            if atom_ids is not None and atom_id not in atom_ids:
                continue
            if item is None or id(item) in seen:
                continue
            seen.add(id(item))
            snapshot = BondPrimitiveGraphicsSnapshot.capture(
                item,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def restore_primitive_graphics(
    snapshots: tuple[BondPrimitiveGraphicsSnapshot, ...],
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


@dataclass(slots=True, kw_only=True)
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


@dataclass(slots=True, kw_only=True)
class SceneRuntimeSnapshot:
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
    collection_attributes: list[_CollectionAttributeSnapshot]
    mark_registry: _MarkRegistrySnapshot | None
    handle_state: Any | None
    handle_target: object | None
    selection_info_state: Any | None
    selection_info_values: dict[str, object]
    bond_primitive_graphics: tuple[BondPrimitiveGraphicsSnapshot, ...]


def _scene_item_topology_snapshots(
    items: list,
) -> list[_SceneItemTopologySnapshot]:
    """Capture every item's topology ports before any transaction mutation.

    Some lightweight test/dummy scene items expose read-only parent/z ports.
    They remain verifiable, but an attempted change is authoritative only when
    the matching capture-bound setter exists. Real QGraphicsItems expose both
    halves of each contract.
    """

    snapshots: list[_SceneItemTopologySnapshot] = []
    for item in items:
        if graphics_item_is_deleted(item):
            continue

        parent_getter: object = _base_graphics_item_port(item, "parentItem")
        parent_setter: object = _base_graphics_item_port(item, "setParentItem")
        if parent_getter is None:
            parent_getter = _snapshot_attribute(item, "parentItem")
        if parent_setter is None:
            parent_setter = _snapshot_attribute(item, "setParentItem")
        parent_ports_present = (
            parent_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
            or parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if parent_getter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(
            parent_getter
        ):
            raise RuntimeError(
                "live scene item does not expose a callable parent getter"
            )
        if parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(
            parent_setter
        ):
            raise RuntimeError(
                "live scene item does not expose a callable parent setter"
            )
        if callable(parent_getter):
            parent = parent_getter()
        elif parent_ports_present and parent_setter is not _MISSING_SNAPSHOT_ATTRIBUTE:
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
            z_getter = _snapshot_attribute(item, "zValue")
        if z_setter is None:
            z_setter = _snapshot_attribute(item, "setZValue")
        if stack_before is None:
            stack_before = _snapshot_attribute(item, "stackBefore")
        z_ports_present = (
            z_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
            or z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if z_getter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(z_getter):
            raise RuntimeError(
                "live scene item does not expose a callable stacking-depth getter"
            )
        if z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(z_setter):
            raise RuntimeError(
                "live scene item does not expose a callable stacking-depth setter"
            )
        if stack_before is not _MISSING_SNAPSHOT_ATTRIBUTE and not callable(
            stack_before
        ):
            raise RuntimeError(
                "live scene item does not expose a callable sibling-stacking setter"
            )
        if callable(z_getter):
            z_value = float(cast("Any", z_getter()))
        elif z_ports_present and z_setter is not _MISSING_SNAPSHOT_ATTRIBUTE:
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
                cast("QGraphicsItem.GraphicsItemFlag", flags_getter())
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


def _collection_attribute_snapshot(
    owner: object | None,
    attribute: str,
) -> _CollectionAttributeSnapshot | None:
    if owner is None:
        return None
    value = _snapshot_attribute(owner, attribute)
    if not isinstance(value, (list, dict)):
        return None
    return _CollectionAttributeSnapshot(owner, attribute, value, value.copy())


def _mark_registry_snapshot(
    registry: object | None,
) -> _MarkRegistrySnapshot | None:
    if registry is None:
        return None
    mapping = _snapshot_attribute(registry, "by_atom")
    if not isinstance(mapping, dict):
        return None
    entries: list[tuple[object, object, list | None]] = []
    for key, value in mapping.items():
        entries.append((key, value, list(value) if isinstance(value, list) else None))
    return _MarkRegistrySnapshot(registry, mapping, entries)


def _visibility_snapshots(
    items: list,
) -> list[_VisibilitySnapshot]:
    snapshots: list[_VisibilitySnapshot] = []
    for item in items:
        if graphics_item_is_deleted(item):
            continue
        data_method = _snapshot_attribute(item, "data")
        if not callable(data_method):
            continue
        kind = data_method(0)
        if kind not in {"note_box", "note_select"}:
            continue
        is_visible = _snapshot_attribute(item, "isVisible")
        if not callable(is_visible):
            continue
        visible = bool(is_visible())
        values: list[object] = []
        for method_name in ("rect", "pen", "brush"):
            method = _snapshot_attribute(item, method_name)
            value: object = _UNAVAILABLE_ITEM_VALUE
            if callable(method):
                value = method()
            values.append(value)
        snapshots.append(_VisibilitySnapshot(item, visible, *values))
    return snapshots


def capture_scene_runtime(
    canvas,
    *,
    scene_override: object = _MISSING_SNAPSHOT_ATTRIBUTE,
    detail_items: tuple[object, ...] | None = None,
    detail_bond_ids: frozenset[int] | None = None,
) -> SceneRuntimeSnapshot:
    """Capture the scene runtime authorities.

    ``detail_items``/``detail_bond_ids`` restrict the per-item detail
    snapshots (topology, selection, visibility, bond primitives) to a
    gesture's known mutation footprint. The full ordered scene-item identity
    list is always captured, so membership restore and identity verification
    stay whole-document. Callers own the completeness of the footprint; pass
    ``None`` (the default) for the whole-document capture.
    """
    scene: object | None
    if scene_override is not _MISSING_SNAPSHOT_ATTRIBUTE:
        scene = scene_override
    else:
        scene_method = _snapshot_attribute(canvas, "scene")
        if scene_method is _MISSING_SNAPSHOT_ATTRIBUTE or not callable(scene_method):
            scene = None
        else:
            scene = scene_method()
    scene_items, scene_items_getter = _scene_items_and_getter_from_scene(
        scene,
        strict=True,
    )
    scene_signals_blocked = None
    signals_blocked_getter = _snapshot_attribute(
        scene,
        "signalsBlocked",
    )
    block_signals_setter = _snapshot_attribute(
        scene,
        "blockSignals",
    )
    signal_ports_present = (
        signals_blocked_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
        or block_signals_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
    )
    if callable(signals_blocked_getter) and callable(block_signals_setter):
        scene_signals_blocked = bool(signals_blocked_getter())
    elif signal_ports_present:
        raise RuntimeError(
            "live scene does not expose a complete signal-blocking contract"
        )
    else:
        signals_blocked_getter = None
        block_signals_setter = None
    focus_item_getter = _snapshot_attribute(scene, "focusItem")
    focus_item_setter = _snapshot_attribute(scene, "setFocusItem")
    focus_item = None
    focus_ports_present = (
        focus_item_getter is not _MISSING_SNAPSHOT_ATTRIBUTE
        or focus_item_setter is not _MISSING_SNAPSHOT_ATTRIBUTE
    )
    if callable(focus_item_getter) and callable(focus_item_setter):
        focus_item = focus_item_getter()
    elif focus_ports_present:
        raise RuntimeError("live scene does not expose a complete focus contract")
    else:
        focus_item_getter = None
        focus_item_setter = None
    if detail_items is None:
        detail_scope_items = scene_items or []
    elif scene_items:
        # The detail contracts (topology/selection/visibility) are only
        # meaningful — and only strict-checked — for items that are actually
        # part of the captured scene, exactly like the whole-document loops
        # over ``scene_items``. Footprint entries that are not scene items
        # (stale registry references, lightweight test doubles) are skipped.
        detail_item_ids = {id(item) for item in detail_items}
        detail_scope_items = [
            item for item in scene_items if id(item) in detail_item_ids
        ]
    else:
        detail_scope_items = []
    topology_states = _scene_item_topology_snapshots(
        detail_scope_items,
    )
    selected_states: list[_SceneSelectionSnapshot] = []
    for item in detail_scope_items:
        if graphics_item_is_deleted(item):
            continue
        is_selected = _snapshot_attribute(item, "isSelected")
        set_selected = _snapshot_attribute(item, "setSelected")
        item_selection_access_present = (
            is_selected is not _MISSING_SNAPSHOT_ATTRIBUTE
            or set_selected is not _MISSING_SNAPSHOT_ATTRIBUTE
        )
        if callable(is_selected) and callable(set_selected):
            selected_states.append(
                _SceneSelectionSnapshot(
                    item=item,
                    selected=bool(is_selected()),
                    getter=is_selected,
                    setter=set_selected,
                )
            )
        elif item_selection_access_present:
            raise RuntimeError(
                "live scene item does not expose a complete selection contract"
            )

    collection_attributes: list[_CollectionAttributeSnapshot] = []
    scene_items_state = _snapshot_runtime_state_object(
        canvas,
        "scene_items_state",
    )
    for attribute in SCENE_ITEM_COLLECTION_ATTRS:
        snapshot = _collection_attribute_snapshot(
            scene_items_state,
            attribute,
        )
        if snapshot is not None:
            collection_attributes.append(snapshot)
    for name in DOCUMENT_COLLECTION_STATES.values():
        document = _snapshot_runtime_state_object(canvas, name)
        collection_attributes.extend(
            snapshot
            for attribute in ("order", "records")
            if (snapshot := _collection_attribute_snapshot(document, attribute))
            is not None
        )
    handle_state = _snapshot_runtime_state_object(
        canvas,
        "handle_state",
    )
    handle_snapshot = _collection_attribute_snapshot(
        handle_state,
        "active_handles",
    )
    if handle_snapshot is not None:
        collection_attributes.append(handle_snapshot)
    selection_state = _snapshot_runtime_state_object(
        canvas,
        "selection_state",
    )
    for attribute in ("outlines", "selected_notes"):
        snapshot = _collection_attribute_snapshot(selection_state, attribute)
        if snapshot is not None:
            collection_attributes.append(snapshot)

    selection_info_state = _snapshot_runtime_state_object(
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
            value = _snapshot_attribute(
                selection_info_state,
                attribute,
            )
            if value is _MISSING_SNAPSHOT_ATTRIBUTE:
                continue
            selection_info_values[attribute] = value

    handle_target = _snapshot_attribute(handle_state, "target")
    if handle_target is _MISSING_SNAPSHOT_ATTRIBUTE:
        handle_target = None

    return SceneRuntimeSnapshot(
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
            detail_scope_items,
        ),
        collection_attributes=collection_attributes,
        mark_registry=_mark_registry_snapshot(
            _snapshot_runtime_state_object(
                canvas,
                "mark_registry",
            ),
        ),
        handle_state=handle_state,
        handle_target=handle_target,
        selection_info_state=selection_info_state,
        selection_info_values=selection_info_values,
        bond_primitive_graphics=_bond_primitive_graphics_snapshots(
            canvas,
            bond_ids=detail_bond_ids,
        ),
    )
