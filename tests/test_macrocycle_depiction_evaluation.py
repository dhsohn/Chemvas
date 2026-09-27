from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("rdkit") is None,
    reason="optional RDKit dependency is not installed",
)

ROOT = Path(__file__).resolve().parents[1]


def test_macrocycle_evaluator_help():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/depiction/evaluate_macrocycles.py"),
            "--help",
        ],
        env={**os.environ, "PYTHONPATH": str(ROOT / "app")},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--output-dir" in result.stdout


def test_macrocycle_corpus_chemical_identity_and_geometry(tmp_path):
    from rdkit.Chem import rdDepictor
    from scripts.depiction.evaluate_macrocycles import evaluate

    preference = rdDepictor.GetPreferCoordGen()
    report = evaluate(ROOT / "tests/fixtures/depiction/macrocycles.json", tmp_path)
    assert rdDepictor.GetPreferCoordGen() == preference
    assert len(report["results"]) == 6
    for result in report["results"]:
        assert result["import_accepted"]
        assert result["isomeric_identity_preserved"]
        assert result["finite_nondegenerate_geometry"]
        assert 0 < result["min_bond_over_median"] <= 1 <= result["max_bond_over_median"]
        assert result["nonbonded_pairs_below_0_5"] >= 0
        assert result["closest_nonbonded_pair"] > 0
        assert (
            result["atoms_in_bond_contacts"] <= result["atom_bond_contacts_below_0_1"]
        )
    assert {
        r["specified_tetrahedral_centers"]
        for r in report["results"]
        if r["molecule"] == "beta-cyclodextrin"
    } == {35}
    assert len(list(tmp_path.glob("*.mol"))) == 6
    assert (tmp_path / "comparison.png").is_file()
    assert json.loads((tmp_path / "results.json").read_text()) == report


def test_corrupt_macrocycle_identity_rejected(tmp_path):
    from scripts.depiction.evaluate_macrocycles import evaluate

    corpus = json.loads(
        (ROOT / "tests/fixtures/depiction/macrocycles.json").read_text()
    )
    corpus["molecules"][0]["formula"] = "C"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(corpus))
    with pytest.raises(ValueError, match="formula mismatch"):
        evaluate(path, tmp_path / "output")
    assert not list((tmp_path / "output").glob("*.mol"))


def test_empty_macrocycle_corpus_is_not_a_success(tmp_path):
    from scripts.depiction.evaluate_macrocycles import evaluate

    path = tmp_path / "empty.json"
    path.write_text('{"molecules": []}')
    with pytest.raises(ValueError, match="nonempty"):
        evaluate(path, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_depiction_metrics_use_hand_computed_coordinates():
    from scripts.depiction.evaluate_macrocycles import geometry

    from chemvas.domain.document import MoleculeModel

    model = MoleculeModel()
    for x, y in ((0, 0), (1, 0), (0.4, 0.05), (0.4, 1.05), (10, 10), (30, 10)):
        model.add_atom("C", x, y)
    for a, b in ((0, 1), (2, 3), (4, 5)):
        model.add_bond(a, b)
    # Bond lengths 1, 1, 20 give median 1. Only atoms 0 and 2 are
    # within 0.5; atom 2 lies 0.05 above the interior of bond 0–1.
    result = geometry(model)
    assert result["finite_nondegenerate_geometry"]
    assert result["nonbonded_pairs_below_0_5"] == 1
    assert result["closest_nonbonded_pair"] == pytest.approx((0.4**2 + 0.05**2) ** 0.5)
    assert result["atom_bond_contacts_below_0_1"] == 1
    assert result["atoms_in_bond_contacts"] == 1
    assert result["min_bond_over_median"] == pytest.approx(1)
    assert result["max_bond_over_median"] == pytest.approx(20)
    model.atoms[1].x = 0
    with pytest.raises(ValueError, match="zero bond"):
        geometry(model)
