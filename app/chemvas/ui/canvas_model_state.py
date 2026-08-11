from __future__ import annotations

from typing import Any


def model_for(canvas: Any) -> Any:
    # Canvas setup creates the model, so a canvas without one is a wiring bug
    # rather than something to paper over with a fresh empty document.
    return canvas.model


def set_model_for(canvas: Any, model: Any) -> None:
    canvas.model = model


__all__ = ["model_for", "set_model_for"]
