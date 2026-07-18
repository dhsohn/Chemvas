from __future__ import annotations

import inspect
from dataclasses import dataclass, fields, is_dataclass

from PyQt6.QtWidgets import QGraphicsItem

from chemvas.ui.history_commands import (
    _BondPrimitiveGraphicsSnapshot,
    _graphics_item_is_deleted,
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


def _add_capture_rollback_note(
    original_error: BaseException,
    secondary_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Object snapshot rollback also encountered "
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
    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
        ):
            raise
        return default


@dataclass(slots=True)
class _ContainerState:
    target: object
    kind: str
    contents: tuple


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
            except BaseException as exc:
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
            except BaseException as exc:
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

        raw_attributes: dict[str, tuple[bool, object]] = {}
        if isinstance(raw_namespace, dict):
            for name in names:
                present = dict.__contains__(raw_namespace, name)
                value = (
                    dict.__getitem__(raw_namespace, name)
                    if present
                    else _MISSING_ATTRIBUTE
                )
                raw_attributes[name] = (present, value)
                if present:
                    containers.capture(value)

        def restore_raw_attributes() -> None:
            if not isinstance(raw_namespace, dict):
                return
            for name, (present, value) in raw_attributes.items():
                if present:
                    dict.__setitem__(raw_namespace, name, value)
                else:
                    try:
                        dict.__delitem__(raw_namespace, name)
                    except KeyError:
                        pass

        def raw_attributes_match() -> bool:
            if not isinstance(raw_namespace, dict):
                return True
            for name, (present, value) in raw_attributes.items():
                if dict.__contains__(raw_namespace, name) is not present:
                    return False
                if present and dict.__getitem__(raw_namespace, name) is not value:
                    return False
            return True

        attributes: dict[str, object] = {}
        try:
            for name in names:
                if (
                    inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
                    is _MISSING_ATTRIBUTE
                ):
                    continue
                value = getattr(target, name)
                attributes[name] = value
                containers.capture(value)
        except BaseException as original_error:
            partial = cls(target=target, attributes=attributes)
            recovery_errors: list[BaseException] = []
            for _attempt in range(2):
                attempt_errors: list[BaseException] = []
                _collect_restore_errors(partial.restore, attempt_errors)
                try:
                    restore_raw_attributes()
                except BaseException as error:
                    attempt_errors.append(error)
                _collect_restore_errors(containers.restore, attempt_errors)
                try:
                    restore_raw_attributes()
                    if not raw_attributes_match():
                        raise RuntimeError(
                            "partial capture raw fields remained mutated"
                        )
                except BaseException as error:
                    attempt_errors.append(error)
                attempt_errors.extend(containers.verify())
                if not attempt_errors:
                    break
                recovery_errors.extend(attempt_errors)
            for recovery_error in recovery_errors:
                _add_capture_rollback_note(original_error, recovery_error)
            raise
        if not attributes:
            return None
        return cls(target=target, attributes=attributes)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for name, value in self.attributes.items():
            try:
                setattr(self.target, name, value)
            except BaseException as exc:
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
            except BaseException as exc:
                errors.append(exc)
        return errors


@dataclass(slots=True)
class SceneItemExactSnapshot:
    item: object
    data_values: tuple[tuple[int, object], ...]
    primitive_graphics: _BondPrimitiveGraphicsSnapshot | None

    @classmethod
    def capture(
        cls,
        item: object,
        containers: ContainerGraphSnapshot,
    ) -> SceneItemExactSnapshot | None:
        if _graphics_item_is_deleted(item):
            return None
        values: list[tuple[int, object]] = []
        data: object = None
        if isinstance(item, QGraphicsItem):
            for role in _SCENE_ITEM_DATA_ROLES:
                value = QGraphicsItem.data(item, role)
                containers.capture(value)
                values.append((role, value))
        else:
            data = _capture_optional_attribute(item, "data")
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
            primitive_graphics=_BondPrimitiveGraphicsSnapshot.capture(
                item,
                strict=True,
            ),
        )

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        if isinstance(self.item, QGraphicsItem):
            for role, value in self.data_values:
                try:
                    QGraphicsItem.setData(self.item, role, value)
                except BaseException as exc:
                    errors.append(exc)
        else:
            try:
                setter = _capture_optional_attribute(self.item, "setData")
            except BaseException as exc:
                errors.append(exc)
                setter = None
            if callable(setter):
                for role, value in self.data_values:
                    try:
                        setter(role, value)
                    except BaseException as exc:
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
                        QGraphicsItem.data(self.item, role),
                        expected,
                    ):
                        raise RuntimeError(
                            f"transaction scene-item data role {role} was re-mutated"
                        )
                except BaseException as exc:
                    errors.append(exc)
        else:
            try:
                data_getter = _capture_optional_attribute(self.item, "data")
            except BaseException as exc:
                errors.append(exc)
                data_getter = None
        if not isinstance(self.item, QGraphicsItem) and callable(data_getter):
            for role, expected in self.data_values:
                try:
                    if not _semantic_value_matches(data_getter(role), expected):
                        raise RuntimeError(
                            f"transaction scene-item data role {role} was re-mutated"
                        )
                except BaseException as exc:
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
                    getter = _capture_optional_attribute(
                        primitive.item,
                        getter_name,
                    )
                    if not callable(getter) or not _semantic_value_matches(
                        getter(),
                        expected,
                    ):
                        raise RuntimeError(
                            f"transaction primitive {getter_name} was re-mutated"
                        )
                except BaseException as exc:
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
                except BaseException as exc:
                    errors.append(exc)
        return errors


__all__ = [
    "ContainerGraphSnapshot",
    "ObjectStateSnapshot",
    "SceneItemExactSnapshot",
]
