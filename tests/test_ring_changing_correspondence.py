"""Ring creation must not manufacture a methyl/radical correspondence."""

import copy
import importlib.util
import time
from dataclasses import replace

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel
from tests.test_catalyst_correspondence import _append_smiles

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)


@pytest.mark.parametrize(
    "reactant,product,anchors",
    [
        ("O=CCCCCO", "OC1CCCCO1", {0: 0}),
        ("[CH2]CCCC=C", "[CH2]C1CCCC1", {5: 0, 0: 2}),
        ("[CH2-]C(=O)CCCC(C)=O", "CC1(O)CCCC(=O)C1", {0: 8}),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_ring_change_requests_review_then_completes_anchored_mapping(
    reactant, product, anchors, reverse
):
    adapter = RDKitAdapter()
    model = MoleculeModel()
    r = _append_smiles(adapter, model, reactant)
    p = _append_smiles(adapter, model, product)
    offset = min(p)
    fixed = {a: b + offset for a, b in anchors.items()}
    if reverse:
        ids = {atom_id: 1000 - atom_id for atom_id in model.atoms}
        model.atoms = {ids[key]: atom for key, atom in model.atoms.items()}
        model.bonds = [
            replace(bond, a=ids[bond.a], b=ids[bond.b])
            for bond in reversed(model.bonds)
            if bond is not None
        ]
        model.atom_annotations = {
            ids[key]: value for key, value in model.atom_annotations.items()
        }
        model.next_atom_id = max(ids.values()) + 1
        r = frozenset(ids[key] for key in r)
        p = frozenset(ids[key] for key in p)
        fixed = {ids[a]: ids[b] for a, b in fixed.items()}
    original = copy.deepcopy(model)
    result = adapter.suggest_atom_correspondence_result(model, r, p)
    assert result.value is None
    assert "multiple structural atom" in result.error
    result = adapter.suggest_atom_correspondence_result(model, r, p, fixed)
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs) == r
    assert set(pairs.values()) == p
    assert all(pairs[a] == b for a, b in fixed.items())
    assert model == original


@pytest.mark.parametrize(
    "product",
    [
        "C1CC1C1CC1",
        # The cyclohexane fits the rim of the bicyclohexane, whose bridging
        # ring bond joins two atoms the query does not bond.
        "C1CC2CCC12",
    ],
)
def test_equal_ring_atom_counts_do_not_bypass_topology_review(product):
    adapter = RDKitAdapter()
    model = MoleculeModel()
    reactants = _append_smiles(adapter, model, "C1CCCCC1")
    products = _append_smiles(adapter, model, product)
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.value is None
    assert "multiple structural atom" in result.error
    # A partial anchor must not re-enable the first-embedding shortcut either.
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, {0: 8}
    )
    assert result.value is None
    assert "multiple structural atom" in result.error


@pytest.mark.parametrize(
    "reactant,product,smarts,anchors",
    [
        ("C1CC1.CCC", "C1CC1.CCC", "CCC", ()),
        ("C1CC1CC", "C1CC1CC", "CC", ((2, 2),)),
        # The first match covers the whole chain, but the ring can hold it too.
        ("CCC.C1CC1", "CCC.C1CC1", "[#6]-[#6]-[#6]", ()),
        # Only the product's embeddings are relabellings of its first match;
        # the reactant's chain is complete too, but its ring holds the query.
        ("CCC.C1CC1", "CCC", "[#6]-[#6]-[#6]", ()),
        # The first match covers every atom of its component but not the
        # ring-closing bond, so other embeddings are not relabellings of it.
        ("C1CC1C", "C1CC1C", "[#6]-[#6]-[#6]-[#6]", ()),
    ],
)
def test_ring_preserving_first_match_does_not_hide_crossing_candidates(
    reactant, product, smarts, anchors
):
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _RDKitCorrespondence

    query = Chem.MolFromSmarts(smarts)
    # Ring-preserving matches must not hide ring-to-chain alternatives,
    # including alternatives beside an anchored ring/chain junction.
    with pytest.raises(ValueError, match="multiple structural atom"):
        _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
            Chem.MolFromSmiles(reactant),
            Chem.MolFromSmiles(product),
            query,
            fixed_atom_indices=anchors,
        )


