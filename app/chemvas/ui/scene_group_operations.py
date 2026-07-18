from __future__ import annotations

from functools import wraps

from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_delete_transaction import canvas_delete_transaction
from chemvas.ui.canvas_group_state import (
    group_ids_for_members_for,
    group_state_for,
    register_group_for,
    remove_group_for,
)
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import atoms_for, bonds_for
from chemvas.ui.canvas_scene_items_state import remove_selected_note_for, ring_items_for
from chemvas.ui.canvas_window_access import history_service_for_canvas
from chemvas.ui.graph_algorithms import (
    adjacency_for_bonds,
    connected_components_for_nodes,
)
from chemvas.ui.history_commands import GroupSceneItemsCommand, UngroupSceneItemsCommand
from chemvas.ui.note_selection_box import update_note_selection_box_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_item_access import attached_canvas_scene_items
from chemvas.ui.scene_item_state_serialization import ARROW_KINDS
from chemvas.ui.selection_collection_access import (
    TRANSFORM_SELECTION_EXCLUDED_KINDS,
    append_selected_item_ids,
    selected_atom_ids_for_transform_for,
    selected_mark_atom_ids_for,
    selected_scene_items_for,
)
from chemvas.ui.selection_scene_access import (
    scene_selected_items_for,
    selected_scene_notes_for,
    set_scene_items_selected_for,
)
from chemvas.ui.selection_service_access import (
    refresh_selection_outline_for,
    select_note_for,
    toggle_note_selection_for,
)
from chemvas.ui.selection_style_access import selection_indicator_rect_for_atom_for

GROUPABLE_STANDALONE_KINDS = frozenset(
    {"note", "ts_bracket", "shape", "orbital"}
) | frozenset(ARROW_KINDS)


def _atomic_group_change(operation):
    @wraps(operation)
    def run(canvas, *args, **kwargs):
        history = history_service_for_canvas(canvas)
        with canvas_delete_transaction(canvas, history_service=history):
            return operation(canvas, *args, **kwargs)

    return run


def _push_group_command(canvas, command) -> None:
    history = history_service_for_canvas(canvas)
    try:
        history.push(command)
    except BaseException as original_error:
        try:
            command.undo(canvas)
        except BaseException as rollback_error:
            try:
                original_error.add_note(
                    "Group mutation rollback also encountered "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                )
            except BaseException:
                pass
        raise


def _bound_mark_atom_id(canvas, item) -> int | None:
    if item.data(0) != "mark":
        return None
    data = item.data(1)
    atom_id = data.get("atom_id") if isinstance(data, dict) else None
    if isinstance(atom_id, int) and atom_id in atoms_for(canvas):
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
        if atom_id in atoms_for(canvas)
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
        adjacency_for_bonds(bonds_for(canvas)),
    )
    return len(components) + len(items)


@_atomic_group_change
def group_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    if not atom_ids and not items:
        return False
    if _selection_unit_count_for(canvas, atom_ids, items) < 2:
        return False
    state = group_state_for(canvas)
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if len(overlapping) == 1:
        # Selection adds nothing beyond the one group it overlaps: no-op.
        existing = state.groups[next(iter(overlapping))]
        existing_items = set(map(id, existing.items))
        if atom_ids <= existing.atom_ids and all(
            id(item) in existing_items for item in items
        ):
            return False
    absorbed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    # Union semantics: an absorbed group's unselected members must join the
    # new group rather than silently losing their membership.
    merged_atom_ids = set(atom_ids)
    merged_items = list(items)
    merged_item_ids = set(map(id, merged_items))
    for _, group in absorbed:
        merged_atom_ids |= group.atom_ids
        for member in group.items:
            if id(member) not in merged_item_ids:
                merged_item_ids.add(id(member))
                merged_items.append(member)
    command = GroupSceneItemsCommand(
        atom_ids=set(merged_atom_ids), items=list(merged_items), absorbed=absorbed
    )
    for absorbed_id, _ in absorbed:
        remove_group_for(canvas, absorbed_id)
    command.group_id = register_group_for(canvas, merged_atom_ids, merged_items)
    _push_group_command(canvas, command)
    refresh_selection_outline_for(canvas)
    return True


