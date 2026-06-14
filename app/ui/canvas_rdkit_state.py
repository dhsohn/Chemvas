from __future__ import annotations

from typing import Any

from core.rdkit_adapter import RDKitAdapter

from ui.canvas_state_lookup import canvas_state_object


def new_rdkit_adapter():
    return RDKitAdapter()


def rdkit_adapter_for(canvas: Any):
    adapter = canvas_state_object(canvas, "rdkit")
    if adapter is not None:
        return adapter
    adapter = new_rdkit_adapter()
    canvas.rdkit = adapter
    return adapter


def set_rdkit_adapter_for(canvas: Any, adapter) -> None:
    canvas.rdkit = adapter


__all__ = ["new_rdkit_adapter", "rdkit_adapter_for", "set_rdkit_adapter_for"]