def test_chain_through_a_whole_ring_does_not_fix_its_first_match():
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _RDKitCorrespondence

    # The chain covers every cyclopentane atom but not every ring bond, so
    # other embeddings leave out another bond instead of relabelling the
    # first one, and the anchored atom can end the chain either way round.
    with pytest.raises(ValueError, match="multiple structural atom"):
        _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
            Chem.MolFromSmiles("C1CCCC1"),
            Chem.MolFromSmiles("CCCCC"),
            Chem.MolFromSmarts("[#6]-[#6]-[#6]-[#6]-[#6]"),
            fixed_atom_indices=((0, 0),),
        )


def test_explicit_anchors_reduce_candidate_pairs_before_the_limit():
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _RDKitCorrespondence

    mol = Chem.MolFromSmiles(".".join(["CO"] * 101))
    query = Chem.MolFromSmarts("CO")
    with pytest.raises(ValueError, match="Too many ring-changing"):
        _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
            mol, mol, query, fixed_atom_indices=(), require_unique=True
        )
    match = _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
        mol,
        mol,
        query,
        fixed_atom_indices=((200, 200), (201, 201)),
        require_unique=True,
    )
    assert match == ((200, 201), (200, 201))


def test_truncated_search_cannot_claim_no_ring_crossing_alternative(monkeypatch):
    from rdkit import Chem

    from chemvas.core import rdkit_correspondence

    monkeypatch.setattr(rdkit_correspondence, "_MAX_CONSTRAINED_MCS_MATCHES", 3)
    mol = Chem.MolFromSmiles("C1CC1.CCC")
    query = Chem.MolFromSmarts("CCC")
    with pytest.raises(ValueError, match="candidate limit"):
        rdkit_correspondence._RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
            mol, mol, query, fixed_atom_indices=()
        )


@pytest.mark.parametrize(
    "smiles,smarts,keeps",
    [
        # A chain atom of the query lands on a ring atom.
        ("C1CC1", "[#6]-[#6]-[#6]", False),
        # The chain bond between the query's two rings lands on a ring bond.
        ("C12CC1C1CC1C2", "[#6]1-[#6]-[#6]-1-[#6]1-[#6]-[#6]-1", False),
        # A ring bond of the drawing joins two atoms of one query ring.
        ("C1CC2CCC12", "[#6]1-[#6]-[#6]-[#6]-[#6]-[#6]-1", False),
        # The phenyl ring fits the naphthalene ring on phosphorus. Its fused
        # carbon has a ring bond the phenyl lacks, but it leads out of the
        # embedding, so ring membership stays the query's own.
        ("CPc1cccc2ccccc12", "[#15]-[#6]1:[#6]:[#6]:[#6]:[#6]:[#6]:1", True),
    ],
)
def test_ring_signature_changes_are_found_where_they_arise(smiles, smarts, keeps):
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _keeps_query_rings

    mol = Chem.MolFromSmiles(smiles)
    assert _keeps_query_rings(mol, Chem.MolFromSmarts(smarts)) is keeps


@pytest.mark.parametrize(
    "smiles,smarts",
    [
        # The propyl chain fits along the cyclohexane until the phosphorus
        # is required.
        ("CCCP.C1CCCCC1", "[#6]-[#6]-[#6]-[#15]"),
        # Both naphthalene rings hold the phenyl ring without a bond it lacks.
        ("CPc1ccccc1.c1ccc2ccccc2c1", "[#15]-[#6]1:[#6]:[#6]:[#6]:[#6]:[#6]:1"),
        # The bond between the two rings fits the triazolidine's ring bonds
        # until the oxygen and sulfur are required.
        ("O1CN1N1CS1.C1NNNC1", "[#8]1-[#6]-[#7]-1-2.[#16]1-[#6]-[#7]-1-2"),
    ],
)
def test_ring_signature_check_stops_at_the_candidate_limit(monkeypatch, smiles, smarts):
    from rdkit import Chem

    from chemvas.core import rdkit_correspondence

    mol = Chem.MolFromSmiles(smiles)
    query = Chem.MolFromSmarts(smarts)
    assert rdkit_correspondence._keeps_query_rings(mol, query)
    # Placements that reach a lowered limit leave the question open.
    monkeypatch.setattr(rdkit_correspondence, "_MAX_CONSTRAINED_MCS_MATCHES", 3)
    assert not rdkit_correspondence._keeps_query_rings(mol, query)


