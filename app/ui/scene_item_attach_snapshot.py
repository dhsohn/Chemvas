from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, cast

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
)

from ui.canvas_mark_registry import CanvasMarkRegistry, mark_registry_for
from ui.canvas_scene_items_state import CanvasSceneItemsState, scene_items_state_for
from ui.history_commands import (
    _restore_scene_runtime_snapshot,
    _run_rollback_step,
    _scene_runtime_snapshot,
    _SceneRuntimeSnapshot,
    _verify_scene_runtime_identity,
)
from ui.scene_item_access import (
    item_is_unavailable_for_scene_operation,
    remove_attached_item_from_scene,
)
from ui.scene_item_state import ARROW_KINDS
from ui.scene_rect_snapshot import SceneRectSnapshot, scene_rect_is_automatic

_KIND_COLLECTION = {
    "ring": "ring_items",
    "mark": "mark_items",
    "note": "note_items",
    "ts_bracket": "ts_bracket_items",
    "shape": "shape_items",
    "orbital": "orbital_items",
    **{kind: "arrow_items" for kind in ARROW_KINDS},
}
_UNAVAILABLE = object()
_QT_BASE_ITEM_CHANGE = inspect.getattr_static(QGraphicsItem, "itemChange")


def _qt_base_port(target: object, owner: type, name: str) -> object:
    if not isinstance(target, owner):
        return _UNAVAILABLE
    port = getattr(owner, name, None)
    if not callable(port):
        return _UNAVAILABLE
    return partial(port, target)


def _item_has_custom_change_callback(item: object) -> bool:
    implementation = inspect.getattr_static(
        type(item),
        "itemChange",
        _UNAVAILABLE,
    )
    if isinstance(item, QGraphicsItem):
        return implementation is not _QT_BASE_ITEM_CHANGE
    return implementation is not _UNAVAILABLE


def _capture_optional_attribute(target: object, name: str) -> object:
    try:
        return getattr(target, name)
    except AttributeError:
        if inspect.getattr_static(target, name, _UNAVAILABLE) is not _UNAVAILABLE:
            raise
        return _UNAVAILABLE


@dataclass(slots=True)
class _AttachRawContainer:
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
                actual_value is expected_value
                for actual_value, expected_value in zip(
                    actual,
                    self.contents,
                    strict=True,
                )
            )
        else:
            exact = {id(value) for value in cast(set, self.target)} == {
                id(value) for value in self.contents
            }
        if not exact:
            raise RuntimeError("attach capture changed a raw container")


@dataclass(slots=True)
class _AttachRawNamespace:
    target: object
    namespace: dict[str, object] | None
    items: tuple[tuple[str, object], ...]

    def restore(self) -> None:
        if self.namespace is None:
            return
        dict.clear(self.namespace)
        dict.update(self.namespace, self.items)

    def verify(self) -> None:
        if self.namespace is None:
            return
        actual = tuple(self.namespace.items())
        if len(actual) != len(self.items) or any(
            actual_key != expected_key or actual_value is not expected_value
            for (actual_key, actual_value), (
                expected_key,
                expected_value,
            ) in zip(actual, self.items, strict=True)
        ):
            raise RuntimeError("attach capture changed a raw namespace")


@dataclass(slots=True)
class _QtAttachValue:
    name: str
    getter: Callable[[], object]
    setter: Callable[[object], object]
    value: object

    def restore(self) -> None:
        self.setter(self.value)

    def verify(self) -> None:
        actual = self.getter()
        try:
            exact = actual == self.value
        except BaseException:
            exact = actual is self.value
        if not exact:
            raise RuntimeError(f"attach capture changed Qt primitive {self.name}")


