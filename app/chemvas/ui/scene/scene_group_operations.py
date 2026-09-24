from __future__ import annotations

from functools import wraps

from chemvas.features.graph import (
    adjacency_for_bonds,
    connected_components_for_nodes,
    reachable_from,
)
from chemvas.ui.annotations.projections import group_projections
from chemvas.ui.annotations.state import ARROW_KINDS
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_group_state import (
    group_ids_for_members_for,
    register_group_for,
)
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    require_scene_record_id,
    ring_items_for,
)
from chemvas.ui.canvas.canvas_window_access import (
    history_service_for_canvas,
    notify_error_for,
)
from chemvas.ui.history.history_commands import (
    GroupSceneItemsCommand,
    UngroupSceneItemsCommand,
)
from chemvas.ui.selection.selection_queries import (
    TRANSFORM_SELECTION_EXCLUDED_KINDS,
    append_selected_item_ids,
    scene_selected_items_for,
    selected_atom_ids_for_transform_for,
    selected_mark_atom_ids_for,
    selected_scene_items_for,
    selected_scene_notes_for,
)
from chemvas.ui.selection.selection_style_access import (
    selection_indicator_rect_for_atom_for,
)
from chemvas.ui.transactions.document import document_transaction

GROUPABLE_STANDALONE_KINDS = frozenset(
    {"note", "image", "ts_bracket", "shape", "orbital"}
) | frozenset(ARROW_KINDS)

GROUP_CONNECTION_MESSAGE = (
    "These structures belong to different groups. Select both structures, "
    "use Edit > Group, then retry the connection."
)


def group_connection_allowed_for(canvas, atom_ids: set[int]) -> bool:
    groups = canvas.runtime_state.group_state.groups
    if len(groups) < 2:
        return True
    connected = reachable_from(atom_ids, adjacency_for_bonds(canvas.model.bonds))
    if len(group_ids_for_members_for(canvas, connected, [])) < 2:
        return True
    notify_error_for(canvas, GROUP_CONNECTION_MESSAGE)
    return False


def group_extensions_for_added_bonds(canvas, bond_ids) -> list[GroupSceneItemsCommand]:
    """Plan same-id membership updates only for newly connected components."""
    groups = canvas.runtime_state.group_state.groups
    if not groups:
        return []
    bonds = canvas.model.bonds
    touched = {
        atom_id
        for bond_id in bond_ids
        if (bond := bonds[bond_id]) is not None
        for atom_id in (bond.a, bond.b)
    }
    if not touched:
        return []
    adjacency = adjacency_for_bonds(bonds)
    updates: dict[int, set[int]] = {}
    while touched:
        component = reachable_from({min(touched)}, adjacency)
        touched -= component
        owners = group_ids_for_members_for(canvas, component, [])
        if len(owners) > 1:
            # GUI connection entry points preflight this before drawing. Keep
            # direct recording callers fail-closed too; their mutation is undone.
            raise ValueError(GROUP_CONNECTION_MESSAGE)
        if owners:
            owner = next(iter(owners))
            updates.setdefault(owner, set(groups[owner].atom_ids)).update(component)
    return [
        GroupSceneItemsCommand(
            atom_ids=atom_ids,
            item_ids=list(groups[group_id].item_ids),
            absorbed=[(group_id, groups[group_id])],
            group_id=group_id,
        )
        for group_id, atom_ids in sorted(updates.items())
        if atom_ids != groups[group_id].atom_ids
    ]


def group_updates_for_atom_merge(
    canvas, survivor_id: int, removed_atom_ids: set[int]
) -> list[GroupSceneItemsCommand]:
    """Retain one group's identity after a preflighted overlapping-atom merge."""
    groups = canvas.runtime_state.group_state.groups
    if not groups or not removed_atom_ids:
        return []
    component = reachable_from({survivor_id}, adjacency_for_bonds(canvas.model.bonds))
    owners = group_ids_for_members_for(canvas, component | removed_atom_ids, [])
    if len(owners) > 1:
        raise ValueError(GROUP_CONNECTION_MESSAGE)
    if not owners:
        return []
    group_id = next(iter(owners))
    previous = groups[group_id]
    atom_ids = (previous.atom_ids - removed_atom_ids) | component
    if atom_ids == previous.atom_ids:
        return []
    return [
        GroupSceneItemsCommand(
            atom_ids=atom_ids,
            item_ids=list(previous.item_ids),
            absorbed=[(group_id, previous)],
            group_id=group_id,
        )
    ]


def _atomic_group_change(operation):
    @wraps(operation)
    def run(canvas, *args, **kwargs):
        history = history_service_for_canvas(canvas)
        with document_transaction(canvas, history_service=history):
            return operation(canvas, *args, **kwargs)

    return run


def _push_group_command(canvas, command) -> None:
    """Publish within the caller's document transaction; it owns failed edits."""
    history = history_service_for_canvas(canvas)
    if history.push(command) is False:
        raise RuntimeError("Group history push did not commit")