def test_symmetric_acyclic_endpoints_do_not_require_enumerating_automorphisms():
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _RDKitCorrespondence

    # Eight identical ligands give 8! embeddings, but no ring crossing exists.
    mol = Chem.MolFromSmiles("[Fe](C)(C)(C)(C)(C)(C)(C)C")
    match = _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
        mol, mol, mol, fixed_atom_indices=()
    )
    assert match is not None
    assert len(match[0]) == mol.GetNumAtoms()
    assert dict(zip(*match, strict=True)) == dict(enumerate(range(mol.GetNumAtoms())))


def test_symmetric_acyclic_structure_beside_a_changed_atom_is_suggested():
    # Neither endpoint is a complete copy of the shared Fe(CH3)8, whose eight
    # identical ligands have 8! embeddings, but no embedding can reach a ring.
    adapter = RDKitAdapter()
    model = MoleculeModel()
    reactants = _append_smiles(adapter, model, "[Fe](C)(C)(C)(C)(C)(C)(C)(C)Cl")
    products = _append_smiles(adapter, model, "[Fe](C)(C)(C)(C)(C)(C)(C)(C)Br")
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.error is None
    assert len(result.value) == 9


def test_bond_order_change_keeps_symmetric_alternatives_under_review():
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _RDKitCorrespondence

    # Either hydroxyl of the diol can become the carbonyl. The query accepts
    # the reversed diol embedding but not the reversed aldehyde embedding, so
    # fixing one diol embedding would hide the other correspondence.
    with pytest.raises(ValueError, match="multiple structural atom"):
        _RDKitCorrespondence._mcs_embeddings_honoring_correspondence(
            Chem.MolFromSmiles("OCCO"),
            Chem.MolFromSmiles("O=CCO"),
            Chem.MolFromSmarts("[#8]-,=[#6]-[#6]-[#8]"),
            fixed_atom_indices=(),
            require_unique=True,
        )


# Four CF3 rotors, two aryl flips and the left/right swap give 10,368
# ring-preserving embeddings of this catalyst, more than the candidate limit.
SCHREINER_THIOUREA = "FC(F)(F)c1cc(cc(c1)C(F)(F)F)NC(=S)Nc1cc(cc(c1)C(F)(F)F)C(F)(F)F"
PPH3 = "P(c1ccccc1)(c1ccccc1)c1ccccc1"
PCY3 = "P(C1CCCCC1)(C1CCCCC1)C1CCCCC1"
TOLYLPHOSPHINE = "P(c1ccccc1)(c1ccccc1)c1ccc(C)cc1"
# 1-Naphthyl written ring by ring: the phosphorus-bearing ring comes first.
NAPHTHYLPHOSPHINE = "P(c1ccccc1)(c1ccccc1)c1cccc2c1cccc2"
CF3_ARYL = "c1cc(cc(c1)C(F)(F)F)C(F)(F)F"
# Bromobenzene adds to Pd(PPh3)4 and two PPh3 ligands leave. The shared
# Pd(PPh3)2 leads both SMILES, so it takes the first 39 ids of either side.
OXIDATIVE_ADDITION = (
    f"[Pd]({PPH3})({PPH3})({PPH3}){PPH3}.Brc1ccccc1",
    f"[Pd]({PPH3})({PPH3})(Br)c1ccccc1.{PPH3}.{PPH3}",
)


def _catalyst_step(reactant_smiles, product_smiles):
    adapter = RDKitAdapter()
    model = MoleculeModel()
    reactants = _append_smiles(adapter, model, reactant_smiles)
    products = _append_smiles(adapter, model, product_smiles)
    return adapter, model, reactants, products


