from __future__ import annotations

from types import SimpleNamespace

from core.rdkit_adapter import RDKitAdapter
from ui.canvas_rdkit_state import rdkit_adapter_for, set_rdkit_adapter_for


def test_canvas_rdkit_state_returns_existing_adapter() -> None:
    adapter = object()
    canvas = SimpleNamespace(rdkit=adapter)

    assert rdkit_adapter_for(canvas) is adapter


def test_canvas_rdkit_state_creates_default_adapter_when_missing() -> None:
    canvas = SimpleNamespace()

    adapter = rdkit_adapter_for(canvas)

    assert isinstance(adapter, RDKitAdapter)
    assert canvas.rdkit is adapter


def test_canvas_rdkit_state_replaces_adapter() -> None:
    canvas = SimpleNamespace(rdkit=object())
    adapter = object()

    set_rdkit_adapter_for(canvas, adapter)

    assert canvas.rdkit is adapter
