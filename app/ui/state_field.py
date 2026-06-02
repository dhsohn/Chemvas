from __future__ import annotations

from typing import Any


class StateField:
    def __init__(self, state_attr: str, field_attr: str) -> None:
        self.state_attr = state_attr
        self.field_attr = field_attr

    def __get__(self, instance: Any, owner: type | None = None):
        if instance is None:
            return self
        return getattr(getattr(instance, self.state_attr), self.field_attr)

    def __set__(self, instance: Any, value) -> None:
        setattr(getattr(instance, self.state_attr), self.field_attr, value)


__all__ = ["StateField"]