def _mapped_bonds_are_kept(model, pairs):
    bonds = {frozenset((bond.a, bond.b)) for bond in model.bonds if bond is not None}
    return all(
        frozenset((pairs[bond.a], pairs[bond.b])) in bonds
        for bond in model.bonds
        if bond is not None and bond.a in pairs and bond.b in pairs
    )


@pytest.mark.parametrize("anchored", [0, 25, 32])
def test_separately_drawn_symmetric_ring_catalyst_is_suggested(anchored):
    adapter, model, reactants, products = _catalyst_step(
        SCHREINER_THIOUREA + ".C[N+](=O)[O-]",
        SCHREINER_THIOUREA + ".C=[N+]([O-])O",
    )
    catalyst = list(zip(sorted(reactants)[:32], sorted(products)[:32], strict=True))
    fixed = dict(catalyst[:anchored])
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, fixed
    )
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs) == {reactant for reactant, _ in catalyst}
    assert set(pairs.values()) == {product for _, product in catalyst}
    assert all(pairs[a] == b for a, b in fixed.items())
    assert _mapped_bonds_are_kept(model, pairs)


def test_complete_catalyst_copies_are_suggested_beside_a_ring_that_fits_them():
    # The spectator imidazolidine-2-thione has a ring carbon with the thiourea
    # carbon's neighbours, so the thiourea carbon fits that ring carbon until
    # the aryl groups are required.
    adapter, model, reactants, products = _catalyst_step(
        SCHREINER_THIOUREA + ".C[N+](=O)[O-].S=C1NCCN1",
        SCHREINER_THIOUREA + ".C=[N+]([O-])O.S=C1NCCN1",
    )
    catalyst = list(zip(sorted(reactants)[:32], sorted(products)[:32], strict=True))
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs) == {reactant for reactant, _ in catalyst}
    assert set(pairs.values()) == {product for _, product in catalyst}
    assert _mapped_bonds_are_kept(model, pairs)


def test_ring_change_beside_a_symmetric_catalyst_is_narrowed_by_anchors():
    adapter, model, reactants, products = _catalyst_step(
        SCHREINER_THIOUREA + ".O=CCCCCO", SCHREINER_THIOUREA + ".OC1CCCCO1"
    )
    catalyst = list(zip(sorted(reactants)[:32], sorted(products)[:32], strict=True))
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.value is None
    assert "candidate limit" in result.error
    # A ring-changing step still refuses the unanchored CF3 rotations.
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, dict(catalyst[:25])
    )
    assert result.value is None
    assert "multiple structural atom" in result.error
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, dict(catalyst)
    )
    assert result.error is None
    assert dict(result.value) == dict(catalyst)


def test_anchors_narrow_the_search_when_only_the_product_catalyst_is_complete():
    # The reactant catalyst carries one extra methyl on nitrogen, so only the
    # product embeddings are relabellings of one another. The ring-forming
    # substrate beside it keeps every correspondence under review.
    adapter, model, reactants, products = _catalyst_step(
        "FC(F)(F)c1cc(cc(c1)C(F)(F)F)N(C)C(=S)Nc1cc(cc(c1)C(F)(F)F)C(F)(F)F.O=CCCCCO",
        SCHREINER_THIOUREA + ".OC1CCCCO1.C",
    )
    methyl = sorted(reactants)[15]
    assert model.atoms[methyl].element == "C"
    catalyst = list(
        zip(
            [atom_id for atom_id in sorted(reactants) if atom_id != methyl][:32],
            sorted(products)[:32],
            strict=True,
        )
    )
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.value is None
    assert "candidate limit" in result.error
    # The unanchored sulfur has one place to go, so the rest decide it.
    sulfur = catalyst[16]
    assert model.atoms[sulfur[0]].element == "S"
    anchors = dict(pair for pair in catalyst if pair != sulfur)
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert result.error is None
    assert dict(result.value) == dict(catalyst)
    assert _mapped_bonds_are_kept(model, dict(result.value))


def test_complete_copy_still_reviews_ring_crossing_partners():
    # The pentane is a complete copy of the shared chain, but the product
    # holds that chain only across its ring, in either direction.
    adapter, model, reactants, products = _catalyst_step("CCCCC.C1CC1", "CC1CC1C")
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.value is None
    assert "multiple structural atom" in result.error


