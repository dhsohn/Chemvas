from __future__ import annotations

from collections.abc import Iterable


def connected_atom_components(
    atom_ids: Iterable[int],
    bond_pairs: Iterable[tuple[int, int]],
) -> tuple[tuple[int, ...], ...]:
    """Return complete atom components in stable minimum-atom order."""

    nodes = set(atom_ids)
    adjacency: dict[int, set[int]] = {atom_id: set() for atom_id in nodes}
    for first, second in bond_pairs:
        if first not in adjacency or second not in adjacency:
            continue
        adjacency[first].add(second)
        adjacency[second].add(first)

    remaining = set(nodes)
    components: list[tuple[int, ...]] = []
    while remaining:
        stack = [min(remaining)]
        component: set[int] = set()
        while stack:
            atom_id = stack.pop()
            if atom_id in component:
                continue
            component.add(atom_id)
            stack.extend(adjacency[atom_id] - component)
        remaining -= component
        components.append(tuple(sorted(component)))
    return tuple(components)


__all__ = ["connected_atom_components"]
