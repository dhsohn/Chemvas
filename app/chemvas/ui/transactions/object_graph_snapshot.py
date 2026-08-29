from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.transactions.scene_runtime import (
    BondPrimitiveGraphicsSnapshot,
    graphics_item_is_deleted,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

_SCENE_ITEM_DATA_ROLES = (0, 1, 2, 6, 9, 20, 21, 22)
_UNAVAILABLE_SCENE_ITEM_DATA = object()
_MISSING_ATTRIBUTE = object()


def collect_restore_errors(
    operation: Callable[[], Iterable[BaseException]],
    destination: list[BaseException],
) -> None:
    """Run one snapshot restore and append what it reports or raises.

    Both savepoints that drive the snapshots defined here restore the same
    way: a restore returns its own error list, and a restore that raises
    instead counts as one error.
    """
    try:
        result = operation()
    except Exception as exc:
        destination.append(exc)
        return
    destination.extend(result)


def _exact_value_matches(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    if isinstance(expected, (dict, list, set)):
        return False
    try:
        return bool(actual == expected)
    except Exception:
        return False


def _semantic_value_matches(actual: object, expected: object) -> bool:
    if actual is expected:
        return True
    try:
        return bool(actual == expected)
    except Exception:
        return False


@dataclass(slots=True)
class _ContainerState:
    target: object
    kind: str
    # One field carries three shapes -- ``dict`` items, ``list`` elements, and
    # ``set`` elements -- captured from an arbitrary object graph, so the
    # element type is genuinely unknown. ``tuple[object, ...]`` would type the
    # list/set shape but reject the item pairs ``dict.update`` consumes below.
    contents: tuple[Any, ...]


class ContainerGraphSnapshot:
    """Preserve mutable container identities, including nested graph sets."""

    def __init__(self) -> None:
        self._states: dict[int, _ContainerState] = {}
        self._visited_immutable: set[int] = set()

    def capture(self, value: object) -> None:
        if isinstance(value, dict):
            if id(value) in self._states:
                return
            contents = tuple(value.items())
            self._states[id(value)] = _ContainerState(value, "dict", contents)
            for key, item in contents:
                self.capture(key)
                self.capture(item)
            return
        if isinstance(value, list):
            if id(value) in self._states:
                return
            contents = tuple(value)
            self._states[id(value)] = _ContainerState(value, "list", contents)
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, set):
            if id(value) in self._states:
                return
            contents = tuple(value)
            self._states[id(value)] = _ContainerState(value, "set", contents)
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, tuple):
            if id(value) in self._visited_immutable:
                return
            self._visited_immutable.add(id(value))
            for item in value:
                self.capture(item)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for state in self._states.values():
            try:
                if state.kind == "dict":
                    target = state.target
                    assert isinstance(target, dict)
                    target.clear()
                    target.update(state.contents)
                elif state.kind == "list":
                    target = state.target
                    assert isinstance(target, list)
                    target[:] = state.contents
                else:
                    target = state.target
                    assert isinstance(target, set)
                    target.clear()
                    target.update(state.contents)
            except Exception as exc:
                errors.append(exc)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for state in self._states.values():
            try:
                target = state.target
                if state.kind == "dict":
                    assert isinstance(target, dict)
                    actual_items = tuple(target.items())
                    matches = len(actual_items) == len(state.contents) and all(
                        actual_key is expected_key and actual_value is expected_value
                        for (actual_key, actual_value), (
                            expected_key,
                            expected_value,
                        ) in zip(actual_items, state.contents, strict=True)
                    )
                elif state.kind == "list":
                    assert isinstance(target, list)
                    matches = len(target) == len(state.contents) and all(
                        actual is expected
                        for actual, expected in zip(
                            target,
                            state.contents,
                            strict=True,
                        )
                    )
                else:
                    assert isinstance(target, set)
                    matches = {id(value) for value in target} == {
                        id(value) for value in state.contents
                    }
                if not matches:
                    raise RuntimeError(
                        "transaction rollback container contents were re-mutated"
                    )
            except Exception as exc:
                errors.append(exc)
        return errors


