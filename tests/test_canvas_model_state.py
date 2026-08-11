from __future__ import annotations

from types import SimpleNamespace

import pytest
from chemvas.ui.canvas_model_state import model_for, set_model_for


def test_canvas_model_state_returns_and_replaces_canvas_model() -> None:
    old_model = object()
    new_model = object()
    canvas = SimpleNamespace(model=old_model)

    assert model_for(canvas) is old_model

    set_model_for(canvas, new_model)

    assert canvas.model is new_model


def test_canvas_model_state_does_not_invent_a_model() -> None:
    # Canvas setup creates the model; a canvas without one is a wiring bug and
    # must not be handed a fresh empty document instead.
    with pytest.raises(AttributeError):
        model_for(SimpleNamespace())
