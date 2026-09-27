from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping, Sequence

    from chemvas.domain.document import Bond


class _SelectableItem(Protocol):
    def isSelected(self) -> bool: ...  # noqa: N802 - Qt name

    def setSelected(self, selected: bool) -> None: ...  # noqa: N802 - Qt name


def refresh_bond_graphics(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    bond_items: MutableMapping[int, list[_SelectableItem]],
    remove_scene_item: Callable[[_SelectableItem], object],
    add_bond_graphics: Callable[[int], None],
    redraw_connected: bool = False,
    redraw_connected_bonds: Callable[[int, int | None], None] | None = None,
) -> bool:
    if not (0 <= bond_id < len(bonds)):
        return False
    bond = bonds[bond_id]
    if bond is None:
        return False
    selected = any(item.isSelected() for item in bond_items.get(bond_id, ()))
    for item in bond_items.get(bond_id, []):
        remove_scene_item(item)
    bond_items[bond_id] = []
    add_bond_graphics(bond_id)
    if selected:
        for item in bond_items.get(bond_id, []):
            item.setSelected(True)
    if redraw_connected and redraw_connected_bonds is not None:
        redraw_connected_bonds(bond.a, bond_id)
        redraw_connected_bonds(bond.b, bond_id)
    return True


__all__ = ["refresh_bond_graphics"]
