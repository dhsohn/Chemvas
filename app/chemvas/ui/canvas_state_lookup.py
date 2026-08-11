from __future__ import annotations

from typing import Any


def canvas_state_object(canvas: Any, name: str):
    public_name = name[1:] if name.startswith("_") else name

    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None:
        state = getattr(runtime_state, public_name, None)
        if state is not None:
            return state

    state = getattr(canvas, public_name, None)
    if state is not None:
        return state

    return None


__all__ = ["canvas_state_object"]
