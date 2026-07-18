from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence

from chemvas.domain.document import Bond


def refresh_bond_graphics(
    bond_id: int,
    *,
    bonds: Sequence[Bond | None],
    bond_items: MutableMapping[int, list[object]],
    remove_scene_item: Callable[[object], object],
    add_bond_graphics: Callable[[int], None],
    redraw_connected: bool = False,
    redraw_connected_bonds: Callable[[int, int | None], None] | None = None,
) -> bool:
    if not (0 <= bond_id < len(bonds)):
        return False
    bond = bonds[bond_id]
    if bond is None:
        return False
    selected = any(_is_selected(item) for item in bond_items.get(bond_id, ()))
    for item in bond_items.get(bond_id, []):
        remove_scene_item(item)
    bond_items[bond_id] = []
    add_bond_graphics(bond_id)
    if selected:
        for item in bond_items.get(bond_id, []):
            _set_selected(item, True)
    if redraw_connected and redraw_connected_bonds is not None:
        redraw_connected_bonds(bond.a, bond_id)
        redraw_connected_bonds(bond.b, bond_id)
    return True


def _is_selected(item: object) -> bool:
    is_selected = getattr(item, "isSelected", None)
    if callable(is_selected):
        return bool(is_selected())
    return False


def _set_selected(item: object, selected: bool) -> None:
    set_selected = getattr(item, "setSelected", None)
    if callable(set_selected):
        set_selected(selected)


__all__ = ["refresh_bond_graphics"]
