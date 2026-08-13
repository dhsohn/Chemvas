from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    precomplex_placement_profile,
    radius_provenance_for,
)
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
    assert [candidate.id for candidate in first] == [
        "pc-0f94dd6951485850e795e9b1410c221166ceb523062db747ef2517f2c84640e5",
        "pc-257130e121cbdf62dbcb9a132012c0aec3f50593ef68a97369c8ff56bce97c5e",
        "pc-b780641105337f9b1fe66dc07bcb2245b2521d3c0e8864dc722c2da2ae5bdfbe",
        "pc-f64c768d00635bba8352712d54dd91292f7e2669c44ddff9f6ddc24c13f48559",
    ]
    assert first[0].xyz == (
        "4\n"
        "Chemvas chemvas-rigid-precomplex-placement/2 S01 reactant\n"
        "C  0.00000000 0.00000000 0.00000000\n"
        "H  -1.00000000 0.00000000 0.00000000\n"
        "O  1.19895788 2.75000000 0.00000000\n"
        "H  0.79930525 1.83333333 0.00000000\n"
    )
    assert first[0].validation.soft_overlap_score == 0.27510025
    assert len({candidate.id for candidate in first}) == len(first)
    for candidate in first:
        assert candidate.geometry_class == "generated_candidate_ensemble"
        assert candidate.profile == CURRENT_PROFILE_ID
        assert candidate.validation.hard_clash_count == 0
        assert candidate.validation.contact_error_angstrom <= 1e-8
        by_index = {atom.path_index: atom.coordinates for atom in candidate.atoms}
        assert _distance(by_index[0], by_index[2]) == 3.0
        assert candidate.xyz.encode("ascii")


