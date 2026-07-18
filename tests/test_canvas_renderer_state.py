from __future__ import annotations

from types import SimpleNamespace

from chemvas.core.renderer import Renderer
from chemvas.ui.canvas_renderer_state import renderer_for, set_renderer_for


def test_renderer_state_returns_existing_public_renderer() -> None:
    renderer = object()
    canvas = SimpleNamespace(renderer=renderer)

    assert renderer_for(canvas) is renderer


def test_renderer_state_prefers_runtime_state_renderer() -> None:
    public_renderer = object()
    runtime_renderer = object()
    canvas = SimpleNamespace(
        renderer=public_renderer,
        runtime_state=SimpleNamespace(renderer=runtime_renderer),
    )

    assert renderer_for(canvas) is runtime_renderer


def test_renderer_state_creates_renderer_and_sets_compat_canvas_attr() -> None:
    canvas = SimpleNamespace()

    renderer = renderer_for(canvas)

    assert isinstance(renderer, Renderer)
    assert canvas.renderer is renderer


def test_set_renderer_state_sets_compat_canvas_attr() -> None:
    renderer = object()
    canvas = SimpleNamespace()

    set_renderer_for(canvas, renderer)

    assert canvas.renderer is renderer
