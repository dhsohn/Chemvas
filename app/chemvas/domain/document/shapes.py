"""A free decorative shape as document data, independent of how it is drawn.

The desktop editor has kept a shape's geometry, kind, stroke and fill on the
``QGraphicsPathItem`` that draws it and read them back when saving. ``Shape`` is
the same information as a Qt-free value, so the saved form has one definition:
``validate_shape_fields`` says which states are shapes, ``shape_from_state`` turns
a valid state into a record, and ``shape_to_state`` writes the record back as the
state it came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .state import validate_shape_fields

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True, kw_only=True)
class Shape:
    left: float
    top: float
    right: float
    bottom: float
    shape_kind: str
    stroke_style: str
    # The two optional keys are independent in the format: a state may carry
    # either without the other, and an absent key stays absent.
    fill: str | None = None
    fill_alpha: float | None = None


def shape_from_state(
    state: Mapping[str, object], *, error: str = "Invalid Chemvas file."
) -> Shape:
    validate_shape_fields(state, error=error)
    fill_alpha = state.get("fill_alpha")
    return Shape(
        left=float(cast("Any", state["left"])),
        top=float(cast("Any", state["top"])),
        right=float(cast("Any", state["right"])),
        bottom=float(cast("Any", state["bottom"])),
        shape_kind=cast("str", state["shape_kind"]),
        stroke_style=cast("str", state["stroke_style"]),
        fill=cast("str | None", state.get("fill")),
        fill_alpha=None if fill_alpha is None else float(cast("Any", fill_alpha)),
    )


def shape_to_state(shape: Shape) -> dict[str, object]:
    state: dict[str, object] = {
        "kind": "shape",
        "left": shape.left,
        "top": shape.top,
        "right": shape.right,
        "bottom": shape.bottom,
        "shape_kind": shape.shape_kind,
        "stroke_style": shape.stroke_style,
    }
    if shape.fill is not None:
        state["fill"] = shape.fill
    if shape.fill_alpha is not None:
        state["fill_alpha"] = shape.fill_alpha
    return state


__all__ = ["Shape", "shape_from_state", "shape_to_state"]
