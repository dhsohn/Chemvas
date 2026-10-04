from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from chemvas.domain.document import Bond, MoleculeModel

Bounds = tuple[float, float, float, float]
AtomAnnotations = dict[int, dict[str, int]]
MarkKindsByAtom = Mapping[int, Iterable[str]]
BoundsGetter = Callable[..., Bounds]


def expand_atom_ids_for_structure(
    model: MoleculeModel,
    atom_ids: Collection[int],
    bond_ids: Collection[int],
) -> set[int]:
    selected_atoms = set(atom_ids)
    for bond_id in bond_ids:
        if not (0 <= bond_id < len(model.bonds)):
            continue
        bond = model.bonds[bond_id]
        if bond is None:
            continue
        selected_atoms.add(bond.a)
        selected_atoms.add(bond.b)
    return selected_atoms


def build_submodel(
    model: MoleculeModel,
    atom_ids: Collection[int],
    bond_ids: Collection[int],
    *,
    bounds_getter: BoundsGetter,
) -> tuple[MoleculeModel, Bounds, dict[int, int]]:
    selected_bond_ids = tuple(bond_ids)
    selected_atoms = expand_atom_ids_for_structure(model, atom_ids, selected_bond_ids)
    submodel = MoleculeModel()
    id_map: dict[int, int] = {}

    for old_id in sorted(selected_atoms):
        atom = model.atoms.get(old_id)
        if atom is None:
            continue
        new_id = submodel.add_atom(atom.element, atom.x, atom.y)
        submodel.atoms[new_id].color = atom.color
        submodel.atoms[new_id].explicit_label = atom.explicit_label
        id_map[old_id] = new_id

    if selected_bond_ids:
        for bond_id in selected_bond_ids:
            _append_selected_bond(submodel, model, id_map, bond_id)
    else:
        for bond in model.bonds:
            if bond is None:
                continue
            _append_bond_copy(submodel, id_map, bond)

    return submodel, bounds_getter(selected_atoms), id_map


def build_atom_annotations(
    atom_ids: Collection[int],
    id_map: Mapping[int, int],
    mark_kinds_by_atom: MarkKindsByAtom,
) -> AtomAnnotations:
    annotations: AtomAnnotations = {}
    for old_id in sorted(atom_ids):
        new_id = id_map.get(old_id)
        if new_id is None:
            continue
        formal_charge, radical_electrons = _annotation_totals(
            mark_kinds_by_atom.get(old_id, ())
        )
        if formal_charge or radical_electrons:
            annotations[new_id] = {}
            if formal_charge:
                annotations[new_id]["formal_charge"] = formal_charge
            if radical_electrons:
                annotations[new_id]["radical_electrons"] = radical_electrons
    return annotations


def build_structure_payload(
    model: MoleculeModel,
    atom_ids: Collection[int],
    bond_ids: Collection[int],
    mark_kinds_by_atom: MarkKindsByAtom,
    *,
    bounds_getter: BoundsGetter,
) -> tuple[MoleculeModel, AtomAnnotations, Bounds]:
    selected_atom_ids = expand_atom_ids_for_structure(model, atom_ids, bond_ids)
    if not selected_atom_ids:
        raise ValueError("There is no chemical structure to export.")
    export_model, bounds, id_map = build_submodel(
        model,
        atom_ids,
        bond_ids,
        bounds_getter=bounds_getter,
    )
    if not export_model.atoms:
        raise ValueError("There is no chemical structure to export.")
    atom_annotations = build_atom_annotations(
        selected_atom_ids, id_map, mark_kinds_by_atom
    )
    return export_model, atom_annotations, bounds


def build_3d_conversion_payload(
    model: MoleculeModel,
    atom_ids: Collection[int],
    bond_ids: Collection[int],
    mark_kinds_by_atom: MarkKindsByAtom,
    *,
    bounds_getter: BoundsGetter,
) -> tuple[MoleculeModel, AtomAnnotations]:
    if atom_ids or bond_ids:
        export_model, atom_annotations, _ = build_structure_payload(
            model,
            atom_ids,
            bond_ids,
            mark_kinds_by_atom,
            bounds_getter=bounds_getter,
        )
    else:
        export_model, atom_annotations, _ = build_structure_payload(
            model,
            set(model.atoms),
            (),
            mark_kinds_by_atom,
            bounds_getter=bounds_getter,
        )
    return export_model, atom_annotations


def model_with_atom_annotations(
    model: MoleculeModel,
    atom_annotations: Mapping[int, Mapping[str, int]] | None,
) -> MoleculeModel:
    if atom_annotations is None:
        return model
    return MoleculeModel(
        atoms=dict(model.atoms),
        bonds=list(model.bonds),
        next_atom_id=model.next_atom_id,
        atom_annotations=_normalized_atom_annotations(atom_annotations),
    )


