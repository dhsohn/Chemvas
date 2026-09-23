"""Arrow and line document values; graphics are derived from these records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from .state import validate_arrow_fields

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, kw_only=True)
class Arrow:
    kind: str
    start: tuple[float, float]
    end: tuple[float, float]
    control: tuple[float, float] | None = None
    double: bool = False
    color: str | None = None
    mirrored: bool = False
    labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        validate_arrow_fields(arrow_to_state(self), error="Invalid arrow.")


def arrow_from_state(state: Mapping[str, object]) -> Arrow:
    validate_arrow_fields(state, error="Invalid arrow.")
    start = cast("tuple[float, float]", state["start"])
    end = cast("tuple[float, float]", state["end"])
    control = cast("tuple[float, float] | None", state.get("control"))
    labels = cast("Mapping[str, str]", state.get("labels", {}))
    return Arrow(
        kind=cast("str", state["kind"]),
        start=(float(start[0]), float(start[1])),
        end=(float(end[0]), float(end[1])),
        control=None if control is None else (float(control[0]), float(control[1])),
        double=bool(state.get("double", False)),
        color=cast("str | None", state.get("color")),
        mirrored=bool(state.get("mirrored", False)),
        labels=tuple(labels.items()),
    )


def arrow_to_state(arrow: Arrow) -> dict[str, object]:
    state: dict[str, object] = {
        "kind": arrow.kind,
        "start": arrow.start,
        "end": arrow.end,
        "control": arrow.control,
        "double": arrow.double,
    }
    if arrow.color is not None:
        state["color"] = arrow.color
    if arrow.mirrored:
        state["mirrored"] = True
    if arrow.labels:
        state["labels"] = dict(arrow.labels)
    return state
