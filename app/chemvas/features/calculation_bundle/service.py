from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.domain.atom_aliases import modeled_atom_formal_charge
from chemvas.domain.document import Atom, Bond, MoleculeModel
from chemvas.domain.document.inspection import (
    ComponentInventory,
    document_annotations,
    document_model,
    graph_index,
)

from .model import CalculationArtifacts, CalculationStateSelection

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def select_components(
    state: Mapping[str, object],
    component_atom_ids: Sequence[Sequence[int]],
) -> CalculationStateSelection:
    return _select_components(state, component_atom_ids)


def _select_components(
    source: Mapping[str, object] | ComponentInventory,
    component_atom_ids: Sequence[Sequence[int]],
) -> CalculationStateSelection:
    if isinstance(source, ComponentInventory):
        model = source.model
        annotations = model.atom_annotations
        components = tuple(summary.atom_ids for summary in source.components)
        component_by_atom = {
            atom_id: index
            for index, atom_ids in enumerate(components)
            for atom_id in atom_ids
        }
        indexed_bonds = tuple(
            (component_by_atom[bond.a], bond)
            for bond in model.bonds
            if bond is not None
            and bond.a in component_by_atom
            and component_by_atom.get(bond.b) == component_by_atom[bond.a]
        )
    else:
        # Standalone selection validates only the selected aliases. A prepared
        # plan has already validated its complete inventory; do not broaden the
        # standalone public API's validation scope to obtain that inventory.
        model = document_model(source)
        annotations = document_annotations(source, model)
        graph = graph_index(model)
        components = graph.components
        indexed_bonds = graph.indexed_bonds
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
    selected_component_indices = set(component_indices)
    atoms = {
        atom_id: _copy_atom(model.atoms[atom_id]) for atom_id in sorted(selected_ids)
    }
    bonds: list[Bond | None] = [
        _copy_bond(bond)
        for index, bond in indexed_bonds
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
        formal_charge=(
            sum(source.components[index].formal_charge for index in component_indices)
            if isinstance(source, ComponentInventory)
            else sum(
                modeled_atom_formal_charge(
                    model.atoms[atom_id].element,
                    selected_annotations.get(atom_id),
                    atom_id=atom_id,
                    attachments=graph.attachments_by_atom.get(atom_id, ()),
                )
                for atom_id in selected_ids
            )
        ),
        radical_electrons=sum(
            int(selected_annotations.get(atom_id, {}).get("radical_electrons", 0))
            for atom_id in selected_ids
        ),
    )


def validate_calculation_artifacts(
    artifacts: CalculationArtifacts,
    *,
    declared_charge: int,
    declared_multiplicity: int,
    modeled_radical_electrons: int,
) -> None:
    """Reject artifacts whose electronic state or atom map contradicts the plan.

    RDKit's own charge and radical counts must agree with the declared state
    and the drawn marks, the multiplicity must be physically possible for the
    electron count, and the atom map must index every XYZ and MOL atom once.
    """
    if artifacts.rdkit_formal_charge != declared_charge:
        raise ValueError(
            "RDKit formal charge does not match the declared charge; "
            "calculation artifacts were not written"
        )
    if artifacts.rdkit_radical_electrons != modeled_radical_electrons:
        raise ValueError(
            "RDKit radical electron count does not match the Chemvas marks; "
            "calculation artifacts were not written"
        )
    if artifacts.electron_count < 1:
        raise ValueError("RDKit produced a nonpositive electron count")
    if declared_multiplicity > artifacts.electron_count + 1:
        raise ValueError("declared multiplicity exceeds the electron-count limit")
    if declared_multiplicity % 2 == artifacts.electron_count % 2:
        raise ValueError(
            "declared multiplicity has the wrong parity for the RDKit electron count"
        )
    if len(artifacts.atom_map) != artifacts.xyz_atom_count:
        raise ValueError("RDKit atom map does not match the XYZ atom count")
    if [entry.xyz_index for entry in artifacts.atom_map] != list(
        range(1, artifacts.xyz_atom_count + 1)
    ):
        raise ValueError("RDKit atom map has non-sequential XYZ indices")
    mol_indices = [
        entry.mol_index for entry in artifacts.atom_map if entry.mol_index is not None
    ]
    if mol_indices != list(range(1, artifacts.mol_atom_count + 1)):
        raise ValueError("RDKit atom map does not match the MOL atom count")


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


__all__ = ["select_components", "validate_calculation_artifacts"]
