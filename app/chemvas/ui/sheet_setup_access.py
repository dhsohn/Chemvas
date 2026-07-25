from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import QRectF

from chemvas.ui.input_view_access import (
    CanvasSceneRectStateSnapshot,
    set_scene_rect_for,
    update_viewport_for,
)
from chemvas.ui.sheet_setup_logic import SHEET_MARGIN_PX, sheet_dimensions_px
from chemvas.ui.sheet_setup_state import (
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)

_MISSING_ATTRIBUTE = object()


def _add_sheet_setup_recovery_note(
    original_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    original_error.add_note(
        f"Sheet setup rollback also failed during {phase}: "
        f"{type(rollback_error).__name__}: {rollback_error}"
    )


@dataclass(slots=True)
class _SheetSetupSavepoint:
    canvas: object
    state: object
    size_name: object
    orientation: object
    rect: QRectF
    sheet_size: object
    sheet_orientation: object
    active: bool = True

    @classmethod
    def capture(cls, canvas) -> _SheetSetupSavepoint:
        state = sheet_setup_state_for(canvas)
        return cls(
            canvas=canvas,
            state=state,
            size_name=state.size_name,
            orientation=state.orientation,
            rect=QRectF(state.rect),
            sheet_size=getattr(canvas, "sheet_size", _MISSING_ATTRIBUTE),
            sheet_orientation=getattr(
                canvas,
                "sheet_orientation",
                _MISSING_ATTRIBUTE,
            ),
        )

    def restore(self) -> tuple[Exception, ...]:
        if not self.active:
            return ()
        errors: list[Exception] = []
        operations = (
            lambda: setattr(self.state, "size_name", self.size_name),
            lambda: setattr(self.state, "orientation", self.orientation),
            lambda: setattr(self.state, "rect", QRectF(self.rect)),
            lambda: self._restore_canvas_attribute("sheet_size", self.sheet_size),
            lambda: self._restore_canvas_attribute(
                "sheet_orientation",
                self.sheet_orientation,
            ),
        )
        for operation in operations:
            try:
                operation()
            except Exception as error:
                errors.append(error)
        self.active = False
        return tuple(errors)

    def _restore_canvas_attribute(self, name: str, value: object) -> None:
        if value is _MISSING_ATTRIBUTE:
            if hasattr(self.canvas, name):
                delattr(self.canvas, name)
            return
        setattr(self.canvas, name, value)

    def release(self) -> None:
        self.active = False


def _run_sheet_setup_transaction(canvas, operation: Callable[[], None]) -> None:
    state_savepoint = _SheetSetupSavepoint.capture(canvas)
    rect_savepoint = CanvasSceneRectStateSnapshot.capture(canvas)
    try:
        operation()
    except Exception as original_error:
        for rollback_error in state_savepoint.restore():
            _add_sheet_setup_recovery_note(
                original_error,
                rollback_error,
                phase="sheet state restore",
            )
        try:
            rect_savepoint.restore()
        except Exception as rect_restore_error:
            _add_sheet_setup_recovery_note(
                original_error,
                rect_restore_error,
                phase="scene/view rect restore",
            )
        for rect_recovery_error in rect_savepoint.recovery_errors:
            _add_sheet_setup_recovery_note(
                original_error,
                rect_recovery_error,
                phase="scene/view rect restore",
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
    sheet_setup_state_for(canvas).rect = sheet_rect
    set_scene_rect_for(canvas, scene_rect)


def _verify_sheet_setup_success(
    canvas,
    expected_size: str,
    expected_orientation: str,
) -> None:
    expected_sheet_rect, expected_scene_rect = _expected_rects(
        expected_size,
        expected_orientation,
    )
    state = sheet_setup_state_for(canvas)
    if (
        state.size_name != expected_size
        or state.orientation != expected_orientation
        or state.rect != expected_sheet_rect
        or getattr(canvas, "sheet_size", None) != expected_size
        or getattr(canvas, "sheet_orientation", None) != expected_orientation
    ):
        raise RuntimeError("sheet setup changed during successful finalization")

    scene_getter = getattr(canvas, "scene", None)
    scene = scene_getter() if callable(scene_getter) else None
    scene_rect_getter = getattr(scene, "sceneRect", None)
    if (
        callable(scene_rect_getter)
        and QRectF(scene_rect_getter()) != expected_scene_rect
    ):
        raise RuntimeError("sheet scene rect changed during successful finalization")
    view_rect_getter = getattr(canvas, "sceneRect", None)
    if callable(view_rect_getter) and QRectF(view_rect_getter()) != expected_scene_rect:
        raise RuntimeError("sheet view rect changed during successful finalization")


def apply_sheet_scene_rect_for(canvas) -> None:
    def apply() -> None:
        expected_size, expected_orientation = sheet_setup_for(canvas)
        _apply_sheet_scene_rect_unchecked(canvas)
        _verify_sheet_setup_success(
            canvas,
            expected_size,
            expected_orientation,
        )

    _run_sheet_setup_transaction(canvas, apply)


def sheet_rect_for(canvas) -> QRectF:
    return QRectF(sheet_setup_state_for(canvas).rect)


def scene_pos_in_sheet_for(canvas, pos) -> bool:
    rect = sheet_rect_for(canvas)
    if rect.isNull() or rect.isEmpty():
        return True
    return rect.contains(pos)


def set_sheet_setup_for(canvas, size_name: str, orientation: str) -> None:
    def apply() -> None:
        expected_size, expected_orientation = set_sheet_setup_state_for(
            canvas,
            size_name,
            orientation,
        )
        _apply_sheet_scene_rect_unchecked(canvas)
        update_viewport_for(canvas)
        _verify_sheet_setup_success(
            canvas,
            expected_size,
            expected_orientation,
        )

    _run_sheet_setup_transaction(canvas, apply)


__all__ = [
    "apply_sheet_scene_rect_for",
    "scene_pos_in_sheet_for",
    "set_sheet_setup_for",
    "sheet_orientation_for",
    "sheet_rect_for",
    "sheet_setup_for",
    "sheet_size_for",
]