@pytest.mark.parametrize(
    "reactant,product,anchored,sharing",
    [
        # Both ortho carbons of the benzyl bromide go to one toluene carbon.
        pytest.param("BrCc1ccccc1", "Cc1ccccc1.Br", 0, (3, 7, 2), id="benzyl"),
        # Two ortho carbons of the second PPh3 go to one product carbon, beside
        # an anchored ligand.
        pytest.param(*OXIDATIVE_ADDITION, 20, (22, 26, 22), id="after-a-ligand"),
    ],
)
def test_anchors_sharing_a_product_atom_are_refused(
    reactant, product, anchored, sharing
):
    # No embedding honours both anchors, so neither may be dropped silently.
    adapter, model, reactants, products = _catalyst_step(reactant, product)
    reactant_ids, product_ids = sorted(reactants), sorted(products)
    anchors = dict(zip(reactant_ids[:anchored], product_ids[:anchored], strict=True))
    first, second = reactant_ids[sharing[0]], reactant_ids[sharing[1]]
    target = product_ids[sharing[2]]
    assert {model.atoms[atom].element for atom in (first, second, target)} == {"C"}
    anchors.update({first: target, second: target})
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert result.value is None
    assert "do not align" in result.error


# The shared structure leads both SMILES, so its atoms take the lowest ids of
# either endpoint. No step changes ring membership, and every shared structure
# has far more symmetric embeddings than the candidate limit. A fused ring
# carbon, whether beside the catalyst or bonded to it, has the ring bonds of a
# phenyl or cyclohexyl carbon and one more, and a phenyl ring of the shared
# structure fits a naphthalene ring bonded where the phenyl is.
@pytest.mark.parametrize(
    "reactant,product,shared",
    [
        pytest.param(*OXIDATIVE_ADDITION, 39, id="oxidative-addition"),
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3}){PPH3}.Brc1cccc2ccccc12",
            f"[Pd]({PPH3})({PPH3})(Br)c1cccc2ccccc12.{PPH3}.{PPH3}",
            39,
            id="oxidative-addition-of-a-naphthyl-bromide",
        ),
        pytest.param(
            f"[Pd]({PCY3})({PCY3})({PCY3}){PCY3}.BrC1CCC2CCCCC2C1",
            f"[Pd]({PCY3})({PCY3})(Br)C1CCC2CCCCC2C1.{PCY3}.{PCY3}",
            39,
            id="oxidative-addition-of-a-decalinyl-bromide",
        ),
        # Bromide to methoxide exchange at Pd(PPh3)3.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3})Br",
            f"[Pd]({PPH3})({PPH3})({PPH3})OC",
            58,
            id="ligand-exchange",
        ),
        # SN1 at a triarylmethyl carbon with six CF3 rotors.
        pytest.param(
            f"C({CF3_ARYL})({CF3_ARYL})({CF3_ARYL})Br",
            f"C({CF3_ARYL})({CF3_ARYL})({CF3_ARYL})O",
            43,
            id="triarylmethyl-substitution",
        ),
        # Suzuki transmetalation of a naphthyl group from boron to
        # Pd(PPh3)2Ph; the phenyl on Pd also fits the naphthyl ring on Pd.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})(c1ccccc1)Br.OB(O)c1cccc2ccccc12",
            f"[Pd]({PPH3})({PPH3})(c1ccccc1)c1cccc2ccccc12.OB(O)Br",
            45,
            id="transmetalation-of-a-naphthyl-group",
        ),
        # Bromide to methoxide exchange beside a naphthylphosphine.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({NAPHTHYLPHOSPHINE})Br",
            f"[Pd]({PPH3})({PPH3})({NAPHTHYLPHOSPHINE})OC",
            62,
            id="exchange-beside-a-naphthylphosphine",
        ),
        # A naphthylphosphine replaces a PPh3 ligand; its phosphorus-bearing
        # naphthalene ring takes the place of one phenyl ring.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3}){PPH3}.{NAPHTHYLPHOSPHINE}",
            f"[Pd]({PPH3})({PPH3})({PPH3}){NAPHTHYLPHOSPHINE}.{PPH3}",
            77,
            id="naphthylphosphine-for-a-phosphine",
        ),
    ],
)
@pytest.mark.parametrize("anchored", [0, 20, None], ids=["none", "some", "all"])
def test_connected_symmetric_structure_is_suggested(
    reactant, product, shared, anchored
):
    adapter, model, reactants, products = _catalyst_step(reactant, product)
    core = dict(zip(sorted(reactants)[:shared], sorted(products)[:shared], strict=True))
    assert all(
        model.atoms[a].element == model.atoms[b].element for a, b in core.items()
    )
    anchors = dict(list(core.items())[:anchored])
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs.values()) == set(core.values())
    assert all(
        model.atoms[a].element == model.atoms[b].element for a, b in pairs.items()
    )
    assert _mapped_bonds_are_kept(model, pairs)
    assert all(pairs[a] == b for a, b in anchors.items())


