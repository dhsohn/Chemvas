from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace
from typing import Any

from chemvas.ui.canvas_runtime_state import CanvasRuntimeState

CANVAS_RUNTIME_STATE_FIELDS = frozenset(
    field.name for field in fields(CanvasRuntimeState)
)


def canvas_runtime_state(**states: Any) -> SimpleNamespace:
    """Partial canonical state container for focused legacy UI tests.

    State accessors read their field straight off ``canvas.runtime_state``, so a
    double needs one too. Names are checked against the real container: a test
    that invents a field would otherwise pin an accessor the product does not
    have.
    """
    unknown = sorted(set(states) - CANVAS_RUNTIME_STATE_FIELDS)
    if unknown:
        raise AssertionError(f"not CanvasRuntimeState fields: {unknown}")
    return SimpleNamespace(**states)


__all__ = ["CANVAS_RUNTIME_STATE_FIELDS", "canvas_runtime_state"]
