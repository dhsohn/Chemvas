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
                if len(matches) >= _MAX_CONSTRAINED_MCS_MATCHES:
                    raise _candidate_limit(fixed_atom_indices)
                paired = _pair_with_fixed_match(
                    fixed_mol,
                    fixed_match,
                    other_mol,
                    matches,
                    require_unique=require_unique,
                )
                if paired is None or not swapped:
                    return paired
                return paired[1], paired[0]

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
            raise _candidate_limit(fixed_atom_indices)

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
                        raise ValueError(_MULTIPLE_CORRESPONDENCES_MESSAGE)
                    selected_pairs = pairs
                    selected = (reactant_match, product_match)
        return selected


def _candidate_limit(anchors: tuple[tuple[int, int], ...]) -> ValueError:
    """The refusal at the candidate limit, naming any existing mappings."""
    if anchors:
        return ValueError(_ANCHORED_CANDIDATE_LIMIT_MESSAGE)
    return ValueError(_CANDIDATE_LIMIT_MESSAGE)


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
    that pairing all embeddings would.
    """
    if not matches:
        return None
    signature = _embedding_ring_signature(fixed_mol, fixed_match)
    # With one side fixed, distinct embeddings are distinct correspondences.
    if len(matches) > 1 and (
        require_unique
        or any(
            _embedding_ring_signature(other_mol, match) != signature
            for match in matches
        )
    ):
        raise ValueError(_MULTIPLE_CORRESPONDENCES_MESSAGE)
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
