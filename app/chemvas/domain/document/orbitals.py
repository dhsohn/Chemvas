"""Qt-free orbital geometry; lobe paths are a rendering detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class Orbital:
    kind: str
    center: tuple[float, float]
    scale: float = 1.0
    rotation: float = 0.0


def orbital_from_state(state: Mapping[str, object]) -> Orbital:
    center = cast("tuple[float, float]", state["center"])
    return Orbital(
        kind=str(state.get("orbital_kind", "s")),
        center=(float(center[0]), float(center[1])),
        scale=float(cast("float", state.get("scale", 1.0))),
        rotation=float(cast("float", state.get("rotation", 0.0))),
    )


def orbital_to_state(orbital: Orbital) -> dict[str, object]:
    return {
        "kind": "orbital",
        "orbital_kind": orbital.kind,
        "center": orbital.center,
        "scale": orbital.scale,
        "rotation": orbital.rotation,
    }