def _iron_cobalt_fixture() -> tuple[tuple[ComponentGeometry, ...], PlacementRequest]:
    components = (
        ComponentGeometry(
            component_atom_ids=(0,),
            conformer_id="fe-conformer",
            atoms=(
                GeometryAtom(
                    path_index=0,
                    symbol="Fe",
                    source_atom_id=0,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
            ),
        ),
        ComponentGeometry(
            component_atom_ids=(2,),
            conformer_id="co-conformer",
            atoms=(
                GeometryAtom(
                    path_index=1,
                    symbol="Co",
                    source_atom_id=2,
                    parent_source_atom_id=None,
                    origin="chemvas_atom",
                    coordinates=(0.0, 0.0, 0.0),
                ),
            ),
        ),
    )
    return components, PlacementRequest(
        source_sha256="a" * 64,
        plan_sha256="b" * 64,
        step_id="S01",
        side="reactant",
        contacts=(
            ContactRequest(
                id="fe-co",
                first_atom_id=0,
                second_atom_id=2,
                target_distance_angstrom=3.0,
                tolerance_angstrom=0.05,
            ),
        ),
        candidate_cap=1,
    )


def test_current_profile_iron_cobalt_output_is_byte_frozen() -> None:
    components, request = _iron_cobalt_fixture()

    candidate = generate_precomplex_candidates(request, components)[0]

    assert request.profile == CURRENT_PROFILE_ID
    assert candidate.id == (
        "pc-0bb3a54a5a65246ae9011ccc89ec6f6a5cec67c3d194fde107ad5b0cf6fb8d52"
    )
    assert candidate.xyz == (
        "2\n"
        "Chemvas chemvas-rigid-precomplex-placement/2 S01 reactant\n"
        "Fe 0.00000000 0.00000000 0.00000000\n"
        "Co 1.19895788 2.75000000 0.00000000\n"
    )
    assert candidate.validation.soft_overlap_score == 1.240996


def test_profile_two_uses_the_complete_cited_radius_table() -> None:
    expected = {
        "H": (0.31, 1.20),
        "Li": (1.28, 2.12),
        "B": (0.84, 1.91),
        "C": (0.76, 1.77),
        "N": (0.71, 1.66),
        "O": (0.66, 1.50),
        "F": (0.57, 1.46),
        "Na": (1.66, 2.50),
        "Mg": (1.41, 2.51),
        "Al": (1.21, 2.25),
        "Si": (1.11, 2.19),
        "P": (1.07, 1.90),
        "S": (1.05, 1.89),
        "Cl": (1.02, 1.82),
        "K": (2.03, 2.73),
        "Ca": (1.76, 2.62),
        "Fe": (1.32, 2.44),
        "Co": (1.26, 2.40),
        "Ni": (1.24, 2.40),
        "Cu": (1.32, 2.38),
        "Zn": (1.22, 2.39),
        "Br": (1.20, 1.86),
        "Ru": (1.46, 2.46),
        "Rh": (1.42, 2.44),
        "Pd": (1.39, 2.15),
        "Ag": (1.45, 2.53),
        "Sn": (1.39, 2.42),
        "I": (1.39, 2.04),
        "Ir": (1.41, 2.41),
        "Pt": (1.36, 2.29),
        "Au": (1.36, 2.32),
    }

    assert dict(precomplex_placement_profile(CURRENT_PROFILE_ID).radii) == expected
    assert radius_provenance_for(CURRENT_PROFILE_ID) == {
        "status": "cited",
        "units": "angstrom",
        "radius_table_sha256": (
            "49382c8b506725b256fa9aaa35350b467f223b036b53275dc20bd6e095eae339"
        ),
        "covalent": {
            "dataset_id": "cordero-2008-table-2",
            "doi": "10.1039/B801115J",
            "selectors": {"C": "sp3", "Fe": "low_spin", "Co": "low_spin"},
        },
        "van_der_waals": {
            "dataset_id": "alvarez-2013-table-1",
            "doi": "10.1039/C3DT50599E",
        },
    }

    components, request = _iron_cobalt_fixture()
    current = generate_precomplex_candidates(request, components)[0]

    assert current.profile == CURRENT_PROFILE_ID
    assert f"Chemvas {CURRENT_PROFILE_ID}" in current.xyz
    assert current.validation.soft_overlap_score == 1.240996


def test_generation_rejects_unknown_profile_and_unsupported_element() -> None:
    components, request = _iron_cobalt_fixture()
    with pytest.raises(ValueError, match="Unsupported precomplex placement profile"):
        generate_precomplex_candidates(
            replace(request, profile="unknown/1"), components
        )

    with pytest.raises(ValueError, match="Unsupported precomplex placement profile"):
        generate_precomplex_candidates(
            replace(request, profile="chemvas-rigid-precomplex-placement/" + "1"),
            components,
        )
    with pytest.raises(ValueError, match="candidate_cap"):
        generate_precomplex_candidates(replace(request, candidate_cap=True), components)

    xenon = replace(
        components[1],
        atoms=(replace(components[1].atoms[0], symbol="Xe"),),
    )
    with pytest.raises(ValueError, match="precomplex_unsupported_radius"):
        generate_precomplex_candidates(
            request,
            (components[0], xenon),
        )


def test_removed_profile_has_no_runtime_or_source_registration() -> None:
    removed_profile_id = "chemvas-rigid-precomplex-placement/" + "1"

    with pytest.raises(ValueError, match="Unsupported precomplex placement profile"):
        precomplex_placement_profile(removed_profile_id)
    with pytest.raises(ValueError, match="Unsupported precomplex placement profile"):
        radius_provenance_for(removed_profile_id)

    app_root = Path(__file__).resolve().parents[1] / "app" / "chemvas"
    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in app_root.rglob("*.py")
    )
    assert removed_profile_id not in production_source
    assert "LEGACY_PROFILE_ID" not in production_source
    assert "legacy_frozen_unverified" not in production_source


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
    assert [component.conformer_id for component in components] == [
        "conf-fec2c2d20d31fcb8a9fe89153c28b66883f2a4b41a9214e95808a58e1c030360",
        "conf-12329ae7d2cd66fb00b09790434653a0941ea2d7dd73fa0dc1b624922c6a6fad",
    ]


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
