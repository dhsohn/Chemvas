from types import SimpleNamespace

from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    clear_last_smiles_input_for,
    last_smiles_input_for,
    set_last_smiles_input_for,
    smiles_input_state_for,
)


def test_smiles_input_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(
        smiles_input_state=CanvasSmilesInputState(last_smiles_input="CCO")
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert smiles_input_state_for(canvas) is runtime_state.smiles_input_state
    assert last_smiles_input_for(canvas) == "CCO"


def test_smiles_input_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    canvas = SimpleNamespace(last_smiles_input="CCO")

    state = smiles_input_state_for(canvas)

    assert state.last_smiles_input is None
    assert last_smiles_input_for(canvas) is None


def test_smiles_input_setters_update_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_last_smiles_input_for(canvas, "CCO")

    assert last_smiles_input_for(canvas) == "CCO"
    assert not hasattr(canvas, "last_smiles_input")

    clear_last_smiles_input_for(canvas)

    assert last_smiles_input_for(canvas) is None
    assert not hasattr(canvas, "last_smiles_input")


def test_smiles_input_state_ignores_canvas_attr_after_state_exists() -> None:
    canvas = SimpleNamespace(last_smiles_input="before")
    smiles_input_state_for(canvas)

    canvas.last_smiles_input = "after"

    assert last_smiles_input_for(canvas) is None
