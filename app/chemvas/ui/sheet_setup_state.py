from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from PyQt6.QtCore import QRectF

from chemvas.ui.sheet_setup_logic import (
    DEFAULT_SHEET_ORIENTATION,
    DEFAULT_SHEET_SIZE,
    SHEET_MARGIN_PX,
    normalize_sheet_setup,
    sheet_dimensions_px,
)


@dataclass(slots=True)
class SheetSetupState:
    size_name: str = DEFAULT_SHEET_SIZE
    orientation: str = DEFAULT_SHEET_ORIENTATION
    rect: QRectF = field(default_factory=QRectF)


def sheet_rects(size_name: str, orientation: str) -> tuple[QRectF, QRectF]:
    width, height = sheet_dimensions_px(size_name, orientation)
    sheet_rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    scene_rect = sheet_rect.adjusted(
        -SHEET_MARGIN_PX,
        -SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
    )
    return sheet_rect, scene_rect


def sheet_setup_state_for(canvas: Any) -> SheetSetupState:
    return cast("SheetSetupState", canvas.runtime_state.sheet_setup_state)


def sheet_setup_values_for(canvas: Any) -> tuple[str, str]:
    state = sheet_setup_state_for(canvas)
    return state.size_name, state.orientation


def set_sheet_setup_state_for(
    canvas: Any, size_name: str, orientation: str
) -> tuple[str, str]:
    size_name, orientation = normalize_sheet_setup(size_name, orientation)
    state = sheet_setup_state_for(canvas)
    state.size_name = size_name
    state.orientation = orientation
    return size_name, orientation


__all__ = [
    "SheetSetupState",
    "set_sheet_setup_state_for",
    "sheet_rects",
    "sheet_setup_state_for",
    "sheet_setup_values_for",
]
