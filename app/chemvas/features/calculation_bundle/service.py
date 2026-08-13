from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast

from chemvas.domain.atom_aliases import (
    alias_attachments_for_atom,
    modeled_atom_formal_charge,
)
from chemvas.domain.document import Atom, Bond, MoleculeModel, deserialize_model_state

from .model import CalculationStateSelection, ComponentSelection, ComponentSummary

_CHARGE_MARKS = {
    "plus": 1,
    "circled_plus": 1,
    "minus": -1,
    "circled_minus": -1,
}


def inspect_components(state: Mapping[str, object]) -> tuple[ComponentSummary, ...]:
    model, annotations = _model_and_annotations(state)
    model.atom_annotations = annotations
    return tuple(
        _component_summary(model, index, atom_ids)
        for index, atom_ids in enumerate(_connected_components(model))
    )


def select_component(
    state: Mapping[str, object], component_index: int
) -> ComponentSelection:
    model, annotations = _model_and_annotations(state)
    components = _connected_components(model)
    if not components:
        raise ValueError("The Chemvas document contains no chemical structure.")
    if component_index < 0 or component_index >= len(components):
        raise ValueError(
            f"Component {component_index} does not exist; choose 0 to "
            f"{len(components) - 1}."
        )

    atom_ids = components[component_index]
    selected_ids = set(atom_ids)
    atoms = {
        atom_id: _copy_atom(model.atoms[atom_id])
        for atom_id in atom_ids
        if atom_id in model.atoms
    }
    bonds: list[Bond | None] = [
        _copy_bond(bond)
        for bond in model.bonds
        if bond is not None and bond.a in selected_ids and bond.b in selected_ids
    ]
    selected_annotations = {
        atom_id: dict(annotations[atom_id])
        for atom_id in atom_ids
        if atom_id in annotations
    }
    selected_model = MoleculeModel(
        atoms=atoms,
        bonds=bonds,
        next_atom_id=max(atoms, default=-1) + 1,
        atom_annotations=selected_annotations,
    )
    return ComponentSelection(
        model=selected_model,
        summary=_component_summary(model, component_index, atom_ids, annotations),
    )


def select_components(
    state: Mapping[str, object],
    component_atom_ids: Sequence[Sequence[int]],
) -> CalculationStateSelection:
    model, annotations = _model_and_annotations(state)
    components = _connected_components(model)
    component_index_by_atoms = {
        tuple(atom_ids): index for index, atom_ids in enumerate(components)
    }
    requested = [tuple(atom_ids) for atom_ids in component_atom_ids]
    if not requested:
        raise ValueError("A calculation state must include at least one component.")
    if len(set(requested)) != len(requested):
        raise ValueError("A calculation state repeats a component.")
    try:
        component_indices = tuple(component_index_by_atoms[ids] for ids in requested)
    except KeyError as exc:
        raise ValueError(
            "A calculation state member no longer matches a connected component."
        ) from exc

    selected_ids = {atom_id for ids in requested for atom_id in ids}
    atoms = {
        atom_id: _copy_atom(model.atoms[atom_id]) for atom_id in sorted(selected_ids)
    }
    bonds: list[Bond | None] = [
        _copy_bond(bond)
        for bond in model.bonds
        if bond is not None and bond.a in selected_ids and bond.b in selected_ids
    ]
    selected_annotations = {
        atom_id: dict(annotations[atom_id])
        for atom_id in sorted(selected_ids)
        if atom_id in annotations
    }
    return CalculationStateSelection(
        model=MoleculeModel(
            atoms=atoms,
            bonds=bonds,
            next_atom_id=max(atoms, default=-1) + 1,
            atom_annotations=selected_annotations,
        ),
        component_indices=component_indices,
        atom_ids=tuple(sorted(selected_ids)),
        formal_charge=sum(
            _modeled_atom_formal_charge(
                model,
                atom_id,
                selected_annotations.get(atom_id),
            )
            for atom_id in selected_ids
        ),
        radical_electrons=sum(
            int(selected_annotations.get(atom_id, {}).get("radical_electrons", 0))
            for atom_id in selected_ids
        ),
    )


def _model_and_annotations(
    state: Mapping[str, object],
) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
    model_state = state.get("model")
    if not isinstance(model_state, Mapping):
        raise ValueError("Invalid Chemvas document state: model is missing.")
    model = deserialize_model_state(cast(Mapping[str, object], model_state))
    marks = state.get("marks", ())
    if not isinstance(marks, Sequence) or isinstance(marks, (str, bytes)):
        raise ValueError("Invalid Chemvas document state: marks are invalid.")
    annotations = _resolve_annotations(
        model,
        cast(Sequence[object], marks),
    )
    return model, annotations


