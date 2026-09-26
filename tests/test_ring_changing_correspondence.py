"""Ring creation must not manufacture a methyl/radical correspondence."""

import copy
import importlib.util
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
