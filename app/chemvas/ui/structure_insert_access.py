from __future__ import annotations

from typing import Any

from chemvas.ui.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.atom_label_access import add_or_update_atom_label, atom_label_service
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    pop_atom_dot_for,
    pop_atom_item_for,
)
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id, pop_bond_items_for
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    atoms_for,
    bond_count_for,
    bond_for_id,
    bond_ids_from,
    bonds_for,
    created_atom_ids_from,
    next_atom_id_for,
    remove_atom_direct_for,
    set_atom_annotation_for,
    set_next_atom_id_for,
    trim_bonds_direct_for,
)
from chemvas.ui.canvas_scene_items_state import remove_scene_item_from_collection_for
from chemvas.ui.canvas_service_ports import (
    structure_insert_build_service_for_access,
    structure_mutation_atom_service,
    structure_mutation_bond_service,
)
from chemvas.ui.graph_index_operations import build_bond_adjacency_index
from chemvas.ui.history_canvas_access import (
    remove_atom_for_history,
    trim_bonds_for_history,
)
from chemvas.ui.history_recording_access import record_additions_for
from chemvas.ui.scene_item_access import remove_item_from_canvas_scene
from chemvas.ui.selection_style_access import restore_selection_from_ids_for
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_benzene_ring_for,
    add_bond_for,
)


def insert_next_atom_id_for(canvas) -> int:
    return next_atom_id_for(canvas)


def insert_bond_count_for(canvas) -> int:
    return bond_count_for(canvas)


def add_insert_atom_for(canvas, element: str, x: float, y: float) -> int:
    return add_atom_for(canvas, element, x, y)


def add_insert_bond_for(canvas, a_id: int, b_id: int, order: int = 1) -> int:
    return add_bond_for(canvas, a_id, b_id, order)


def insert_atom_for_id(canvas, atom_id: int):
    return atom_for_id(canvas, atom_id)


def insert_bond_for_id(canvas, bond_id: int | None):
    return bond_for_id(canvas, bond_id)


def new_insert_bond_ids_from(canvas, start: int) -> range:
    return bond_ids_from(canvas, start)


def add_insert_bond_graphics_for(canvas, bond_id: int) -> None:
    add_bond_graphics_for(canvas, bond_id)


def has_insert_mutation_since_for(
    canvas, before_next_atom_id: int, before_bond_count: int
) -> bool:
    return (
        insert_next_atom_id_for(canvas) != before_next_atom_id
        or insert_bond_count_for(canvas) != before_bond_count
    )


def set_inserted_atom_metadata_for(
    canvas, atom_id: int, *, color: str | None, explicit_label: bool
) -> bool:
    atom = insert_atom_for_id(canvas, atom_id)
    if atom is None:
        return False
    atom.color = color
    atom.explicit_label = explicit_label
    return True


def set_inserted_atom_annotation_for(
    canvas, atom_id: int, annotation: dict[str, int] | None
) -> bool:
    if insert_atom_for_id(canvas, atom_id) is None:
        return False
    set_atom_annotation_for(canvas, atom_id, annotation)
    return True


def set_inserted_bond_metadata_for(
    canvas, bond_id: int, *, style: str, color: str | None
) -> bool:
    bond = insert_bond_for_id(canvas, bond_id)
    if bond is None:
        return False
    bond.style = style
    bond.color = color
    return True


def add_insert_benzene_ring_for(
    canvas,
    center,
    *,
    attach_atom_id: int | None = None,
    attach_bond_id: int | None = None,
    before_smiles_input: str | None = None,
):
    return add_benzene_ring_for(
        canvas,
        center,
        attach_atom_id=attach_atom_id,
        attach_bond_id=attach_bond_id,
        before_smiles_input=before_smiles_input,
    )


def ensure_insert_carbon_dot_for(canvas, atom_id: int) -> None:
    atom_label_service(canvas).ensure_carbon_dot(atom_id)


def add_or_update_insert_atom_label_for(
    canvas, atom_id: int, element: str, **kwargs
) -> None:
    add_or_update_atom_label(canvas, atom_id, element, **kwargs)


