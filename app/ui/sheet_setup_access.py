from __future__ import annotations

from PyQt6.QtCore import QRectF

from ui.input_view_access import set_scene_rect_for, update_viewport_for
from ui.sheet_setup_logic import (
    SHEET_MARGIN_PX,
    sheet_dimensions_px,
)
from ui.sheet_setup_state import (
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)


def sheet_setup_for(canvas) -> tuple[str, str]:
    return sheet_setup_values_for(canvas)


def sheet_size_for(canvas) -> str:
    return sheet_setup_for(canvas)[0]


def sheet_orientation_for(canvas) -> str:
    return sheet_setup_for(canvas)[1]


def apply_sheet_scene_rect_for(canvas) -> None:
    width, height = sheet_dimensions_px(*sheet_setup_for(canvas))
    state = sheet_setup_state_for(canvas)
    state.rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    set_scene_rect_for(
        canvas,
        state.rect.adjusted(
            -SHEET_MARGIN_PX,
            -SHEET_MARGIN_PX,
            SHEET_MARGIN_PX,
            SHEET_MARGIN_PX,
        )
    )


def sheet_rect_for(canvas) -> QRectF:
    return QRectF(sheet_setup_state_for(canvas).rect)


def set_sheet_setup_for(canvas, size_name: str, orientation: str) -> None:
    set_sheet_setup_state_for(canvas, size_name, orientation)
    apply_sheet_scene_rect_for(canvas)
    update_viewport_for(canvas)


__all__ = [
    "apply_sheet_scene_rect_for",
    "set_sheet_setup_for",
    "sheet_orientation_for",
    "sheet_rect_for",
    "sheet_setup_for",
    "sheet_size_for",
]