def _append_selected_bond(
    submodel: MoleculeModel,
    model: MoleculeModel,
    id_map: Mapping[int, int],
    bond_id: int,
) -> None:
    if not (0 <= bond_id < len(model.bonds)):
        return
    bond = model.bonds[bond_id]
    if bond is None:
        return
    _append_bond_copy(submodel, id_map, bond)


def _append_bond_copy(
    submodel: MoleculeModel,
    id_map: Mapping[int, int],
    bond: Bond,
) -> None:
    if bond.a not in id_map or bond.b not in id_map:
        return
    submodel.bonds.append(
        Bond(
            a=id_map[bond.a],
            b=id_map[bond.b],
            order=bond.order,
            style=bond.style,
            color=bond.color,
        )
    )


def _annotation_totals(mark_kinds: Iterable[str]) -> tuple[int, int]:
    formal_charge = 0
    radical_electrons = 0
    for kind in mark_kinds:
        if kind in {"plus", "circled_plus"}:
            formal_charge += 1
        elif kind in {"minus", "circled_minus"}:
            formal_charge -= 1
        elif kind == "radical":
            radical_electrons += 1
    return formal_charge, radical_electrons


def _normalized_atom_annotations(
    atom_annotations: Mapping[int, Mapping[str, int]],
) -> AtomAnnotations:
    annotations: AtomAnnotations = {}
    for atom_id, values in atom_annotations.items():
        annotation: dict[str, int] = {}
        formal_charge = int(values.get("formal_charge", 0))
        radical_electrons = int(values.get("radical_electrons", 0))
        if formal_charge:
            annotation["formal_charge"] = formal_charge
        if radical_electrons:
            annotation["radical_electrons"] = radical_electrons
        if annotation:
            annotations[int(atom_id)] = annotation
    return annotations


@dataclass(frozen=True)
class MarkRebindPlan:
    old_id: int | None
    before_marks: dict[int, tuple[Any, ...]]
    after_marks: dict[int, tuple[Any, ...]]
    before_annotations: AtomAnnotations
    after_annotations: AtomAnnotations


def plan_mark_rebind(
    model: MoleculeModel,
    item: Any,
    atom_id: int,
    marks_by_atom: Mapping[int, Sequence[Any]],
) -> MarkRebindPlan | None:
    """Validate explicit ownership transfer without changing glyph or model state."""
    if type(atom_id) is not int or model.atom_for_id(atom_id) is None:
        raise ValueError("Choose an existing atom in this document.")
    old_id = (item.data(1) or {}).get("atom_id")
    if atom_id == old_id:
        return None
    if old_id is not None and model.atom_for_id(old_id) is None:
        raise ValueError("The mark's original atom no longer exists.")
    affected_ids = {atom_id} | ({old_id} if old_id is not None else set())
    before_marks = {key: tuple(marks_by_atom.get(key) or ()) for key in affected_ids}
    if old_id is not None and item not in before_marks[old_id]:
        raise ValueError(
            "The mark's binding is inconsistent; reload the document before reassigning."
        )
    annotations = model.atom_annotations
    before_annotations = {
        key: dict(annotations[key]) for key in affected_ids if key in annotations
    }
    expected = build_atom_annotations(
        affected_ids,
        {key: key for key in affected_ids},
        {
            key: [(mark.data(1) or {})["kind"] for mark in items]
            for key, items in before_marks.items()
        },
    )
    normalized = {
        key: {k: v for k, v in value.items() if v}
        for key, value in before_annotations.items()
    }
    normalized = {key: value for key, value in normalized.items() if value}
    if normalized != expected:
        raise ValueError(
            "Atom annotations and marks disagree; resolve them before reassigning a mark."
        )
    after_marks = dict(before_marks)
    if old_id is not None:
        after_marks[old_id] = tuple(
            mark for mark in before_marks[old_id] if mark is not item
        )
    after_marks[atom_id] = (*before_marks[atom_id], item)
    after_annotations = build_atom_annotations(
        affected_ids,
        {key: key for key in affected_ids},
        {
            key: [(mark.data(1) or {})["kind"] for mark in items]
            for key, items in after_marks.items()
        },
    )
    return MarkRebindPlan(
        old_id, before_marks, after_marks, before_annotations, after_annotations
    )


def opposite_charge_mark(items: Sequence[Any], delta: int) -> Any | None:
    """A charge shortcut cancels the last opposite mark before adding a new one."""
    if delta not in {-1, 1}:
        raise ValueError("Charge shortcuts require a change of +1 or -1.")
    opposite = {"minus", "circled_minus"} if delta > 0 else {"plus", "circled_plus"}
    return next(
        (
            item
            for item in reversed(items)
            if (item.data(1) or {}).get("kind") in opposite
        ),
        None,
    )
