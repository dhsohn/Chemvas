from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

MISSING_ATTRIBUTE = object()


def capture_optional_attribute(target: object, name: str) -> object:
    """Read an optional attribute without hiding a failing descriptor."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, MISSING_ATTRIBUTE)
            is not MISSING_ATTRIBUTE
        ):
            raise
        return MISSING_ATTRIBUTE


@dataclass(frozen=True, slots=True)
class BoundAttributePort:
    """Capture-bound raw get/set operations for one object attribute."""

    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]

    @classmethod
    def capture(
        cls,
        target: object,
        name: str,
        *,
        value: object,
        description: str,
    ) -> BoundAttributePort:
        getattribute = inspect.getattr_static(
            type(target),
            "__getattribute__",
            MISSING_ATTRIBUTE,
        )
        setattribute = inspect.getattr_static(
            type(target),
            "__setattr__",
            MISSING_ATTRIBUTE,
        )
        if not callable(getattribute) or not callable(setattribute):
            raise RuntimeError(f"{description} has incomplete bound ports")
        getattribute_port = cast(Callable[[object, str], object], getattribute)
        setattribute_port = cast(
            Callable[[object, str, object], object],
            setattribute,
        )

        def get_value(
            _getattribute: Callable[[object, str], object] = getattribute_port,
            _target: object = target,
            _name: str = name,
        ) -> object:
            return _getattribute(_target, _name)

        def set_value(
            new_value: object,
            _setattribute: Callable[[object, str, object], object] = setattribute_port,
            _target: object = target,
            _name: str = name,
        ) -> object:
            return _setattribute(_target, _name, new_value)

        return cls(value=value, getter=get_value, setter=set_value)

    def apply_once(self) -> None:
        if self.getter() is self.value:
            return
        self.setter(self.value)

    def verify(self) -> None:
        if self.getter() is not self.value:
            raise RuntimeError("bound attribute did not restore captured identity")


__all__ = [
    "MISSING_ATTRIBUTE",
    "BoundAttributePort",
    "capture_optional_attribute",
]
