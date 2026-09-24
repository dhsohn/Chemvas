from __future__ import annotations

from typing import Any

from chemvas.features.graph import build_bond_adjacency_index
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    pop_atom_dot_for,
    pop_atom_item_for,
)
from chemvas.ui.canvas.canvas_bond_graphics_state import pop_bond_items_for
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import (
    remove_scene_item_from_collection_for,
)
from chemvas.ui.history.history_operations import CanvasHistoryOperations
from chemvas.ui.molecule.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.molecule.atom_label_access import add_or_update_atom_label
from chemvas.ui.scene.scene_item_access import remove_item_from_canvas_scene


def has_insert_mutation_since_for(
    canvas, before_next_atom_id: int, before_bond_count: int
) -> bool:
    return (
        int(canvas.model.next_atom_id) != before_next_atom_id
        or len(canvas.model.bonds) != before_bond_count
    )


def set_inserted_atom_metadata_for(
    canvas, atom_id: int, *, color: str | None, explicit_label: bool
) -> bool:
    atom = canvas.model.atom_for_id(atom_id)
    if atom is None:
        return False
    atom.color = color
    atom.explicit_label = explicit_label
    return True


def set_inserted_atom_annotation_for(
    canvas, atom_id: int, annotation: dict[str, int] | None
) -> bool:
    if canvas.model.atom_for_id(atom_id) is None:
        return False
    canvas.model.set_atom_annotation(atom_id, annotation)
    return True


def set_inserted_bond_metadata_for(
    canvas, bond_id: int, *, style: str, color: str | None
) -> bool:
    bond = canvas.model.bond_for_id(bond_id)
    if bond is None:
        return False
    bond.style = style
    bond.color = color
    return True


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
    canvas.services.canvas_history_recording_service.record_additions(**kwargs)


def insert_bond_exists_for(canvas, a_id: int, b_id: int, *, bond_exists=None) -> bool:
    if bond_exists is not None:
        return bool(bond_exists(a_id, b_id))
    return any(
        bond is not None
        and ((bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id))
        for bond in canvas.model.bonds
    )


def build_insert_benzene_ring_for(
    canvas,
    center,
    *,
    attach_atom_id: int | None = None,
    attach_bond_id: int | None = None,
) -> object | None:
    return canvas.services.structure_build_service.build_benzene_ring(
        center,
        attach_atom_id=attach_atom_id,
        attach_bond_id=attach_bond_id,
    )


def add_insert_ring_from_points_for(
    canvas,
    points,
    elements: list[str] | None = None,
    merge: list | None = None,
) -> list[int]:
    return canvas.services.structure_build_service.add_ring_from_points(
        points,
        elements=elements,
        merge=merge,
    )


def rollback_insert_mutation_for(
    canvas, *, before_next_atom_id: int, before_bond_count: int
) -> None:
    rollback_errors: list[BaseException] = []
    created_atom_ids = canvas.model.created_atom_ids_from(before_next_atom_id)
    created_bond_ids = list(canvas.model.bond_ids_from(before_bond_count))

    def record_failure(error: BaseException) -> None:
        rollback_errors.append(error)

    atom_graphics = {
        atom_id: (
            canvas.runtime_state.atom_graphics_state.atom_items.get(atom_id),
            canvas.runtime_state.atom_graphics_state.atom_dots.get(atom_id),
        )
        for atom_id in created_atom_ids
    }
    marks = mark_registry_for(canvas)
    atom_marks = {
        atom_id: tuple(marks.get_for_atom(atom_id) or ())
        for atom_id in created_atom_ids
    }
    bond_graphics = {
        bond_id: tuple(
            canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, [])
        )
        for bond_id in created_bond_ids
    }

    def trim_bonds_directly() -> None:
        try:
            canvas.model.trim_bonds(before_bond_count)
        except Exception as error:
            record_failure(error)

    try:
        bond_service = canvas.services.canvas_bond_mutation_service
    except AttributeError:
        bond_service = None
    if callable(getattr(bond_service, "trim_bonds_to_length", None)):
        try:
            CanvasHistoryOperations(canvas).trim_bonds_for_history(before_bond_count)
        except Exception as error:
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
            atom_service = canvas.services.canvas_atom_mutation_service
        except AttributeError:
            atom_service = None
        if callable(getattr(atom_service, "remove_atom_only", None)):
            try:
                CanvasHistoryOperations(canvas).remove_atom_for_history(atom_id)
            except Exception as error:
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
        canvas.model.next_atom_id = before_next_atom_id
    except Exception as error:
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
        canvas.model.pop_atom(atom_id)
    except Exception as error:
        rollback_errors.append(error)
    try:
        pop_atom_coords_3d_for(canvas, atom_id)
    except Exception as error:
        rollback_errors.append(error)
    graphics_items: list[object] = [item for item in known_graphics if item is not None]
    for pop_item in (pop_atom_item_for, pop_atom_dot_for):
        try:
            item = pop_item(canvas, atom_id)
        except Exception as error:
            rollback_errors.append(error)
            continue
        if item is not None:
            graphics_items.append(item)
    for item in _unique_insert_items(graphics_items):
        _remove_insert_scene_item_directly(canvas, item, rollback_errors)
    try:
        current_marks = mark_registry_for(canvas).pop_for_atom(atom_id)
    except Exception as error:
        rollback_errors.append(error)
        current_marks = []
    for mark in _unique_insert_items((*known_marks, *current_marks)):
        try:
            remove_scene_item_from_collection_for(canvas, "mark_items", mark)
        except Exception as error:
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
        except Exception as error:
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
    except Exception as error:
        rollback_errors.append(error)


def _rebuild_insert_graph_directly(
    canvas,
    rollback_errors: list[BaseException],
) -> None:
    try:
        atom_neighbors, atom_bond_ids = build_bond_adjacency_index(
            canvas.model.atoms,
            canvas.model.bonds,
        )
        graph = canvas.runtime_state.graph_state
        graph.atom_neighbors.clear()
        graph.atom_neighbors.update(atom_neighbors)
        graph.atom_bond_ids.clear()
        graph.atom_bond_ids.update(atom_bond_ids)
        graph.bump_version()
        graph.selection_component_cache = []
    except Exception as error:
        rollback_errors.append(error)


__all__ = [
    "add_insert_ring_from_points_for",
    "add_or_update_insert_atom_label_for",
    "build_insert_benzene_ring_for",
    "has_insert_mutation_since_for",
    "insert_bond_exists_for",
    "record_insert_additions_for",
    "rollback_insert_mutation_for",
    "set_inserted_atom_annotation_for",
    "set_inserted_atom_metadata_for",
    "set_inserted_bond_metadata_for",
]