@pytest.mark.parametrize(
    "reactant,product,shared,distinct",
    [
        # The catalyst drawn apart on each side; atom 74 is the tolyl para
        # carbon.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C[N+](=O)[O-]",
            f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C=[N+]([O-])O",
            78,
            74,
            id="tolylphosphine-catalyst",
        ),
        # Atom 76 is the fused carbon beside the phosphorus-bearing carbon.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3}){NAPHTHYLPHOSPHINE}.C[N+](=O)[O-]",
            f"[Pd]({PPH3})({PPH3})({PPH3}){NAPHTHYLPHOSPHINE}.C=[N+]([O-])O",
            81,
            76,
            id="naphthylphosphine-catalyst",
        ),
        # The same complex bonded to the exchanging bromide and methoxide.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3})({NAPHTHYLPHOSPHINE})Br",
            f"[Pd]({PPH3})({PPH3})({PPH3})({NAPHTHYLPHOSPHINE})OC",
            81,
            76,
            id="naphthylphosphine-complex",
        ),
    ],
)
@pytest.mark.parametrize("every_atom", [False, True], ids=["one-atom", "every-atom"])
def test_anchors_on_the_distinct_ligand_are_honoured_promptly(
    reactant, product, shared, distinct, every_atom
):
    # The suggestion runs on the desktop's UI thread. Mapping the one ligand
    # that differs from the PPh3 ligands must not start a search through
    # every symmetric placement of the others.
    adapter, model, reactants, products = _catalyst_step(reactant, product)
    core = dict(zip(sorted(reactants)[:shared], sorted(products)[:shared], strict=True))
    reactant_atom, product_atom = list(core.items())[distinct]
    assert model.atoms[reactant_atom].element == "C"
    anchors = core if every_atom else {reactant_atom: product_atom}
    started = time.monotonic()
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert time.monotonic() - started < 5
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs.values()) == set(core.values())
    assert all(pairs[a] == b for a, b in anchors.items())
    assert _mapped_bonds_are_kept(model, pairs)


def test_misplaced_anchor_on_a_symmetric_catalyst_is_refused_promptly():
    # The tolyl para carbon is mapped onto a PPh3 phenyl carbon, which no
    # embedding pair allows. The tolyl carbon fits any phenyl ring until its
    # methyl is required, so the refusal must not wait for every symmetric
    # placement of the other ligands around it.
    adapter, model, reactants, products = _catalyst_step(
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C[N+](=O)[O-]",
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C=[N+]([O-])O",
    )
    para, phenyl = sorted(reactants)[74], sorted(products)[4]
    assert model.atoms[para].element == model.atoms[phenyl].element == "C"
    started = time.monotonic()
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, {para: phenyl}
    )
    assert time.monotonic() - started < 5
    assert result.value is None
    assert "do not align" in result.error


