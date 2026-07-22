from types import SimpleNamespace

import pytest
from chemvas.features.hover import HoverState
from chemvas.ui.canvas_hover_state import hover_state_for


def test_hover_state_for_returns_canonical_runtime_state() -> None:
    state = HoverState(style="wedge")
    canvas = SimpleNamespace(
        runtime_state=SimpleNamespace(hover_preview_state=state),
        hover_preview_state=HoverState(style="legacy-shadow"),
    )

    assert hover_state_for(canvas) is state


def test_hover_state_for_rejects_missing_runtime_owner() -> None:
    with pytest.raises(AttributeError):
        hover_state_for(SimpleNamespace(hover_preview_state=HoverState()))
