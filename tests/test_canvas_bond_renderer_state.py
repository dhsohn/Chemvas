from __future__ import annotations

from types import SimpleNamespace

from ui.bond_renderer import BondRenderer
from ui.canvas_bond_renderer_state import bond_renderer_for, set_bond_renderer_for


def test_canvas_bond_renderer_state_returns_existing_renderer() -> None:
    renderer = object()
    canvas = SimpleNamespace(bond_renderer=renderer)

    assert bond_renderer_for(canvas) is renderer


def test_canvas_bond_renderer_state_creates_default_renderer_when_missing() -> None:
    canvas = SimpleNamespace()

    renderer = bond_renderer_for(canvas)

    assert isinstance(renderer, BondRenderer)
    assert canvas.bond_renderer is renderer


def test_canvas_bond_renderer_state_replaces_renderer() -> None:
    canvas = SimpleNamespace(bond_renderer=object())
    renderer = object()

    set_bond_renderer_for(canvas, renderer)

    assert canvas.bond_renderer is renderer
