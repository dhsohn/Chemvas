from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF

from chemvas.domain.transactions import add_recovery_error_note
from chemvas.features.export import (
    collect_export_items,
    content_bounds,
    export_item_closure,
)
from chemvas.ui.canvas_window_access import notify_error_for
from chemvas.ui.input_view_access import (
    CanvasSceneRectStateSnapshot,
    set_scene_rect_for,
    update_viewport_for,
)
from chemvas.ui.sheet_setup_logic import (
    SHEET_MARGIN_PX,
    sheet_dimensions_px,
)
from chemvas.ui.sheet_setup_state import (
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)

if TYPE_CHECKING:
    from collections.abc import Callable

OFF_SHEET_EDIT_GUIDANCE = (
    "Drawing and hover edits are only available inside the sheet. "
    "Move the pointer inside, or use Select to move the object onto the sheet."
)


@dataclass(slots=True)
class _SheetSetupSavepoint:
    state: object
    size_name: object
    orientation: object
    rect: QRectF
    active: bool = True

    @classmethod
    def capture(cls, canvas) -> _SheetSetupSavepoint:
        state = sheet_setup_state_for(canvas)
        return cls(
            state=state,
            size_name=state.size_name,
            orientation=state.orientation,
            rect=QRectF(state.rect),
        )

    def restore(self) -> tuple[Exception, ...]:
        if not self.active:
            return ()
        errors: list[Exception] = []
        operations = (
            lambda: setattr(self.state, "size_name", self.size_name),
            lambda: setattr(self.state, "orientation", self.orientation),
            lambda: setattr(self.state, "rect", QRectF(self.rect)),
        )
        for operation in operations:
            try:
                operation()
            except Exception as error:
                errors.append(error)
        self.active = False
        return tuple(errors)

    def release(self) -> None:
        self.active = False


def _run_sheet_setup_transaction(canvas, operation: Callable[[], None]) -> None:
    state_savepoint = _SheetSetupSavepoint.capture(canvas)
    rect_savepoint = CanvasSceneRectStateSnapshot.capture(canvas)
    try:
        operation()
    except Exception as original_error:
        for rollback_error in state_savepoint.restore():
            add_recovery_error_note(
                original_error,
                rollback_error,
                phase="restoring the sheet setup state",
            )
        try:
            rect_savepoint.restore()
        except Exception as rect_restore_error:
            add_recovery_error_note(
                original_error,
                rect_restore_error,
                phase="restoring the scene and view rects",
            )
        for rect_recovery_error in rect_savepoint.recovery_errors:
            add_recovery_error_note(
                original_error,
                rect_recovery_error,
                phase="restoring the scene and view rects",
            )
        raise
    rect_savepoint.release()
    state_savepoint.release()


def sheet_setup_for(canvas) -> tuple[str, str]:
    return sheet_setup_values_for(canvas)


def sheet_size_for(canvas) -> str:
    return sheet_setup_for(canvas)[0]


def sheet_orientation_for(canvas) -> str:
    return sheet_setup_for(canvas)[1]


def _expected_rects(
    size_name: str,
    orientation: str,
) -> tuple[QRectF, QRectF]:
    width, height = sheet_dimensions_px(size_name, orientation)
    sheet_rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    scene_rect = sheet_rect.adjusted(
        -SHEET_MARGIN_PX,
        -SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
    )
    return sheet_rect, scene_rect


def _apply_sheet_scene_rect_unchecked(canvas) -> None:
    sheet_rect, scene_rect = _expected_rects(*sheet_setup_for(canvas))
    scene_getter = getattr(canvas, "scene", None)
    scene = scene_getter() if callable(scene_getter) else None
    if scene is not None:
        bounds = content_bounds(export_item_closure(collect_export_items(scene)))
        if bounds is not None:
            scene_rect = scene_rect.united(
                bounds.adjusted(
                    -SHEET_MARGIN_PX, -SHEET_MARGIN_PX, SHEET_MARGIN_PX, SHEET_MARGIN_PX
                )
            )
    sheet_setup_state_for(canvas).rect = sheet_rect
    set_scene_rect_for(canvas, scene_rect)


def apply_sheet_scene_rect_for(canvas) -> None:
    def apply() -> None:
        _apply_sheet_scene_rect_unchecked(canvas)

    _run_sheet_setup_transaction(canvas, apply)


def refresh_canvas_scroll_range_for(canvas) -> bool:
    """Refresh view-only bounds without invalidating an already committed edit."""
    try:
        apply_sheet_scene_rect_for(canvas)
    except Exception:
        if not notify_error_for(
            canvas,
            "The scroll range could not be refreshed. Use Fit to Window to try again.",
        ):
            raise
        return False
    return True


def sheet_rect_for(canvas) -> QRectF:
    return QRectF(sheet_setup_state_for(canvas).rect)


def scene_pos_in_sheet_for(canvas, pos) -> bool:
    rect = sheet_rect_for(canvas)
    if rect.isNull() or rect.isEmpty():
        return True
    return rect.contains(pos)


def set_sheet_setup_for(canvas, size_name: str, orientation: str) -> None:
    def apply() -> None:
        set_sheet_setup_state_for(canvas, size_name, orientation)
        _apply_sheet_scene_rect_unchecked(canvas)
        update_viewport_for(canvas)

    _run_sheet_setup_transaction(canvas, apply)


__all__ = [
    "OFF_SHEET_EDIT_GUIDANCE",
    "apply_sheet_scene_rect_for",
    "refresh_canvas_scroll_range_for",
    "scene_pos_in_sheet_for",
    "set_sheet_setup_for",
    "sheet_orientation_for",
    "sheet_rect_for",
    "sheet_setup_for",
    "sheet_size_for",
]