def record_insert_additions_for(
    canvas,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
    added_scene_items: list | None = None,
) -> None:
    kwargs: dict[str, Any] = {
        "before_next_atom_id": before_next_atom_id,
        "before_bond_count": before_bond_count,
        "before_smiles_input": before_smiles_input,
    }
    if added_scene_items is not None:
        kwargs["added_scene_items"] = added_scene_items
    record_additions_for(canvas, **kwargs)


def add_atom_with_merge_for(canvas, point, element: str, merge: list) -> int:
    return structure_insert_build_service_for_access(canvas).add_atom_with_merge(
        point, element, merge
    )


def insert_bond_exists_for(canvas, a_id: int, b_id: int, *, bond_exists=None) -> bool:
    if bond_exists is not None:
        return bool(bond_exists(a_id, b_id))
    return any(
        bond is not None
        and ((bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id))
        for bond in bonds_for(canvas)
    )


def add_insert_ring_from_points_for(
    canvas,
    points,
    elements: list[str] | None = None,
    merge: list | None = None,
) -> list[int]:
    return structure_insert_build_service_for_access(canvas).add_ring_from_points(
        points,
        elements=elements,
        merge=merge,
    )


def restore_insert_selection_from_ids_for(
    canvas, atom_ids: set[int], bond_ids: set[int]
) -> None:
    restore_selection_from_ids_for(canvas, atom_ids, bond_ids)


def rollback_insert_mutation_for(
    canvas, *, before_next_atom_id: int, before_bond_count: int
) -> None:
    rollback_errors: list[BaseException] = []
    created_atom_ids = created_atom_ids_from(canvas, before_next_atom_id)
    created_bond_ids = list(bond_ids_from(canvas, before_bond_count))

    def record_failure(error: BaseException) -> None:
        rollback_errors.append(error)

    atom_graphics = {
        atom_id: (
            atom_items_for(canvas).get(atom_id),
            atom_dots_for(canvas).get(atom_id),
        )
        for atom_id in created_atom_ids
    }
    marks = mark_registry_for(canvas)
    atom_marks = {
        atom_id: tuple(marks.get_for_atom(atom_id) or ())
        for atom_id in created_atom_ids
    }
    bond_graphics = {
        bond_id: tuple(bond_items_for_id(canvas, bond_id))
        for bond_id in created_bond_ids
    }

    def trim_bonds_directly() -> None:
        try:
            trim_bonds_direct_for(canvas, before_bond_count)
        except BaseException as error:
            record_failure(error)

    try:
        bond_service = structure_mutation_bond_service(canvas)
    except AttributeError:
        bond_service = None
    if callable(getattr(bond_service, "trim_bonds_to_length", None)):
        try:
            trim_bonds_for_history(canvas, before_bond_count)
        except BaseException as error:
            # A service callback can mutate the model and then raise while cleaning
            # graph/graphics state. Preserve that failure, make the raw model
            # truncation idempotently authoritative, and continue with atom cleanup.
            record_failure(error)
    trim_bonds_directly()
    _remove_insert_bond_graphics_directly(
        canvas,
        created_bond_ids,
        bond_graphics,
        rollback_errors,
    )

    for atom_id in created_atom_ids:
        try:
            atom_service = structure_mutation_atom_service(canvas)
        except AttributeError:
            atom_service = None
        if callable(getattr(atom_service, "remove_atom_only", None)):
            try:
                remove_atom_for_history(canvas, atom_id)
            except BaseException as error:
                # Do not let one broken lifecycle callback strand every later atom
                # or prevent next_atom_id from returning to its savepoint.
                record_failure(error)
        _remove_insert_atom_directly(
            canvas,
            atom_id,
            atom_graphics.get(atom_id, (None, None)),
            atom_marks.get(atom_id, ()),
            rollback_errors,
        )

    _rebuild_insert_graph_directly(canvas, rollback_errors)

    try:
        set_next_atom_id_for(canvas, before_next_atom_id)
    except BaseException as error:
        record_failure(error)

    if len(rollback_errors) == 1:
        raise rollback_errors[0]
    if rollback_errors:
        raise BaseExceptionGroup("Insert mutation rollback failed", rollback_errors)