@_atomic_group_change
def ungroup_selection_for(canvas) -> bool:
    atom_ids, items = _selected_group_members_for(canvas)
    state = group_state_for(canvas)
    overlapping = group_ids_for_members_for(canvas, atom_ids, items)
    if not overlapping:
        return False
    removed = [(group_id, state.groups[group_id]) for group_id in sorted(overlapping)]
    for group_id, _ in removed:
        remove_group_for(canvas, group_id)
    _push_group_command(canvas, UngroupSceneItemsCommand(removed=removed))
    refresh_selection_outline_for(canvas)
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
    for bond_id, bond in enumerate(bonds_for(canvas)):
        if bond is None:
            continue
        if bond.a not in atom_ids or bond.b not in atom_ids:
            continue
        items.extend(bond_items_for_id(canvas, bond_id))
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
    state = group_state_for(canvas)
    if not state.groups or not targets:
        return targets
    atom_ids: set[int] = set()
    bond_ids: set[int] = set()
    for item in targets:
        append_selected_item_ids(canvas, atom_ids, bond_ids, item)
        # An atom-bound mark stands in for its atom; it is not stored in
        # group.items, so it must resolve to the atom to reach the group.
        mark_atom_id = _bound_mark_atom_id(canvas, item)
        if mark_atom_id is not None:
            atom_ids.add(mark_atom_id)
    bonds = bonds_for(canvas)
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
        for member in attached_canvas_scene_items(canvas, group.items):
            if id(member) not in seen:
                seen.add(id(member))
                extended.append(member)
    for structure_item in _structure_items_for_atom_ids(canvas, member_atom_ids):
        if id(structure_item) not in seen:
            seen.add(id(structure_item))
            extended.append(structure_item)
    return extended


def _group_has_scene_members(canvas, group) -> bool:
    if group.atom_ids & set(atoms_for(canvas)):
        return True
    return any(
        member.data(0) != "note"
        for member in attached_canvas_scene_items(canvas, group.items)
    )


