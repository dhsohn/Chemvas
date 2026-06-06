from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import QRectF

from ui.canvas_state_lookup import canvas_state_object
from ui.sheet_setup_logic import (
    DEFAULT_SHEET_ORIENTATION,
    DEFAULT_SHEET_SIZE,
    normalize_sheet_setup,
)


@dataclass(slots=True)
class SheetSetupState:
    size_name: str = DEFAULT_SHEET_SIZE
    orientation: str = DEFAULT_SHEET_ORIENTATION
    rect: QRectF = field(default_factory=QRectF)


def sheet_setup_state_for(canvas: Any) -> SheetSetupState:
    state = canvas_state_object(canvas, "sheet_setup_state")
    if state is not None:
        return state
    size_name, orientation = normalize_sheet_setup(
        getattr(canvas, "sheet_size", DEFAULT_SHEET_SIZE),
        getattr(canvas, "sheet_orientation", DEFAULT_SHEET_ORIENTATION),
    )
    state = SheetSetupState(size_name=size_name, orientation=orientation)
    canvas.sheet_setup_state = state
    canvas.sheet_size = state.size_name
    canvas.sheet_orientation = state.orientation
    return state


def sheet_setup_values_for(canvas: Any) -> tuple[str, str]:
    state = sheet_setup_state_for(canvas)
    return state.size_name, state.orientation


def set_sheet_setup_state_for(canvas: Any, size_name: str, orientation: str) -> tuple[str, str]:
    size_name, orientation = normalize_sheet_setup(size_name, orientation)
    state = sheet_setup_state_for(canvas)
    state.size_name = size_name
    state.orientation = orientation
    canvas.sheet_size = size_name
    canvas.sheet_orientation = orientation
    return size_name, orientation


__all__ = [
    "SheetSetupState",
    "set_sheet_setup_state_for",
    "sheet_setup_state_for",
    "sheet_setup_values_for",
]