def _remove_insert_atom_directly(
    canvas,
    atom_id: int,
    known_graphics: tuple[object | None, object | None],
    known_marks: tuple[object, ...],
    rollback_errors: list[BaseException],
) -> None:
    try:
        remove_atom_direct_for(canvas, atom_id)
    except BaseException as error:
        rollback_errors.append(error)
    try:
        pop_atom_coords_3d_for(canvas, atom_id)
    except BaseException as error:
        rollback_errors.append(error)
    graphics_items: list[object] = [item for item in known_graphics if item is not None]
    for pop_item in (pop_atom_item_for, pop_atom_dot_for):
        try:
            item = pop_item(canvas, atom_id)
        except BaseException as error:
            rollback_errors.append(error)
            continue
        if item is not None:
            graphics_items.append(item)
    for item in _unique_insert_items(graphics_items):
        _remove_insert_scene_item_directly(canvas, item, rollback_errors)
    try:
        current_marks = mark_registry_for(canvas).pop_for_atom(atom_id)
    except BaseException as error:
        rollback_errors.append(error)
        current_marks = []
    for mark in _unique_insert_items((*known_marks, *current_marks)):
        try:
            remove_scene_item_from_collection_for(canvas, "mark_items", mark)
        except BaseException as error:
            rollback_errors.append(error)
        _remove_insert_scene_item_directly(canvas, mark, rollback_errors)


def _remove_insert_bond_graphics_directly(
    canvas,
    bond_ids: list[int],
    known_graphics: dict[int, tuple[object, ...]],
    rollback_errors: list[BaseException],
) -> None:
    for bond_id in bond_ids:
        items = list(known_graphics.get(bond_id, ()))
        try:
            items.extend(pop_bond_items_for(canvas, bond_id) or ())
        except BaseException as error:
            rollback_errors.append(error)
        for item in _unique_insert_items(items):
            _remove_insert_scene_item_directly(canvas, item, rollback_errors)


def _unique_insert_items(items) -> list[object]:
    unique: list[object] = []
    seen: set[int] = set()
    for item in items:
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        unique.append(item)
    return unique


def _remove_insert_scene_item_directly(
    canvas,
    item,
    rollback_errors: list[BaseException],
) -> None:
    if item is None:
        return
    try:
        remove_item_from_canvas_scene(canvas, item)
    except BaseException as error:
        rollback_errors.append(error)


def _rebuild_insert_graph_directly(
    canvas,
    rollback_errors: list[BaseException],
) -> None:
    try:
        atom_neighbors, atom_bond_ids = build_bond_adjacency_index(
            atoms_for(canvas),
            bonds_for(canvas),
        )
        graph = graph_state_for(canvas)
        graph.atom_neighbors.clear()
        graph.atom_neighbors.update(atom_neighbors)
        graph.atom_bond_ids.clear()
        graph.atom_bond_ids.update(atom_bond_ids)
        graph.bump_version()
        graph.selection_component_cache = []
    except BaseException as error:
        rollback_errors.append(error)


__all__ = [
    "add_atom_with_merge_for",
    "add_insert_atom_for",
    "add_insert_benzene_ring_for",
    "add_insert_bond_for",
    "add_insert_bond_graphics_for",
    "add_insert_ring_from_points_for",
    "add_or_update_insert_atom_label_for",
    "ensure_insert_carbon_dot_for",
    "has_insert_mutation_since_for",
    "insert_atom_for_id",
    "insert_bond_count_for",
    "insert_bond_exists_for",
    "insert_bond_for_id",
    "insert_next_atom_id_for",
    "new_insert_bond_ids_from",
    "record_insert_additions_for",
    "restore_insert_selection_from_ids_for",
    "rollback_insert_mutation_for",
    "set_inserted_atom_annotation_for",
    "set_inserted_atom_metadata_for",
    "set_inserted_bond_metadata_for",
]
