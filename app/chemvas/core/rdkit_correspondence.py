"""Suggest atom correspondences between reactant and product structures with MCS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chemvas.core.rdkit_diagnostics import RDKIT_UNAVAILABLE_MESSAGE
from chemvas.domain.document import (
    MoleculeModel,
    connected_atom_components,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.core.rdkit_mol_building import _RDKitMolBuilding

logger = logging.getLogger(__name__)

_MAX_CONSTRAINED_MCS_MATCHES = 10_000


class _RDKitCorrespondence(_RDKitMolBuilding):
    adapter: RDKitAdapter

    @staticmethod
    def _submodel(
        model: MoleculeModel, atom_ids: frozenset[int] | set[int]
    ) -> MoleculeModel:
        # atom_ids comes from a caller, not from a component walk, so an id that
        # is no longer in the model is reachable here.
        atoms = {
            atom_id: model.atoms[atom_id]
            for atom_id in atom_ids
            if atom_id in model.atoms
        }
        bonds = [
            bond
            for bond in model.bonds
            if bond is not None and bond.a in atoms and bond.b in atoms
        ]
        annotations = model.atom_annotations
        return MoleculeModel(
            atoms=dict(atoms),
            bonds=list(bonds),
            atom_annotations={
                atom_id: dict(annotations[atom_id])
                for atom_id in atoms
                if atom_id in annotations
            },
        )

    def _suggest_atom_correspondence(
        self,
        model: MoleculeModel,
        reactant_atom_ids: frozenset[int] | set[int],
        product_atom_ids: frozenset[int] | set[int],
        existing_correspondence: Mapping[int, int] | None = None,
    ) -> list[tuple[int, int]] | None:
        """Suggest reactant->product atom pairs from the common substructure.

        Returns element-consistent ``(reactant_id, product_id)`` pairs for the
        atoms RDKit matches by element and connectivity. Bond orders are compared
        loosely, so atoms whose bonds only change order (a typical reaction
        center, e.g. C-O -> C=O) are mapped too. This connected-match heuristic
        can leave other shared components and reaction centres unmapped. An empty
        list means this search found no usable pairs, not proof that no shared
        substructure exists; ``None`` with
        ``adapter.last_error`` set means the suggestion could not run. The two
        are distinct on purpose — reporting a failure as an empty result would
        present a tool problem as a chemistry claim about the drawing. This is
        a review-only suggestion and decides no chemistry on its own. Existing
        correspondence is a hard constraint on symmetry-equivalent MCS
        embeddings; a suggestion is refused instead of mixing an incompatible
        automorphism into the researcher's mapping. Fully identity-mapped,
        complete components shared by both endpoints are retained separately
        so an already-reviewed catalyst cannot crowd out the reacting structure.
        """
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = RDKIT_UNAVAILABLE_MESSAGE
            return None
        Chem, _ = rdkit
        try:
            from rdkit.Chem import rdFMCS
        except Exception:
            self.adapter.last_error = (
                "RDKit is installed, but its substructure-search module "
                "(rdkit.Chem.rdFMCS) failed to import."
            )
            return None
        retained_ids = self._mapped_shared_components(
            model, reactant_atom_ids, product_atom_ids, existing_correspondence or {}
        )
        retained_pairs = [(atom_id, atom_id) for atom_id in sorted(retained_ids)]
        remaining_reactants = reactant_atom_ids - retained_ids
        remaining_products = product_atom_ids - retained_ids
        if retained_ids and (not remaining_reactants or not remaining_products):
            return retained_pairs
        reactant_mol, reactant_map = self.model_to_rdkit_with_map_tolerant(
            self._submodel(model, remaining_reactants)
        )
        product_mol, product_map = self.model_to_rdkit_with_map_tolerant(
            self._submodel(model, remaining_products)
        )
        for side, mol, atom_map in (
            ("reactant", reactant_mol, reactant_map),
            ("product", product_mol, product_map),
        ):
            if mol is None or atom_map is None:
                # The tolerant build records its own reason; keep it instead of
                # clobbering it with a vaguer one.
                if self.adapter.last_error is None:
                    self.adapter.last_error = (
                        f"Failed to build the {side} structure for the suggestion."
                    )
                return None
            if mol.GetNumAtoms() == 0:
                self.adapter.last_error = (
                    f"The {side} endpoint has no included structure to compare."
                )
                return None
        result = rdFMCS.FindMCS(
            [reactant_mol, product_mol],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            # Order-agnostic so a bond-order change at the reaction center does
            # not drop those atoms. Ring membership may change in a reaction;
            # ambiguous embeddings of ring-changing steps require anchors below.
            bondCompare=rdFMCS.BondCompare.CompareAny,
            ringMatchesRingOnly=False,
            completeRingsOnly=False,
            timeout=5,
        )
        if result.canceled:
            # A canceled search can stop in well under the timeout and is not
            # deterministic; it may already hold a large valid MCS, but using a
            # possibly non-maximal one is a chemistry decision this suggestion
            # does not make. Retrying routinely succeeds.
            self.adapter.last_error = (
                "The substructure search stopped before it finished. "
                "Try the suggestion again."
            )
            return None
        if result.numAtoms == 0:
            return retained_pairs
        query = Chem.MolFromSmarts(result.smartsString)
        if query is None:
            self.adapter.last_error = (
                "RDKit could not re-read the substructure pattern it found."
            )
            return None
        fixed_atom_indices = tuple(
            (reactant_map[reactant_id], product_map[product_id])
            for reactant_id, product_id in sorted(
                (existing_correspondence or {}).items()
            )
            if reactant_id in reactant_map and product_id in product_map
        )
        ring_change = sum(atom.IsInRing() for atom in reactant_mol.GetAtoms()) != sum(
            atom.IsInRing() for atom in product_mol.GetAtoms()
        )
        try:
            matched_embeddings = self._mcs_embeddings_honoring_correspondence(
                reactant_mol,
                product_mol,
                query,
                fixed_atom_indices=fixed_atom_indices,
                require_unique=ring_change,
            )
        except ValueError as error:
            self.adapter.last_error = str(error)
            return None
        if matched_embeddings is None:
            self.adapter.last_error = (
                "The existing atom mappings do not align with the shared "
                "substructure. Review or clear them before requesting a "
                "structural suggestion."
            )
            return None
        reactant_match, product_match = matched_embeddings
        if len(reactant_match) != len(product_match):
            self.adapter.last_error = (
                "The shared substructure matched the two endpoints inconsistently."
            )
            return None
        reactant_id_by_idx = {idx: atom_id for atom_id, idx in reactant_map.items()}
        product_id_by_idx = {idx: atom_id for atom_id, idx in product_map.items()}
        pairs = retained_pairs
        used_products = set(retained_ids)
        for reactant_idx, product_idx in zip(
            reactant_match, product_match, strict=True
        ):
            reactant_id = reactant_id_by_idx.get(reactant_idx)
            product_id = product_id_by_idx.get(product_idx)
            if reactant_id is None or product_id is None:
                continue
            # The drawn element is authoritative (aliases collapse to carbon in
            # the tolerant mol), so keep the same-element rule the dialog enforces.
            if model.atoms[reactant_id].element != model.atoms[product_id].element:
                continue
            if product_id in used_products:
                continue
            used_products.add(product_id)
            pairs.append((reactant_id, product_id))
        return pairs

    @staticmethod
    def _mapped_shared_components(
        model: MoleculeModel,
        reactant_atom_ids: frozenset[int] | set[int],
        product_atom_ids: frozenset[int] | set[int],
        existing_correspondence: Mapping[int, int],
    ) -> set[int]:
        shared = reactant_atom_ids & product_atom_ids
        identity_ids = {
            atom_id
            for atom_id in shared
            if existing_correspondence.get(atom_id) == atom_id
        }
        # A conflicting non-identity anchor must still reach constrained MCS,
        # not disappear merely because its target belongs to a shared component.
        identity_ids.difference_update(
            target
            for source, target in existing_correspondence.items()
            if source != target
        )
        if not identity_ids:
            return set()
        components = connected_atom_components(
            model.atoms,
            ((bond.a, bond.b) for bond in model.bonds if bond is not None),
        )
        return {
            atom_id
            for component in components
            if identity_ids.issuperset(component)
            for atom_id in component
        }

    @staticmethod
    def _mcs_embeddings_honoring_correspondence(
        reactant_mol,
        product_mol,
        query,
        *,
        fixed_atom_indices: tuple[tuple[int, int], ...],
        require_unique: bool = False,
    ) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
        """Choose paired MCS embeddings that contain and preserve every anchor."""

        reactant_matches = reactant_mol.GetSubstructMatches(
            query, uniquify=False, maxMatches=_MAX_CONSTRAINED_MCS_MATCHES
        )
        product_matches = product_mol.GetSubstructMatches(
            query, uniquify=False, maxMatches=_MAX_CONSTRAINED_MCS_MATCHES
        )
        # A truncated search cannot establish that no ring-crossing alternative
        # exists, even when the first pair preserves ring membership.
        if any(
            len(matches) >= _MAX_CONSTRAINED_MCS_MATCHES
            for matches in (reactant_matches, product_matches)
        ):
            raise ValueError(
                "The substructure search reached its candidate limit. "
                "Use a smaller structure or map the atoms manually."
            )

        def grouped_matches(matches, anchor_indices):
            groups: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
            for raw_match in matches:
                match = tuple(raw_match)
                positions = {atom: index for index, atom in enumerate(match)}
                if not all(atom in positions for atom in anchor_indices):
                    continue
                signature = tuple(positions[atom] for atom in anchor_indices)
                groups.setdefault(signature, []).append(match)
            return groups

        reactant_groups = grouped_matches(
            reactant_matches, tuple(a for a, _ in fixed_atom_indices)
        )
        product_groups = grouped_matches(
            product_matches, tuple(b for _, b in fixed_atom_indices)
        )
        compatible = [
            (matches, product_groups[signature])
            for signature, matches in reactant_groups.items()
            if signature in product_groups
        ]
        if not compatible:
            return None

        # Check every anchor-compatible embedding's ring signature. Comparing
        # signature sets avoids an unbounded Cartesian product just to discover
        # whether a ring-preserving first pair hides a ring-crossing candidate.
        for reactants, products in compatible:
            signatures = {
                _embedding_ring_signature(mol, match)
                for mol, matches in (
                    (reactant_mol, reactants),
                    (product_mol, products),
                )
                for match in matches
            }
            if len(signatures) > 1:
                require_unique = True
                break
        if not require_unique:
            return compatible[0][0][0], compatible[0][1][0]

        if sum(len(r) * len(p) for r, p in compatible) > _MAX_CONSTRAINED_MCS_MATCHES:
            raise ValueError(
                "Too many ring-changing correspondences to review safely. "
                "Add explicit atom mappings before requesting a suggestion."
            )
        selected = None
        selected_pairs = None
        for reactants, products in compatible:
            for reactant_match in reactants:
                for product_match in products:
                    pairs = dict(zip(reactant_match, product_match, strict=True))
                    if selected_pairs is not None and pairs != selected_pairs:
                        raise ValueError(
                            "The ring-changing step has multiple structural atom "
                            "correspondences. Add explicit atom mappings to choose "
                            "the intended correspondence, then suggest again."
                        )
                    selected_pairs = pairs
                    selected = (reactant_match, product_match)
        return selected


def _embedding_ring_signature(mol, match):
    """Mapped ring atoms and edges in query order, suitable for set comparison."""
    positions = {atom: index for index, atom in enumerate(match)}
    atoms = tuple(mol.GetAtomWithIdx(atom).IsInRing() for atom in match)
    edges = frozenset(
        tuple(
            sorted((positions[bond.GetBeginAtomIdx()], positions[bond.GetEndAtomIdx()]))
        )
        for bond in mol.GetBonds()
        if bond.IsInRing()
        and bond.GetBeginAtomIdx() in positions
        and bond.GetEndAtomIdx() in positions
    )
    return atoms, edges