def _resolve_annotations(
    model: MoleculeModel, marks: Sequence[object]
) -> dict[int, dict[str, int]]:
    mark_totals: dict[int, dict[str, int]] = {}
    electronic_marked_atom_ids: set[int] = set()
    for raw_mark in marks:
        if not isinstance(raw_mark, Mapping):
            raise ValueError("Invalid Chemvas document state: mark entry is invalid.")
        atom_id = raw_mark.get("atom_id")
        kind = raw_mark.get("kind")
        if atom_id is None:
            continue
        if type(atom_id) is not int or atom_id not in model.atoms:
            raise ValueError("Invalid Chemvas document state: mark atom is invalid.")
        if not isinstance(kind, str):
            raise ValueError("Invalid Chemvas document state: mark kind is invalid.")
        if kind not in _CHARGE_MARKS and kind != "radical":
            continue
        electronic_marked_atom_ids.add(atom_id)
        values = mark_totals.setdefault(
            atom_id, {"formal_charge": 0, "radical_electrons": 0}
        )
        values["formal_charge"] += _CHARGE_MARKS.get(kind, 0)
        if kind == "radical":
            values["radical_electrons"] += 1

    normalized_marks = {
        atom_id: _normalize_annotation(values)
        for atom_id, values in mark_totals.items()
    }
    normalized_model = {
        int(atom_id): _normalize_annotation(values)
        for atom_id, values in model.atom_annotations.items()
    }
    model_electronic_atom_ids = {
        int(atom_id)
        for atom_id, values in model.atom_annotations.items()
        if any(key in values for key in ("formal_charge", "radical_electrons"))
    }
    for atom_id in model_electronic_atom_ids:
        if atom_id not in electronic_marked_atom_ids or normalized_marks.get(
            atom_id, {}
        ) != normalized_model.get(atom_id, {}):
            raise ValueError(
                "Conflicting charge/radical annotations for Chemvas atom "
                f"{atom_id}; repair the document before calculation export."
            )

    resolved: dict[int, dict[str, int]] = {}
    for atom_id in electronic_marked_atom_ids:
        annotation = normalized_marks.get(atom_id, {})
        resolved[atom_id] = annotation or {"formal_charge": 0}
    return resolved


def _normalize_annotation(values: Mapping[str, int]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    formal_charge = int(values.get("formal_charge", 0))
    radical_electrons = int(values.get("radical_electrons", 0))
    if formal_charge:
        normalized["formal_charge"] = formal_charge
    if radical_electrons:
        normalized["radical_electrons"] = radical_electrons
    return normalized


def _connected_components(model: MoleculeModel) -> list[tuple[int, ...]]:
    adjacency: dict[int, set[int]] = {atom_id: set() for atom_id in model.atoms}
    for bond in model.bonds:
        if bond is None or bond.a not in adjacency or bond.b not in adjacency:
            continue
        adjacency[bond.a].add(bond.b)
        adjacency[bond.b].add(bond.a)

    remaining = set(model.atoms)
    components: list[tuple[int, ...]] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        component: set[int] = set()
        while stack:
            atom_id = stack.pop()
            if atom_id in component:
                continue
            component.add(atom_id)
            stack.extend(sorted(adjacency[atom_id] - component, reverse=True))
        remaining -= component
        components.append(tuple(sorted(component)))
    return components


def _component_summary(
    model: MoleculeModel,
    index: int,
    atom_ids: tuple[int, ...],
    annotations: Mapping[int, Mapping[str, int]] | None = None,
) -> ComponentSummary:
    selected_ids = set(atom_ids)
    active_annotations = (
        annotations if annotations is not None else model.atom_annotations
    )
    labels = Counter(model.atoms[atom_id].element for atom_id in atom_ids)
    xs = [model.atoms[atom_id].x for atom_id in atom_ids]
    ys = [model.atoms[atom_id].y for atom_id in atom_ids]
    return ComponentSummary(
        index=index,
        atom_ids=atom_ids,
        bond_count=sum(
            1
            for bond in model.bonds
            if bond is not None and bond.a in selected_ids and bond.b in selected_ids
        ),
        formula_labels=tuple(sorted(labels.items())),
        formal_charge=sum(
            _modeled_atom_formal_charge(
                model,
                atom_id,
                active_annotations.get(atom_id),
            )
            for atom_id in atom_ids
        ),
        radical_electrons=sum(
            int(active_annotations.get(atom_id, {}).get("radical_electrons", 0))
            for atom_id in atom_ids
        ),
        bounds=(min(xs), min(ys), max(xs), max(ys)),
    )


def _modeled_atom_formal_charge(
    model: MoleculeModel,
    atom_id: int,
    annotation: Mapping[str, int] | None,
) -> int:
    return modeled_atom_formal_charge(
        model.atoms[atom_id].element,
        annotation,
        atom_id=atom_id,
        attachments=alias_attachments_for_atom(model, atom_id),
    )


def _copy_atom(atom: Atom) -> Atom:
    return Atom(
        element=atom.element,
        x=atom.x,
        y=atom.y,
        color=atom.color,
        explicit_label=atom.explicit_label,
    )


def _copy_bond(bond: Bond) -> Bond:
    return Bond(
        a=bond.a,
        b=bond.b,
        order=bond.order,
        style=bond.style,
        color=bond.color,
    )


__all__ = ["inspect_components", "select_component", "select_components"]