def _bound_mark_atom_id(canvas, item) -> int | None:
    if item.data(0) != "mark":
        return None
    data = item.data(1)
    atom_id = data.get("atom_id") if isinstance(data, dict) else None
    if isinstance(atom_id, int) and atom_id in canvas.model.atoms:
        return atom_id
    return None


def _is_standalone_mark(canvas, item) -> bool:
    # Atom-bound marks already travel with their atom; only free-floating marks
    # are independent objects that a group needs to track.
    return _bound_mark_atom_id(canvas, item) is None


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
        if atom_id in canvas.model.atoms
    }
    # A selected atom-bound mark stands in for its atom (charges travel with the
    # atom), so grouping/ungrouping via the mark reaches the atom's group.
    atom_ids |= selected_mark_atom_ids_for(canvas)
    items = [
        item
        for item in selected_scene_items_for(
            canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS
        )
        if _is_groupable_standalone_item(canvas, item)
    ]
    return atom_ids, items


def _selection_unit_count_for(canvas, atom_ids: set[int], items: list) -> int:
    components = connected_components_for_nodes(
        atom_ids,
        adjacency_for_bonds(canvas.model.bonds),
    )
    return len(components) + len(items)


@_atomic_group_change
def group_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    if not atom_ids and not items:
        return False
    # A persistent group owns whole molecules. Literal partial-atom selection
    # remains available for direct reshaping, but must not create a group whose
    # later drag stretches bonds to ungrouped atoms in the same molecule.
    adjacency = adjacency_for_bonds(canvas.model.bonds)
    atom_ids = reachable_from(atom_ids, adjacency)
    state = canvas.runtime_state.group_state
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if not overlapping and _selection_unit_count_for(canvas, atom_ids, items) < 2:
        notify_error_for(
            canvas,
            "Group needs at least two objects: a molecule is one object. "
            "Select its caption or another object too, then use Edit > Group.",
        )
        return False
    merged_atom_ids = set(atom_ids)
    merged_items = [require_scene_record_id(item) for item in items]
    merged_item_ids = set(merged_items)
    absorbed_ids: set[int] = set()
    # Older documents may contain partial-molecule groups. Only normalize those
    # explicitly absorbed by this Group action, including groups reached when
    # their remaining molecule atoms join the new group.
    while remaining := overlapping - absorbed_ids:
        for group_id in sorted(remaining):
            group = state.groups[group_id]
            merged_atom_ids |= group.atom_ids
            for member in group.item_ids:
                if member not in merged_item_ids:
                    merged_item_ids.add(member)
                    merged_items.append(member)
        absorbed_ids |= remaining
        merged_atom_ids = reachable_from(merged_atom_ids, adjacency)
        overlapping = {
            key
            for key, candidate in state.groups.items()
            if candidate.atom_ids & merged_atom_ids
            or set(candidate.item_ids) & set(merged_items)
        }
    if len(overlapping) == 1:
        # Selection adds nothing beyond the one group it overlaps: no-op.
        existing = state.groups[next(iter(overlapping))]
        existing_items = set(existing.item_ids)
        if merged_atom_ids <= existing.atom_ids and all(
            item in existing_items for item in merged_items
        ):
            return False
    absorbed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    command = GroupSceneItemsCommand(
        atom_ids=set(merged_atom_ids), item_ids=list(merged_items), absorbed=absorbed
    )
    for absorbed_id, _ in absorbed:
        canvas.runtime_state.group_state.groups.pop(absorbed_id, None)
    command.group_id = register_group_for(canvas, merged_atom_ids, merged_items)
    _push_group_command(canvas, command)
    canvas.services.selection.expand_selection_to_groups()
    canvas.services.selection.update_selection_outline()
    return True


@_atomic_group_change
def ungroup_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    state = canvas.runtime_state.group_state
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if not overlapping:
        return False
    removed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    for group_id, _ in removed:
        canvas.runtime_state.group_state.groups.pop(group_id, None)
    _push_group_command(canvas, UngroupSceneItemsCommand(removed=removed))
    canvas.services.selection.update_selection_outline()
    return True


def _structure_items_for_atom_ids(canvas, atom_ids: set[int]) -> list:
    items: list = []
    registry = mark_registry_for(canvas)
    for atom_id in atom_ids:
        atom_item = visible_atom_item_for(canvas, atom_id)
        if atom_item is not None:
            items.append(atom_item)
        # Atom-bound marks travel with their atom, so they select and deselect
        # as part of the structure; a lingering Qt-selected charge mark would
        # otherwise keep re-triggering its atom's group after a deselect.
        items.extend(registry.get_for_atom(atom_id) or [])
    for bond_id, bond in enumerate(canvas.model.bonds):
        if bond is None:
            continue
        if bond.a not in atom_ids or bond.b not in atom_ids:
            continue
        items.extend(
            canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, [])
        )
    for ring_item in ring_items_for(canvas):
        ring_atom_ids = ring_item.data(2)
        if (
            isinstance(ring_atom_ids, list)
            and ring_atom_ids
            and all(atom_id in atom_ids for atom_id in ring_atom_ids)
        ):
            items.append(ring_item)
    return items


