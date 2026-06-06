from __future__ import annotations

from typing import Any

from core.model import MoleculeModel

from ui.canvas_state_lookup import canvas_state_object


def model_for(canvas: Any) -> Any:
    model = canvas_state_object(canvas, "model")
    if model is not None:
        return model
    model = MoleculeModel()
    canvas.model = model
    return model


def set_model_for(canvas: Any, model: Any) -> None:
    canvas.model = model


__all__ = ["model_for", "set_model_for"]
