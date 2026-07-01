from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(slots=True)
class PasteApplyResult:
    atom_id_map: dict[int, int] = field(default_factory=dict)
    new_atom_ids: set[int] = field(default_factory=set)
    added_scene_items: list[object] = field(default_factory=list)

    def has_changes(self) -> bool:
        return bool(self.atom_id_map or self.added_scene_items)


def apply_paste_payload(
    *,
    atoms: Sequence[object],
    bonds: Sequence[object],
    rings: Sequence[object],
    marks: Sequence[object],
    scene_items: Sequence[object],
    dx: float,
    dy: float,
    add_atom: Callable[[str, float, float], int],
    apply_atom_color: Callable[[int, str], None],
    add_or_update_atom_label: Callable[..., None],
    add_bond: Callable[[int, int, int], int],
    restore_bond_from_state: Callable[[int, dict], None],
    translated_scene_item_state: Callable[..., dict | None],
    create_scene_item_from_state: Callable[[dict], object],
) -> PasteApplyResult:
    result = PasteApplyResult()

    for atom_state in atoms:
        if not isinstance(atom_state, dict):
            continue
        atom_id = atom_state.get("id")
        x = atom_state.get("x")
        y = atom_state.get("y")
        if not isinstance(atom_id, int) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        element = str(atom_state.get("element", "C"))
        new_atom_id = add_atom(element, float(x) + dx, float(y) + dy)
        result.atom_id_map[atom_id] = new_atom_id
        result.new_atom_ids.add(new_atom_id)
        color = atom_state.get("color")
        if isinstance(color, str):
            apply_atom_color(new_atom_id, color)
        if element.upper() == "C" and bool(atom_state.get("explicit_label", False)):
            add_or_update_atom_label(
                new_atom_id,
                element,
                clear_smiles=False,
                record=False,
                allow_merge=False,
                show_carbon=True,
            )

    for bond_state in bonds:
        if not isinstance(bond_state, dict):
            continue
        atom_a = bond_state.get("a")
        atom_b = bond_state.get("b")
        if not isinstance(atom_a, int) or not isinstance(atom_b, int):
            continue
        if atom_a not in result.atom_id_map or atom_b not in result.atom_id_map:
            continue
        new_a = result.atom_id_map[atom_a]
        new_b = result.atom_id_map[atom_b]
        # Defensively skip bonds a foreign/corrupt payload could contain rather
        # than letting add_bond raise mid-paste (which would leave the document
        # with atoms added but no bonds and no undo grouping). Mirrors the
        # isinstance guards used for atoms above.
        if new_a == new_b:
            continue
        try:
            order = int(bond_state.get("order", 1))
        except (TypeError, ValueError):
            continue
        if order not in (1, 2, 3):
            continue
        new_bond_id = add_bond(new_a, new_b, order)
        restore_bond_from_state(
            new_bond_id,
            {
                "a": new_a,
                "b": new_b,
                "order": order,
                "style": bond_state.get("style", "single"),
                "color": bond_state.get("color", "#000000"),
            },
        )

    for state_group in (rings, marks, scene_items):
        for state in state_group:
            translated_state = translated_scene_item_state(
                state,
                dx=dx,
                dy=dy,
                atom_id_map=result.atom_id_map,
            )
            if not translated_state:
                continue
            item = create_scene_item_from_state(translated_state)
            if item is not None:
                result.added_scene_items.append(item)

    return result


__all__ = ["PasteApplyResult", "apply_paste_payload"]
