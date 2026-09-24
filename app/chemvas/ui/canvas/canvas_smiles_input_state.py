from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CanvasSmilesInputState:
    last_smiles_input: str | None = None


def set_last_smiles_input_for(canvas: Any, smiles: str | None) -> None:
    state = canvas.runtime_state.smiles_input_state
    state.last_smiles_input = smiles


def clear_last_smiles_input_for(canvas: Any) -> None:
    set_last_smiles_input_for(canvas, None)


__all__ = [
    "CanvasSmilesInputState",
    "clear_last_smiles_input_for",
    "set_last_smiles_input_for",
]
