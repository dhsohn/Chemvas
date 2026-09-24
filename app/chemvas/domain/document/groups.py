"""Document group membership, independent of graphics and selection state."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class SceneGroup:
    atom_ids: set[int] = field(default_factory=set)
    item_ids: list[int] = field(default_factory=list)
