from __future__ import annotations

from typing import Any

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.ui.canvas_state_lookup import ensure_canvas_state


def new_rdkit_adapter():
    return RDKitAdapter()


def rdkit_adapter_for(canvas: Any):
    return ensure_canvas_state(canvas, "rdkit", new_rdkit_adapter, runtime_field=False)


def set_rdkit_adapter_for(canvas: Any, adapter) -> None:
    canvas.rdkit = adapter


__all__ = ["new_rdkit_adapter", "rdkit_adapter_for", "set_rdkit_adapter_for"]