def group_selection_targets_for(canvas, targets: list) -> list:
    """Extend shift-click toggle targets so grouped objects toggle as a unit."""
    state = canvas.runtime_state.group_state
    if not state.groups or not targets:
        return targets
    atom_ids: set[int] = set()
    bond_ids: set[int] = set()
    for item in targets:
        append_selected_item_ids(canvas, atom_ids, bond_ids, item)
        # An atom-bound mark stands in for its atom; it is not stored in
        # group.item_ids, so it must resolve to the atom to reach the group.
        mark_atom_id = _bound_mark_atom_id(canvas, item)
        if mark_atom_id is not None:
            atom_ids.add(mark_atom_id)
    bonds = canvas.model.bonds
    for bond_id in bond_ids:
        if 0 <= bond_id < len(bonds) and bonds[bond_id] is not None:
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
        for member in group_projections(canvas, group.item_ids):
            if id(member) not in seen:
                seen.add(id(member))
                extended.append(member)
    for structure_item in _structure_items_for_atom_ids(canvas, member_atom_ids):
        if id(structure_item) not in seen:
            seen.add(id(structure_item))
            extended.append(structure_item)
    return extended


def _group_has_scene_members(canvas, group) -> bool:
    if group.atom_ids & set(canvas.model.atoms):
        return True
    return any(
        member.data(0) != "note" for member in group_projections(canvas, group.item_ids)
    )


def selected_group_rects_for(canvas) -> list:
    """Scene rects of groups intersecting the current selection.

    The selection outline draws one ChemDraw-style dashed box per selected
    group so grouped objects visibly act as a unit. Boxes key off Qt scene
    selection (matching the expansion trigger); only notes-only groups key off
    the explicit note selection, since they have no scene-selectable members.
    """
    state = canvas.runtime_state.group_state
    if not state.groups:
        return []
    atom_ids = {
        atom_id
        for atom_id in selected_atom_ids_for_transform_for(canvas)
        if atom_id in canvas.model.atoms
    }
    trigger_items = [
        item
        for item in scene_selected_items_for(canvas)
        if _is_groupable_standalone_item(canvas, item)
    ]
    group_ids = group_ids_for_members_for(
        canvas,
        atom_ids | selected_mark_atom_ids_for(canvas),
        trigger_items,
    )
    # A notes-only group must never be scene-triggered (e.g. by a lingering
    # Qt-selected note): its box is gated exclusively by the full note-service
    # selection check below, so it never claims notes a drag would not move.
    group_ids = {
        group_id
        for group_id in group_ids
        if _group_has_scene_members(canvas, state.groups[group_id])
    }
    selected_notes = selected_scene_notes_for(canvas)
    if selected_notes:
        for group_id, group in state.groups.items():
            if group_id in group_ids or _group_has_scene_members(canvas, group):
                continue
            member_notes = [
                member
                for member in group_projections(canvas, group.item_ids)
                if member.data(0) == "note"
            ]
            # Draw the box only when the whole note group is selected, so it
            # never claims more than drag/delete/copy would actually act on.
            if member_notes and all(
                any(member is note for note in selected_notes)
                for member in member_notes
            ):
                group_ids.add(group_id)
    if not group_ids:
        return []
    live_atom_ids = set(canvas.model.atoms)
    pad = canvas.renderer.style.bond_length_px * 0.18
    rects = []
    for group_id in sorted(group_ids):
        group = state.groups[group_id]
        rect = None
        for atom_id in group.atom_ids & live_atom_ids:
            atom_rect = selection_indicator_rect_for_atom_for(canvas, atom_id)
            if atom_rect is None:
                continue
            rect = atom_rect if rect is None else rect.united(atom_rect)
        for member in group_projections(canvas, group.item_ids):
            member_rect = member.sceneBoundingRect()
            rect = member_rect if rect is None else rect.united(member_rect)
        if rect is not None:
            rects.append(rect.adjusted(-pad, -pad, pad, pad))
    return rects


def notes_only_group_member_notes_for(canvas, note) -> list:
    """Attached note members of the notes-only group containing ``note``.

    Returns an empty list for ungrouped notes, members of mixed groups (those
    expand through the scene selectionChanged hook), or while a group
    expansion is already applying a selection change.
    """
    state = canvas.runtime_state.group_state
    if state.expanding or not state.groups:
        return []
    for group in state.groups.values():
        if require_scene_record_id(note) not in group.item_ids:
            continue
        if _group_has_scene_members(canvas, group):
            continue
        return [
            member
            for member in group_projections(canvas, group.item_ids)
            if member.data(0) == "note"
        ]
    return []


__all__ = [
    "GROUPABLE_STANDALONE_KINDS",
    "group_connection_allowed_for",
    "group_extensions_for_added_bonds",
    "group_selection_for",
    "group_selection_targets_for",
    "group_updates_for_atom_merge",
    "notes_only_group_member_notes_for",
    "selected_group_rects_for",
    "ungroup_selection_for",
]
