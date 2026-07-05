from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from core.rdkit_adapter import RDKitAdapter
from ui.structure_fragment_build_service import FRAGMENT_BUILD_FAILED
from ui.structure_template_commands import (
    apply_structure_template_command,
    known_structure_template_keys,
)

from tests.test_structure_build_service import _FakeCanvas, _service_for

try:
    from rdkit import Chem as _RealChem
except ModuleNotFoundError:
    _RealChem = None


def _template_service():
    method_names = (
        "add_regular_ring_template",
        "add_hetero_ring_template",
        "add_fused_benzenes",
        "add_crown_ether",
        "add_cyclohexane_chair",
        "add_phenyl",
    )
    template_builder = SimpleNamespace()
    service = SimpleNamespace(
        run_recorded_build=mock.Mock(side_effect=lambda action: action()),
        template_builder=template_builder,
    )
    for name in method_names:
        setattr(template_builder, name, mock.Mock())
    return service


def test_structure_template_commands_dispatch_recorded_catalog_templates() -> None:
    service = _template_service()

    apply_structure_template_command(service, "cyclopropane")
    apply_structure_template_command(service, "pyridine")
    apply_structure_template_command(service, "phenanthrene")
    apply_structure_template_command(service, "crown_18_6")

    assert service.run_recorded_build.call_count == 4
    service.template_builder.add_regular_ring_template.assert_called_once_with(3)
    service.template_builder.add_hetero_ring_template.assert_called_once_with(
        6,
        ["C", "C", "C", "C", "C", "N"],
        [2, 1, 2, 1, 2, 1],
    )
    service.template_builder.add_fused_benzenes.assert_called_once_with(3, mode="angled")
    service.template_builder.add_crown_ether.assert_called_once_with(18, 6)


def test_structure_template_commands_dispatch_imidazole_pyrrolic_bond_orders() -> None:
    service = _template_service()

    apply_structure_template_command(service, "imidazole")

    service.template_builder.add_hetero_ring_template.assert_called_once_with(
        5,
        ["C", "N", "C", "N", "C"],
        [1, 2, 1, 1, 2],
    )


def test_structure_template_commands_dispatch_service_methods_and_unknown_keys() -> None:
    service = _template_service()

    apply_structure_template_command(service, "cyclohexane_chair")
    apply_structure_template_command(service, "phenyl")

    service.template_builder.add_cyclohexane_chair.assert_called_once_with()
    service.template_builder.add_phenyl.assert_called_once_with()
    assert "phenyl" in known_structure_template_keys()
    with pytest.raises(ValueError, match="Unknown structure template"):
        apply_structure_template_command(service, "not-a-template")


def test_structure_template_commands_preserve_recorded_action_result_conventions() -> None:
    service = _template_service()
    recorded_results = []
    service.run_recorded_build.side_effect = lambda action: recorded_results.append(action())
    scene_item = object()

    service.template_builder.add_regular_ring_template.return_value = [scene_item]
    apply_structure_template_command(service, "cyclopropane")
    service.template_builder.add_regular_ring_template.return_value = FRAGMENT_BUILD_FAILED
    apply_structure_template_command(service, "cyclopropane")

    assert recorded_results == [[scene_item], None]


def test_structure_template_commands_record_real_catalog_builds_without_rollback() -> None:
    cases = (
        ("cyclopropane", 3, 3, 0),
        ("pyridine", 6, 6, 3),
        ("naphthalene", 10, 11, 5),
        ("crown_12_4", 12, 12, 0),
    )

    for key, atom_count, bond_count, double_bond_count in cases:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        apply_structure_template_command(service, key)
        bonds = [bond for bond in canvas.model.bonds if bond is not None]

        assert len(canvas.model.atoms) == atom_count, key
        assert len(bonds) == bond_count, key
        assert sum(1 for bond in bonds if bond.order == 2) == double_bond_count, key
        assert len(canvas.record_calls) == 1, key
        assert canvas.record_calls[0]["added_scene_items"] == canvas.ring_items, key


@pytest.mark.skipif(_RealChem is None, reason="RDKit is required for aromatic template identity tests")
def test_structure_template_commands_build_imidazole_identity() -> None:
    canvas = _FakeCanvas()
    service = _service_for(canvas)

    apply_structure_template_command(service, "imidazole")
    mol = RDKitAdapter().model_to_rdkit(canvas.model)

    assert mol is not None
    assert _RealChem.MolToSmiles(mol, canonical=True) == "c1c[nH]cn1"


@pytest.mark.skipif(_RealChem is None, reason="RDKit is required for aromatic template MOL export tests")
def test_structure_template_commands_mol_export_preserves_pyrrolic_n_identity() -> None:
    cases = (
        ("pyrrole", "c1cc[nH]c1"),
        ("imidazole", "c1c[nH]cn1"),
    )

    for key, expected_smiles in cases:
        canvas = _FakeCanvas()
        service = _service_for(canvas)

        apply_structure_template_command(service, key)
        block = RDKitAdapter().model_to_mol_block(canvas.model)
        assert block is not None, key
        mol = _RealChem.MolFromMolBlock(block)

        assert mol is not None, key
        assert _RealChem.MolToSmiles(mol, canonical=True) == expected_smiles
