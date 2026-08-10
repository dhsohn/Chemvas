from __future__ import annotations

import hashlib
import json
import math

import pytest
from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts
from chemvas.features.precomplex_generation import (
    ComponentGeometry,
    ContactRequest,
    GeometryAtom,
    PlacementRequest,
    component_geometries_from_artifacts,
    generate_precomplex_candidates,
)


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def test_generate_precomplex_candidates_is_bounded_and_byte_deterministic() -> None:
    components = (
        ComponentGeometry(
            component_atom_ids=(0,),
            conformer_id="root-0",
            atoms=(
                GeometryAtom(
                    path_index=0,
                    symbol="C",
                    source_atom_id=0,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
                GeometryAtom(
                    path_index=1,
                    symbol="H",
                    source_atom_id=None,
                    parent_source_atom_id=0,
                    origin="implicit_hydrogen",
                    coordinates=(-1.0, 0.0, 0.0),
                ),
            ),
        ),
        ComponentGeometry(
            component_atom_ids=(2,),
            conformer_id="child-0",
            atoms=(
                GeometryAtom(
                    path_index=2,
                    symbol="O",
                    source_atom_id=2,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
                GeometryAtom(
                    path_index=3,
                    symbol="H",
                    source_atom_id=None,
                    parent_source_atom_id=2,
                    origin="implicit_hydrogen",
                    coordinates=(1.0, 0.0, 0.0),
                ),
            ),
        ),
    )
    request = PlacementRequest(
        source_sha256="a" * 64,
        plan_sha256="b" * 64,
        step_id="S01",
        side="reactant",
        contacts=(
            ContactRequest(
                id="contact-1",
                first_atom_id=0,
                second_atom_id=2,
                target_distance_angstrom=3.0,
                tolerance_angstrom=0.05,
            ),
        ),
        candidate_cap=4,
    )

    first = generate_precomplex_candidates(request, components)
    second = generate_precomplex_candidates(request, components)

    assert 0 < len(first) <= 4
    assert [candidate.id for candidate in first] == [
        candidate.id for candidate in second
    ]
    assert [candidate.xyz for candidate in first] == [
        candidate.xyz for candidate in second
    ]
    assert len({candidate.id for candidate in first}) == len(first)
    for candidate in first:
        assert candidate.geometry_class == "generated_candidate_ensemble"
        assert candidate.profile == "chemvas-rigid-precomplex-placement/1"
        assert candidate.validation.hard_clash_count == 0
        assert candidate.validation.contact_error_angstrom <= 1e-8
        by_index = {atom.path_index: atom.coordinates for atom in candidate.atoms}
        assert _distance(by_index[0], by_index[2]) == 3.0
        assert candidate.xyz.encode("ascii")


def test_candidate_provenance_preserves_plan_component_order() -> None:
    components = (
        ComponentGeometry(
            component_atom_ids=(0,),
            conformer_id="small-first",
            atoms=(
                GeometryAtom(
                    path_index=0,
                    symbol="O",
                    source_atom_id=0,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
            ),
        ),
        ComponentGeometry(
            component_atom_ids=(2, 3),
            conformer_id="large-second",
            atoms=(
                GeometryAtom(
                    path_index=1,
                    symbol="C",
                    source_atom_id=2,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(-1.5, 0.0, 0.0),
                ),
                GeometryAtom(
                    path_index=2,
                    symbol="S",
                    source_atom_id=3,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
            ),
        ),
    )
    request = PlacementRequest(
        source_sha256="a" * 64,
        plan_sha256="b" * 64,
        step_id="S01",
        side="reactant",
        contacts=(
            ContactRequest(
                id="forming-o-s",
                first_atom_id=0,
                second_atom_id=3,
                target_distance_angstrom=3.0,
                tolerance_angstrom=0.05,
            ),
        ),
        candidate_cap=1,
    )

    candidate = generate_precomplex_candidates(request, components)[0]

    assert candidate.component_conformer_ids == ("small-first", "large-second")
    identity = {
        "profile": candidate.profile,
        "source_sha256": request.source_sha256,
        "plan_sha256": request.plan_sha256,
        "step_id": request.step_id,
        "side": request.side,
        "contacts": [
            {
                "id": "forming-o-s",
                "first_atom_id": 0,
                "second_atom_id": 3,
                "target_distance_angstrom": 3.0,
                "tolerance_angstrom": 0.05,
            }
        ],
        "component_atom_ids": [[0], [2, 3]],
        "component_conformer_ids": ["small-first", "large-second"],
        "approach_index": candidate.transform.approach_index,
        "rotation_index": candidate.transform.rotation_index,
        "xyz_sha256": candidate.xyz_sha256,
    }
    expected_id = (
        "pc-"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    )
    assert candidate.id == expected_id


def test_component_geometries_preserve_canonical_atom_order_and_ownership() -> None:
    atom_map = (
        AtomMapEntry(1, 1, "C", "chemvas_atom", 0),
        AtomMapEntry(2, 2, "O", "chemvas_atom", 2),
        AtomMapEntry(
            3,
            None,
            "H",
            "implicit_hydrogen",
            None,
            parent_xyz_index=1,
            parent_chemvas_atom_id=0,
        ),
        AtomMapEntry(
            4,
            None,
            "H",
            "implicit_hydrogen",
            None,
            parent_xyz_index=2,
            parent_chemvas_atom_id=2,
        ),
    )
    artifacts = CalculationArtifacts(
        mol_block="fixture\n",
        xyz_block=(
            "4\nfixture\nC 0.0 0.0 0.0\nO 8.0 0.0 0.0\nH -1.0 0.0 0.0\nH 9.0 0.0 0.0\n"
        ),
        atom_map=atom_map,
        rdkit_version="test-rdkit",
        rdkit_formal_charge=0,
        rdkit_radical_electrons=0,
        electron_count=18,
        geometry_embedding="ETKDGv3",
        geometry_random_seed=7,
        geometry_optimization_policy="fixture",
        geometry_optimization_result="MMFF_converged",
        mol_atom_count=2,
        xyz_atom_count=4,
    )

    components = component_geometries_from_artifacts(
        artifacts,
        ((0,), (2,)),
    )

    assert [component.component_atom_ids for component in components] == [(0,), (2,)]
    assert [
        [atom.path_index for atom in component.atoms] for component in components
    ] == [
        [0, 2],
        [1, 3],
    ]
    assert [atom.parent_source_atom_id for atom in components[0].atoms] == [None, 0]
    assert [atom.parent_source_atom_id for atom in components[1].atoms] == [None, 2]
    assert all(component.conformer_id.startswith("conf-") for component in components)


def test_component_geometries_reject_nonconverged_seed() -> None:
    artifacts = CalculationArtifacts(
        mol_block="fixture\n",
        xyz_block="0\nfixture\n",
        atom_map=(),
        rdkit_version="test-rdkit",
        rdkit_formal_charge=0,
        rdkit_radical_electrons=0,
        electron_count=0,
        geometry_embedding="ETKDGv3",
        geometry_random_seed=7,
        geometry_optimization_policy="fixture",
        geometry_optimization_result="MMFF_not_converged_status_1",
        mol_atom_count=0,
        xyz_atom_count=0,
    )

    with pytest.raises(ValueError, match="converged component geometry"):
        component_geometries_from_artifacts(artifacts, ((0,), (2,)))
