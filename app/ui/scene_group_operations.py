from __future__ import annotations

from ui.canvas_atom_graphics_state import visible_atom_item_for
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_group_state import (
    group_ids_for_members_for,
    group_state_for,
    register_group_for,
    remove_group_for,
)
from ui.canvas_model_access import atoms_for, bonds_for
from ui.canvas_scene_items_state import ring_items_for
from ui.canvas_window_access import history_service_for_canvas
from ui.graph_algorithms import adjacency_for_bonds, connected_components_for_nodes
from ui.history_commands import GroupSceneItemsCommand, UngroupSceneItemsCommand
from ui.scene_item_access import attached_canvas_scene_items
from ui.scene_item_state_serialization import ARROW_KINDS
from ui.selection_collection_access import (
    TRANSFORM_SELECTION_EXCLUDED_KINDS,
    selected_atom_ids_for_transform_for,
    selected_scene_items_for,
)
from ui.selection_scene_access import set_scene_items_selected_for
from ui.selection_service_access import (
    refresh_selection_outline_for,
    select_note_for,
)

GROUPABLE_STANDALONE_KINDS = frozenset({"note", "ts_bracket", "shape", "orbital"}) | frozenset(ARROW_KINDS)


def _is_standalone_mark(canvas, item) -> bool:
    data = item.data(1)
    atom_id = data.get("atom_id") if isinstance(data, dict) else None
    # Atom-bound marks already travel with their atom; only free-floating marks
    # are independent objects that a group needs to track.
    return not (isinstance(atom_id, int) and atom_id in atoms_for(canvas))


def _is_groupable_standalone_item(canvas, item) -> bool:
    kind = item.data(0)
    if kind in GROUPABLE_STANDALONE_KINDS:
        return True
    if kind == "mark":
        return _is_standalone_mark(canvas, item)
    return False


def _selected_group_members_for(canvas) -> tuple[set[int], list]:
    atom_ids = {
        atom_id
        for atom_id in selected_atom_ids_for_transform_for(canvas)
        if atom_id in atoms_for(canvas)
    }
    items = [
        item
        for item in selected_scene_items_for(canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS)
        if _is_groupable_standalone_item(canvas, item)
    ]
    return atom_ids, items


def _selection_unit_count_for(canvas, atom_ids: set[int], items: list) -> int:
    components = connected_components_for_nodes(
        atom_ids,
        adjacency_for_bonds(bonds_for(canvas)),
    )
    return len(components) + len(items)


def group_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    if not atom_ids and not items:
        return False
    if _selection_unit_count_for(canvas, atom_ids, items) < 2:
        return False
    state = group_state_for(canvas)
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if len(overlapping) == 1:
        existing = state.groups[next(iter(overlapping))]
        if existing.atom_ids == atom_ids and len(existing.items) == len(items):
            existing_items = set(map(id, existing.items))
            if all(id(item) in existing_items for item in items):
                return False
    absorbed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    command = GroupSceneItemsCommand(atom_ids=set(atom_ids), items=list(items), absorbed=absorbed)
    for absorbed_id, _ in absorbed:
        remove_group_for(canvas, absorbed_id)
    command.group_id = register_group_for(canvas, atom_ids, items)
    history_service_for_canvas(canvas).push(command)
    return True


def ungroup_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    state = group_state_for(canvas)
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if not overlapping:
        return False
    removed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    for group_id, _ in removed:
        remove_group_for(canvas, group_id)
    history_service_for_canvas(canvas).push(UngroupSceneItemsCommand(removed=removed))
    return True


def _structure_items_for_atom_ids(canvas, atom_ids: set[int]) -> list:
    items: list = []
    for atom_id in atom_ids:
        atom_item = visible_atom_item_for(canvas, atom_id)
        if atom_item is not None:
            items.append(atom_item)
    for bond_id, bond in enumerate(bonds_for(canvas)):
        if bond is None:
            continue
        if bond.a not in atom_ids or bond.b not in atom_ids:
            continue
        items.extend(bond_items_for_id(canvas, bond_id))
    for ring_item in ring_items_for(canvas):
        ring_atom_ids = ring_item.data(2)
        if isinstance(ring_atom_ids, list) and ring_atom_ids and all(
            atom_id in atom_ids for atom_id in ring_atom_ids
        ):
            items.append(ring_item)
    return items


def group_selection_targets_for(canvas, targets: list) -> list:
    """Extend shift-click toggle targets so grouped objects toggle as a unit."""
    state = group_state_for(canvas)
    if not state.groups or not targets:
        return targets
    atom_ids = {
        item.data(1)
        for item in targets
        if item.data(0) == "atom" and isinstance(item.data(1), int)
    }
    for item in targets:
        if item.data(0) != "bond":
            continue
        bond_id = item.data(1)
        bonds = bonds_for(canvas)
        if isinstance(bond_id, int) and 0 <= bond_id < len(bonds) and bonds[bond_id] is not None:
            atom_ids.update((bonds[bond_id].a, bonds[bond_id].b))
    group_ids = group_ids_for_members_for(canvas, atom_ids, targets)
    if not group_ids:
        return targets
    extended = list(targets)
    seen = set(map(id, extended))
    member_atom_ids: set[int] = set()
    for group_id in group_ids:
        group = state.groups[group_id]
        member_atom_ids.update(group.atom_ids)
        for member in attached_canvas_scene_items(canvas, group.items):
            if id(member) not in seen:
                seen.add(id(member))
                extended.append(member)
    for structure_item in _structure_items_for_atom_ids(canvas, member_atom_ids):
        if id(structure_item) not in seen:
            seen.add(id(structure_item))
            extended.append(structure_item)
    return extended


def expand_selection_to_groups_for(canvas) -> None:
    state = group_state_for(canvas)
    if state.expanding or not state.groups:
        return
    atom_ids, items = _selected_group_members_for(canvas)
    selected_items = selected_scene_items_for(canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS)
    if not atom_ids and not selected_items:
        return
    group_ids = group_ids_for_members_for(canvas, atom_ids, selected_items)
    if not group_ids:
        return
    member_atom_ids: set[int] = set()
    member_items: list = []
    for group_id in group_ids:
        group = state.groups[group_id]
        member_atom_ids.update(group.atom_ids)
        member_items.extend(attached_canvas_scene_items(canvas, group.items))
    member_atom_ids &= set(atoms_for(canvas))
    selected_ids = set(map(id, selected_items))
    missing_atoms = member_atom_ids - atom_ids
    missing_items = [item for item in member_items if id(item) not in selected_ids]
    if not missing_atoms and not missing_items:
        return
    state.expanding = True
    try:
        scene_items = _structure_items_for_atom_ids(canvas, member_atom_ids)
        scene_items.extend(item for item in missing_items if item.data(0) != "note")
        set_scene_items_selected_for(canvas, scene_items, True)
        for note in missing_items:
            if note.data(0) == "note":
                select_note_for(canvas, note, additive=True)
        refresh_selection_outline_for(canvas)
    finally:
        state.expanding = False


__all__ = [
    "GROUPABLE_STANDALONE_KINDS",
    "expand_selection_to_groups_for",
    "group_selection_for",
    "group_selection_targets_for",
    "ungroup_selection_for",
]