@dataclass(slots=True)
class ObjectStateSnapshot:
    target: object
    attributes: dict[str, object]

    @classmethod
    def capture(
        cls,
        target: object,
        containers: ContainerGraphSnapshot,
        *,
        names: tuple[str, ...] | None = None,
    ) -> ObjectStateSnapshot | None:
        try:
            raw_namespace = object.__getattribute__(target, "__dict__")
        except (AttributeError, TypeError):
            raw_namespace = None
        if names is None:
            if is_dataclass(target) and not isinstance(target, type):
                names = tuple(field.name for field in fields(target))
            else:
                if not isinstance(raw_namespace, dict):
                    return None
                names = tuple(dict.__iter__(raw_namespace))

        attributes: dict[str, object] = {}
        for name in names:
            value = getattr(target, name, _MISSING_ATTRIBUTE)
            if value is _MISSING_ATTRIBUTE:
                continue
            attributes[name] = value
            containers.capture(value)
        if not attributes:
            return None
        return cls(target=target, attributes=attributes)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for name, value in self.attributes.items():
            try:
                setattr(self.target, name, value)
            except Exception as exc:
                errors.append(exc)
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for name, expected in self.attributes.items():
            try:
                actual = getattr(self.target, name)
                if not _exact_value_matches(actual, expected):
                    raise RuntimeError(
                        f"transaction object attribute {name!r} was re-mutated"
                    )
            except Exception as exc:
                errors.append(exc)
        return errors


@dataclass(slots=True)
class SceneItemExactSnapshot:
    item: object
    data_values: tuple[tuple[int, object], ...]
    primitive_graphics: BondPrimitiveGraphicsSnapshot | None

    @classmethod
    def capture(
        cls,
        item: object,
        containers: ContainerGraphSnapshot,
    ) -> SceneItemExactSnapshot | None:
        if graphics_item_is_deleted(item):
            return None
        values: list[tuple[int, object]] = []
        data: object = None
        if isinstance(item, QGraphicsItem):
            for role in _SCENE_ITEM_DATA_ROLES:
                value = item.data(role)
                containers.capture(value)
                values.append((role, value))
        else:
            data = getattr(item, "data", None)
            if not callable(data):
                data = None
        if not isinstance(item, QGraphicsItem) and callable(data):
            for role in _SCENE_ITEM_DATA_ROLES:
                value = data(role)
                if value is _UNAVAILABLE_SCENE_ITEM_DATA:
                    continue
                containers.capture(value)
                values.append((role, value))
        return cls(
            item=item,
            data_values=tuple(values),
            primitive_graphics=BondPrimitiveGraphicsSnapshot.capture(
                item,
            ),
        )

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        if isinstance(self.item, QGraphicsItem):
            for role, value in self.data_values:
                try:
                    self.item.setData(role, value)
                except Exception as exc:
                    errors.append(exc)
        else:
            try:
                setter = getattr(self.item, "setData", None)
            except Exception as exc:
                errors.append(exc)
                setter = None
            if callable(setter):
                for role, value in self.data_values:
                    try:
                        setter(role, value)
                    except Exception as exc:
                        errors.append(exc)
        if self.primitive_graphics is not None:
            errors.extend(self.primitive_graphics.restore())
        return errors

    def verify(self) -> list[BaseException]:
        errors: list[BaseException] = []
        data_getter: object = None
        if isinstance(self.item, QGraphicsItem):
            for role, expected in self.data_values:
                try:
                    if not _semantic_value_matches(
                        self.item.data(role),
                        expected,
                    ):
                        raise RuntimeError(
                            f"transaction scene-item data role {role} was re-mutated"
                        )
                except Exception as exc:
                    errors.append(exc)
        else:
            try:
                data_getter = getattr(self.item, "data", None)
            except Exception as exc:
                errors.append(exc)
                data_getter = None
        if not isinstance(self.item, QGraphicsItem) and callable(data_getter):
            for role, expected in self.data_values:
                try:
                    if not _semantic_value_matches(data_getter(role), expected):
                        raise RuntimeError(
                            f"transaction scene-item data role {role} was re-mutated"
                        )
                except Exception as exc:
                    errors.append(exc)
        primitive = self.primitive_graphics
        if primitive is not None:
            for setter_name, expected in primitive.properties:
                getter_name = (
                    "toHtml"
                    if setter_name == "setHtml"
                    else setter_name[3:4].lower() + setter_name[4:]
                )
                try:
                    getter = getattr(primitive.item, getter_name, None)
                    if not callable(getter) or not _semantic_value_matches(
                        getter(),
                        expected,
                    ):
                        raise RuntimeError(
                            f"transaction primitive {getter_name} was re-mutated"
                        )
                except Exception as exc:
                    errors.append(exc)
            for name, expected in primitive.direct_attributes:
                try:
                    if not _semantic_value_matches(
                        getattr(primitive.item, name),
                        expected,
                    ):
                        raise RuntimeError(
                            f"transaction primitive attribute {name!r} was re-mutated"
                        )
                except Exception as exc:
                    errors.append(exc)
        return errors


__all__ = [
    "ContainerGraphSnapshot",
    "ObjectStateSnapshot",
    "SceneItemExactSnapshot",
    "collect_restore_errors",
]
