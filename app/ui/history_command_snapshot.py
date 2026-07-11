from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, cast

from core.history import HistoryCommand
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QTransform


def _read_dataclass_field(value: object, name: str) -> object:
    """Read an ordinary dataclass field without a replaceable live getter."""

    try:
        namespace = object.__getattribute__(value, "__dict__")
    except (AttributeError, TypeError):
        namespace = None
    if isinstance(namespace, dict) and name in namespace:
        return dict.__getitem__(namespace, name)
    return object.__getattribute__(value, name)


@dataclass(frozen=True, slots=True)
class _FrozenValue:
    kind: str
    value_type: type
    identity: Any = None
    scalar: Any = None
    children: tuple[Any, ...] = ()

    @classmethod
    def capture(cls, value: object) -> _FrozenValue:
        value_type = type(value)
        if value is None or value_type in {bool, int, float, str, bytes}:
            return cls("scalar", value_type, scalar=value)
        if isinstance(value, Enum):
            return cls("enum", value_type, identity=value, scalar=value.value)
        if isinstance(value, QColor):
            return cls(
                "qcolor",
                value_type,
                identity=value,
                scalar=QColor(value).rgba(),
            )
        if isinstance(value, QPointF):
            return cls(
                "qpointf",
                value_type,
                scalar=(QPointF.x(value), QPointF.y(value)),
            )
        if isinstance(value, QRectF):
            return cls(
                "qrectf",
                value_type,
                scalar=(
                    QRectF.x(value),
                    QRectF.y(value),
                    QRectF.width(value),
                    QRectF.height(value),
                ),
            )
        if isinstance(value, QPen):
            return cls("qpen", value_type, scalar=QPen(value))
        if isinstance(value, QBrush):
            return cls("qbrush", value_type, scalar=QBrush(value))
        if isinstance(value, QFont):
            return cls("qfont", value_type, scalar=QFont(value))
        if isinstance(value, QTransform):
            return cls("qtransform", value_type, scalar=QTransform(value))
        if isinstance(value, tuple):
            return cls(
                "tuple",
                value_type,
                children=tuple(
                    cls.capture(item) for item in tuple.__iter__(value)
                ),
            )
        if isinstance(value, list):
            return cls(
                "list",
                value_type,
                identity=value,
                children=tuple(cls.capture(item) for item in list.__iter__(value)),
            )
        if isinstance(value, dict):
            return cls(
                "dict",
                value_type,
                identity=value,
                children=tuple(
                    (cls.capture(key), cls.capture(item))
                    for key, item in dict.items(value)
                ),
            )
        if isinstance(value, set):
            return cls(
                "set",
                value_type,
                identity=value,
                children=tuple(cls.capture(item) for item in set.__iter__(value)),
            )
        if is_dataclass(value) and not isinstance(value, type):
            return cls(
                "dataclass",
                value_type,
                identity=value,
                children=tuple(
                    (field.name, cls.capture(_read_dataclass_field(value, field.name)))
                    for field in fields(value)
                ),
            )
        if isinstance(value, HistoryCommand):
            try:
                namespace = object.__getattribute__(value, "__dict__")
            except (AttributeError, TypeError):
                namespace = None
            if not isinstance(namespace, dict):
                raise RuntimeError(
                    "non-dataclass history command has no raw payload namespace"
                )
            return cls(
                "command-object",
                value_type,
                identity=value,
                children=tuple(
                    (name, cls.capture(item))
                    for name, item in dict.items(namespace)
                ),
            )
        # Scene items and other command targets are authorities by identity.
        # Deliberately do not deepcopy or compare arbitrary extension objects:
        # both operations can execute user callbacks during transaction close.
        return cls("identity", value_type, identity=value)

    def verify(self, actual: Any, *, path: str) -> None:  # noqa: C901
        if type(actual) is not self.value_type:
            raise RuntimeError(f"history command field {path} changed type")
        if self.kind == "scalar":
            if actual != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind == "enum":
            if not isinstance(actual, Enum) or actual.value != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind == "qcolor":
            if QColor(actual).rgba() != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind == "qpointf":
            point = cast(QPointF, actual)
            if (QPointF.x(point), QPointF.y(point)) != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind == "qrectf":
            rect = cast(QRectF, actual)
            if (
                QRectF.x(rect),
                QRectF.y(rect),
                QRectF.width(rect),
                QRectF.height(rect),
            ) != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind in {"qpen", "qbrush", "qfont", "qtransform"}:
            if actual != self.scalar:
                raise RuntimeError(f"history command field {path} changed")
            return
        if self.kind == "identity":
            if actual is not self.identity:
                raise RuntimeError(f"history command target {path} changed identity")
            return
        if self.kind == "tuple":
            actual_items: tuple[Any, ...] = tuple(
                tuple.__iter__(cast(tuple[Any, ...], actual))
            )
        elif self.kind == "list":
            if actual is not self.identity:
                raise RuntimeError(
                    f"history command container {path} changed identity"
                )
            actual_items = tuple(list.__iter__(cast(list[Any], actual)))
        elif self.kind == "dict":
            if actual is not self.identity:
                raise RuntimeError(
                    f"history command container {path} changed identity"
                )
            actual_items = tuple(dict.items(cast(dict[Any, Any], actual)))
            if len(actual_items) != len(self.children):
                raise RuntimeError(f"history command container {path} changed")
            for index, ((key, item), frozen_pair) in enumerate(
                zip(actual_items, self.children, strict=True)
            ):
                frozen_key, frozen_item = frozen_pair
                assert isinstance(frozen_key, _FrozenValue)
                assert isinstance(frozen_item, _FrozenValue)
                frozen_key.verify(key, path=f"{path}.key[{index}]")
                frozen_item.verify(item, path=f"{path}[{index}]")
            return
        elif self.kind == "set":
            if actual is not self.identity:
                raise RuntimeError(
                    f"history command container {path} changed identity"
                )
            actual_items = tuple(set.__iter__(cast(set[Any], actual)))
            if len(actual_items) != len(self.children):
                raise RuntimeError(f"history command container {path} changed")
            unmatched = list(self.children)
            for actual_item in actual_items:
                for index, frozen_item in enumerate(unmatched):
                    assert isinstance(frozen_item, _FrozenValue)
                    try:
                        frozen_item.verify(actual_item, path=f"{path}[*]")
                    except RuntimeError:
                        continue
                    unmatched.pop(index)
                    break
                else:
                    raise RuntimeError(f"history command container {path} changed")
            return
        elif self.kind in {"dataclass", "command-object"}:
            if actual is not self.identity:
                raise RuntimeError(
                    f"history command structure {path} changed identity"
                )
            if self.kind == "command-object":
                namespace = object.__getattribute__(actual, "__dict__")
                if not isinstance(namespace, dict):
                    raise RuntimeError(
                        f"history command structure {path} lost its namespace"
                    )
                expected_names = tuple(name for name, _item in self.children)
                if tuple(dict.__iter__(namespace)) != expected_names:
                    raise RuntimeError(
                        f"history command structure {path} changed fields"
                    )
            for name, frozen_item in self.children:
                assert isinstance(name, str)
                assert isinstance(frozen_item, _FrozenValue)
                frozen_item.verify(
                    _read_dataclass_field(actual, name),
                    path=f"{path}.{name}",
                )
            return
        else:  # pragma: no cover - every capture kind is handled above.
            raise RuntimeError(f"unsupported frozen history value at {path}")

        if len(actual_items) != len(self.children):
            raise RuntimeError(f"history command container {path} changed")
        for index, (actual_item, frozen_item) in enumerate(
            zip(actual_items, self.children, strict=True)
        ):
            assert isinstance(frozen_item, _FrozenValue)
            frozen_item.verify(actual_item, path=f"{path}[{index}]")

    def restore_value(self) -> object:  # noqa: C901
        if self.kind == "scalar":
            return self.scalar
        if self.kind == "enum":
            return self.identity
        if self.kind == "qcolor":
            return QColor.fromRgba(self.scalar)
        if self.kind == "qpointf":
            assert isinstance(self.scalar, tuple)
            return QPointF(*self.scalar)
        if self.kind == "qrectf":
            assert isinstance(self.scalar, tuple)
            return QRectF(*self.scalar)
        if self.kind == "qpen":
            return QPen(self.scalar)
        if self.kind == "qbrush":
            return QBrush(self.scalar)
        if self.kind == "qfont":
            return QFont(self.scalar)
        if self.kind == "qtransform":
            return QTransform(self.scalar)
        if self.kind == "identity":
            return self.identity
        if self.kind == "tuple":
            return tuple(
                child.restore_value()
                for child in self.children
                if isinstance(child, _FrozenValue)
            )
        if self.kind == "list":
            target = self.identity
            assert isinstance(target, list)
            restored = tuple(
                child.restore_value()
                for child in self.children
                if isinstance(child, _FrozenValue)
            )
            list.__setitem__(target, slice(None), restored)
            return target
        if self.kind == "dict":
            target = self.identity
            assert isinstance(target, dict)
            restored_items: list[tuple[object, object]] = []
            for frozen_pair in self.children:
                frozen_key, frozen_item = frozen_pair
                assert isinstance(frozen_key, _FrozenValue)
                assert isinstance(frozen_item, _FrozenValue)
                restored_items.append(
                    (frozen_key.restore_value(), frozen_item.restore_value())
                )
            dict.clear(target)
            for key, item in restored_items:
                dict.__setitem__(target, key, item)
            return target
        if self.kind == "set":
            target = self.identity
            assert isinstance(target, set)
            restored = tuple(
                child.restore_value()
                for child in self.children
                if isinstance(child, _FrozenValue)
            )
            set.clear(target)
            for item in restored:
                set.add(target, item)
            return target
        if self.kind in {"dataclass", "command-object"}:
            target = self.identity
            assert target is not None
            if self.kind == "command-object":
                namespace = object.__getattribute__(target, "__dict__")
                if not isinstance(namespace, dict):
                    raise RuntimeError(
                        "history command payload namespace cannot be restored"
                    )
                dict.clear(namespace)
            for name, frozen_item in self.children:
                assert isinstance(name, str)
                assert isinstance(frozen_item, _FrozenValue)
                restored_value = frozen_item.restore_value()
                try:
                    namespace = object.__getattribute__(target, "__dict__")
                except (AttributeError, TypeError):
                    namespace = None
                if isinstance(namespace, dict) and name in namespace:
                    dict.__setitem__(namespace, name, restored_value)
                else:
                    object.__setattr__(target, name, restored_value)
            return target
        raise RuntimeError("unsupported frozen history value restore")


@dataclass(frozen=True, slots=True)
class HistoryCommandSnapshot:
    """Callback-free structural/payload authority for one published command."""

    command: HistoryCommand
    frozen: _FrozenValue

    @classmethod
    def capture(cls, command: HistoryCommand) -> HistoryCommandSnapshot:
        return cls(command=command, frozen=_FrozenValue.capture(command))

    def verify(self) -> None:
        self.frozen.verify(self.command, path=type(self.command).__name__)

    def restore(self) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                restored = self.frozen.restore_value()
                if restored is not self.command:
                    raise RuntimeError("history command root identity changed")
                self.verify()
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup(
            "history command payload restore failed",
            errors,
        )


__all__ = ["HistoryCommandSnapshot"]
