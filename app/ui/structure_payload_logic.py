from collections.abc import Callable, Collection, Iterable, Mapping

from core.model import Bond, MoleculeModel

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
        formal_charge, radical_electrons = _annotation_totals(mark_kinds_by_atom.get(old_id, ()))
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
    atom_annotations = build_atom_annotations(selected_atom_ids, id_map, mark_kinds_by_atom)
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
        if kind == "plus":
            formal_charge += 1
        elif kind == "minus":
            formal_charge -= 1
        elif kind == "radical":
            radical_electrons += 1
    return formal_charge, radical_electrons