@pytest.mark.parametrize(
    "shared_anchors", [0, 39], ids=["alone", "with-every-shared-atom"]
)
def test_anchor_outside_the_shared_structure_is_refused_at_once(shared_anchors):
    # Mapping the reacting ipso carbon of bromobenzene is natural, but the
    # bromobenzene is too small to hold the shared Pd(PPh3)2, so no embedding
    # holds that anchor however many shared atoms are mapped as well.
    adapter, model, reactants, products = _catalyst_step(*OXIDATIVE_ADDITION)
    reactant_ids, product_ids = sorted(reactants), sorted(products)
    anchors = dict(
        zip(reactant_ids[:shared_anchors], product_ids[:shared_anchors], strict=True)
    )
    ipso = reactant_ids[78], product_ids[40]
    assert model.atoms[ipso[0]].element == model.atoms[ipso[1]].element == "C"
    anchors[ipso[0]] = ipso[1]
    started = time.monotonic()
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert time.monotonic() - started < 5
    assert result.value is None
    assert "do not align" in result.error


def test_anchor_on_a_ligand_that_differs_far_from_it_ends_promptly():
    # A PPh3 phosphorus is mapped onto the tolylphosphine phosphorus. Every
    # ring around it fits until the para methyl is required, so the search
    # tries placements of the free ligands in turn and gives up within its
    # budget instead of trying them all. Giving up does not show the anchor
    # is misplaced, so the step ends at the candidate limit.
    adapter, model, reactants, products = _catalyst_step(
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C[N+](=O)[O-]",
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.C=[N+]([O-])O",
    )
    phosphorus = sorted(reactants)[1], sorted(products)[58]
    assert {model.atoms[atom].element for atom in phosphorus} == {"P"}
    started = time.monotonic()
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, dict([phosphorus])
    )
    assert time.monotonic() - started < 5
    assert result.value is None
    assert "candidate limit" in result.error


def test_anchor_search_that_gives_up_does_not_refuse_the_anchor():
    # One tolyl anchor leaves too many placements of the PPh3 ligands to
    # review the ring-forming step, so the search around it gives up without
    # trying them all. That ends at the candidate limit; it does not show the
    # anchor is misplaced.
    adapter, model, reactants, products = _catalyst_step(
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.O=CCCCCO",
        f"[Pd]({PPH3})({PPH3})({PPH3}){TOLYLPHOSPHINE}.OC1CCCCO1",
    )
    para = sorted(reactants)[74], sorted(products)[74]
    started = time.monotonic()
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, dict([para])
    )
    assert time.monotonic() - started < 5
    assert result.value is None
    assert "candidate limit" in result.error


@pytest.mark.parametrize(
    "reactant,product,reactant_atoms,product_atoms",
    [
        # Bromide to methoxide exchange at Pd(PPh3)3, with the first PPh3 of
        # the reactant on the second PPh3 of the product.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3})Br",
            f"[Pd]({PPH3})({PPH3})({PPH3})OC",
            range(58),
            [0, *range(20, 39), *range(1, 20), *range(39, 58)],
            id="exchange",
        ),
        # The same exchange at Pd(PPh3)4 leaves three PPh3 ligands free.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3})({PPH3})Br",
            f"[Pd]({PPH3})({PPH3})({PPH3})({PPH3})OC",
            range(77),
            [0, *range(20, 39), *range(1, 20), *range(39, 77)],
            id="exchange-at-four-phosphines",
        ),
        # Pd(PPh3)4 drawn apart from the reacting nitromethane on each side.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3}){PPH3}.C[N+](=O)[O-]",
            f"[Pd]({PPH3})({PPH3})({PPH3}){PPH3}.C=[N+]([O-])O",
            range(77),
            [0, *range(20, 39), *range(1, 20), *range(39, 77)],
            id="catalyst-drawn-apart",
        ),
        # The two PPh3 ligands that stay on Pd are the reactant's last two,
        # which the reactant's first match leaves out.
        pytest.param(
            *OXIDATIVE_ADDITION, [0, *range(39, 77)], range(39), id="oxidative-addition"
        ),
        # The two phenyl rings of a naphthylphosphine swapped, one of them
        # flipped. The first placement tried around them swaps the naphthyl
        # ring-fusion carbon with its neighbour in the far ring, which stops
        # fitting further out, so the search moves on to the next placement.
        pytest.param(
            f"[Pd]({PPH3})({PPH3})({PPH3})(P(c1ccccc1)(c1ccccc1)c1cccc2ccccc12)Br",
            f"[Pd]({PPH3})({PPH3})({PPH3})(P(c1ccccc1)(c1ccccc1)c1cccc2ccccc12)OC",
            [70, 65, 69, 68, 67, 66, *range(59, 65), *range(59), *range(71, 81)],
            [60, 59, 61, 62, 63, 64, *range(65, 71), *range(59), *range(71, 81)],
            id="naphthylphosphine-phenyls",
        ),
    ],
)
@pytest.mark.parametrize("anchored", [2, 20, None], ids=["two", "twenty", "all"])
def test_anchors_that_swap_symmetric_ligands_are_honoured(
    reactant, product, reactant_atoms, product_atoms, anchored
):
    # The anchors pair symmetric ligands differently from the first matches,
    # and the ligands left free around them have more placements than the
    # candidate limit.
    adapter, model, reactants, products = _catalyst_step(reactant, product)
    reactant_ids, product_ids = sorted(reactants), sorted(products)
    core = {
        reactant_ids[i]: product_ids[j]
        for i, j in zip(reactant_atoms, product_atoms, strict=True)
    }
    anchors = dict(list(core.items())[:anchored])
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, anchors
    )
    assert result.error is None
    pairs = dict(result.value)
    assert set(pairs.values()) == set(core.values())
    assert all(pairs[a] == b for a, b in anchors.items())
    assert _mapped_bonds_are_kept(model, pairs)


