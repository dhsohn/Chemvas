"""Document binding shared by the native dot, text and circled mark views."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from chemvas.domain.document.marks import Mark, mark_to_state
from chemvas.ui.scene.scene_record_ids import (
    bind_scene_record,
    new_scene_record_id,
)

if TYPE_CHECKING:
    from chemvas.domain.document.annotation_collection import AnnotationCollection


class MarkItem:
    """Native geometry publishes positions; metadata lives only in the record."""

    def bind_mark(self, marks: AnnotationCollection[Mark], kind: str) -> None:
        self.marks = marks
        self.record_id = new_scene_record_id()
        marks.records[self.record_id] = Mark(kind=kind)
        bind_scene_record(self, marks, self.record_id)
        native = cast("QGraphicsItem", self)
        native.setData(3, self.record_id)
        native.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        if isinstance(self, QGraphicsTextItem):
            document = self.document()
            assert document is not None
            document.contentsChanged.connect(self.publish_mark_center)
        self.publish_mark_center()

    def mark_state(self) -> dict[str, object]:
        return mark_to_state(self.marks.records[self.record_id])

    def data(self, key: int) -> Any:
        if key == 1 and hasattr(self, "marks"):
            mark = self.marks.records.get(self.record_id)
            if mark is not None:
                return {
                    "kind": mark.kind,
                    "atom_id": mark.atom_id,
                    **({"dx": mark.dx} if mark.dx is not None else {}),
                    **({"dy": mark.dy} if mark.dy is not None else {}),
                    **({"text": mark.text} if mark.text is not None else {}),
                    **({"color": mark.color} if mark.color is not None else {}),
                }
        return QGraphicsItem.data(cast("QGraphicsItem", self), key)

    def setData(self, key: int, value: Any) -> None:  # noqa: N802 - Qt virtual
        if key == 1 and hasattr(self, "marks"):
            current = self.marks.records.get(self.record_id)
            if current is not None:
                data = value or {}
                updated = replace(
                    current,
                    kind=data.get("kind", "plus"),
                    atom_id=data.get("atom_id"),
                    dx=data.get("dx"),
                    dy=data.get("dy"),
                    text=data.get("text"),
                    color=data.get("color"),
                )
                if updated != current:
                    self.marks.records[self.record_id] = updated
                return
        QGraphicsItem.setData(cast("QGraphicsItem", self), key, value)

    def publish_mark_center(self) -> None:
        if not hasattr(self, "marks"):
            return
        current = self.marks.records.get(self.record_id)
        if current is None:
            return
        native = cast("QGraphicsItem", self)
        center = native.pos()
        if isinstance(self, QGraphicsTextItem):
            center += self.boundingRect().center()
        if (current.x, current.y) != (center.x(), center.y()):
            self.marks.records[self.record_id] = replace(
                current, x=center.x(), y=center.y()
            )

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:  # noqa: N802 - Qt virtual
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.publish_mark_center()
        return QGraphicsItem.itemChange(cast("QGraphicsItem", self), change, value)