@dataclass(slots=True)
class _AttachCaptureAuthority:
    item: object
    target_scene: object | None
    raw_namespaces: tuple[_AttachRawNamespace, ...]
    raw_containers: tuple[_AttachRawContainer, ...]
    qt_values: tuple[_QtAttachValue, ...]
    qt_scene: QGraphicsScene | None
    qt_parent: QGraphicsItem | None
    qt_focus: tuple[tuple[QGraphicsScene, QGraphicsItem | None], ...]
    qt_signals: tuple[tuple[QGraphicsScene, bool], ...]

    @classmethod
    def capture(
        cls,
        scene: object | None,
        item: object,
    ) -> _AttachCaptureAuthority:
        containers: list[_AttachRawContainer] = []
        container_ids: set[int] = set()

        def capture_container(value: object) -> None:
            if type(value) is dict:
                if id(value) in container_ids:
                    return
                container_ids.add(id(value))
                contents = tuple(cast(dict, value).items())
                containers.append(_AttachRawContainer(value, "dict", contents))
                for key, child in contents:
                    capture_container(key)
                    capture_container(child)
            elif type(value) in {list, set}:
                if id(value) in container_ids:
                    return
                container_ids.add(id(value))
                member_contents: tuple[object, ...] = tuple(cast(Any, value))
                containers.append(
                    _AttachRawContainer(
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

        namespaces: list[_AttachRawNamespace] = []
        for target in (item, scene):
            if target is None:
                continue
            try:
                namespace_value = object.__getattribute__(target, "__dict__")
            except (AttributeError, TypeError):
                namespace = None
                items: tuple[tuple[str, object], ...] = ()
            else:
                namespace = (
                    namespace_value if isinstance(namespace_value, dict) else None
                )
                items = (
                    tuple(
                        (key, dict.__getitem__(namespace, key))
                        for key in tuple(dict.__iter__(namespace))
                    )
                    if namespace is not None
                    else ()
                )
                for _key, value in items:
                    capture_container(value)
            namespaces.append(_AttachRawNamespace(target, namespace, items))

        qt_values: list[_QtAttachValue] = []

        def capture_qt_value(owner: type, getter_name: str, setter_name: str) -> None:
            if not isinstance(item, owner):
                return
            getter = getattr(owner, getter_name)
            setter = getattr(owner, setter_name)
            bound_getter = partial(getter, item)
            qt_values.append(
                _QtAttachValue(
                    getter_name,
                    bound_getter,
                    partial(setter, item),
                    bound_getter(),
                )
            )

        if isinstance(item, QGraphicsItem):
            for getter_name, setter_name in (
                ("flags", "setFlags"),
                ("pos", "setPos"),
                ("transform", "setTransform"),
                ("transformOriginPoint", "setTransformOriginPoint"),
                ("rotation", "setRotation"),
                ("scale", "setScale"),
                ("opacity", "setOpacity"),
                ("zValue", "setZValue"),
                ("isVisible", "setVisible"),
                ("isEnabled", "setEnabled"),
                ("isSelected", "setSelected"),
            ):
                capture_qt_value(QGraphicsItem, getter_name, setter_name)
            for role in (0, 1, 2, 6, 9, 20, 21, 22):
                getter = partial(QGraphicsItem.data, item, role)
                qt_values.append(
                    _QtAttachValue(
                        f"data({role})",
                        getter,
                        partial(QGraphicsItem.setData, item, role),
                        getter(),
                    )
                )
        for owner, properties in (
            (
                QAbstractGraphicsShapeItem,
                (("pen", "setPen"), ("brush", "setBrush")),
            ),
            (QGraphicsRectItem, (("rect", "setRect"),)),
            (QGraphicsEllipseItem, (("rect", "setRect"),)),
            (QGraphicsLineItem, (("line", "setLine"),)),
            (QGraphicsPathItem, (("path", "setPath"),)),
            (QGraphicsPolygonItem, (("polygon", "setPolygon"),)),
            (
                QGraphicsPixmapItem,
                (
                    ("pixmap", "setPixmap"),
                    ("offset", "setOffset"),
                    ("transformationMode", "setTransformationMode"),
                    ("shapeMode", "setShapeMode"),
                ),
            ),
            (
                QGraphicsTextItem,
                (
                    ("toHtml", "setHtml"),
                    ("font", "setFont"),
                    ("defaultTextColor", "setDefaultTextColor"),
                    ("textWidth", "setTextWidth"),
                    ("textInteractionFlags", "setTextInteractionFlags"),
                ),
            ),
            (
                QGraphicsSimpleTextItem,
                (("text", "setText"), ("font", "setFont")),
            ),
        ):
            for getter_name, setter_name in properties:
                capture_qt_value(owner, getter_name, setter_name)

        qt_scene = QGraphicsItem.scene(item) if isinstance(item, QGraphicsItem) else None
        qt_parent = (
            QGraphicsItem.parentItem(item)
            if isinstance(item, QGraphicsItem)
            else None
        )
        focus_scenes: list[QGraphicsScene] = []
        for candidate in (qt_scene, scene):
            if isinstance(candidate, QGraphicsScene) and all(
                candidate is not existing for existing in focus_scenes
            ):
                focus_scenes.append(candidate)
        return cls(
            item=item,
            target_scene=scene,
            raw_namespaces=tuple(namespaces),
            raw_containers=tuple(containers),
            qt_values=tuple(qt_values),
            qt_scene=qt_scene,
            qt_parent=qt_parent,
            qt_focus=tuple(
                (candidate, QGraphicsScene.focusItem(candidate))
                for candidate in focus_scenes
            ),
            qt_signals=tuple(
                (candidate, bool(QObject.signalsBlocked(candidate)))
                for candidate in focus_scenes
            ),
        )

    def _restore_once(self) -> None:
        for raw_namespace in self.raw_namespaces:
            raw_namespace.restore()
        for raw_container in self.raw_containers:
            raw_container.restore()
        if isinstance(self.item, QGraphicsItem):
            current_scene = QGraphicsItem.scene(self.item)
            if current_scene is not self.qt_scene:
                if isinstance(current_scene, QGraphicsScene):
                    QGraphicsScene.removeItem(current_scene, self.item)
                if self.qt_parent is not None:
                    QGraphicsItem.setParentItem(self.item, self.qt_parent)
                elif isinstance(self.qt_scene, QGraphicsScene):
                    QGraphicsScene.addItem(self.qt_scene, self.item)
            elif QGraphicsItem.parentItem(self.item) is not self.qt_parent:
                QGraphicsItem.setParentItem(self.item, self.qt_parent)
        for value in self.qt_values:
            value.restore()
        for focus_scene, focus in self.qt_focus:
            QGraphicsScene.setFocusItem(focus_scene, focus)
        for raw_namespace in self.raw_namespaces:
            raw_namespace.restore()
        for raw_container in self.raw_containers:
            raw_container.restore()

    def _verify(self) -> None:
        for raw_namespace in self.raw_namespaces:
            raw_namespace.verify()
        for raw_container in self.raw_containers:
            raw_container.verify()
        if isinstance(self.item, QGraphicsItem):
            if QGraphicsItem.scene(self.item) is not self.qt_scene:
                raise RuntimeError("attach capture changed item scene membership")
            if QGraphicsItem.parentItem(self.item) is not self.qt_parent:
                raise RuntimeError("attach capture changed item parent")
        for value in self.qt_values:
            value.verify()
        for focus_scene, focus in self.qt_focus:
            if QGraphicsScene.focusItem(focus_scene) is not focus:
                raise RuntimeError("attach capture changed scene focus")
        for signal_scene, blocked in self.qt_signals:
            if bool(QObject.signalsBlocked(signal_scene)) is not blocked:
                raise RuntimeError("attach capture changed scene signal state")

    def restore(self, original_error: BaseException) -> None:
        recorded: list[BaseException] = []
        for _attempt in range(2):
            errors: list[BaseException] = []
            try:
                for signal_scene, _blocked in self.qt_signals:
                    QObject.blockSignals(signal_scene, True)
                self._restore_once()
            except BaseException as error:
                errors.append(error)
            finally:
                for signal_scene, blocked in self.qt_signals:
                    try:
                        QObject.blockSignals(signal_scene, blocked)
                    except BaseException as error:
                        errors.append(error)
            try:
                self._verify()
            except BaseException as error:
                errors.append(error)
            if not errors:
                return
            recorded.extend(errors)
        for recorded_error in recorded:
            try:
                add_note = getattr(original_error, "add_note", None)
                if callable(add_note):
                    add_note(
                        "Attach port capture recovery also failed with "
                        f"{type(recorded_error).__name__}: {recorded_error}"
                    )
            except BaseException:
                continue


def _requires_full_graph_snapshot(
    *,
    item: object,
    attach_ports: SceneItemAttachPorts,
    collection_owner: object,
    collection_name: str | None,
    collection: list | None,
    mark_registry: object | None,
    mark_mapping: dict | None,
    mark_entry_existed: bool,
    mark_list: list | None,
) -> bool:
    if (
        attach_ports.requires_authoritative_scene_bounds
        or attach_ports.requires_full_graph_snapshot
    ):
        return True
    if _item_has_custom_change_callback(item):
        return True
    if collection_name is not None and (
        type(collection_owner) is not CanvasSceneItemsState
        or type(collection) is not list
    ):
        return True
    if mark_registry is None:
        return False
    return (
        type(mark_registry) is not CanvasMarkRegistry
        or type(mark_mapping) is not dict
        or (mark_entry_existed and type(mark_list) is not list)
    )


class _AttachRuntimeSceneCaptureProxy:
    """Feed already-bound scene roots into the shared runtime capturer."""

    __slots__ = ("_focus_capture_pending", "_ports", "_scene")

    def __init__(self, scene: object, ports: SceneItemAttachPorts) -> None:
        self._scene = scene
        self._ports = ports
        self._focus_capture_pending = True

    def _bound_focus_item(self) -> object:
        if self._focus_capture_pending:
            self._focus_capture_pending = False
            return self._ports.focus_item
        getter = self._ports.focus_item_getter
        if getter is None:
            return None
        return getter()

    def __getattr__(self, name: str) -> object:
        if name == "items" and self._ports.scene_items_getter is not None:
            return self._ports.scene_items_getter
        if name == "focusItem" and self._ports.focus_item_getter is not None:
            return self._bound_focus_item
        if name == "setFocusItem" and self._ports.focus_item_setter is not None:
            return self._ports.focus_item_setter
        return getattr(self._scene, name)


def _capture_full_scene_runtime(
    canvas: object,
    scene: object,
    attach_ports: SceneItemAttachPorts,
) -> _SceneRuntimeSnapshot:
    snapshot = _scene_runtime_snapshot(
        canvas,
        strict=True,
        scene_override=_AttachRuntimeSceneCaptureProxy(scene, attach_ports),
    )
    snapshot.scene = scene
    return snapshot


@dataclass(frozen=True, slots=True)
class SceneItemAttachPorts:
    scene: object | None
    item_scene_getter: Callable[[], object] | None
    initial_item_scene: object | None
    item_scene_available: bool
    item_data_getter: Callable[[int], object] | None
    item_kind: object
    item_metadata: object
    scene_add_item: Callable[[object], object] | None
    scene_remove_item: Callable[[object], object] | None
    scene_items_getter: Callable[[], object] | None
    scene_items_bounding_rect_getter: Callable[[], object] | None
    scene_rect_getter: Callable[[], object] | None
    scene_rect_setter: Callable[[object], object] | None
    requires_authoritative_scene_bounds: bool
    requires_full_graph_snapshot: bool
    item_flags: object
    item_flags_getter: Callable[[], object] | None
    item_flags_setter: Callable[[object], object] | None
    text_interaction_flags: object
    text_interaction_flags_getter: Callable[[], object] | None
    text_interaction_flags_setter: Callable[[object], object] | None
    scene_bounding_rect_getter: Callable[[], object] | None
    focus_item: object | None
    focus_item_getter: Callable[[], object] | None
    focus_item_setter: Callable[[object | None], object] | None

    @classmethod
    def _unavailable(
        cls,
        scene: object | None,
        item_scene_getter: Callable[[], object] | None = None,
    ) -> SceneItemAttachPorts:
        return cls(
            scene=scene,
            item_scene_getter=item_scene_getter,
            initial_item_scene=None,
            item_scene_available=False,
            item_data_getter=None,
            item_kind=_UNAVAILABLE,
            item_metadata=_UNAVAILABLE,
            scene_add_item=None,
            scene_remove_item=None,
            scene_items_getter=None,
            scene_items_bounding_rect_getter=None,
            scene_rect_getter=None,
            scene_rect_setter=None,
            requires_authoritative_scene_bounds=False,
            requires_full_graph_snapshot=False,
            item_flags=_UNAVAILABLE,
            item_flags_getter=None,
            item_flags_setter=None,
            text_interaction_flags=_UNAVAILABLE,
            text_interaction_flags_getter=None,
            text_interaction_flags_setter=None,
            scene_bounding_rect_getter=None,
            focus_item=None,
            focus_item_getter=None,
            focus_item_setter=None,
        )

    @classmethod
    def capture(cls, scene: object | None, item: object) -> SceneItemAttachPorts:
        if item_is_unavailable_for_scene_operation(item):
            return cls._unavailable(scene)
        authority = _AttachCaptureAuthority.capture(scene, item)
        try:
            return cls._capture_live(scene, item)
        except BaseException as original_error:
            authority.restore(original_error)
            raise

    @classmethod
    def _capture_live(
        cls,
        scene: object | None,
        item: object,
    ) -> SceneItemAttachPorts:
        if item_is_unavailable_for_scene_operation(item):
            return cls._unavailable(scene)
        qt_item = isinstance(item, QGraphicsItem)
        item_scene_port = _qt_base_port(item, QGraphicsItem, "scene")
        if item_scene_port is _UNAVAILABLE:
            item_scene_port = _capture_optional_attribute(item, "scene")
        item_scene_getter = item_scene_port if callable(item_scene_port) else None
        initial_item_scene = None
        if item_scene_getter is not None:
            try:
                initial_item_scene = item_scene_getter()
            except RuntimeError:
                if item_is_unavailable_for_scene_operation(item):
                    return cls._unavailable(scene, item_scene_getter)
                raise
        if initial_item_scene is not None and initial_item_scene is not scene:
            raise RuntimeError("scene item is already attached to a different scene")
        item_data_port = _qt_base_port(item, QGraphicsItem, "data")
        if item_data_port is _UNAVAILABLE:
            item_data_port = _capture_optional_attribute(item, "data")
        item_data_getter = item_data_port if callable(item_data_port) else None
        item_kind = (
            item_data_getter(0) if item_data_getter is not None else _UNAVAILABLE
        )
        item_metadata = (
            item_data_getter(1)
            if item_data_getter is not None and item_kind == "mark"
            else _UNAVAILABLE
        )
        item_flags_getter = _qt_base_port(item, QGraphicsItem, "flags")
        item_flags_setter = _qt_base_port(item, QGraphicsItem, "setFlags")
        if item_flags_getter is _UNAVAILABLE:
            item_flags_getter = _capture_optional_attribute(item, "flags")
        if item_flags_setter is _UNAVAILABLE:
            item_flags_setter = _capture_optional_attribute(item, "setFlags")
        item_flags_ports_present = (
            item_flags_getter is not _UNAVAILABLE
            or item_flags_setter is not _UNAVAILABLE
        )
        if callable(item_flags_getter) and callable(item_flags_setter):
            item_flags = item_flags_getter()
        elif item_flags_ports_present:
            raise RuntimeError(
                "live scene item does not expose a complete flags contract"
            )
        else:
            item_flags = _UNAVAILABLE
            item_flags_getter = None
            item_flags_setter = None
        text_flags_getter = _qt_base_port(
            item,
            QGraphicsTextItem,
            "textInteractionFlags",
        )
        text_flags_setter = _qt_base_port(
            item,
            QGraphicsTextItem,
            "setTextInteractionFlags",
        )
        if text_flags_getter is _UNAVAILABLE:
            text_flags_getter = _capture_optional_attribute(
                item,
                "textInteractionFlags",
            )
        if text_flags_setter is _UNAVAILABLE:
            text_flags_setter = _capture_optional_attribute(
                item,
                "setTextInteractionFlags",
            )
        text_flags_ports_present = (
            text_flags_getter is not _UNAVAILABLE
            or text_flags_setter is not _UNAVAILABLE
        )
        if callable(text_flags_getter) and callable(text_flags_setter):
            text_interaction_flags = text_flags_getter()
        elif text_flags_ports_present:
            raise RuntimeError(
                "live scene item does not expose a complete text-interaction contract"
            )
        else:
            text_interaction_flags = _UNAVAILABLE
            text_flags_getter = None
            text_flags_setter = None
        scene_bounding_rect_getter = _qt_base_port(
            item,
            QGraphicsItem,
            "sceneBoundingRect",
        )
        if scene_bounding_rect_getter is _UNAVAILABLE:
            scene_bounding_rect_getter = _capture_optional_attribute(
                item,
                "sceneBoundingRect",
            )
        scene_add_item = (
            _capture_optional_attribute(scene, "addItem")
            if scene is not None
            else _UNAVAILABLE
        )
        scene_remove_item = (
            _capture_optional_attribute(scene, "removeItem")
            if scene is not None
            else _UNAVAILABLE
        )
        scene_items_getter = (
            _capture_optional_attribute(scene, "items")
            if scene is not None
            else _UNAVAILABLE
        )
        scene_items_bounding_rect = (
            _capture_optional_attribute(scene, "itemsBoundingRect")
            if scene is not None
            else _UNAVAILABLE
        )
        scene_rect_getter = (
            _capture_optional_attribute(scene, "sceneRect")
            if scene is not None
            else _UNAVAILABLE
        )
        scene_rect_setter = (
            _capture_optional_attribute(scene, "setSceneRect")
            if scene is not None
            else _UNAVAILABLE
        )
        focus_item_getter = (
            _qt_base_port(scene, QGraphicsScene, "focusItem")
            if scene is not None
            else _UNAVAILABLE
        )
        if focus_item_getter is _UNAVAILABLE and scene is not None:
            focus_item_getter = _capture_optional_attribute(scene, "focusItem")
        focus_item_setter = (
            _capture_optional_attribute(scene, "setFocusItem")
            if scene is not None
            else _UNAVAILABLE
        )
        focus_item = None
        focus_ports_present = (
            focus_item_getter is not _UNAVAILABLE
            or focus_item_setter is not _UNAVAILABLE
        )
        if callable(focus_item_getter) and callable(focus_item_setter):
            focus_item = focus_item_getter()
        elif focus_ports_present:
            raise RuntimeError("live scene does not expose a complete focus contract")
        else:
            focus_item_getter = None
            focus_item_setter = None
        mutation_ports = (
            scene_add_item,
            scene_remove_item,
            item_scene_getter,
            item_flags_setter,
            text_flags_setter,
            scene_bounding_rect_getter,
            scene_rect_getter,
            scene_rect_setter,
            focus_item_setter,
        )
        untrusted_ports = (
            (
                scene_add_item,
                scene_remove_item,
                scene_rect_getter,
                scene_rect_setter,
                focus_item_setter,
            )
            if qt_item
            else mutation_ports
        )
        requires_authoritative_scene_bounds = any(
            callable(port) and not inspect.isbuiltin(port) for port in untrusted_ports
        )
        requires_full_graph_snapshot = bool(
            qt_item
            and (
                QGraphicsItem.isSelected(cast(QGraphicsItem, item))
                or QGraphicsItem.focusItem(cast(QGraphicsItem, item)) is not None
            )
        )
        return cls(
            scene=scene,
            item_scene_getter=item_scene_getter,
            initial_item_scene=initial_item_scene,
            item_scene_available=True,
            item_data_getter=item_data_getter,
            item_kind=item_kind,
            item_metadata=item_metadata,
            scene_add_item=(scene_add_item if callable(scene_add_item) else None),
            scene_remove_item=(
                scene_remove_item if callable(scene_remove_item) else None
            ),
            scene_items_getter=(
                scene_items_getter if callable(scene_items_getter) else None
            ),
            scene_items_bounding_rect_getter=(
                scene_items_bounding_rect
                if callable(scene_items_bounding_rect)
                else None
            ),
            scene_rect_getter=(
                scene_rect_getter if callable(scene_rect_getter) else None
            ),
            scene_rect_setter=(
                scene_rect_setter if callable(scene_rect_setter) else None
            ),
            requires_authoritative_scene_bounds=(requires_authoritative_scene_bounds),
            requires_full_graph_snapshot=requires_full_graph_snapshot,
            item_flags=item_flags,
            item_flags_getter=(
                item_flags_getter if callable(item_flags_getter) else None
            ),
            item_flags_setter=(
                item_flags_setter if callable(item_flags_setter) else None
            ),
            text_interaction_flags=text_interaction_flags,
            text_interaction_flags_getter=(
                text_flags_getter if callable(text_flags_getter) else None
            ),
            text_interaction_flags_setter=(
                text_flags_setter if callable(text_flags_setter) else None
            ),
            scene_bounding_rect_getter=(
                scene_bounding_rect_getter
                if callable(scene_bounding_rect_getter)
                else None
            ),
            focus_item=focus_item,
            focus_item_getter=(
                focus_item_getter if callable(focus_item_getter) else None
            ),
            focus_item_setter=(
                focus_item_setter if callable(focus_item_setter) else None
            ),
        )

    def item_can_be_added(self) -> bool:
        if self.scene is None or not self.item_scene_available:
            return False
        return (
            self.item_scene_getter is None or self.initial_item_scene is not self.scene
        )

    def item_kind_for_attach(self) -> object:
        if self.item_data_getter is None or self.item_kind is _UNAVAILABLE:
            raise RuntimeError("live scene item does not expose a data getter")
        return self.item_kind

    def validate_attachment_contract(
        self,
        *,
        require_text_interaction: bool = False,
    ) -> None:
        if self.scene is None:
            raise RuntimeError("live canvas does not expose a scene for item attach")
        if self.scene_add_item is None:
            raise RuntimeError("live scene does not expose an item-add port")
        if self.scene_remove_item is None:
            raise RuntimeError("live scene does not expose an item-remove port")
        if self.item_scene_getter is None:
            raise RuntimeError("live scene item does not expose a membership getter")
        if self.item_flags_getter is None or self.item_flags_setter is None:
            raise RuntimeError(
                "live scene item does not expose a complete flags contract"
            )
        if require_text_interaction and (
            self.text_interaction_flags_getter is None
            or self.text_interaction_flags_setter is None
        ):
            raise RuntimeError(
                "live note item does not expose a complete text-interaction contract"
            )

    def apply_selectable(self) -> None:
        getter = self.item_flags_getter
        setter = self.item_flags_setter
        if getter is None or setter is None:
            raise RuntimeError("live scene item has no captured flags contract")
        try:
            expected = (
                cast(Any, self.item_flags)
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
        except TypeError as error:
            raise RuntimeError(
                "live scene item returned an invalid flags value"
            ) from error
        setter(expected)
        if getter() != expected:
            raise RuntimeError("scene item was not made selectable")

    def apply_text_interaction_flags(self, expected: object) -> None:
        getter = self.text_interaction_flags_getter
        setter = self.text_interaction_flags_setter
        if getter is None or setter is None:
            raise RuntimeError(
                "live note item has no captured text-interaction contract"
            )
        setter(expected)
        if getter() != expected:
            raise RuntimeError("scene note text-interaction flags were not applied")

    def add_item(self, item: object) -> None:
        self.validate_attachment_contract()
        add_item = self.scene_add_item
        assert add_item is not None
        result = add_item(item)
        if result is False:
            raise RuntimeError("scene item-add port reported failure")
        getter = self.item_scene_getter
        assert getter is not None
        if getter() is not self.scene:
            raise RuntimeError("scene item-add port did not attach the item")

    def remove_item(self, item: object) -> bool:
        scene = self.scene
        if scene is None:
            return False
        getter = self.item_scene_getter
        if getter is not None and getter() is not scene:
            return False
        remove_item = self.scene_remove_item
        if remove_item is None:
            raise RuntimeError("live scene does not expose an item-remove port")
        result = remove_item(item)
        if result is False:
            raise RuntimeError("scene item-remove port reported failure")
        if getter is not None and getter() is scene:
            raise RuntimeError("scene item-remove port did not detach the item")
        return True


@dataclass(slots=True)
class SceneItemAttachSnapshot:
    """Attach savepoint with an O(1) builtin path and full callback isolation."""

    canvas: object
    item: object
    collection_owner: object
    collection_name: str | None
    collection: list | None
    collection_contents: tuple[object, ...]
    mark_registry: object | None
    mark_mapping: dict | None
    mark_entries: tuple[
        tuple[object, object, tuple[object, ...] | None],
        ...,
    ]
    mark_atom_id: int | None
    mark_entry_existed: bool
    mark_list: list | None
    item_flags: object
    text_interaction_flags: object
    scene: object | None
    scene_rect_snapshot: SceneRectSnapshot | None
    focus_item: object | None
    focus_item_getter: Callable[[], object] | None
    focus_item_setter: Callable[[object | None], object] | None
    scene_runtime_snapshot: _SceneRuntimeSnapshot | None
    full_graph_snapshot: bool
    attach_ports: SceneItemAttachPorts | None = None

    @classmethod
    def capture(
        cls,
        canvas,
        item,
        *,
        scene: object = _UNAVAILABLE,
        attach_ports: SceneItemAttachPorts | None = None,
    ) -> SceneItemAttachSnapshot:
        if attach_ports is None and scene is _UNAVAILABLE:
            scene_getter = _capture_optional_attribute(canvas, "scene")
            scene = scene_getter() if callable(scene_getter) else None
        if attach_ports is None:
            attach_ports = SceneItemAttachPorts.capture(scene, item)
        else:
            scene = attach_ports.scene
        kind = attach_ports.item_kind_for_attach()
        collection_owner = scene_items_state_for(canvas)
        collection_name = _KIND_COLLECTION.get(kind) if isinstance(kind, str) else None
        collection_candidate = (
            _capture_optional_attribute(collection_owner, collection_name)
            if collection_name is not None
            else _UNAVAILABLE
        )
        collection = collection_candidate
        if not isinstance(collection, list):
            collection = None

        registry = mark_registry_for(canvas) if kind == "mark" else None
        mapping = (
            _capture_optional_attribute(registry, "by_atom")
            if registry is not None
            else _UNAVAILABLE
        )
        mark_mapping = mapping if isinstance(mapping, dict) else None
        data = attach_ports.item_metadata if kind == "mark" else None
        atom_id = data.get("atom_id") if isinstance(data, dict) else None
        mark_atom_id = atom_id if isinstance(atom_id, int) else None
        mark_entry_existed = bool(
            mark_mapping is not None
            and mark_atom_id is not None
            and mark_atom_id in mark_mapping
        )
        candidate_marks = (
            mark_mapping.get(mark_atom_id)
            if mark_mapping is not None and mark_atom_id is not None
            else None
        )
        mark_list = candidate_marks if isinstance(candidate_marks, list) else None
        full_graph_snapshot = _requires_full_graph_snapshot(
            item=item,
            attach_ports=attach_ports,
            collection_owner=collection_owner,
            collection_name=collection_name,
            collection=collection,
            mark_registry=registry,
            mark_mapping=mark_mapping,
            mark_entry_existed=mark_entry_existed,
            mark_list=mark_list,
        )
        collection_contents = (
            tuple(collection) if full_graph_snapshot and collection is not None else ()
        )
        mark_entries = (
            tuple(
                (
                    key,
                    value,
                    tuple(value) if isinstance(value, list) else None,
                )
                for key, value in mark_mapping.items()
            )
            if full_graph_snapshot and mark_mapping is not None
            else ()
        )

        focus_item = attach_ports.focus_item
        focus_item_getter = attach_ports.focus_item_getter
        focus_item_setter = attach_ports.focus_item_setter
        scene_runtime_snapshot = (
            _capture_full_scene_runtime(
                canvas,
                scene,
                attach_ports,
            )
            if (
                full_graph_snapshot
                and scene is not None
                and attach_ports.scene_items_getter is not None
            )
            else None
        )
        # Open the temporary automatic-scene guard only after every other
        # fallible getter. Nothing capable of raising remains between guard
        # creation and returning the owning snapshot.
        scene_rect_snapshot = SceneRectSnapshot.capture(
            scene,
            scene_rect_getter=attach_ports.scene_rect_getter,
            set_scene_rect_setter=attach_ports.scene_rect_setter,
            scene_items_bounding_rect_getter=(
                attach_ports.scene_items_bounding_rect_getter
            ),
            incremental_tracking=(not attach_ports.requires_authoritative_scene_bounds),
        )

        return cls(
            canvas=canvas,
            item=item,
            collection_owner=collection_owner,
            collection_name=collection_name,
            collection=collection,
            collection_contents=collection_contents,
            mark_registry=registry,
            mark_mapping=mark_mapping,
            mark_entries=mark_entries,
            mark_atom_id=mark_atom_id,
            mark_entry_existed=mark_entry_existed,
            mark_list=mark_list,
            item_flags=attach_ports.item_flags,
            text_interaction_flags=attach_ports.text_interaction_flags,
            scene=scene,
            scene_rect_snapshot=scene_rect_snapshot,
            focus_item=focus_item,
            focus_item_getter=(
                focus_item_getter if callable(focus_item_getter) else None
            ),
            focus_item_setter=(
                focus_item_setter if callable(focus_item_setter) else None
            ),
            scene_runtime_snapshot=scene_runtime_snapshot,
            full_graph_snapshot=full_graph_snapshot,
            attach_ports=attach_ports,
        )

    @staticmethod
    def _remove_item_identity(items: list, item: object) -> None:
        items[:] = [candidate for candidate in items if candidate is not item]

    @staticmethod
    def _identity_sequence_matches(
        actual: list | tuple,
        expected: tuple[object, ...],
    ) -> bool:
        return len(actual) == len(expected) and all(
            current is captured
            for current, captured in zip(actual, expected, strict=True)
        )

    @staticmethod
    def _raise_restore_error(error: BaseException) -> None:
        raise error

    @staticmethod
    def _replace_list_contents(
        target: list,
        expected: tuple[object, ...],
    ) -> None:
        target[:] = expected

    def _restore_captured_collection(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> None:
        collection = self.collection
        collection_name = self.collection_name
        if collection is None:
            return

        def remove_from_replacement_collection() -> None:
            if collection_name is None:
                return
            current_collection = getattr(
                self.collection_owner,
                collection_name,
                None,
            )
            if (
                isinstance(current_collection, list)
                and current_collection is not collection
            ):
                self._remove_item_identity(current_collection, self.item)

        def restore_contents() -> None:
            collection[:] = self.collection_contents

        if collection_name is not None:
            _run_rollback_step(
                original_error,
                f"cleaning a replacement collection after {phase}",
                remove_from_replacement_collection,
            )
        _run_rollback_step(
            original_error,
            f"restoring complete collection contents after {phase}",
            restore_contents,
        )
        if collection_name is not None:
            _run_rollback_step(
                original_error,
                f"restoring collection identity after {phase}",
                lambda: setattr(
                    self.collection_owner,
                    collection_name,
                    collection,
                ),
            )

    def _restore_captured_mark_mapping(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> None:
        mapping = self.mark_mapping
        if mapping is None:
            return

        restored_lists: set[int] = set()
        for _key, value, contents in self.mark_entries:
            if (
                contents is None
                or not isinstance(value, list)
                or id(value) in restored_lists
            ):
                continue
            restored_lists.add(id(value))
            _run_rollback_step(
                original_error,
                f"restoring a complete mark-list after {phase}",
                partial(
                    self._replace_list_contents,
                    cast(list, value),
                    cast(tuple[object, ...], contents),
                ),
            )

        _run_rollback_step(
            original_error,
            f"clearing the captured mark mapping after {phase}",
            mapping.clear,
        )
        _run_rollback_step(
            original_error,
            f"restoring complete mark-mapping contents after {phase}",
            lambda: mapping.update(
                (key, value) for key, value, _contents in self.mark_entries
            ),
        )
        if self.mark_registry is not None:
            _run_rollback_step(
                original_error,
                f"restoring mark-registry identity after {phase}",
                lambda: setattr(self.mark_registry, "by_atom", mapping),
            )

    def _restore_lightweight_registration(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> None:
        collection = self.collection
        collection_name = self.collection_name

        def remove_from_replacement_collection() -> None:
            if collection_name is None:
                return
            current_collection = getattr(
                self.collection_owner,
                collection_name,
                None,
            )
            if (
                isinstance(current_collection, list)
                and current_collection is not collection
            ):
                self._remove_item_identity(current_collection, self.item)

        if collection_name is not None:
            _run_rollback_step(
                original_error,
                f"cleaning a replacement collection after {phase}",
                remove_from_replacement_collection,
            )
        if collection is not None:
            _run_rollback_step(
                original_error,
                f"removing the new item from its collection after {phase}",
                partial(self._remove_item_identity, collection, self.item),
            )
            if collection_name is not None:
                _run_rollback_step(
                    original_error,
                    f"restoring collection identity after {phase}",
                    lambda: setattr(
                        self.collection_owner,
                        collection_name,
                        collection,
                    ),
                )

        mapping = self.mark_mapping
        atom_id = self.mark_atom_id
        if mapping is None or atom_id is None:
            return
        if self.mark_entry_existed and self.mark_list is not None:
            _run_rollback_step(
                original_error,
                f"removing the new item from its mark list after {phase}",
                partial(self._remove_item_identity, self.mark_list, self.item),
            )
            _run_rollback_step(
                original_error,
                f"restoring the target mark-list identity after {phase}",
                lambda: mapping.__setitem__(atom_id, self.mark_list),
            )
        else:
            _run_rollback_step(
                original_error,
                f"removing the new mark key after {phase}",
                partial(mapping.pop, atom_id, None),
            )
        if self.mark_registry is not None:
            _run_rollback_step(
                original_error,
                f"restoring mark-registry identity after {phase}",
                lambda: setattr(self.mark_registry, "by_atom", mapping),
            )

    def _restore_captured_scene_runtime(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> bool:
        runtime_snapshot = self.scene_runtime_snapshot
        if runtime_snapshot is None:
            return False
        runtime_errors = _run_rollback_step(
            original_error,
            f"applying complete scene/runtime recovery after {phase}",
            partial(
                _restore_scene_runtime_snapshot,
                runtime_snapshot,
                collect_errors=True,
                restore_attempts=1,
            ),
            default=[],
        )
        if isinstance(runtime_errors, list):
            for runtime_error in runtime_errors:
                _run_rollback_step(
                    original_error,
                    f"recording scene/runtime recovery failure after {phase}",
                    partial(self._raise_restore_error, runtime_error),
                )
        return True

    def restore(
        self,
        original_error: BaseException,
        *,
        phase: str,
        restore_scene_rect: bool = True,
    ) -> None:
        for pass_index in range(2):
            self._restore_pass(
                original_error,
                phase=phase,
                restore_scene_rect=restore_scene_rect,
                reapply_scene_rect=pass_index > 0,
            )
            exact = _run_rollback_step(
                original_error,
                (
                    f"verifying exact scene-item recovery after {phase}"
                    if pass_index == 0
                    else f"verifying retried scene-item recovery after {phase}"
                ),
                partial(
                    self._assert_runtime_exact,
                    include_scene_rect=restore_scene_rect,
                ),
                default=False,
            )
            if exact:
                return

    def _restore_pass(
        self,
        original_error: BaseException,
        *,
        phase: str,
        restore_scene_rect: bool,
        reapply_scene_rect: bool,
    ) -> None:
        detach_operation = (
            partial(self.attach_ports.remove_item, self.item)
            if self.attach_ports is not None
            else partial(remove_attached_item_from_scene, self.scene, self.item)
        )
        _run_rollback_step(
            original_error,
            f"detaching the item after {phase}",
            detach_operation,
        )

        attach_ports = self.attach_ports
        if (
            attach_ports is not None
            and self.item_flags is not _UNAVAILABLE
            and attach_ports.item_flags_getter is not None
            and attach_ports.item_flags_setter is not None
        ):
            self._restore_bound_item_value(
                original_error,
                phase=f"restoring item flags after {phase}",
                getter=attach_ports.item_flags_getter,
                setter=attach_ports.item_flags_setter,
                expected=self.item_flags,
            )
        elif self.item_flags is not _UNAVAILABLE:

            def restore_item_flags() -> None:
                set_flags = getattr(self.item, "setFlags", None)
                if callable(set_flags):
                    set_flags(self.item_flags)

            _run_rollback_step(
                original_error,
                f"restoring item flags after {phase}",
                restore_item_flags,
            )
        if (
            attach_ports is not None
            and self.text_interaction_flags is not _UNAVAILABLE
            and attach_ports.text_interaction_flags_getter is not None
            and attach_ports.text_interaction_flags_setter is not None
        ):
            self._restore_bound_item_value(
                original_error,
                phase=f"restoring text interaction flags after {phase}",
                getter=attach_ports.text_interaction_flags_getter,
                setter=attach_ports.text_interaction_flags_setter,
                expected=self.text_interaction_flags,
            )
        elif self.text_interaction_flags is not _UNAVAILABLE:

            def restore_text_interaction_flags() -> None:
                set_text_interaction_flags = getattr(
                    self.item,
                    "setTextInteractionFlags",
                    None,
                )
                if callable(set_text_interaction_flags):
                    set_text_interaction_flags(self.text_interaction_flags)

            _run_rollback_step(
                original_error,
                f"restoring text interaction flags after {phase}",
                restore_text_interaction_flags,
            )

        # Setters above are untrusted and may delete or replace unrelated
        # registrations. A full runtime snapshot reapplies its captured lists,
        # mark graph, and scene membership/order together; sparse fallback
        # snapshots restore the targeted containers through their bound roots.
        restored_runtime = self._restore_captured_scene_runtime(
            original_error,
            phase=phase,
        )
        if not restored_runtime:
            if self.full_graph_snapshot:
                self._restore_captured_collection(original_error, phase=phase)
                self._restore_captured_mark_mapping(original_error, phase=phase)
            else:
                self._restore_lightweight_registration(
                    original_error,
                    phase=phase,
                )
            self._restore_scene_focus(original_error, phase=phase)

        # Scene bounds are the final geometric authority. Registry, flag,
        # text, and focus setters can synchronously trigger callbacks that
        # alter membership or an explicit scene rect, so repair the rect only
        # after every one of those fallible recovery steps has run.
        if restore_scene_rect:
            self.restore_scene_rect(
                original_error,
                phase=phase,
                reapply=reapply_scene_rect,
            )

    def _append_collection_mismatches(self, mismatches: list[str]) -> None:
        collection = self.collection
        if collection is None:
            return
        collection_name = self.collection_name
        if collection_name is not None:
            current_collection = getattr(
                self.collection_owner,
                collection_name,
                None,
            )
            if current_collection is not collection:
                mismatches.append("scene-item collection identity changed")
        if not self._identity_sequence_matches(
            collection,
            self.collection_contents,
        ):
            mismatches.append("scene-item collection contents differ from the capture")

    def _append_lightweight_registration_mismatches(
        self,
        mismatches: list[str],
    ) -> None:
        collection = self.collection
        collection_name = self.collection_name
        if collection is not None:
            if collection_name is not None:
                current_collection = getattr(
                    self.collection_owner,
                    collection_name,
                    None,
                )
                if current_collection is not collection:
                    mismatches.append("scene-item collection identity changed")
            if any(candidate is self.item for candidate in collection):
                mismatches.append("item remained in its captured collection")

        mapping = self.mark_mapping
        atom_id = self.mark_atom_id
        if mapping is None or atom_id is None:
            return
        if (
            self.mark_registry is not None
            and getattr(self.mark_registry, "by_atom", None) is not mapping
        ):
            mismatches.append("mark-registry mapping identity changed")
        if self.mark_entry_existed and self.mark_list is not None:
            if mapping.get(atom_id) is not self.mark_list:
                mismatches.append("captured mark-list identity changed")
            if any(candidate is self.item for candidate in self.mark_list):
                mismatches.append("item remained in its captured mark list")
        elif atom_id in mapping:
            mismatches.append("new mark-registry key remained present")

    def _append_mark_mismatches(self, mismatches: list[str]) -> None:
        mark_mapping = self.mark_mapping
        if mark_mapping is None:
            return
        if (
            self.mark_registry is not None
            and getattr(self.mark_registry, "by_atom", None) is not mark_mapping
        ):
            mismatches.append("mark-registry mapping identity changed")
        actual_entries = tuple(mark_mapping.items())
        if len(actual_entries) != len(self.mark_entries) or any(
            actual_key is not expected_key or actual_value is not expected_value
            for (actual_key, actual_value), (
                expected_key,
                expected_value,
                _expected_contents,
            ) in zip(actual_entries, self.mark_entries, strict=True)
        ):
            mismatches.append(
                "mark-registry keys or value identities differ from the capture"
            )
        for _key, value, contents in self.mark_entries:
            if (
                contents is not None
                and isinstance(value, list)
                and not self._identity_sequence_matches(value, contents)
            ):
                mismatches.append("captured mark-list contents differ from the capture")
                break

    def _append_scene_runtime_container_mismatches(
        self,
        mismatches: list[str],
    ) -> None:
        runtime_snapshot = self.scene_runtime_snapshot
        if runtime_snapshot is None:
            return
        for list_snapshot in runtime_snapshot.list_attributes:
            current_list = getattr(
                list_snapshot.owner,
                list_snapshot.attribute,
                None,
            )
            if current_list is not list_snapshot.list_object:
                mismatches.append(
                    f"runtime list {list_snapshot.attribute!r} identity changed"
                )
                continue
            if not self._identity_sequence_matches(
                list_snapshot.list_object,
                tuple(list_snapshot.contents),
            ):
                mismatches.append(
                    f"runtime list {list_snapshot.attribute!r} contents changed"
                )
        runtime_marks = runtime_snapshot.mark_registry
        if runtime_marks is None:
            return
        if runtime_marks.registry.by_atom is not runtime_marks.mapping_object:
            mismatches.append("runtime mark-mapping identity changed")
        actual_runtime_entries = tuple(runtime_marks.mapping_object.items())
        if len(actual_runtime_entries) != len(runtime_marks.entries) or any(
            actual_key is not expected_key or actual_value is not expected_value
            for (actual_key, actual_value), (
                expected_key,
                expected_value,
                _contents,
            ) in zip(
                actual_runtime_entries,
                runtime_marks.entries,
                strict=True,
            )
        ):
            mismatches.append("runtime mark-mapping contents changed")
        for _key, value, contents in runtime_marks.entries:
            if (
                contents is not None
                and isinstance(value, list)
                and not self._identity_sequence_matches(
                    value,
                    tuple(contents),
                )
            ):
                mismatches.append("runtime mark-list contents changed")
                break

    def _assert_runtime_exact(self, *, include_scene_rect: bool) -> bool:
        mismatches: list[str] = []
        attach_ports = self.attach_ports
        if (
            attach_ports is not None
            and attach_ports.item_scene_getter is not None
            and attach_ports.item_scene_getter() is self.scene
        ):
            mismatches.append("item remained attached to the target scene")

        if self.full_graph_snapshot:
            self._append_collection_mismatches(mismatches)
            self._append_mark_mismatches(mismatches)
        else:
            self._append_lightweight_registration_mismatches(mismatches)
        runtime_snapshot = self.scene_runtime_snapshot
        self._append_scene_runtime_container_mismatches(mismatches)

        if attach_ports is not None:
            if (
                self.item_flags is not _UNAVAILABLE
                and attach_ports.item_flags_getter is not None
                and attach_ports.item_flags_getter() != self.item_flags
            ):
                mismatches.append("item flags differ from the captured value")
            if (
                self.text_interaction_flags is not _UNAVAILABLE
                and attach_ports.text_interaction_flags_getter is not None
                and attach_ports.text_interaction_flags_getter()
                != self.text_interaction_flags
            ):
                mismatches.append(
                    "text-interaction flags differ from the captured value"
                )

        if (
            self.focus_item_getter is not None
            and self.focus_item_getter() is not self.focus_item
        ):
            mismatches.append("scene focus differs from the captured item")

        rect_snapshot = self.scene_rect_snapshot
        if include_scene_rect and rect_snapshot is not None:
            if rect_snapshot.active:
                mismatches.append("scene-rect snapshot remained active")
            elif rect_snapshot.tracker.depth == 0:
                if (
                    scene_rect_is_automatic(rect_snapshot.tracker.scene)
                    != rect_snapshot.automatic
                ):
                    mismatches.append("scene-rect mode differs from the capture")
                if rect_snapshot.scene_rect_getter() != rect_snapshot.baseline_rect:
                    mismatches.append("scene rect differs from the captured value")

        if mismatches:
            raise RuntimeError("; ".join(mismatches))
        if runtime_snapshot is not None:
            _verify_scene_runtime_identity(runtime_snapshot)
        return True

    @staticmethod
    def _restore_bound_item_value(
        original_error: BaseException,
        *,
        phase: str,
        getter: Callable[[], object],
        setter: Callable[[object], object],
        expected: object,
    ) -> None:
        def restore_once() -> bool:
            setter(expected)
            if getter() != expected:
                raise RuntimeError(f"{phase} did not restore the captured value")
            return True

        for attempt in range(2):
            restored = _run_rollback_step(
                original_error,
                phase if attempt == 0 else f"retrying {phase}",
                restore_once,
                default=False,
            )
            if restored:
                return

    def _restore_scene_focus(
        self,
        original_error: BaseException,
        *,
        phase: str,
    ) -> None:
        getter = self.focus_item_getter
        setter = self.focus_item_setter
        if getter is None or setter is None:
            return

        def restore_once() -> bool:
            setter(self.focus_item)
            if getter() is not self.focus_item:
                raise RuntimeError(
                    "scene-item attach rollback did not restore focus identity"
                )
            return True

        for attempt in range(2):
            restored = _run_rollback_step(
                original_error,
                (
                    f"restoring scene focus after {phase}"
                    if attempt == 0
                    else f"retrying scene focus restore after {phase}"
                ),
                restore_once,
                default=False,
            )
            if restored:
                return

    def restore_scene_rect(
        self,
        original_error: BaseException,
        *,
        phase: str,
        reapply: bool = False,
    ) -> None:
        rect_snapshot = self.scene_rect_snapshot
        if rect_snapshot is not None:
            recovery_error_count = len(rect_snapshot.recovery_errors)
            if reapply and not rect_snapshot.active:
                if rect_snapshot.tracker.depth != 0:
                    return

                def reapply_captured_rect() -> None:
                    if rect_snapshot.automatic:
                        rect_snapshot._restore_automatic_scene_rect()
                    else:
                        rect_snapshot._restore_explicit_scene_rect()

                _run_rollback_step(
                    original_error,
                    f"reapplying the scene rect after {phase}",
                    reapply_captured_rect,
                )
            else:
                _run_rollback_step(
                    original_error,
                    f"restoring the scene rect after {phase}",
                    rect_snapshot.restore,
                )
                if rect_snapshot.active:
                    _run_rollback_step(
                        original_error,
                        f"retrying the scene rect restore after {phase}",
                        rect_snapshot.restore,
                    )

            for recovery_error in rect_snapshot.recovery_errors[recovery_error_count:]:

                def report_recovery_error(
                    error: BaseException = recovery_error,
                ) -> None:
                    raise error

                _run_rollback_step(
                    original_error,
                    f"recording transient scene-rect recovery after {phase}",
                    report_recovery_error,
                )

    def release(self) -> None:
        if self.scene_rect_snapshot is None:
            return
        if not self.scene_rect_snapshot.automatic:
            self.scene_rect_snapshot.release()
            return
        expanded_rect = None
        scene_bounding_rect = (
            self.attach_ports.scene_bounding_rect_getter
            if self.attach_ports is not None
            else getattr(self.item, "sceneBoundingRect", None)
        )
        if callable(scene_bounding_rect):
            expanded_rect = scene_bounding_rect()
        expansion_owner_scene_getter = (
            self.attach_ports.item_scene_getter
            if self.attach_ports is not None
            else None
        )
        authoritative_bounds_getter = (
            self.attach_ports.scene_items_bounding_rect_getter
            if self.attach_ports is not None
            and self.attach_ports.requires_authoritative_scene_bounds
            else None
        )
        if authoritative_bounds_getter is None:
            self.scene_rect_snapshot.release(
                cast(Any, expanded_rect),
                expansion_key=self.item,
                expansion_owner_scene_getter=expansion_owner_scene_getter,
            )
        else:
            self.scene_rect_snapshot.release(
                cast(Any, expanded_rect),
                expansion_key=self.item,
                expansion_owner_scene_getter=expansion_owner_scene_getter,
                authoritative_scene_bounds_getter=(authoritative_bounds_getter),
            )


__all__ = ["SceneItemAttachPorts", "SceneItemAttachSnapshot"]
