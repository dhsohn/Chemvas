from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from chemvas.domain.atom_aliases import (
    AliasAttachment,
    alias_attachment_inventory,
    modeled_atom_formal_charge,
)
from chemvas.domain.document import (
    Atom,
    Bond,
    MoleculeModel,
    connected_atom_components,
    deserialize_model_state,
)

from .model import (
    CalculationStateSelection,
    ComponentInventory,
    ComponentSelection,
    ComponentSummary,
)

_CHARGE_MARKS = {
    "plus": 1,
    "circled_plus": 1,
    "minus": -1,
    "circled_minus": -1,
}


@dataclass(frozen=True)
class _GraphIndex:
    components: tuple[tuple[int, ...], ...]
    bond_counts: tuple[int, ...]
    indexed_bonds: tuple[tuple[int, Bond], ...]
    attachments_by_atom: Mapping[int, tuple[AliasAttachment, ...]]


def inspect_components(state: Mapping[str, object]) -> tuple[ComponentSummary, ...]:
    return inspect_component_inventory(state).components


def inspect_component_inventory(state: Mapping[str, object]) -> ComponentInventory:
    """Deserialize and annotate a document once for complete graph inspection."""
    model, annotations = _model_and_annotations(state)
    model.atom_annotations = annotations
    graph = _graph_index(model)
    return ComponentInventory(
        model=model,
        components=tuple(
            _component_summary(
                model,
                index,
                atom_ids,
                bond_count=graph.bond_counts[index],
                attachments_by_atom=graph.attachments_by_atom,
            )
            for index, atom_ids in enumerate(graph.components)
        ),
    )


def select_component(
    state: Mapping[str, object], component_index: int
) -> ComponentSelection:
    model, annotations = _model_and_annotations(state)
    graph = _graph_index(model)
    if not graph.components:
        raise ValueError("The Chemvas document contains no chemical structure.")
    if component_index < 0 or component_index >= len(graph.components):
        raise ValueError(
            f"Component {component_index} does not exist; choose 0 to "
            f"{len(graph.components) - 1}."
        )

    atom_ids = graph.components[component_index]
    # atom_ids is one component of model.atoms, so every id is live.
    atoms = {atom_id: _copy_atom(model.atoms[atom_id]) for atom_id in atom_ids}
    bonds: list[Bond | None] = [
        _copy_bond(bond)
        for index, bond in graph.indexed_bonds
        if index == component_index
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
        summary=_component_summary(
            model,
            component_index,
            atom_ids,
            annotations,
            bond_count=graph.bond_counts[component_index],
            attachments_by_atom=graph.attachments_by_atom,
        ),
    )


def select_components(
    state: Mapping[str, object],
    component_atom_ids: Sequence[Sequence[int]],
) -> CalculationStateSelection:
    model, annotations = _model_and_annotations(state)
    graph = _graph_index(model)
    component_index_by_atoms = {
        tuple(atom_ids): index for index, atom_ids in enumerate(graph.components)
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
    selected_component_indices = set(component_indices)
    atoms = {
        atom_id: _copy_atom(model.atoms[atom_id]) for atom_id in sorted(selected_ids)
    }
    bonds: list[Bond | None] = [
        _copy_bond(bond)
        for index, bond in graph.indexed_bonds
        if index in selected_component_indices
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
                graph.attachments_by_atom.get(atom_id, ()),
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
    model = deserialize_model_state(cast("Mapping[str, object]", model_state))
    marks = state.get("marks", ())
    if not isinstance(marks, Sequence) or isinstance(marks, (str, bytes)):
        raise ValueError("Invalid Chemvas document state: marks are invalid.")
    annotations = _resolve_annotations(
        model,
        cast("Sequence[object]", marks),
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


def _component_atom_ids(model: MoleculeModel) -> tuple[tuple[int, ...], ...]:
    return connected_atom_components(
        model.atoms,
        ((bond.a, bond.b) for bond in model.bonds if bond is not None),
    )


def _graph_index(model: MoleculeModel) -> _GraphIndex:
    components = _component_atom_ids(model)
    component_by_atom = {
        atom_id: index
        for index, atom_ids in enumerate(components)
        for atom_id in atom_ids
    }
    bond_counts = [0] * len(components)
    indexed_bonds: list[tuple[int, Bond]] = []
    attachment_inventory = alias_attachment_inventory(model)
    for bond in attachment_inventory.bonds:
        first_component = component_by_atom.get(bond.a)
        second_component = component_by_atom.get(bond.b)
        if first_component is not None and first_component == second_component:
            bond_counts[first_component] += 1
            indexed_bonds.append((first_component, bond))
    return _GraphIndex(
        components=components,
        bond_counts=tuple(bond_counts),
        indexed_bonds=tuple(indexed_bonds),
        attachments_by_atom=attachment_inventory.attachments_by_atom,
    )


def _component_summary(
    model: MoleculeModel,
    index: int,
    atom_ids: tuple[int, ...],
    annotations: Mapping[int, Mapping[str, int]] | None = None,
    *,
    bond_count: int,
    attachments_by_atom: Mapping[int, tuple[AliasAttachment, ...]],
) -> ComponentSummary:
    active_annotations = (
        annotations if annotations is not None else model.atom_annotations
    )
    labels = Counter(model.atoms[atom_id].element for atom_id in atom_ids)
    xs = [model.atoms[atom_id].x for atom_id in atom_ids]
    ys = [model.atoms[atom_id].y for atom_id in atom_ids]
    return ComponentSummary(
        index=index,
        atom_ids=atom_ids,
        bond_count=bond_count,
        formula_labels=tuple(sorted(labels.items())),
        formal_charge=sum(
            _modeled_atom_formal_charge(
                model,
                atom_id,
                active_annotations.get(atom_id),
                attachments_by_atom.get(atom_id, ()),
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
    attachments: Sequence[AliasAttachment],
) -> int:
    return modeled_atom_formal_charge(
        model.atoms[atom_id].element,
        annotation,
        atom_id=atom_id,
        attachments=attachments,
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


__all__ = [
    "inspect_component_inventory",
    "inspect_components",
    "select_component",
    "select_components",
]
