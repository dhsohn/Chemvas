"""Ring appearance and membership; the molecular graph owns its coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .model import Atom


@dataclass(frozen=True, slots=True)
class RingFill:
    atom_ids: tuple[int, ...]
    color: str | None
    alpha: float


def ring_fill_to_state(ring: RingFill, atoms: Mapping[int, Atom]) -> dict[str, object]:
    return {
        "kind": "ring",
        "points": [(atoms[i].x, atoms[i].y) for i in ring.atom_ids if i in atoms],
        "atom_ids": list(ring.atom_ids),
        "color": ring.color,
        "alpha": ring.alpha,
    }
