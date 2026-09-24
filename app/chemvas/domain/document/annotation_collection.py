"""Ordered document records whose lifetime is independent of their projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True, kw_only=True)
class AnnotationCollection[Record]:
    """Own active IDs and values; retain detached records while views use them.

    Runtime IDs are never written into the document format. View finalization
    may release detached records, but cannot remove active document data.
    History owns independent values and can recreate collected records and views.
    """

    records: dict[int, Record] = field(default_factory=dict)
    order: list[int] = field(default_factory=list)

    def add(self, record_id: int) -> None:
        if record_id not in self.records:
            raise RuntimeError("annotation has no record; it cannot join the document")
        if record_id not in self.order:
            self.order.append(record_id)

    def remove(self, record_id: int) -> bool:
        if record_id not in self.order:
            return False
        self.order.remove(record_id)
        return True

    def reorder(self, order: list[int]) -> None:
        if len(order) != len(self.order) or set(order) != set(self.order):
            raise ValueError("order must contain every document annotation once")
        self.order[:] = order

    def discard_detached(self, record_id: int) -> None:
        if record_id not in self.order:
            self.records.pop(record_id, None)

    def clear(self) -> None:
        # An already empty scene may still have redo commands. Explicit document
        # replacement clears detached records separately, with its history.
        for record_id in self.order:
            self.records.pop(record_id, None)
        self.order.clear()

    def snapshot(
        self, serialize: Callable[[Record], dict[str, object]]
    ) -> list[dict[str, object]]:
        try:
            return [serialize(self.records[record_id]) for record_id in self.order]
        except KeyError as error:
            raise RuntimeError("document annotation has no record") from error
