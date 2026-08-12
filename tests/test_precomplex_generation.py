from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace

import pytest
from chemvas.domain.document.precomplex_profile import (
    CURRENT_PROFILE_ID,
    LEGACY_PROFILE_ID,
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
        "pc-bbfe4f941b0e7ced9c944b7b4856e79fcb7efd23994e9f904a7184df52aa0401",
        "pc-e68ba791403ad9f271bf1a291d35a3115110c6bba6ae00e66c90703ff6f6045a",
        "pc-b2f5a07e888dcec2db0d9d010616cea605f29a071e93626fd24a4dfe852f153a",
        "pc-cc2a1653c31085dbdc23d5580c089618f7e247fb3ecd9a2a8ddf8d0f20c232b2",
    ]
    assert first[0].xyz == (
        "4\n"
        "Chemvas chemvas-rigid-precomplex-placement/1 S01 reactant\n"
        "C  0.00000000 0.00000000 0.00000000\n"
        "H  -1.00000000 0.00000000 0.00000000\n"
        "O  1.19895788 2.75000000 0.00000000\n"
        "H  0.79930525 1.83333333 0.00000000\n"
    )
    assert first[0].validation.soft_overlap_score == 0.216225
    assert len({candidate.id for candidate in first}) == len(first)
    for candidate in first:
        assert candidate.geometry_class == "generated_candidate_ensemble"
        assert candidate.profile == "chemvas-rigid-precomplex-placement/1"
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


def test_legacy_profile_one_iron_cobalt_output_is_byte_frozen() -> None:
    components, request = _iron_cobalt_fixture()

    candidate = generate_precomplex_candidates(request, components)[0]

    assert request.profile == LEGACY_PROFILE_ID
    assert candidate.id == (
        "pc-2ede86589189dcc3fc7d921d6c7f181a3c5a035f780542ef973ef6da8059c76a"
    )
    assert candidate.xyz == (
        "2\n"
        "Chemvas chemvas-rigid-precomplex-placement/1 S01 reactant\n"
        "Fe 0.00000000 0.00000000 0.00000000\n"
        "Co 1.19895788 2.75000000 0.00000000\n"
    )
    assert candidate.validation.soft_overlap_score == 0.16


def test_legacy_profile_one_radius_table_and_provenance_are_frozen() -> None:
    assert dict(precomplex_placement_profile(LEGACY_PROFILE_ID).radii) == {
        "H": (0.31, 1.20),
        "Li": (1.28, 1.82),
        "B": (0.84, 1.92),
        "C": (0.76, 1.70),
        "N": (0.71, 1.55),
        "O": (0.66, 1.52),
        "F": (0.57, 1.47),
        "Na": (1.66, 2.27),
        "Mg": (1.41, 1.73),
        "Al": (1.21, 1.84),
        "Si": (1.11, 2.10),
        "P": (1.07, 1.80),
        "S": (1.05, 1.80),
        "Cl": (1.02, 1.75),
        "K": (2.03, 2.75),
        "Ca": (1.76, 2.31),
        "Fe": (1.32, 2.00),
        "Co": (1.26, 2.00),
        "Ni": (1.24, 1.63),
        "Cu": (1.32, 1.40),
        "Zn": (1.22, 1.39),
        "Br": (1.20, 1.85),
        "Ru": (1.46, 2.00),
        "Rh": (1.42, 2.00),
        "Pd": (1.39, 1.63),
        "Ag": (1.45, 1.72),
        "Sn": (1.39, 2.17),
        "I": (1.39, 1.98),
        "Ir": (1.41, 2.00),
        "Pt": (1.36, 1.75),
        "Au": (1.36, 1.66),
    }
    assert radius_provenance_for(LEGACY_PROFILE_ID) == {
        "status": "legacy_frozen_unverified",
        "units": "angstrom",
        "radius_table_sha256": (
            "d352219ef2bea3619f3ba81aff64958f146bd6246b7396c454c9de4213fd80ad"
        ),
        "dataset_id": "chemvas-precomplex-legacy-radius-table-v1",
        "doi": None,
    }


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

    components, legacy_request = _iron_cobalt_fixture()
    current_components = tuple(
        replace(component, profile=CURRENT_PROFILE_ID) for component in components
    )
    current = generate_precomplex_candidates(
        replace(legacy_request, profile=CURRENT_PROFILE_ID), current_components
    )[0]

    assert current.profile == CURRENT_PROFILE_ID
    assert f"Chemvas {CURRENT_PROFILE_ID}" in current.xyz
    assert current.validation.soft_overlap_score == 1.240996


def test_generation_rejects_unknown_profile_and_unsupported_element() -> None:
    components, request = _iron_cobalt_fixture()
    with pytest.raises(ValueError, match="Unsupported precomplex placement profile"):
        generate_precomplex_candidates(
            replace(request, profile="unknown/1"), components
        )

    with pytest.raises(ValueError, match="do not match the requested profile"):
        generate_precomplex_candidates(
            replace(request, profile=CURRENT_PROFILE_ID), components
        )
    with pytest.raises(ValueError, match="candidate_cap"):
        generate_precomplex_candidates(replace(request, candidate_cap=True), components)

    xenon = replace(
        components[1],
        atoms=(replace(components[1].atoms[0], symbol="Xe"),),
        profile=CURRENT_PROFILE_ID,
    )
    with pytest.raises(ValueError, match="precomplex_unsupported_radius"):
        generate_precomplex_candidates(
            replace(request, profile=CURRENT_PROFILE_ID),
            (replace(components[0], profile=CURRENT_PROFILE_ID), xenon),
        )


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
        "conf-3d149225284863bd4cdd9f20d525d440df99ad1bf3749c80680b221161bb240b",
        "conf-1d147cac2d7cd7bd228059a00e3caab832add1a20813b7fe2071d7b390acb054",
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