@pytest.mark.parametrize(
    "chain,macrocycle",
    [
        pytest.param(
            f"[Pd]({PPH3})({PPH3})(Br)" + "C" * 32 + "O",
            f"[Pd]({PPH3})({PPH3})(Br)C1" + "C" * 31 + "1",
            id="complexes",
        ),
        # Each search is cheap here, but there is one from every carbon.
        pytest.param("Br" + "C" * 160 + "O", "C1" + "C" * 159 + "1", id="long-chain"),
    ],
)
def test_ring_signature_check_is_bounded_beside_a_decoy_macrocycle(chain, macrocycle):
    from rdkit import Chem

    from chemvas.core.rdkit_correspondence import _keeps_query_rings

    # Each carbon of the chain fits the macrocycle until an end of the chain
    # is required, so the search from every chain atom runs far.
    mol = Chem.MolFromSmiles(f"{chain}.{macrocycle}")
    query = Chem.MolFromSmarts(Chem.MolToSmarts(Chem.MolFromSmiles(chain)))
    started = time.monotonic()
    _keeps_query_rings(mol, query)
    assert time.monotonic() - started < 2


def test_fully_anchored_ring_change_on_a_connected_symmetric_structure():
    # A 5-exo cyclisation on Pd(PPh3)3. Neither side is a complete copy of the
    # shared structure and the ring change keeps every correspondence under
    # review, but anchoring every shared atom leaves only one.
    adapter, model, reactants, products = _catalyst_step(
        f"[Pd]({PPH3})({PPH3})({PPH3})(Br)CCCCC=C",
        f"[Pd]({PPH3})({PPH3})({PPH3})(I)CC1CCCC1",
    )
    reactant_ids, product_ids = sorted(reactants), sorted(products)
    shared = dict(
        zip(
            reactant_ids[:58] + reactant_ids[59:],
            product_ids[:58] + product_ids[59:],
            strict=True,
        )
    )
    result = adapter.suggest_atom_correspondence_result(model, reactants, products)
    assert result.value is None
    assert "candidate limit" in result.error
    # The anchors leave one ortho carbon a single place to go, but without a
    # complete copy every embedding still has to be reviewed.
    ortho = reactant_ids[3]
    assert model.atoms[ortho].element == "C"
    result = adapter.suggest_atom_correspondence_result(
        model,
        reactants,
        products,
        {a: b for a, b in shared.items() if a != ortho},
    )
    assert result.value is None
    assert "candidate limit" in result.error
    result = adapter.suggest_atom_correspondence_result(
        model, reactants, products, shared
    )
    assert result.error is None
    assert dict(result.value) == shared
