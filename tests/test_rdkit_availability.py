from __future__ import annotations

import builtins
from unittest import mock

import pytest

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel


@pytest.mark.parametrize(
    "operation",
    [
        "preload",
        "smiles",
        "identifiers",
        "mol",
        "preview",
        "xyz",
        "artifacts",
        "suggest",
    ],
)
def test_missing_rdkit_message_includes_one_install_command_even_when_cached(operation):
    model = MoleculeModel()
    model.add_atom("C", 0.0, 0.0)
    adapter = RDKitAdapter()
    original_import = builtins.__import__

    def missing_rdkit(name, *args, **kwargs):
        if name == "rdkit" or name.startswith("rdkit."):
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, *args, **kwargs)

    operations = {
        "preload": adapter.preload,
        "smiles": lambda: adapter.smiles_to_2d("C"),
        "identifiers": lambda: adapter.compute_identifiers(model),
        "mol": lambda: adapter.model_to_mol_block(model),
        "preview": lambda: adapter.model_to_3d_scene_result(model),
        "xyz": lambda: adapter.model_to_xyz_block(model),
        "artifacts": lambda: adapter.model_to_calculation_artifacts_result(model),
        "suggest": lambda: adapter.suggest_atom_correspondence_result(model, {0}, {0}),
    }
    with mock.patch("builtins.__import__", side_effect=missing_rdkit):
        for _ in range(2):
            adapter.last_error = None
            operations[operation]()
            assert adapter.last_error == (
                "RDKit is not available in this environment. "
                'Install it with: pip install "chemvas[rdkit]".'
            )
