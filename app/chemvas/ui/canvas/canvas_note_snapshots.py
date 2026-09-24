"""Rollback snapshots for note editing: box geometry, mutation state and the editing note."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem

from chemvas.domain.transactions import run_rollback_step
from chemvas.ui.canvas.input_view_access import (
    _MISSING_CAPTURE_ATTRIBUTE,
)
from chemvas.ui.scene.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
)
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import (
        QBrush,
        QPen,
    )


def _capture_optional_attribute(target: object, name: str) -> object:
    return getattr(target, name, _MISSING_CAPTURE_ATTRIBUTE)


def _call_required_rollback_method(target: object, name: str, *args) -> object:
    method = getattr(target, name)
    if not callable(method):
        raise TypeError(f"Rollback port {name!r} is not callable")
    return method(*args)


def _call_optional_rollback_method(target: object, name: str, *args) -> object | None:
    method = _capture_optional_attribute(target, name)
    if method is _MISSING_CAPTURE_ATTRIBUTE or not callable(method):
        return None
    return method(*args)


@dataclass(slots=True)
class _NoteMutationSnapshot:
    item: QGraphicsTextItem
    before_state: dict
    committed_text: str
    committed_html: str
    interaction_flags: Qt.TextInteractionFlag


@dataclass(slots=True, kw_only=True)
class _NoteBoxSnapshot:
    role: int
    box: QGraphicsRectItem | None
    rect: QRectF | None
    pen: QPen | None
    brush: QBrush | None
    visible: bool | None

    @classmethod
    def capture(cls, item: QGraphicsTextItem, role: int) -> _NoteBoxSnapshot:
        box = item.data(role)
        if not isinstance(box, QGraphicsRectItem):
            return cls(
                role=role, box=None, rect=None, pen=None, brush=None, visible=None
            )
        return cls(
            role=role,
            box=box,
            rect=box.rect(),
            pen=box.pen(),
            brush=box.brush(),
            visible=box.isVisible(),
        )


@dataclass(slots=True, kw_only=True)
class _EditingNoteSnapshot:
    item: QGraphicsTextItem
    html: str
    committed_text: str
    committed_html: str
    interaction_flags: Qt.TextInteractionFlag
    cursor_anchor: int
    cursor_position: int
    scene: object | None
    focus_item: object | None
    boxes: tuple[_NoteBoxSnapshot, ...]

    @classmethod
    def capture(cls, item: QGraphicsTextItem) -> _EditingNoteSnapshot:
        cursor = item.textCursor()
        scene = item.scene()
        focus_item_getter = _capture_optional_attribute(scene, "focusItem")
        return cls(
            item=item,
            html=item.toHtml(),
            committed_text=committed_note_text_for(item),
            committed_html=committed_note_html_for(item),
            interaction_flags=item.textInteractionFlags(),
            cursor_anchor=cursor.anchor(),
            cursor_position=cursor.position(),
            scene=scene,
            focus_item=focus_item_getter() if callable(focus_item_getter) else None,
            boxes=(
                _NoteBoxSnapshot.capture(item, 20),
                _NoteBoxSnapshot.capture(item, 21),
            ),
        )


@dataclass(slots=True)
class _NoteSceneRectTransaction:
    snapshot: SceneRectSnapshot | None
    items_bounding_rect: Callable[[], QRectF] | None

    @classmethod
    def capture(cls, scene: object | None) -> _NoteSceneRectTransaction:
        items_bounding_rect = _capture_optional_attribute(
            scene,
            "itemsBoundingRect",
        )
        bound_items_bounding_rect = (
            items_bounding_rect if callable(items_bounding_rect) else None
        )
        # SceneRectSnapshot temporarily fixes an automatic Qt scene. Open it
        # only after the bounds port and every note snapshot are safely owned.
        snapshot = SceneRectSnapshot.capture(scene)
        return cls(snapshot, bound_items_bounding_rect)

    def release(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        expanded_rect = None
        if snapshot.automatic:
            items_bounding_rect = self.items_bounding_rect
            if not callable(items_bounding_rect):
                raise AttributeError(
                    "Automatic note-formatting scene requires itemsBoundingRect"
                )
            expanded_rect = QRectF(items_bounding_rect())
        snapshot.release(expanded_rect)

    def restore(self, original_error: BaseException) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        prior_recovery_count = len(snapshot.recovery_errors)
        run_rollback_step(
            original_error,
            "restoring the note-formatting scene rect",
            snapshot.restore,
        )
        if not snapshot.active:
            for recovery_error in snapshot.recovery_errors[prior_recovery_count:]:

                def report_recovered_error(
                    error: BaseException = recovery_error,
                ) -> None:
                    raise error

                run_rollback_step(
                    original_error,
                    "restoring the note-formatting scene rect",
                    report_recovered_error,
                )
        if snapshot.active:
            run_rollback_step(
                original_error,
                "verifying the note-formatting scene-rect restore",
                lambda: (_ for _ in ()).throw(
                    RuntimeError(
                        "Note-formatting scene-rect restore remained incomplete"
                    )
                ),
            )
