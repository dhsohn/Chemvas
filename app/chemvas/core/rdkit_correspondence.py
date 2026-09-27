"""Suggest atom correspondences between reactant and product structures with MCS."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Protocol

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
_PLACEMENT_BUDGET = 5 * _MAX_CONSTRAINED_MCS_MATCHES
_ANCHOR_PROPERTY = "chemvas_anchor"
_DRAWN_ELEMENT_PROPERTY = "chemvas_element"
_SINGLE_ELEMENT_ATOM = re.compile(r"\[#\d+\]")
_SINGLE_TYPE_BONDS = frozenset(("-", "=", "#", ":"))
_CANDIDATE_LIMIT_MESSAGE = (
    "The substructure search reached its candidate limit. "
    "Use a smaller structure or map the atoms manually."
)
_ANCHORED_CANDIDATE_LIMIT_MESSAGE = (
    "The substructure search reached its candidate limit with the existing "
    "atom mappings. Review them or map the remaining atoms of the shared "
    "substructure, then suggest again."
)
_MULTIPLE_CORRESPONDENCES_MESSAGE = (
    "The ring-changing step has multiple structural atom "
    "correspondences. Add explicit atom mappings to choose "
    "the intended correspondence, then suggest again."
)


class _MatchParameters(Protocol):
    """The ``Chem.SubstructMatchParameters`` fields a grown search sets."""

    uniquify: bool
    maxMatches: int
    atomProperties: list[str]


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
            # Aliases collapse to carbon here; symmetry must keep the drawn label.
            for atom_id, index in atom_map.items():
                mol.GetAtomWithIdx(index).SetProp(
                    _DRAWN_ELEMENT_PROPERTY, model.atoms[atom_id].element
                )
        result = rdFMCS.FindMCS(
            [reactant_mol, product_mol],
            atomCompare=rdFMCS.AtomCompare.CompareElements,
            # Order-agnostic so a bond-order change at the reaction center does
            # not drop those atoms. Ring membership may change in a reaction;
            # ring-changing correspondences that symmetry does not relate
            # require anchors below.
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

        # An embedding places an atom at one query position only, and the
        # connected query lies within one fragment that has room for it.
        for side, mol in enumerate((reactant_mol, product_mol)):
            atoms = {pair[side] for pair in fixed_atom_indices}
            if len(atoms) < len(fixed_atom_indices) or not _fragment_holds(
                mol, query, atoms
            ):
                return None
        first = (
            tuple(reactant_mol.GetSubstructMatch(query)),
            tuple(product_mol.GetSubstructMatch(query)),
        )
        if not all(first):
            return None
        anchored = _anchored_pair(
            reactant_mol, product_mol, query, first, anchors=fixed_atom_indices
        )
        # Anchors on every query atom leave one correspondence. When no
        # embedding of either endpoint changes the query's own ring
        # membership, no pairing crosses a ring and any anchored one will do.
        if anchored is not None and (
            len(fixed_atom_indices) == query.GetNumAtoms()
            or (
                not require_unique
                and _keeps_query_rings(reactant_mol, query)
                and _keeps_query_rings(product_mol, query)
            )
        ):
            return anchored

        # When every embedding of one endpoint relabels its first match, that
        # match can stay fixed and the anchors narrow the other endpoint's
        # search before the candidate limit applies.
        if _single_type_query(query):
            for fixed_mol, fixed_match, other_mol, anchors, swapped in (
                (reactant_mol, first[0], product_mol, fixed_atom_indices, False),
                (
                    product_mol,
                    first[1],
                    reactant_mol,
                    tuple((b, a) for a, b in fixed_atom_indices),
                    True,
                ),
            ):
                if not _covers_its_component(fixed_mol, query, fixed_match):
                    continue
                # The other fragments have no room for the query, so the
                # anchors checked above all lie in this component.
                positions = {atom: index for index, atom in enumerate(fixed_match)}
                matches = _anchored_matches(
                    other_mol,
                    query,
                    {positions[fixed]: other for fixed, other in anchors},
                )
                # A search that gave up decides nothing; the other endpoint or
                # the full review below does.
                if matches is None:
                    continue
                if not matches:
                    return None
                paired = None
                if len(matches) < _MAX_CONSTRAINED_MCS_MATCHES:
                    paired = _pair_with_fixed_match(
                        fixed_mol,
                        fixed_match,
                        other_mol,
                        matches,
                        require_unique=require_unique,
                    )
                if paired is None:
                    return _pair_up_to_symmetry(
                        reactant_mol,
                        product_mol,
                        query,
                        fixed_atom_indices,
                        require_unique=require_unique,
                    )
                if not swapped:
                    return paired
                return paired[1], paired[0]

        reactant_matches = reactant_mol.GetSubstructMatches(
            query, uniquify=False, maxMatches=_MAX_CONSTRAINED_MCS_MATCHES
        )
        product_matches = product_mol.GetSubstructMatches(
            query, uniquify=False, maxMatches=_MAX_CONSTRAINED_MCS_MATCHES
        )
        # A truncated search cannot establish that no ring-crossing alternative
        # exists, even when the first pair preserves ring membership; the
        # symmetry review can.
        if any(
            len(matches) >= _MAX_CONSTRAINED_MCS_MATCHES
            for matches in (reactant_matches, product_matches)
        ):
            return _pair_up_to_symmetry(
                reactant_mol,
                product_mol,
                query,
                fixed_atom_indices,
                require_unique=require_unique,
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
        return _pair_up_to_symmetry(
            reactant_mol, product_mol, query, fixed_atom_indices, require_unique=True
        )


def _candidate_limit(anchors: tuple[tuple[int, int], ...]) -> ValueError:
    """The refusal at the candidate limit, naming any existing mappings."""
    if anchors:
        return ValueError(_ANCHORED_CANDIDATE_LIMIT_MESSAGE)
    return ValueError(_CANDIDATE_LIMIT_MESSAGE)


def _pair_up_to_symmetry(
    reactant_mol,
    product_mol,
    query,
    anchors: tuple[tuple[int, int], ...],
    *,
    require_unique: bool,
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Embeddings for the step's correspondence, counted up to symmetry.

    Two correspondences are the same when an automorphism of each endpoint
    carries one onto the other and the existing mappings onto themselves.
    The automorphisms keep each atom's drawn element, charge, radicals,
    isotope and hydrogens and each bond's order and aromaticity, so they
    keep ring membership too, and correspondences with different ring
    signatures never merge. Unless one correspondence is required,
    correspondences with a single ring signature leave the choice to the
    first, as before. None when no embedding pair holds the anchors.
    """
    signatures: set[tuple] = set()
    forms: dict[tuple, tuple[tuple[int, ...], tuple[int, ...]]] = {}

    def several() -> bool:
        return (require_unique or len(signatures) > 1) and len(forms) > 1

    def review(pair: tuple[tuple[int, ...], tuple[int, ...]]) -> bool:
        signatures.update(
            _embedding_ring_signature(mol, match)
            for mol, match in zip((reactant_mol, product_mol), pair, strict=True)
        )
        forms.setdefault(
            _correspondence_form(reactant_mol, product_mol, anchors, pair), pair
        )
        return several()

    finished = _symmetry_classes(reactant_mol, product_mol, query, anchors, review)
    if several():
        raise ValueError(_MULTIPLE_CORRESPONDENCES_MESSAGE)
    if not finished:
        raise _candidate_limit(anchors)
    return next(iter(forms.values()), None)


