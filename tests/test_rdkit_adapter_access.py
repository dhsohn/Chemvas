from types import SimpleNamespace
from unittest import mock

from chemvas.ui.rdkit_adapter_access import (
    compute_props_for,
    model_to_xyz_block_for,
    preload_rdkit_for,
    rdkit_adapter_for,
    rdkit_is_loaded_for,
    rdkit_is_unavailable_for,
    rdkit_last_error_for,
    smiles_to_2d_for,
)


def test_rdkit_adapter_access_delegates_to_canvas_adapter() -> None:
    adapter = SimpleNamespace(
        last_error="bad input",
        smiles_to_2d=mock.Mock(return_value="model-2d"),
        model_to_xyz_block=mock.Mock(return_value="xyz"),
        is_loaded=mock.Mock(return_value=True),
        is_unavailable=mock.Mock(return_value=False),
        preload=mock.Mock(return_value=True),
        compute_props=mock.Mock(return_value=("H2O", 18.015, "O")),
    )
    canvas = SimpleNamespace(rdkit=adapter)

    assert rdkit_adapter_for(canvas) is adapter
    assert rdkit_last_error_for(canvas) == "bad input"
    assert smiles_to_2d_for(canvas, "CCO", scale=24.0) == "model-2d"
    assert (
        model_to_xyz_block_for(canvas, "model-3d", atom_annotations={1: {"atom": 1}})
        == "xyz"
    )
    assert rdkit_is_loaded_for(canvas) is True
    assert rdkit_is_unavailable_for(canvas) is False
    assert preload_rdkit_for(canvas) is True
    assert compute_props_for(canvas, "submodel") == ("H2O", 18.015, "O")

    adapter.smiles_to_2d.assert_called_once_with("CCO", scale=24.0)
    adapter.model_to_xyz_block.assert_called_once_with(
        "model-3d", atom_annotations={1: {"atom": 1}}
    )
    adapter.is_loaded.assert_called_once_with()
    adapter.is_unavailable.assert_called_once_with()
    adapter.preload.assert_called_once_with()
    adapter.compute_props.assert_called_once_with("submodel")


def test_rdkit_last_error_handles_missing_error_attribute() -> None:
    canvas = SimpleNamespace(rdkit=SimpleNamespace())

    assert rdkit_last_error_for(canvas) is None
