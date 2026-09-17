"""A transition-state bracket as document data, independent of how it is drawn.

The desktop editor keeps a bracket's rectangle and kind on the
``QGraphicsPathItem`` that draws it and reads them back when saving.
``TSBracket`` is the same information as a Qt-free value, following ``Shape``:
``validate_ts_bracket_fields`` says which states are brackets,
``ts_bracket_from_state`` turns a valid state into a record, and
``ts_bracket_to_state`` writes the record back as the state it came from.
``ts_bracket_from_state`` holds numbers as floats, so a state whose numbers were
ints or floats comes back equal and a ``Decimal`` comes back as the float of the
same value. A bracket has no colour or stroke of its own; the editor derives
both from the document's bond settings, and the dagger kinds are glyphs in the
document font. A ``TSBracket`` that is not a valid bracket state cannot be
constructed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from .state import validate_ts_bracket_fields

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, kw_only=True)
class TSBracket:
    left: float
    top: float
    right: float
    bottom: float
    bracket_kind: str

    def __post_init__(self) -> None:
        # Edits build new records with dataclasses.replace; a record that
        # could not be saved must fail here, not when the document is written.
        validate_ts_bracket_fields(
            ts_bracket_to_state(self), error="Invalid TS bracket."
        )


def ts_bracket_from_state(
    state: Mapping[str, object], *, error: str = "Invalid Chemvas file."
) -> TSBracket:
    validate_ts_bracket_fields(state, error=error)
    return TSBracket(
        left=float(cast("Any", state["left"])),
        top=float(cast("Any", state["top"])),
        right=float(cast("Any", state["right"])),
        bottom=float(cast("Any", state["bottom"])),
        bracket_kind=cast("str", state["bracket_kind"]),
    )


def ts_bracket_to_state(ts_bracket: TSBracket) -> dict[str, object]:
    return {
        "kind": "ts_bracket",
        "left": ts_bracket.left,
        "top": ts_bracket.top,
        "right": ts_bracket.right,
        "bottom": ts_bracket.bottom,
        "bracket_kind": ts_bracket.bracket_kind,
    }


def normalized_ts_bracket(ts_bracket: TSBracket) -> TSBracket:
    """The canonical form of a bracket record: an ordered rectangle.

    The desktop editor has applied the same rule by pushing the corners through
    ``QRectF.normalized()``. What that round trip also does and this function
    deliberately does not is recompute edges from a width and a height, which
    can move one by a few floating-point units (10.2 has come back as
    10.199999999999989).
    """
    left, right = sorted((ts_bracket.left, ts_bracket.right))
    top, bottom = sorted((ts_bracket.top, ts_bracket.bottom))
    return replace(ts_bracket, left=left, top=top, right=right, bottom=bottom)


__all__ = [
    "TSBracket",
    "normalized_ts_bracket",
    "ts_bracket_from_state",
    "ts_bracket_to_state",
]
