from __future__ import annotations

from collections.abc import Callable
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


def ensure_canvas_state[T](
    canvas: Any,
    name: str,
    factory: Callable[[], T],
    *,
    runtime_field: bool = True,
) -> T:
    """Return the canvas state stored under ``name``, creating it on first use.

    One ``name`` covers lookup and attach, so the two can never diverge (a
    divergence would silently hand out a fresh empty state). States with
    ``runtime_field=True`` live as fields of the eagerly-built
    ``CanvasRuntimeState`` container on real canvases: if that container is
    present but lacks the field, the accessor and the container are out of
    sync (e.g. a renamed field), and creating a shadow copy on the canvas
    would split the state in two — fail loudly instead. ``runtime_field=False``
    states (model, renderer, ...) are stored as direct canvas attributes; a
    ``runtime_state`` entry still wins for them, but its absence is normal.
    Plain attribute storage remains the fallback that keeps lightweight test
    doubles working.
    """
    runtime_state = getattr(canvas, "runtime_state", None)
    if runtime_state is not None:
        state = getattr(runtime_state, name, None)
        if state is not None:
            return state
        if runtime_field and getattr(runtime_state, "STRICT_STATE_CONTAINER", False):
            msg = (
                f"CanvasRuntimeState has no state field {name!r}; "
                "the state accessor and the runtime container are out of sync"
            )
            raise AttributeError(msg)
    state = getattr(canvas, name, None)
    if state is not None:
        return state
    state = factory()
    setattr(canvas, name, state)
    return state


__all__ = ["canvas_state_object", "ensure_canvas_state"]
