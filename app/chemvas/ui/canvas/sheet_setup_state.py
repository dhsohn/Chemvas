from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import QRectF

from chemvas.ui.canvas.sheet_setup_logic import (
    DEFAULT_SHEET_ORIENTATION,
    DEFAULT_SHEET_SIZE,
    normalize_sheet_setup,
    sheet_dimensions_px,
    sheet_scene_bounds,
)


@dataclass(slots=True)
class SheetSetupState:
    size_name: str = DEFAULT_SHEET_SIZE
    orientation: str = DEFAULT_SHEET_ORIENTATION
    custom_size_mm: tuple[float, float] | None = None
    rect: QRectF = field(default_factory=QRectF)


def sheet_rects(
    size_name: str, orientation: str, custom_size_mm: tuple[float, float] | None = None
) -> tuple[QRectF, QRectF]:
    width, height = sheet_dimensions_px(size_name, orientation, custom_size_mm)
    sheet_rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    scene_rect = QRectF(*sheet_scene_bounds(width, height))
    return sheet_rect, scene_rect


def sheet_setup_values_for(canvas: Any) -> tuple[str, str, tuple[float, float] | None]:
    state = canvas.runtime_state.sheet_setup_state
    return state.size_name, state.orientation, state.custom_size_mm


def set_sheet_setup_state_for(
    canvas: Any,
    size_name: str,
    orientation: str,
    custom_size_mm: tuple[float, float] | None = None,
) -> tuple[str, str, tuple[float, float] | None]:
    size_name, orientation, custom_size_mm = normalize_sheet_setup(
        size_name, orientation, custom_size_mm
    )
    state = canvas.runtime_state.sheet_setup_state
    state.custom_size_mm = custom_size_mm
    state.size_name = size_name
    state.orientation = orientation
    return size_name, orientation, custom_size_mm


__all__ = [
    "SheetSetupState",
    "set_sheet_setup_state_for",
    "sheet_rects",
    "sheet_setup_values_for",
]
