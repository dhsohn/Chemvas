from types import SimpleNamespace

from chemvas.ui.canvas.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    clear_last_smiles_input_for,
    set_last_smiles_input_for,
)
from tests.runtime_state import canvas_runtime_state


def test_smiles_input_state_for_uses_runtime_state() -> None:
    runtime_state = canvas_runtime_state(
        smiles_input_state=CanvasSmilesInputState(last_smiles_input="CCO")
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert canvas.runtime_state.smiles_input_state is runtime_state.smiles_input_state
    assert canvas.runtime_state.smiles_input_state.last_smiles_input == "CCO"


def test_smiles_input_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    canvas = SimpleNamespace(
        last_smiles_input="CCO",
        runtime_state=canvas_runtime_state(smiles_input_state=CanvasSmilesInputState()),
    )

    state = canvas.runtime_state.smiles_input_state

    assert state.last_smiles_input is None
    assert canvas.runtime_state.smiles_input_state.last_smiles_input is None


def test_smiles_input_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace(
        runtime_state=canvas_runtime_state(smiles_input_state=CanvasSmilesInputState())
    )

    set_last_smiles_input_for(canvas, "CCO")

    assert canvas.runtime_state.smiles_input_state.last_smiles_input == "CCO"
    assert not hasattr(canvas, "last_smiles_input")

    clear_last_smiles_input_for(canvas)

    assert canvas.runtime_state.smiles_input_state.last_smiles_input is None
    assert not hasattr(canvas, "last_smiles_input")


def test_smiles_input_state_ignores_canvas_attr_after_state_exists() -> None:
    canvas = SimpleNamespace(
        last_smiles_input="before",
        runtime_state=canvas_runtime_state(smiles_input_state=CanvasSmilesInputState()),
    )
    canvas.last_smiles_input = "after"

    assert canvas.runtime_state.smiles_input_state.last_smiles_input is None