def selected_group_rects_for(canvas) -> list:
    """Scene rects of groups intersecting the current selection.

    The selection outline draws one ChemDraw-style dashed box per selected
    group so grouped objects visibly act as a unit. Boxes key off Qt scene
    selection (matching the expansion trigger); only notes-only groups key off
    the note-service selection, since they have no scene-selectable members.
    """
    state = group_state_for(canvas)
    if not state.groups:
        return []
    atom_ids = {
        atom_id
        for atom_id in selected_atom_ids_for_transform_for(canvas)
        if atom_id in atoms_for(canvas)
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
                for member in attached_canvas_scene_items(canvas, group.items)
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
    live_atom_ids = set(atoms_for(canvas))
    pad = bond_length_px_for(canvas) * 0.18
    rects = []
    for group_id in sorted(group_ids):
        group = state.groups[group_id]
        rect = None
        for atom_id in group.atom_ids & live_atom_ids:
            atom_rect = selection_indicator_rect_for_atom_for(canvas, atom_id)
            if atom_rect is None:
                continue
            rect = atom_rect if rect is None else rect.united(atom_rect)
        for member in attached_canvas_scene_items(canvas, group.items):
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
    state = group_state_for(canvas)
    if state.expanding or not state.groups:
        return []
    for group in state.groups.values():
        if not any(member is note for member in group.items):
            continue
        if _group_has_scene_members(canvas, group):
            continue
        return [
            member
            for member in attached_canvas_scene_items(canvas, group.items)
            if member.data(0) == "note"
        ]
    return []


def expand_note_selection_to_groups_for(canvas, note) -> None:
    """Select the remaining notes of a notes-only group when one is selected.

    Mixed groups expand through the scene selectionChanged hook; notes-only
    groups have no scene-selectable member, so the note service calls this
    when a note becomes selected to keep the group acting as a unit.
    """
    member_notes = notes_only_group_member_notes_for(canvas, note)
    if not member_notes:
        return
    selected_notes = selected_scene_notes_for(canvas)
    missing = [
        member
        for member in member_notes
        if not any(member is selected for selected in selected_notes)
    ]
    if not missing:
        return
    state = group_state_for(canvas)
    state.expanding = True
    try:
        for member in missing:
            select_note_for(canvas, member, additive=True)
    finally:
        state.expanding = False


def deselect_groups_for_note_for(canvas, note) -> None:
    """Deselect the whole group when one of its notes is deselected directly.

    Mirrors the scene-side unit rule: without this, deselecting a mixed
    group's note (note focus-out, NoteTool Ctrl-click) leaves the scene
    members selected, so the group box keeps spanning a note that a drag
    would leave behind.
    """
    state = group_state_for(canvas)
    if state.expanding or not state.groups:
        return
    target_groups = [
        group
        for group in state.groups.values()
        if any(member is note for member in group.items)
        and _group_has_scene_members(canvas, group)
    ]
    if not target_groups:
        return
    state.expanding = True
    try:
        for group in target_groups:
            live_atom_ids = group.atom_ids & set(atoms_for(canvas))
            members = attached_canvas_scene_items(canvas, group.items)
            scene_items = _structure_items_for_atom_ids(canvas, live_atom_ids)
            # Notes are included: attach_scene_item makes them Qt-selectable,
            # so a rubber-band-selected note would otherwise keep its Qt
            # selection and keep triggering the group box.
            scene_items.extend(members)
            set_scene_items_selected_for(canvas, scene_items, False)
            selected_notes = selected_scene_notes_for(canvas)
            for member in members:
                if member.data(0) != "note" or member is note:
                    continue
                if any(member is selected for selected in selected_notes):
                    remove_selected_note_for(canvas, member)
                    update_note_selection_box_for(canvas, member)
    finally:
        state.expanding = False


def _stale_group_notes_for(canvas, state, active_group_ids: set[int]) -> list:
    """Selected note members of groups that are no longer scene-selected.

    Qt's rubber band and clearSelection only touch scene selection, so once an
    expansion selects a group's note, nothing would ever deselect it — and a
    still-selected note would keep re-triggering the group. These notes must be
    dropped so the group deselects as a unit.
    """
    selected_notes = selected_scene_notes_for(canvas)
    if not selected_notes:
        return []
    stale: list = []
    for group_id, group in state.groups.items():
        if group_id in active_group_ids:
            continue
        member_notes = [
            note
            for note in selected_notes
            if any(member is note for member in group.items)
        ]
        if not member_notes:
            continue
        # A notes-only group is never scene-triggered; leave its manual
        # note-tool selection alone.
        if not _group_has_scene_members(canvas, group):
            continue
        stale.extend(member_notes)
    return stale


def expand_selection_to_groups_for(canvas) -> None:
    state = group_state_for(canvas)
    if state.expanding or not state.groups:
        return
    atom_ids = {
        atom_id
        for atom_id in selected_atom_ids_for_transform_for(canvas)
        if atom_id in atoms_for(canvas)
    }
    # Trigger only from Qt scene selection. Note-service selection must not
    # anchor a group: the rubber band never deselects notes, so a note trigger
    # would make a once-touched group impossible to marquee-deselect.
    trigger_items = [
        item
        for item in scene_selected_items_for(canvas)
        if _is_groupable_standalone_item(canvas, item)
    ]
    # Selected atom-bound marks stand in for their atoms when matching groups,
    # but stay out of `atom_ids` so the atoms still count as missing and get
    # selected by the expansion below.
    trigger_atom_ids = atom_ids | selected_mark_atom_ids_for(canvas)
    group_ids = group_ids_for_members_for(canvas, trigger_atom_ids, trigger_items)
    # Notes-only groups have no shrink path here (the stale-note reconciliation
    # skips them), so a Qt-selected note must not scene-expand them or a
    # marquee that once touched the note could never deselect the group; their
    # unit behaviour lives entirely in the note-service paths.
    group_ids = {
        group_id
        for group_id in group_ids
        if _group_has_scene_members(canvas, state.groups[group_id])
    }
    member_atom_ids: set[int] = set()
    member_items: list = []
    for group_id in group_ids:
        group = state.groups[group_id]
        member_atom_ids.update(group.atom_ids)
        member_items.extend(attached_canvas_scene_items(canvas, group.items))
    member_atom_ids &= set(atoms_for(canvas))
    selected_items = selected_scene_items_for(
        canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS
    )
    selected_ids = set(map(id, selected_items))
    missing_atoms = member_atom_ids - atom_ids
    missing_items = [item for item in member_items if id(item) not in selected_ids]
    stale_notes = _stale_group_notes_for(canvas, state, group_ids)
    if not missing_atoms and not missing_items and not stale_notes:
        return
    state.expanding = True
    try:
        scene_items = _structure_items_for_atom_ids(canvas, member_atom_ids)
        scene_items.extend(item for item in missing_items if item.data(0) != "note")
        set_scene_items_selected_for(canvas, scene_items, True)
        for note in missing_items:
            if note.data(0) == "note":
                select_note_for(canvas, note, additive=True)
        for note in stale_notes:
            toggle_note_selection_for(canvas, note)
        refresh_selection_outline_for(canvas)
    finally:
        state.expanding = False


__all__ = [
    "GROUPABLE_STANDALONE_KINDS",
    "deselect_groups_for_note_for",
    "expand_note_selection_to_groups_for",
    "expand_selection_to_groups_for",
    "group_selection_for",
    "group_selection_targets_for",
    "notes_only_group_member_notes_for",
    "selected_group_rects_for",
    "ungroup_selection_for",
]