def _single_type_query(query) -> bool:
    """Whether every query atom and bond accepts one element or bond type.

    A bond-order change pairs two types in one query bond ("-,="). Such a
    query can accept an embedding yet reject its symmetric relabelling, so a
    fixed embedding would no longer stand for all of them.
    """
    return all(
        _SINGLE_ELEMENT_ATOM.fullmatch(atom.GetSmarts()) for atom in query.GetAtoms()
    ) and all(bond.GetSmarts() in _SINGLE_TYPE_BONDS for bond in query.GetBonds())


def _anchored_pair(
    reactant_mol,
    product_mol,
    query,
    first: tuple[tuple[int, ...], tuple[int, ...]],
    *,
    anchors: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Embeddings that place both atoms of each anchor at one query position.

    The first matches serve when they already hold every anchor. Otherwise
    one endpoint's first match sets the anchors' positions and the other
    endpoint is searched around them. None when neither search finds a pair,
    which does not rule one out.
    """
    if all(
        a in first[0] and b in first[1] and first[0].index(a) == first[1].index(b)
        for a, b in anchors
    ):
        return first
    mols = (reactant_mol, product_mol)
    for fixed, other in ((0, 1), (1, 0)):
        if not all(pair[fixed] in first[fixed] for pair in anchors):
            continue
        match = _anchored_match(
            mols[other],
            query,
            {first[fixed].index(pair[fixed]): pair[other] for pair in anchors},
        )
        if match is not None:
            return (first[0], match) if fixed == 0 else (match, first[1])
    return None


def _fragment_holds(mol, query, atoms: set[int]) -> bool:
    """Whether one fragment holds these atoms and has room for the query."""
    from rdkit import Chem

    return any(
        atoms <= set(fragment) and len(fragment) >= query.GetNumAtoms()
        for fragment in Chem.GetMolFrags(mol)
    )


def _covers_its_component(mol, query, match: tuple[int, ...]) -> bool:
    """Whether every embedding maps onto the atoms and bonds of this match.

    The match must cover every atom and bond of its component, and the other
    components must be too small to hold the query. Any embedding is then
    that component's automorphism applied to the match: it keeps ring
    membership, and for a single-type query it permutes query atoms.
    """
    from rdkit import Chem

    covered = set(match)
    fragments = Chem.GetMolFrags(mol)
    if not any(set(fragment) == covered for fragment in fragments):
        return False
    if sum(len(fragment) >= len(match) for fragment in fragments) > 1:
        return False
    bonds = sum(bond.GetBeginAtomIdx() in covered for bond in mol.GetBonds())
    return bonds == query.GetNumBonds()


def _keeps_query_rings(mol, query) -> bool:
    """Whether every embedding has the query's own ring signature.

    Query ring atoms and bonds always land on ring atoms and bonds. When no
    query chain atom lands on a ring atom and no chain bond on a ring bond,
    a ring bond joining two embedded atoms that the query does not bond
    closes a ring with the embedded path between them. Every query bond on
    that path lands on a ring bond, so the path lies in one ring system of
    the query. Three searches therefore decide it: a chain atom on a ring
    atom, a chain bond on a ring bond, and a ring system whose embedded
    atoms carry a bond the system lacks. Placements that reach the
    candidate limit, or together spend one placement budget, leave the
    question open.
    """
    from rdkit import Chem

    # An endpoint without rings cannot give any atom a ring.
    if not mol.GetRingInfo().NumRings():
        return True
    budget = _PlacementBudget()
    # A query read from SMARTS has no ring information of its own.
    ringed = Chem.Mol(query)
    Chem.FastFindRings(ringed)
    for atom in ringed.GetAtoms():
        if atom.IsInRing():
            continue
        landing = Chem.Mol(query)
        landing.GetAtomWithIdx(atom.GetIdx()).ExpandQuery(Chem.AtomFromSmarts("[R]"))
        landed = _grown_matches(
            mol, landing, [atom.GetIdx()], max_matches=1, budget=budget
        )
        if landed != []:
            return False
    for bond in ringed.GetBonds():
        ends = [bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]
        # A chain bond with a chain atom at one end lands on a ring bond only
        # where that atom lands on a ring atom.
        if bond.IsInRing() or not all(
            ringed.GetAtomWithIdx(end).IsInRing() for end in ends
        ):
            continue
        landing = Chem.Mol(query)
        landing.GetBondWithIdx(bond.GetIdx()).ExpandQuery(Chem.BondFromSmarts("@"))
        if _grown_matches(mol, landing, ends, max_matches=1, budget=budget) != []:
            return False
    bonds = [(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()) for bond in mol.GetBonds()]
    assigned: set[int] = set()
    for atom in ringed.GetAtoms():
        if not atom.IsInRing() or atom.GetIdx() in assigned:
            continue
        # The atoms reached from this one through ring bonds form its system.
        system = [atom.GetIdx()]
        assigned.add(atom.GetIdx())
        for index in system:
            for bond in ringed.GetAtomWithIdx(index).GetBonds():
                neighbor = bond.GetOtherAtomIdx(index)
                if bond.IsInRing() and neighbor not in assigned:
                    assigned.add(neighbor)
                    system.append(neighbor)
        system_query = Chem.RWMol(query)
        system_query.BeginBatchEdit()
        for index in range(query.GetNumAtoms()):
            if index not in system:
                system_query.RemoveAtom(index)
        system_query.CommitBatchEdit()
        matches = _grown_matches(
            mol,
            system_query,
            [0],
            max_matches=_MAX_CONSTRAINED_MCS_MATCHES,
            budget=budget,
        )
        if matches is None or len(matches) >= _MAX_CONSTRAINED_MCS_MATCHES:
            return False
        for covered in {frozenset(match) for match in matches}:
            joined = sum(a in covered and b in covered for a, b in bonds)
            if joined > system_query.GetNumBonds():
                return False
    return True


def _pair_with_fixed_match(
    fixed_mol,
    fixed_match: tuple[int, ...],
    other_mol,
    matches: list[tuple[int, ...]],
    *,
    require_unique: bool,
) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
    """Review the other endpoint's anchored embeddings against a fixed match.

    Relabelling both embeddings by one query automorphism keeps their atom
    correspondence, so pairing the fixed match with each anchored embedding
    of the other endpoint reaches every correspondence and ring signature
    that pairing all embeddings would. None when several correspondences
    are left for the symmetry review.
    """
    signature = _embedding_ring_signature(fixed_mol, fixed_match)
    # With one side fixed, distinct embeddings are distinct correspondences.
    if len(matches) > 1 and (
        require_unique
        or any(
            _embedding_ring_signature(other_mol, match) != signature
            for match in matches
        )
    ):
        return None
    return fixed_match, matches[0]


def _anchored_match(
    mol, query, anchored_positions: dict[int, int]
) -> tuple[int, ...] | None:
    """One embedding that places each anchored atom at its query position.

    The search grows outward from the anchors. Where the placements at a
    distance reach the candidate limit, the placements one bond closer are
    pinned one at a time and the search grows on from each, so symmetric
    ligands left free around the anchors take the first placement that
    fits. None when no embedding is found within the placement budget,
    which does not rule one out.
    """
    budget = _PlacementBudget()

    def grow(mol, query, lead: list[int]) -> tuple[int, ...] | None:
        closer: tuple[list[int], tuple[tuple[int, ...], ...]] = ([], ())
        for prefix, placements in _outward_placements(mol, query, lead, max_matches=1):
            budget.spend(placements)
            if not placements:
                return None
            if len(prefix) == query.GetNumAtoms():
                return _in_query_order(prefix, placements[0])
            if len(placements) >= _MAX_CONSTRAINED_MCS_MATCHES:
                break
            closer = (prefix, placements)
        prefix, placements = closer
        # Pinning the only placement of the closer atoms narrows nothing.
        if len(placements) < 2:
            return None
        for placement in placements:
            if budget.spent:
                return None
            pinned_mol, pinned_query = _labelled(
                mol, query, dict(zip(prefix, placement, strict=True))
            )
            pinned = grow(pinned_mol, pinned_query, prefix)
            if pinned is not None:
                return pinned
        return None

    mol, query = _labelled(mol, query, anchored_positions)
    return grow(mol, query, list(anchored_positions))


def _anchored_matches(
    mol, query, anchored_positions: dict[int, int]
) -> list[tuple[int, ...]] | None:
    """Embeddings that place each anchored atom at its query position.

    None when the placements around the anchors reach the candidate limit
    or spend the placement budget before the whole query is placed.
    """
    mol, query = _labelled(mol, query, anchored_positions)
    # Without anchors the search grows from the first query atom.
    return _grown_matches(
        mol,
        query,
        list(anchored_positions) or [0],
        max_matches=_MAX_CONSTRAINED_MCS_MATCHES,
        budget=_PlacementBudget(),
    )


def _labelled(mol, query, positions: dict[int, int]):
    """Copies whose labels hold each query position to its atom."""
    from rdkit import Chem

    # Label copies so the callers' molecules stay unchanged.
    query = Chem.Mol(query)
    mol = Chem.Mol(mol)
    for label, (position, atom) in enumerate(positions.items(), start=1):
        query.GetAtomWithIdx(position).SetIntProp(_ANCHOR_PROPERTY, label)
        mol.GetAtomWithIdx(atom).SetIntProp(_ANCHOR_PROPERTY, label)
    return mol, query


class _PlacementBudget:
    """The placements a grown search may enumerate, across its steps."""

    def __init__(self) -> None:
        self._left = _PLACEMENT_BUDGET

    def spend(self, placements: tuple[tuple[int, ...], ...]) -> None:
        self._left -= len(placements)

    @property
    def spent(self) -> bool:
        return self._left <= 0


def _grown_matches(
    mol, query, lead: list[int], *, max_matches: int, budget: _PlacementBudget
) -> list[tuple[int, ...]] | None:
    """Embeddings of the query, searched outward from the lead positions.

    None when the placements reach the candidate limit or spend the budget
    before the whole query is placed.
    """
    for prefix, placements in _outward_placements(
        mol, query, lead, max_matches=max_matches
    ):
        budget.spend(placements)
        if not placements:
            return []
        if len(prefix) < query.GetNumAtoms() and (
            len(placements) >= _MAX_CONSTRAINED_MCS_MATCHES or budget.spent
        ):
            return None
    return [_in_query_order(prefix, placement) for placement in placements]


def _outward_placements(mol, query, lead: list[int], *, max_matches: int):
    """Placements of the query atoms within each distance of the lead.

    The search is repeated with the query atoms one bond farther from the
    lead each time. A lead that cannot be placed fails at the distance where
    its surroundings stop fitting, not after every symmetric placement of
    the atoms beyond them, and the placements at each distance bound the
    work at the next. Yields the query positions placed so far with up to
    the candidate limit of their placements, and up to max_matches for the
    whole query.
    """
    from rdkit import Chem

    # Numbered outward from the lead, the atoms within each distance form a
    # prefix of the query, and the search starts at the lead.
    order = list(lead)
    distance = dict.fromkeys(lead, 0)
    for index in order:
        for neighbor in query.GetAtomWithIdx(index).GetNeighbors():
            if neighbor.GetIdx() not in distance:
                distance[neighbor.GetIdx()] = distance[index] + 1
                order.append(neighbor.GetIdx())
    led = Chem.RenumberAtoms(query, order)
    params: _MatchParameters = Chem.SubstructMatchParameters()
    params.uniquify = False
    # A labelled atom matches only an atom carrying the same label.
    params.atomProperties = [_ANCHOR_PROPERTY]
    farthest = distance[order[-1]]
    for radius in range(farthest + 1):
        near = Chem.RWMol(led)
        near.BeginBatchEdit()
        for position, index in enumerate(order):
            if distance[index] > radius:
                near.RemoveAtom(position)
        near.CommitBatchEdit()
        params.maxMatches = (
            max_matches if radius == farthest else _MAX_CONSTRAINED_MCS_MATCHES
        )
        yield order[: near.GetNumAtoms()], mol.GetSubstructMatches(near, params)


def _in_query_order(prefix: list[int], placement: tuple[int, ...]) -> tuple[int, ...]:
    """A placement of every query atom, listed by query position."""
    position_of = {index: position for position, index in enumerate(prefix)}
    return tuple(placement[position_of[index]] for index in range(len(prefix)))


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


def _symmetry_classes(reactant_mol, product_mol, query, anchors, review) -> bool:
    """Offer the review one embedding pair of each class under symmetry.

    Query positions are placed outward from the one with the fewest
    candidate pairs. A position's candidates are cut to one per class of
    the automorphisms that fix every atom placed so far: first on each
    endpoint with the anchors fixed too, then, with anchors, on both
    endpoints at once with the anchors mapped onto themselves. Every
    embedding pair is then an automorphic image of an offered one, so every
    correspondence reaches the review, which stops the search by returning
    True. False when the placements and symmetry checks reach the candidate
    limit first.
    """
    mols = (reactant_mol, product_mol)
    partners = (dict(anchors), {b: a for a, b in anchors})
    reactant_domains = _embedding_domains(reactant_mol, query)
    product_domains = _embedding_domains(product_mol, query)
    if reactant_domains is None or product_domains is None:
        return True
    domains = (reactant_domains, product_domains)
    order = [
        min(
            range(query.GetNumAtoms()),
            key=lambda index: len(domains[0][index]) * len(domains[1][index]),
        )
    ]
    parent = {order[0]: order[0]}
    for index in order:
        for neighbor in query.GetAtomWithIdx(index).GetNeighbors():
            if neighbor.GetIdx() not in parent:
                parent[neighbor.GetIdx()] = index
                order.append(neighbor.GetIdx())
    step_of = {index: step for step, index in enumerate(order)}
    # The query bonds from each position back to the positions placed before.
    placed_bonds = [
        [
            (step_of[other], query.GetBondBetweenAtoms(index, other))
            for other in (
                atom.GetIdx() for atom in query.GetAtomWithIdx(index).GetNeighbors()
            )
            if step_of[other] < step
        ]
        for step, index in enumerate(order)
    ]
    # Both endpoints share one index space, the product's atoms after the
    # reactant's, as in the joined graph.
    offset = reactant_mol.GetNumAtoms()
    marks = _symmetry_marks(reactant_mol, product_mol, anchors)
    # Marks from here on single out one atom each.
    single = max(marks) + 1
    candidate = single + len(marks)
    joined = _joined(reactant_mol, product_mol, anchors)
    checks = 0

    def candidates(side: int, placed: tuple[int, ...]) -> list[int]:
        index = order[len(placed)]
        if not placed:
            return sorted(domains[side][index])
        mol = mols[side]
        bonded = mol.GetAtomWithIdx(placed[step_of[parent[index]]])
        return [
            atom
            for atom in (neighbor.GetIdx() for neighbor in bonded.GetNeighbors())
            if atom in domains[side][index]
            and atom not in placed
            and all(
                (bond := mol.GetBondBetweenAtoms(atom, placed[step])) is not None
                and query_bond.Match(bond)
                for step, query_bond in placed_bonds[len(placed)]
            )
        ]

    def distinct(mol, pinned: list[int], options: list[tuple[int, ...]]):
        # Options whose marked graphs share a canonical form are automorphic.
        nonlocal checks
        if len(options) < 2:
            return options
        checks += len(options)
        kept: dict[tuple, tuple[int, ...]] = {}
        for option in options:
            marked = list(pinned)
            for rank, atom in enumerate(option):
                marked[atom] = candidate + rank
            kept.setdefault(_canonical_form(mol, marked), option)
        return list(kept.values())

    stack: list[tuple[tuple[int, ...], tuple[int, ...]]] = [((), ())]
    while stack:
        placed = stack.pop()
        checks += 1
        if checks >= _MAX_CONSTRAINED_MCS_MATCHES:
            return False
        if len(placed[0]) == len(order):
            # A placed anchor has its partner beside it; each must be placed.
            if not partners[0].keys() <= set(placed[0]):
                continue
            pair = tuple(
                tuple(atoms[step_of[index]] for index in range(len(order)))
                for atoms in placed
            )
            if review(pair):
                return True
            continue
        options = []
        for side, shift in ((0, 0), (1, offset)):
            pinned = marks[shift : shift + mols[side].GetNumAtoms()]
            for atom in (*partners[side], *placed[side]):
                pinned[atom] = single + shift + atom
            options.append(
                distinct(
                    mols[side],
                    pinned,
                    [(atom,) for atom in candidates(side, placed[side])],
                )
            )
        children: list[tuple[int, ...]] = [
            (reactant, offset + product)
            for (reactant,) in options[0]
            for (product,) in options[1]
            if partners[0].get(reactant, product) == product
            and partners[1].get(product, reactant) == reactant
        ]
        if anchors:
            pinned = list(marks)
            for atom in (*placed[0], *(offset + atom for atom in placed[1])):
                pinned[atom] = single + atom
            children = distinct(joined, pinned, children)
        stack.extend(
            ((*placed[0], reactant), (*placed[1], product - offset))
            for reactant, product in reversed(children)
        )
    return True


def _embedding_domains(mol, query) -> list[set[int]] | None:
    """The atoms each query position can take in the molecule.

    An atom stays in a position's domain while the query neighbours of the
    position have distinct bonded atoms in their own domains, and the only
    atom of one domain stays in no other. None when a position has no atom
    left.
    """
    domains = [
        {atom.GetIdx() for atom in mol.GetAtoms() if query_atom.Match(atom)}
        for query_atom in query.GetAtoms()
    ]
    neighbors = [
        [
            (other.GetIdx(), query.GetBondBetweenAtoms(index, other.GetIdx()))
            for other in query.GetAtomWithIdx(index).GetNeighbors()
        ]
        for index in range(len(domains))
    ]

    def supported(index: int, atom: int) -> bool:
        bonds = mol.GetAtomWithIdx(atom).GetBonds()
        return _distinct_choice(
            [
                [
                    bond.GetOtherAtomIdx(atom)
                    for bond in bonds
                    if bond.GetOtherAtomIdx(atom) in domains[other]
                    and query_bond.Match(bond)
                ]
                for other, query_bond in neighbors[index]
            ]
        )

    changed = True
    while changed:
        changed = False
        for index, domain in enumerate(domains):
            kept = {atom for atom in domain if supported(index, atom)}
            if len(kept) == 1:
                for other, others in enumerate(domains):
                    if other != index and kept & others:
                        others -= kept
                        changed = True
            if kept != domain:
                domains[index] = kept
                changed = True
    if not all(domains):
        return None
    return domains


def _distinct_choice(options: list[list[int]]) -> bool:
    """Whether each list can contribute a different atom, found by matching."""
    owner: dict[int, int] = {}

    def assign(index: int, tried: set[int]) -> bool:
        for atom in options[index]:
            if atom not in tried:
                tried.add(atom)
                if atom not in owner or assign(owner[atom], tried):
                    owner[atom] = index
                    return True
        return False

    return all(assign(index, set()) for index in range(len(options)))


def _symmetry_marks(reactant_mol, product_mol, anchors) -> list[int]:
    """A positive mark per atom of both endpoints for what automorphisms keep.

    Aliases collapse to carbon in the tolerant build, so the drawn element
    recorded on each atom is kept alongside the built one.
    """
    kinds = [
        (
            side,
            atom.GetAtomicNum(),
            atom.GetProp(_DRAWN_ELEMENT_PROPERTY)
            if atom.HasProp(_DRAWN_ELEMENT_PROPERTY)
            else "",
            atom.GetFormalCharge(),
            atom.GetNumRadicalElectrons(),
            atom.GetIsotope(),
            atom.GetTotalNumHs(),
            atom.GetIsAromatic(),
            atom.GetIdx() in anchored,
        )
        for side, mol, anchored in (
            (0, reactant_mol, {a for a, _ in anchors}),
            (1, product_mol, {b for _, b in anchors}),
        )
        for atom in mol.GetAtoms()
    ]
    numbers = {kind: number for number, kind in enumerate(sorted(set(kinds)), 1)}
    return [numbers[kind] for kind in kinds]


def _joined(reactant_mol, product_mol, pairs):
    """Both endpoints as one graph, each pair of atoms joined by a bond.

    The joining bonds have order zero, so they leave every atom's hydrogen
    count as it was.
    """
    from rdkit import Chem

    joined = Chem.RWMol(Chem.CombineMols(reactant_mol, product_mol))
    offset = reactant_mol.GetNumAtoms()
    for reactant, product in pairs:
        joined.AddBond(reactant, offset + product, Chem.BondType.ZERO)
    mol = joined.GetMol()
    mol.UpdatePropertyCache(strict=False)
    return mol


def _correspondence_form(reactant_mol, product_mol, anchors, pair) -> tuple:
    """The canonical form of a correspondence joined to both endpoints.

    Equal forms are correspondences that automorphisms of the endpoints,
    mapping anchored atoms onto anchored atoms, carry onto one another; an
    anchored atom is joined to its partner in both.
    """
    return _canonical_form(
        _joined(reactant_mol, product_mol, zip(*pair, strict=True)),
        _symmetry_marks(reactant_mol, product_mol, anchors),
    )


def _canonical_form(mol, marks: list[int]) -> tuple:
    """The marked graph relabelled by its canonical ranking.

    Equal forms prove the graphs isomorphic: mapping the atoms of equal
    rank onto one another keeps every mark and bond. RDKit gives
    isomorphic graphs equal forms, and where it would not, two classes stay
    apart, which refuses a suggestion but never merges correspondences.
    """
    from rdkit import Chem

    marked = Chem.Mol(mol)
    for atom, mark in zip(marked.GetAtoms(), marks, strict=True):
        atom.SetAtomMapNum(mark)
    ranks = list(Chem.CanonicalRankAtoms(marked, includeChirality=False))
    by_rank = sorted(range(len(ranks)), key=ranks.__getitem__)
    return tuple(marks[index] for index in by_rank), frozenset(
        (
            *sorted((ranks[bond.GetBeginAtomIdx()], ranks[bond.GetEndAtomIdx()])),
            bond.GetBondType(),
        )
        for bond in marked.GetBonds()
    )
