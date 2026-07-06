from __future__ import annotations

from typing import Any

from core.model import MoleculeModel

from ui.canvas_state_lookup import ensure_canvas_state


def model_for(canvas: Any) -> Any:
    return ensure_canvas_state(canvas, "model", MoleculeModel, runtime_field=False)


def set_model_for(canvas: Any, model: Any) -> None:
    canvas.model = model


__all__ = ["model_for", "set_model_for"]
