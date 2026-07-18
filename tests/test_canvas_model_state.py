from __future__ import annotations

from types import SimpleNamespace

from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas_model_state import model_for, set_model_for


def test_canvas_model_state_returns_and_replaces_canvas_model() -> None:
    old_model = object()
    new_model = object()
    canvas = SimpleNamespace(model=old_model)

    assert model_for(canvas) is old_model

    set_model_for(canvas, new_model)

    assert canvas.model is new_model


def test_canvas_model_state_creates_default_model_when_missing() -> None:
    canvas = SimpleNamespace()

    model = model_for(canvas)

    assert isinstance(model, MoleculeModel)
    assert canvas.model is model
